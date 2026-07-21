from __future__ import annotations

PROJECT_STAGE_ORDER = (
    "INTAKE",
    "DIRECTIONS",
    "LOGO",
    "IP",
)
KNOWN_PROJECT_STAGES = frozenset(PROJECT_STAGE_ORDER)


def normalize_stage_key(stage_key: str) -> str:
    return stage_key.strip().upper().replace("-", "_")


def downstream_project_stages(stage: str) -> tuple[str, ...]:
    stage_index = PROJECT_STAGE_ORDER.index(stage)
    return PROJECT_STAGE_ORDER[stage_index + 1 :]
