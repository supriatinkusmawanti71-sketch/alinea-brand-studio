from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from backend.agents.ports import ModelInvocationRecord, StoredArtifact
from backend.providers.models.base import GeneratedImage


class InMemoryArtifactWriter:
    """Deterministic test adapter; production storage is intentionally absent."""

    def __init__(self) -> None:
        self.items: dict[str, GeneratedImage] = {}

    def store_generated_image(
        self,
        *,
        request_id: str,
        image: GeneratedImage,
    ) -> StoredArtifact:
        artifact_id = uuid5(
            NAMESPACE_URL,
            f"fake-artifact:{request_id}:{image.provider_request_id}",
        )
        self.items[str(artifact_id)] = image
        return StoredArtifact(
            artifact_id=artifact_id,
            mime_type=image.mime_type,
            size_bytes=len(image.content),
        )

    def discard_temporary_artifacts(self, artifact_ids: list) -> None:
        for artifact_id in artifact_ids:
            self.items.pop(str(artifact_id), None)


class InMemoryInvocationRecorder:
    def __init__(self) -> None:
        self.records: list[ModelInvocationRecord] = []

    def record_model_invocation(self, record: ModelInvocationRecord) -> None:
        self.records.append(record)
