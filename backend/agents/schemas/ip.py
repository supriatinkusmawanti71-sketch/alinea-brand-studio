from __future__ import annotations

from uuid import UUID

from pydantic import Field

from backend.agents.schemas.common import ContractModel


class CharacterDefinition(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=500)
    personality: list[str] = Field(min_length=2, max_length=8)
    appearance: str = Field(min_length=1, max_length=1_500)
    brand_connection: str = Field(min_length=1, max_length=1_000)


class PoseDefinition(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)


class IPDraft(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    character: CharacterDefinition
    pose: PoseDefinition
    image_prompt: str = Field(min_length=1, max_length=2_000)


class IPView(ContractModel):
    name: str = Field(min_length=1, max_length=40)
    preview_asset_id: UUID


class IPOutput(IPDraft):
    preview_asset_id: UUID
    # Turnaround views (e.g. 侧面/背面) generated from the confirmed main
    # image. Defaults to empty so pre-existing single-image versions still
    # validate.
    views: list[IPView] = Field(default_factory=list)
