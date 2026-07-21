from __future__ import annotations

import base64
import io

import pytest

from backend.infrastructure.storage.reference_images import (
    ReferenceImageLocation,
    ReferenceImageResolver,
)
from backend.providers.models.factory import build_model_providers

_PNG = b"\x89PNG\r\n\x1a\nmock-bytes"


class _FakeS3Client:
    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self._objects = objects
        self.get_calls: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        self.get_calls.append((Bucket, Key))
        return {"Body": io.BytesIO(self._objects[(Bucket, Key)])}


def _resolver(
    client: _FakeS3Client,
    locations: dict[str, ReferenceImageLocation],
) -> ReferenceImageResolver:
    return ReferenceImageResolver(
        database_conninfo="postgresql://unused",
        endpoint_url="http://minio:9000",
        access_key_id="test-key",
        secret_access_key="test-secret",
        region="us-east-1",
        use_ssl=False,
        s3_client=client,
        locate_artifact=locations.get,
    )


def test_resolver_returns_base64_data_uri() -> None:
    client = _FakeS3Client({("brand-bucket", "projects/p1/a1.png"): _PNG})
    resolver = _resolver(
        client,
        {
            "artifact-1": ReferenceImageLocation(
                bucket="brand-bucket",
                object_key="projects/p1/a1.png",
                mime_type="image/png",
            )
        },
    )

    data_uri = resolver("artifact-1")

    expected = base64.b64encode(_PNG).decode("ascii")
    assert data_uri == f"data:image/png;base64,{expected}"


def test_resolver_caches_repeated_lookups() -> None:
    client = _FakeS3Client({("brand-bucket", "projects/p1/a1.png"): _PNG})
    resolver = _resolver(
        client,
        {
            "artifact-1": ReferenceImageLocation(
                bucket="brand-bucket",
                object_key="projects/p1/a1.png",
                mime_type="image/png",
            )
        },
    )

    first = resolver("artifact-1")
    second = resolver("artifact-1")

    assert first == second
    assert len(client.get_calls) == 1


def test_resolver_rejects_unknown_artifact() -> None:
    resolver = _resolver(_FakeS3Client({}), {})

    with pytest.raises(ValueError, match="not found"):
        resolver("missing-artifact")


def test_resolver_rejects_non_image_mime_type() -> None:
    client = _FakeS3Client({("brand-bucket", "projects/p1/a1.pdf"): b"%PDF"})
    resolver = _resolver(
        client,
        {
            "artifact-1": ReferenceImageLocation(
                bucket="brand-bucket",
                object_key="projects/p1/a1.pdf",
                mime_type="application/pdf",
            )
        },
    )

    with pytest.raises(ValueError, match="unsupported MIME type"):
        resolver("artifact-1")


def test_resolver_prefers_artifacts_registered_in_current_run() -> None:
    """Artifacts stored mid-run are not committed yet; the resolver must find
    them via the local index instead of the database."""

    client = _FakeS3Client({("brand-bucket", "projects/p1/fresh.png"): _PNG})

    def failing_db_lookup(artifact_id: str) -> ReferenceImageLocation | None:
        raise AssertionError("database lookup should not run for local artifacts")

    resolver = ReferenceImageResolver(
        database_conninfo="postgresql://unused",
        endpoint_url="http://minio:9000",
        access_key_id="test-key",
        secret_access_key="test-secret",
        region="us-east-1",
        use_ssl=False,
        s3_client=client,
        locate_artifact=failing_db_lookup,
    )
    resolver.register_stored_artifact(
        "fresh-artifact",
        bucket="brand-bucket",
        object_key="projects/p1/fresh.png",
        mime_type="image/png",
    )

    data_uri = resolver("fresh-artifact")

    expected = base64.b64encode(_PNG).decode("ascii")
    assert data_uri == f"data:image/png;base64,{expected}"


def test_factory_wires_resolver_into_image_provider(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_TEXT_MODEL", "test-text-model")
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "test-image-model")

    def resolver(artifact_id: str) -> str:
        return "data:image/png;base64,AAAA"

    _, image_provider = build_model_providers(
        text_provider_name="openrouter",
        image_provider_name="openrouter",
        reference_image_resolver=resolver,
    )

    assert image_provider._reference_image_resolver is resolver
