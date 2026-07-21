from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from backend.infrastructure.storage.errors import InvalidArtifactReference
from backend.infrastructure.storage.keys import (
    build_artifact_object_key,
    normalize_artifact_id,
    sanitize_storage_filename,
)
from backend.infrastructure.storage.models import ArtifactReference, ArtifactUpload
from backend.infrastructure.storage.service import ArtifactStorage

DEFAULT_UPLOAD_CACHE_CONTROL = "private, max-age=0, no-store"
DEFAULT_UPLOAD_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class FileArtifactUploadRequest:
    bucket: str
    project_id: str
    filename: str
    body: bytes
    artifact_id: str | None = None
    content_type: str | None = None
    stage: str = "references"
    root_prefix: str = "artifacts"
    cache_control: str | None = DEFAULT_UPLOAD_CACHE_CONTROL


@dataclass(frozen=True, slots=True)
class StoredFileArtifact:
    artifact_id: str
    bucket: str
    object_key: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    etag: str | None
    version_id: str | None


class FileArtifactService:
    def __init__(self, *, storage: ArtifactStorage) -> None:
        self._storage = storage

    def store_file(self, request: FileArtifactUploadRequest) -> StoredFileArtifact:
        body = _validate_body(request.body)
        artifact_id = (
            normalize_artifact_id(request.artifact_id) if request.artifact_id else str(uuid4())
        )
        filename = sanitize_storage_filename(
            request.filename,
            fallback=f"{artifact_id}.bin",
        )
        content_type = _normalize_content_type(request.content_type)
        object_key = build_artifact_object_key(
            project_id=request.project_id,
            stage=request.stage,
            artifact_id=artifact_id,
            filename=filename,
            root_prefix=request.root_prefix,
        )
        digest = sha256(body).hexdigest()
        reference = ArtifactReference(
            artifact_id=artifact_id,
            bucket=request.bucket,
            object_key=object_key,
            filename=filename,
            content_type=content_type,
        )
        stored = self._storage.put_artifact(
            ArtifactUpload(
                reference=reference,
                body=body,
                cache_control=request.cache_control,
            )
        )

        return StoredFileArtifact(
            artifact_id=artifact_id,
            bucket=stored.bucket,
            object_key=stored.object_key,
            filename=filename,
            content_type=content_type,
            size_bytes=len(body),
            sha256=digest,
            etag=stored.etag,
            version_id=stored.version_id,
        )


def _validate_body(value: bytes) -> bytes:
    if not value:
        raise InvalidArtifactReference("file body must not be empty")
    return value


def _normalize_content_type(value: str | None) -> str:
    content_type = (value or DEFAULT_UPLOAD_CONTENT_TYPE).strip().lower()
    if (
        not content_type
        or "/" not in content_type
        or "\r" in content_type
        or "\n" in content_type
        or len(content_type) > 100
    ):
        raise InvalidArtifactReference("content_type must be a valid MIME type")
    return content_type
