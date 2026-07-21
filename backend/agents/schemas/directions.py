from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel, PaletteColor


class DirectionBrief(ContractModel):
    positioning: str = Field(min_length=1, max_length=1_000)
    audience_insight: str = Field(min_length=1, max_length=1_000)
    brand_promise: str = Field(min_length=1, max_length=1_000)
    tone: str = Field(min_length=1, max_length=500)


class TypographyDirection(ContractModel):
    heading_style: str = Field(min_length=1, max_length=500)
    body_style: str = Field(min_length=1, max_length=500)


class DirectionDraft(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    concept: str = Field(min_length=1, max_length=1_500)
    keywords: list[str] = Field(min_length=3, max_length=6)
    palette: list[PaletteColor] = Field(min_length=3, max_length=5)
    typography: TypographyDirection
    composition: str = Field(min_length=1, max_length=1_000)
    rationale: str = Field(min_length=1, max_length=1_000)
    risks: list[str] = Field(default_factory=list, max_length=8)
    image_prompt: str = Field(min_length=1, max_length=2_000)


class Direction(DirectionDraft):
    preview_asset_id: UUID


class DirectionDraftOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    brief: DirectionBrief
    directions: list[DirectionDraft]

    @model_validator(mode="after")
    def require_three_directions(self) -> DirectionDraftOutput:
        if len(self.directions) != 3:
            raise ValueError("directions must contain exactly three items")
        ids = [item.id for item in self.directions]
        if len(set(ids)) != 3:
            raise ValueError("direction ids must be unique")
        return self


class DirectionOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    brief: DirectionBrief
    directions: list[Direction]

    @model_validator(mode="after")
    def require_three_directions(self) -> DirectionOutput:
        if len(self.directions) != 3:
            raise ValueError("directions must contain exactly three items")
        ids = [item.id for item in self.directions]
        asset_ids = [item.preview_asset_id for item in self.directions]
        if len(set(ids)) != 3 or len(set(asset_ids)) != 3:
            raise ValueError("direction and asset ids must be unique")
        return self
