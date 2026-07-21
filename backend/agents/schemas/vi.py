from __future__ import annotations

from uuid import UUID

from pydantic import Field

from backend.agents.schemas.common import ContractModel, PaletteColor


class TypographySystem(ContractModel):
    heading_style: str = Field(min_length=1, max_length=500)
    body_style: str = Field(min_length=1, max_length=500)
    fallbacks: list[str] = Field(min_length=1, max_length=8)
    usage_rules: list[str] = Field(min_length=1, max_length=12)


class LogoRules(ContractModel):
    clear_space: str = Field(min_length=1, max_length=500)
    minimum_size: str = Field(min_length=1, max_length=500)
    background_rules: list[str] = Field(min_length=1, max_length=12)
    prohibited_uses: list[str] = Field(min_length=1, max_length=20)


class LayoutRule(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    grid: str = Field(min_length=1, max_length=500)
    spacing: str = Field(min_length=1, max_length=500)
    example_usage: str = Field(min_length=1, max_length=1_000)


class VIOutput(ContractModel):
    schema_version: int = Field(default=1, ge=1)
    palette: list[PaletteColor] = Field(min_length=3, max_length=6)
    typography: TypographySystem
    logo_rules: LogoRules
    layouts: list[LayoutRule] = Field(min_length=1, max_length=4)
    source_logo_asset_id: UUID
