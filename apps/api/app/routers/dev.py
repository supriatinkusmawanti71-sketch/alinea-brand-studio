import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response

from apps.api.app.config import get_settings
from backend.application.exports import (
    ProposalExportManifest,
    render_proposal_markdown,
    render_proposal_zip,
)

router = APIRouter(prefix="/dev", tags=["development"])
CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts" / "examples"


@router.get("/environment")
async def environment() -> dict[str, str]:
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "text_model_provider": settings.text_model_provider,
        "image_model_provider": settings.image_model_provider,
    }


@router.get("/demo-flow")
async def demo_flow() -> dict[str, Any]:
    path = CONTRACTS_DIR / "demo-flow.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/demo-completed-flow")
async def demo_completed_flow() -> dict[str, Any]:
    path = CONTRACTS_DIR / "demo-completed-flow.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/demo-proposal-manifest")
async def demo_proposal_manifest() -> dict[str, Any]:
    path = CONTRACTS_DIR / "demo-proposal-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_demo_proposal_manifest() -> ProposalExportManifest:
    path = CONTRACTS_DIR / "demo-proposal-manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ProposalExportManifest(
        project_id=payload["project_id"],
        project_name=payload["project_name"],
        proposal_version_id=payload["proposal_version_id"],
        proposal_stage_run_id=payload["proposal_stage_run_id"],
        decision_id=payload["decision_id"],
        title=payload["title"],
        narrative=payload["narrative"],
        sections=payload["sections"],
        asset_refs=payload["asset_refs"],
        generated_at=datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00")),
    )


@router.get(
    "/demo-proposal.md",
    responses={
        200: {
            "content": {"text/markdown": {"schema": {"type": "string"}}},
            "description": "Markdown proposal export demo",
        }
    },
)
async def demo_proposal_markdown() -> Response:
    manifest = _load_demo_proposal_manifest()
    return Response(
        content=render_proposal_markdown(manifest),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="demo-proposal.md"'},
    )


@router.get(
    "/demo-proposal.zip",
    responses={
        200: {
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            "description": "ZIP proposal export bundle demo",
        }
    },
)
async def demo_proposal_zip() -> Response:
    manifest = _load_demo_proposal_manifest()
    return Response(
        content=render_proposal_zip(manifest),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="demo-proposal.zip"'},
    )
