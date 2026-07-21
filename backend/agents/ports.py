from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from backend.agents.schemas.common import ContractModel
from backend.providers.models.base import GeneratedImage, ModelCapability


class StoredArtifact(ContractModel):
    artifact_id: UUID
    mime_type: str
    size_bytes: int = Field(gt=0)


class ArtifactWriter(Protocol):
    """Application-layer port; storage implementation belongs to development 5."""

    def store_generated_image(
        self,
        *,
        request_id: str,
        image: GeneratedImage,
    ) -> StoredArtifact: ...

    def discard_temporary_artifacts(self, artifact_ids: list[UUID]) -> None: ...


class InvocationStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    FAILED = "FAILED"


class ModelInvocationRecord(ContractModel):
    request_id: str
    capability: ModelCapability
    prompt_version: str
    provider: str
    model: str
    status: InvocationStatus
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error_code: str | None = None


class InvocationRecorder(Protocol):
    """Application-layer audit port; persistence belongs to development 1."""

    def record_model_invocation(self, record: ModelInvocationRecord) -> None: ...


class RecoverableInvocationRecorder(InvocationRecorder, Protocol):
    """Recorder that can rebuild audit rows after a business rollback."""

    def restore_after_rollback(self) -> None: ...
