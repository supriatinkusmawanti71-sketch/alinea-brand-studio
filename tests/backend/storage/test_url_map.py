from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.infrastructure.storage import (
    ArtifactReference,
    InvalidArtifactReference,
    PresignedArtifactUrl,
    create_asset_url_map,
    create_presigned_url_map,
)


def test_create_asset_url_map_returns_frontend_asset_urls() -> None:
    references = [_reference("logo.png"), _reference("direction.png")]
    storage = RecordingStorage()

    result = create_asset_url_map(storage, references, expires_in_seconds=300)

    assert result == {
        references[0].artifact_id: f"https://cdn.test/{references[0].object_key}",
        references[1].artifact_id: f"https://cdn.test/{references[1].object_key}",
    }
    assert storage.calls == [
        (references[0], 300),
        (references[1], 300),
    ]


def test_create_presigned_url_map_returns_full_url_metadata() -> None:
    reference = _reference("logo.png")
    storage = RecordingStorage()

    result = create_presigned_url_map(storage, [reference])

    assert result[reference.artifact_id].artifact_id == reference.artifact_id
    assert result[reference.artifact_id].expires_in_seconds == 900


def test_create_asset_url_map_accepts_empty_references() -> None:
    storage = RecordingStorage()

    assert create_asset_url_map(storage, []) == {}
    assert storage.calls == []


def test_create_asset_url_map_rejects_duplicate_artifact_ids() -> None:
    artifact_id = str(uuid4())
    references = [
        _reference("logo-a.png", artifact_id=artifact_id),
        _reference("logo-b.png", artifact_id=artifact_id),
    ]

    with pytest.raises(InvalidArtifactReference):
        create_asset_url_map(RecordingStorage(), references)


class RecordingStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[ArtifactReference, int | None]] = []

    def create_download_url(
        self,
        reference: ArtifactReference,
        *,
        expires_in_seconds: int | None = None,
    ) -> PresignedArtifactUrl:
        self.calls.append((reference, expires_in_seconds))
        ttl = expires_in_seconds or 900
        return PresignedArtifactUrl(
            artifact_id=reference.artifact_id,
            url=f"https://cdn.test/{reference.object_key}",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            expires_in_seconds=ttl,
        )


def _reference(filename: str, *, artifact_id: str | None = None) -> ArtifactReference:
    resolved_artifact_id = artifact_id or str(uuid4())
    return ArtifactReference(
        artifact_id=resolved_artifact_id,
        bucket="brand-studio",
        object_key=f"artifacts/project-1/logo/{resolved_artifact_id}/{filename}",
        filename=filename,
        content_type="image/png",
    )
