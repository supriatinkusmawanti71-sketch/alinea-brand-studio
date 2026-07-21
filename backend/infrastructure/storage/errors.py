class ArtifactStorageError(RuntimeError):
    """Base error for artifact storage operations."""


class InvalidArtifactReference(ArtifactStorageError, ValueError):
    """Raised when an artifact id, bucket, object key, or URL TTL is unsafe."""


class ArtifactNotFound(ArtifactStorageError):
    def __init__(self, artifact_id: str) -> None:
        self.artifact_id = artifact_id
        super().__init__(f"artifact {artifact_id} was not found")


class ArtifactStorageUnavailable(ArtifactStorageError):
    def __init__(self, message: str = "artifact storage is unavailable") -> None:
        super().__init__(message)
