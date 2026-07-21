from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel


class Severity(StrEnum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class ReviewCategory(StrEnum):
    BRAND_CONSISTENCY = "BRAND_CONSISTENCY"
    LOGO_USAGE = "LOGO_USAGE"
    COLOR = "COLOR"
    TYPOGRAPHY = "TYPOGRAPHY"
    IP_CONSISTENCY = "IP_CONSISTENCY"
    MATERIAL_CONTENT = "MATERIAL_CONTENT"
    TEXT_ERROR = "TEXT_ERROR"
    MISSING_ASSET = "MISSING_ASSET"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    SECURITY = "SECURITY"
    PERMISSION = "PERMISSION"


class ReviewIssue(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    severity: Severity
    category: ReviewCategory
    evidence: str = Field(min_length=1, max_length=1_500)
    suggestion: str = Field(min_length=1, max_length=1_500)
    target_stage: str = Field(min_length=1, max_length=50)
    target_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ReviewOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    passed: bool = Field(alias="pass")
    summary: str = Field(min_length=1, max_length=2_000)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def passed_review_has_no_blockers(self) -> ReviewOutput:
        has_blocker = any(item.severity is Severity.BLOCKER for item in self.issues)
        if self.passed and has_blocker:
            raise ValueError("passed review cannot contain blockers")
        return self
