from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel


class MaterialDraft(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    scenario_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=1_000)
    used_asset_ids: list[UUID] = Field(min_length=1, max_length=20)
    image_prompt: str = Field(min_length=1, max_length=2_000)


class MaterialScene(MaterialDraft):
    preview_asset_id: UUID


class MaterialDraftOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    scenes: list[MaterialDraft]

    @model_validator(mode="after")
    def require_two_scenes(self) -> MaterialDraftOutput:
        if len(self.scenes) != 2:
            raise ValueError("scenes must contain exactly two items")
        if len({item.id for item in self.scenes}) != 2:
            raise ValueError("scene ids must be unique")
        return self


class MaterialOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    scenes: list[MaterialScene]

    @model_validator(mode="after")
    def require_two_scenes(self) -> MaterialOutput:
        if len(self.scenes) != 2:
            raise ValueError("scenes must contain exactly two items")
        if len({item.id for item in self.scenes}) != 2:
            raise ValueError("scene ids must be unique")
        if len({item.preview_asset_id for item in self.scenes}) != 2:
            raise ValueError("scene asset ids must be unique")
        return self
