from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from backend.agents.schemas.common import ContractModel


class AnswerType(StrEnum):
    TEXT = "TEXT"
    TEXT_LIST = "TEXT_LIST"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"


class Question(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    field_path: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    required: bool = True
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def choice_questions_need_options(self) -> Question:
        is_choice = self.answer_type in {
            AnswerType.SINGLE_CHOICE,
            AnswerType.MULTI_CHOICE,
        }
        if is_choice and len(self.options) < 2:
            raise ValueError("choice questions require at least two options")
        if not is_choice and self.options:
            raise ValueError("free-text questions cannot define options")
        return self


class Suggestion(ContractModel):
    field_path: str = Field(min_length=1, max_length=120)
    value: Any
    reason: str = Field(min_length=1, max_length=500)


class Conflict(ContractModel):
    code: str = Field(min_length=1, max_length=120)
    field_paths: list[str] = Field(min_length=2, max_length=8)
    message: str = Field(min_length=1, max_length=500)


class IntakeOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    ready: bool
    questions: list[Question] = Field(default_factory=list, max_length=5)
    brand_spec_patch: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=10)
    conflicts: list[Conflict] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def ready_output_has_no_blockers(self) -> IntakeOutput:
        if self.ready and (self.questions or self.conflicts):
            raise ValueError("ready output cannot contain questions or conflicts")
        if not self.ready and not (self.questions or self.conflicts):
            raise ValueError("non-ready output must explain what blocks progress")
        return self


class IntakeAnswer(ContractModel):
    field_path: str = Field(min_length=1, max_length=120)
    value: Any


class IntakeResumePayload(ContractModel):
    answers: list[IntakeAnswer] = Field(default_factory=list, max_length=10)
