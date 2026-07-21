from datetime import datetime
from typing import Protocol

from backend.infrastructure.storage.models import (
    ArtifactCleanupResult,
    ArtifactMetadata,
    ArtifactReference,
    ArtifactUpload,
    PresignedArtifactUrl,
    StoredArtifact,
)


class ArtifactStorage(Protocol):
    def put_artifact(self, upload: ArtifactUpload) -> StoredArtifact:
        """Upload bytes or a file-like object into artifact storage."""

    def ensure_artifact_exists(self, reference: ArtifactReference) -> ArtifactMetadata:
        """Return metadata for an existing artifact or raise ArtifactNotFound."""

    def create_download_url(
        self,
        reference: ArtifactReference,
        *,
        expires_in_seconds: int | None = None,
    ) -> PresignedArtifactUrl:
        """Create a short-lived URL that can be returned by a business API."""

    def delete_artifact(self, reference: ArtifactReference) -> None:
        """Delete an artifact object. Missing objects are treated as already deleted."""

    def delete_artifacts_by_prefix(
        self,
        *,
        bucket: str,
        prefix: str,
        older_than: datetime | None = None,
        batch_size: int = 1000,
    ) -> ArtifactCleanupResult:
        """Delete temporary artifacts below a safe prefix, optionally filtered by age."""
