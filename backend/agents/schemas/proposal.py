from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel


class ProposalSectionType(StrEnum):
    BRIEF = "BRIEF"
    DIRECTION = "DIRECTION"
    LOGO = "LOGO"
    VI = "VI"
    IP = "IP"
    MATERIALS = "MATERIALS"
    REVIEW_SUMMARY = "REVIEW_SUMMARY"


class ProposalSection(ContractModel):
    type: ProposalSectionType
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2_000)
    version_id: UUID
    asset_ids: list[UUID] = Field(default_factory=list, max_length=30)


class ProposalOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)
    narrative: str = Field(min_length=1, max_length=3_000)
    sections: list[ProposalSection] = Field(min_length=6, max_length=7)
    asset_refs: list[UUID] = Field(min_length=4, max_length=30)

    @model_validator(mode="after")
    def validate_section_order(self) -> ProposalOutput:
        actual = [section.type for section in self.sections]
        without_ip = [
            ProposalSectionType.BRIEF,
            ProposalSectionType.DIRECTION,
            ProposalSectionType.LOGO,
            ProposalSectionType.VI,
            ProposalSectionType.MATERIALS,
            ProposalSectionType.REVIEW_SUMMARY,
        ]
        with_ip = without_ip[:4] + [ProposalSectionType.IP] + without_ip[4:]
        if actual not in (without_ip, with_ip):
            raise ValueError("proposal sections must use the fixed product order")
        if len(set(self.asset_refs)) != len(self.asset_refs):
            raise ValueError("asset_refs must be unique")
        return self
