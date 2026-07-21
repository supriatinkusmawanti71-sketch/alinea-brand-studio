"""Object storage adapters."""

from backend.infrastructure.storage.errors import (
    ArtifactNotFound,
    ArtifactStorageError,
    ArtifactStorageUnavailable,
    InvalidArtifactReference,
)
from backend.infrastructure.storage.keys import (
    build_artifact_object_key,
    build_prefixed_artifact_object_key,
    build_temporary_artifact_prefix,
    normalize_artifact_id,
    sanitize_storage_filename,
    sanitize_storage_prefix,
    sanitize_storage_segment,
)
from backend.infrastructure.storage.models import (
    ArtifactCleanupResult,
    ArtifactMetadata,
    ArtifactReference,
    ArtifactUpload,
    PresignedArtifactUrl,
    StoredArtifact,
)
from backend.infrastructure.storage.s3 import S3ArtifactStorage
from backend.infrastructure.storage.service import ArtifactStorage
from backend.infrastructure.storage.uploads import (
    FileArtifactService,
    FileArtifactUploadRequest,
    StoredFileArtifact,
)
from backend.infrastructure.storage.url_map import create_asset_url_map, create_presigned_url_map

__all__ = [
    "ArtifactCleanupResult",
    "ArtifactMetadata",
    "ArtifactNotFound",
    "ArtifactReference",
    "ArtifactStorage",
    "ArtifactStorageError",
    "ArtifactStorageUnavailable",
    "ArtifactUpload",
    "InvalidArtifactReference",
    "PresignedArtifactUrl",
    "S3ArtifactStorage",
    "StoredArtifact",
    "StoredFileArtifact",
    "build_artifact_object_key",
    "build_prefixed_artifact_object_key",
    "build_temporary_artifact_prefix",
    "create_asset_url_map",
    "create_presigned_url_map",
    "FileArtifactService",
    "FileArtifactUploadRequest",
    "normalize_artifact_id",
    "sanitize_storage_filename",
    "sanitize_storage_prefix",
    "sanitize_storage_segment",
]
