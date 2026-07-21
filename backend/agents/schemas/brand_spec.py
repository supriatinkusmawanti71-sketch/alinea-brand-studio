from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from backend.agents.schemas.common import ContractModel


class SourceType(StrEnum):
    USER_INPUT = "USER_INPUT"
    USER_CONFIRMATION = "USER_CONFIRMATION"
    REFERENCE_FILE = "REFERENCE_FILE"
    MODEL_SUGGESTION = "MODEL_SUGGESTION"


class SourceRecord(ContractModel):
    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=200)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BrandSpec(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    project_name: str = Field(min_length=1, max_length=100)
    industry: str | None = Field(default=None, max_length=200)
    brand_background: str | None = Field(default=None, max_length=5_000)
    target_audiences: list[str] = Field(default_factory=list, max_length=10)
    price_positioning: str | None = Field(default=None, max_length=500)
    brand_personality: list[str] = Field(default_factory=list, max_length=12)
    style_keywords: list[str] = Field(default_factory=list, max_length=12)
    required_elements: list[str] = Field(default_factory=list, max_length=30)
    prohibited_elements: list[str] = Field(default_factory=list, max_length=30)
    competitor_notes: str | None = Field(default=None, max_length=3_000)
    slogan: str | None = Field(default=None, max_length=300)
    language: str = Field(default="zh-CN", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    reference_artifact_ids: list[UUID] = Field(default_factory=list, max_length=20)
    source_map: dict[str, list[SourceRecord]] = Field(default_factory=dict)

    @field_validator(
        "target_audiences",
        "brand_personality",
        "style_keywords",
        "required_elements",
        "prohibited_elements",
    )
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_value in values:
            value = raw_value.strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def apply_user_answers(
        self,
        answers: list[tuple[str, Any]],
        *,
        source_id: str,
    ) -> BrandSpec:
        """Return a validated copy containing explicitly supplied user answers."""

        allowed_fields = set(type(self).model_fields) - {
            "schema_version",
            "project_name",
            "source_map",
        }
        patch: dict[str, Any] = {}
        next_source_map = {key: list(value) for key, value in self.source_map.items()}

        for field_path, value in answers:
            if field_path not in allowed_fields:
                raise ValueError(f"Unsupported BrandSpec field: {field_path}")
            patch[field_path] = value
            next_source_map.setdefault(field_path, []).append(
                SourceRecord(
                    source_type=SourceType.USER_CONFIRMATION,
                    source_id=source_id,
                )
            )

        patch["source_map"] = next_source_map
        merged = self.model_dump(mode="python")
        merged.update(patch)
        return type(self).model_validate(merged)
