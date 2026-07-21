from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    """Base class for checkpoint-safe, strict public contracts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class PaletteColor(ContractModel):
    name: str = Field(min_length=1, max_length=60)
    hex: str
    usage: str = Field(min_length=1, max_length=300)

    @field_validator("hex")
    @classmethod
    def validate_hex_color(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", normalized):
            raise ValueError("hex must use #RRGGBB format")
        return normalized
