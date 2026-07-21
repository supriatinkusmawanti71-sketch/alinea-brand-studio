from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents.schemas.common import PaletteColor
from backend.agents.schemas.directions import (
    DirectionBrief,
    DirectionDraft,
    DirectionDraftOutput,
    TypographyDirection,
)


def _draft(identifier: str) -> DirectionDraft:
    return DirectionDraft(
        id=identifier,
        name=identifier,
        concept="一个完整的方向概念",
        keywords=["清晰", "可信", "现代"],
        palette=[
            PaletteColor(name="黑", hex="#111111", usage="文字"),
            PaletteColor(name="白", hex="#FFFFFF", usage="背景"),
            PaletteColor(name="蓝", hex="#2457FF", usage="强调"),
        ],
        typography=TypographyDirection(
            heading_style="现代标题",
            body_style="清晰正文",
        ),
        composition="网格构图",
        rationale="符合品牌定位",
        image_prompt="品牌视觉方向图",
    )


def test_direction_output_requires_exactly_three_items() -> None:
    with pytest.raises(ValidationError, match="exactly three"):
        DirectionDraftOutput(
            brief=DirectionBrief(
                positioning="定位",
                audience_insight="洞察",
                brand_promise="承诺",
                tone="语气",
            ),
            directions=[_draft("one"), _draft("two")],
        )
