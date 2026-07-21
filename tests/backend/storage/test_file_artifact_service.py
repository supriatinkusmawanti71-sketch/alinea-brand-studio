from hashlib import sha256
from uuid import uuid4

import pytest

from backend.infrastructure.storage import (
    ArtifactUpload,
    FileArtifactService,
    FileArtifactUploadRequest,
    InvalidArtifactReference,
    StoredArtifact,
)


def test_store_file_uploads_reference_artifact_and_returns_metadata() -> None:
    artifact_id = str(uuid4())
    storage = RecordingStorage()
    service = FileArtifactService(storage=storage)

    result = service.store_file(
        FileArtifactUploadRequest(
            artifact_id=artifact_id,
            bucket="brand-studio",
            project_id="project alpha",
            filename="../Reference Material?.PNG",
            body=b"image bytes",
            content_type="IMAGE/PNG",
        )
    )

    assert result.artifact_id == artifact_id
    assert result.bucket == "brand-studio"
    assert (
        result.object_key
        == f"artifacts/project-alpha/references/{artifact_id}/Reference-Material.PNG"
    )
    assert result.filename == "Reference-Material.PNG"
    assert result.content_type == "image/png"
    assert result.size_bytes == len(b"image bytes")
    assert result.sha256 == sha256(b"image bytes").hexdigest()
    assert result.etag == '"etag"'
    assert result.version_id == "version-1"
    assert storage.upload.reference.object_key == result.object_key
    assert storage.upload.reference.filename == "Reference-Material.PNG"
    assert storage.upload.reference.content_type == "image/png"
    assert storage.upload.body == b"image bytes"
    assert storage.upload.cache_control == "private, max-age=0, no-store"


def test_store_file_generates_artifact_id_and_defaults_content_type() -> None:
    storage = RecordingStorage()
    service = FileArtifactService(storage=storage)

    result = service.store_file(
        FileArtifactUploadRequest(
            bucket="brand-studio",
            project_id="project-1",
            filename="brand brief",
            body=b"plain text",
        )
    )

    assert result.artifact_id
    assert result.object_key.endswith(f"/{result.artifact_id}/brand-brief")
    assert result.content_type == "application/octet-stream"


@pytest.mark.parametrize(
    "upload_request",
    [
        FileArtifactUploadRequest(
            bucket="brand-studio",
            project_id="project-1",
            filename="empty.png",
            body=b"",
            content_type="image/png",
        ),
        FileArtifactUploadRequest(
            artifact_id="not-a-uuid",
            bucket="brand-studio",
            project_id="project-1",
            filename="logo.png",
            body=b"bytes",
            content_type="image/png",
        ),
        FileArtifactUploadRequest(
            bucket="brand-studio",
            project_id="project-1",
            filename="logo.png",
            body=b"bytes",
            content_type="image/png\r\nx-bad: true",
        ),
    ],
)
def test_store_file_rejects_unsafe_upload_inputs(
    upload_request: FileArtifactUploadRequest,
) -> None:
    service = FileArtifactService(storage=RecordingStorage())

    with pytest.raises(InvalidArtifactReference):
        service.store_file(upload_request)


class RecordingStorage:
    def __init__(self) -> None:
        self.upload: ArtifactUpload | None = None

    def put_artifact(self, upload: ArtifactUpload) -> StoredArtifact:
        self.upload = upload
        return StoredArtifact(
            artifact_id=upload.reference.artifact_id,
            bucket=upload.reference.bucket,
            object_key=upload.reference.object_key,
            etag='"etag"',
            version_id="version-1",
        )
