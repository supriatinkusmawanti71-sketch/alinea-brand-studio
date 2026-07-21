from __future__ import annotations

from collections.abc import Iterable

from backend.infrastructure.storage.errors import InvalidArtifactReference
from backend.infrastructure.storage.models import ArtifactReference, PresignedArtifactUrl
from backend.infrastructure.storage.service import ArtifactStorage


def create_presigned_url_map(
    storage: ArtifactStorage,
    references: Iterable[ArtifactReference],
    *,
    expires_in_seconds: int | None = None,
) -> dict[str, PresignedArtifactUrl]:
    urls: dict[str, PresignedArtifactUrl] = {}

    for reference in references:
        if reference.artifact_id in urls:
            raise InvalidArtifactReference(
                "artifact references must have unique artifact_id values"
            )
        urls[reference.artifact_id] = storage.create_download_url(
            reference,
            expires_in_seconds=expires_in_seconds,
        )

    return urls


def create_asset_url_map(
    storage: ArtifactStorage,
    references: Iterable[ArtifactReference],
    *,
    expires_in_seconds: int | None = None,
) -> dict[str, str]:
    presigned_urls = create_presigned_url_map(
        storage,
        references,
        expires_in_seconds=expires_in_seconds,
    )
    return {artifact_id: presigned_url.url for artifact_id, presigned_url in presigned_urls.items()}
