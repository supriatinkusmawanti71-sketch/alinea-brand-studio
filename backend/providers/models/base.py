from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field

from backend.agents.schemas.common import ContractModel


class ModelCapability(StrEnum):
    INTAKE = "INTAKE"
    DIRECTIONS = "DIRECTIONS"
    LOGO = "LOGO"
    VI = "VI"
    IP = "IP"
    MATERIALS = "MATERIALS"
    REVIEW = "REVIEW"
    PROPOSAL = "PROPOSAL"


class ModelRole(StrEnum):
    SYSTEM = "system"
    USER = "user"


class ModelMessage(ContractModel):
    role: ModelRole
    content: str = Field(min_length=1, max_length=100_000)


class TextGenerationRequest(ContractModel):
    request_id: str = Field(min_length=1, max_length=200)
    capability: ModelCapability
    prompt_version: str = Field(min_length=1, max_length=100)
    messages: list[ModelMessage] = Field(min_length=2, max_length=20)
    json_schema: dict[str, Any]
    temperature_policy: str = Field(default="stage_default", min_length=1, max_length=50)
    timeout_seconds: int = Field(default=90, ge=1, le=600)

    @property
    def payload(self) -> dict[str, Any]:
        """Machine-readable input used only by deterministic test providers."""

        data = json.loads(self.messages[-1].content)
        return data["input"]


class TextGenerationResult(ContractModel):
    provider: str
    model: str
    content_json: Any
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    provider_request_id: str
    finish_reason: str


class ImageGenerationRequest(ContractModel):
    request_id: str = Field(min_length=1, max_length=200)
    capability: ModelCapability | None = None
    prompt: str = Field(min_length=1, max_length=4_000)
    negative_prompt: str = Field(default="", max_length=2_000)
    reference_artifact_ids: list[str] = Field(default_factory=list, max_length=20)
    count: int = Field(default=1, ge=1, le=3)
    size_policy: str = Field(default="preview", min_length=1, max_length=100)
    timeout_seconds: int = Field(default=180, ge=1, le=1_200)


class GeneratedImage(ContractModel):
    provider: str
    model: str
    content: bytes
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    provider_request_id: str
    latency_ms: int = Field(ge=0)


class TextModelProvider(Protocol):
    def generate_structured(
        self,
        request: TextGenerationRequest,
    ) -> TextGenerationResult: ...


class ImageModelProvider(Protocol):
    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]: ...
