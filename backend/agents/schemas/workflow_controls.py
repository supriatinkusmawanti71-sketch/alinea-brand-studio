from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.agents.schemas.common import ContractModel


class SelectItemDecision(ContractModel):
    version_id: UUID
    selected_item_id: str = Field(min_length=1, max_length=120)


class ConfirmStageDecision(ContractModel):
    version_id: UUID
    confirmed: Literal[True]


class IPChoiceAction(StrEnum):
    GENERATE = "GENERATE"
    SKIP = "SKIP"


class IPChoice(ContractModel):
    action: IPChoiceAction


class ReviewDecision(ContractModel):
    version_id: UUID
    proceed: Literal[True]
    accepted_issue_ids: list[str] = Field(default_factory=list, max_length=50)
