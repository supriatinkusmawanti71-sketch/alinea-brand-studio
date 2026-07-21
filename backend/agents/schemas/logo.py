from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel


class LogoDraft(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=1_000)
    symbolism: str = Field(min_length=1, max_length=1_000)
    shape_language: str = Field(min_length=1, max_length=1_000)
    color_strategy: str = Field(min_length=1, max_length=1_000)
    image_prompt: str = Field(min_length=1, max_length=2_000)


class LogoConcept(LogoDraft):
    preview_asset_id: UUID


class LogoDraftOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    concepts: list[LogoDraft]

    @model_validator(mode="after")
    def require_four_concepts(self) -> LogoDraftOutput:
        if len(self.concepts) != 4:
            raise ValueError("concepts must contain exactly four items")
        if len({item.id for item in self.concepts}) != 4:
            raise ValueError("concept ids must be unique")
        return self


class LogoOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    concepts: list[LogoConcept]

    @model_validator(mode="after")
    def require_four_concepts(self) -> LogoOutput:
        if len(self.concepts) != 4:
            raise ValueError("concepts must contain exactly four items")
        if len({item.id for item in self.concepts}) != 4:
            raise ValueError("concept ids must be unique")
        if len({item.preview_asset_id for item in self.concepts}) != 4:
            raise ValueError("concept asset ids must be unique")
        return self
