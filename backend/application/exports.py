from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.schemas.directions import DirectionOutput
from backend.agents.schemas.ip import IPOutput
from backend.agents.schemas.logo import LogoOutput
from backend.infrastructure.database.models import Decision, Project, StageVersion


@dataclass(frozen=True)
class ProposalExportManifest:
    project_id: str
    project_name: str
    proposal_version_id: str
    proposal_stage_run_id: str
    decision_id: str
    title: str
    narrative: str
    sections: list[dict[str, Any]]
    asset_refs: list[str]
    generated_at: datetime


@dataclass(frozen=True)
class ProposalExportAsset:
    asset_id: str
    filename: str
    content: bytes
    mime_type: str


class ProjectExportError(ValueError):
    pass


class ProjectExportNotFoundError(ProjectExportError):
    pass


class ProjectExportConflictError(ProjectExportError):
    pass


async def get_proposal_export_manifest(
    session: AsyncSession,
    *,
    project_id: str,
    workspace_id: str,
) -> ProposalExportManifest:
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    if project is None:
        raise ProjectExportNotFoundError("Project not found")
    if project.status != "COMPLETED":
        raise ProjectExportConflictError("Project is not completed")

    ip_version = await session.scalar(
        select(StageVersion)
        .where(
            StageVersion.project_id == project_id,
            StageVersion.stage == "IP",
            StageVersion.status == "GENERATED",
        )
        .order_by(StageVersion.version_no.desc())
        .limit(1)
    )
    if ip_version is None:
        raise ProjectExportConflictError("Completed project has no IP version")

    final_decision = await session.scalar(
        select(Decision)
        .where(
            Decision.project_id == project_id,
            Decision.stage == "IP",
            Decision.action == "CONFIRM_VERSION",
            Decision.source_version_id == ip_version.id,
        )
        .order_by(Decision.created_at.desc())
        .limit(1)
    )
    if final_decision is None:
        raise ProjectExportConflictError("Completed project has no IP confirmation")

    logo_version_id = ip_version.input_refs_json.get("logo_version_id")
    if not isinstance(logo_version_id, str):
        raise ProjectExportConflictError("IP version is missing Logo reference")
    logo_version = await session.get(StageVersion, logo_version_id)
    if (
        logo_version is None
        or logo_version.project_id != project_id
        or logo_version.stage != "LOGO"
        or logo_version.status != "GENERATED"
    ):
        raise ProjectExportConflictError("Completed project has no generated Logo version")

    direction_version_id = logo_version.input_refs_json.get("direction_version_id")
    if not isinstance(direction_version_id, str):
        raise ProjectExportConflictError("Logo version is missing Direction reference")
    direction_version = await session.get(StageVersion, direction_version_id)
    if (
        direction_version is None
        or direction_version.project_id != project_id
        or direction_version.stage != "DIRECTIONS"
        or direction_version.status != "GENERATED"
    ):
        raise ProjectExportConflictError("Completed project has no generated Direction version")

    direction_decision = await _get_selection_decision(
        session,
        project_id=project_id,
        stage="DIRECTIONS",
        source_version_id=direction_version.id,
    )
    logo_decision = await _get_selection_decision(
        session,
        project_id=project_id,
        stage="LOGO",
        source_version_id=logo_version.id,
    )
    directions = DirectionOutput.model_validate(direction_version.output_json)
    logos = LogoOutput.model_validate(logo_version.output_json)
    ip = IPOutput.model_validate(ip_version.output_json)
    selected_direction = next(
        item for item in directions.directions if item.id == direction_decision.selected_item_id
    )
    selected_logo = next(
        item for item in logos.concepts if item.id == logo_decision.selected_item_id
    )
    ip_asset_ids = [
        str(ip.preview_asset_id),
        *(str(view.preview_asset_id) for view in ip.views),
    ]
    asset_refs = [
        str(selected_direction.preview_asset_id),
        str(selected_logo.preview_asset_id),
        *ip_asset_ids,
    ]
    sections = [
        {
            "type": "BRIEF",
            "title": "品牌简报",
            "summary": directions.brief.brand_promise,
            "version_id": direction_version.id,
            "asset_ids": [],
        },
        {
            "type": "DIRECTION",
            "title": selected_direction.name,
            "summary": selected_direction.concept,
            "version_id": direction_version.id,
            "asset_ids": [str(selected_direction.preview_asset_id)],
        },
        {
            "type": "LOGO",
            "title": selected_logo.name,
            "summary": selected_logo.rationale,
            "version_id": logo_version.id,
            "asset_ids": [str(selected_logo.preview_asset_id)],
        },
        {
            "type": "IP",
            "title": ip.character.name,
            "summary": ip.character.brand_connection,
            "version_id": ip_version.id,
            "asset_ids": ip_asset_ids,
        },
    ]
    return ProposalExportManifest(
        project_id=project.id,
        project_name=project.name,
        proposal_version_id=ip_version.id,
        proposal_stage_run_id=ip_version.stage_run_id,
        decision_id=final_decision.id,
        title=f"{project.name} 品牌交付包",
        narrative="由艺术总监 Agent、Logo Agent 和 IP 设计师 Agent 生成并经用户确认。",
        sections=sections,
        asset_refs=asset_refs,
        generated_at=ip_version.created_at,
    )


async def _get_selection_decision(
    session: AsyncSession,
    *,
    project_id: str,
    stage: str,
    source_version_id: str,
) -> Decision:
    decision = await session.scalar(
        select(Decision)
        .where(
            Decision.project_id == project_id,
            Decision.stage == stage,
            Decision.action == "SELECT_VERSION",
            Decision.source_version_id == source_version_id,
        )
        .order_by(Decision.created_at.desc())
        .limit(1)
    )
    if decision is None or decision.selected_item_id is None:
        raise ProjectExportConflictError(f"Completed project has no {stage} selection")
    return decision


def render_proposal_markdown(manifest: ProposalExportManifest) -> str:
    lines = [
        f"# {manifest.project_name} 品牌说明",
        "",
        manifest.narrative,
        "",
        "## 交付文件",
        "",
        "- `品牌说明.md`：本说明文档，用于向团队或设计师解释最终选择。",
        "- `品牌方向.png`：已确认的艺术总监方向图。",
        "- `Logo方案.png`：已确认的 Logo 方案图。",
        "- `IP形象.png`：已确认的 IP 主形象图。",
        "",
        "## 方案内容",
        "",
    ]
    for section in manifest.sections:
        asset_ids = section.get("asset_ids", [])
        lines.extend(
            [
                f"### {section['title']}",
                "",
                f"{section['summary']}",
            ]
        )
        if asset_ids:
            lines.extend(["", f"- 资产 ID：`{asset_ids[0]}`"])
        lines.append("")

    lines.extend(
        [
            "## 系统追踪信息",
            "",
            f"- Project ID: `{manifest.project_id}`",
            f"- Proposal version: `{manifest.proposal_version_id}`",
            f"- Proposal stage run: `{manifest.proposal_stage_run_id}`",
            f"- Final decision: `{manifest.decision_id}`",
            f"- Generated at: {manifest.generated_at.isoformat()}",
            "",
            "## Asset References",
            "",
        ]
    )
    lines.extend(f"- `{asset_id}`" for asset_id in manifest.asset_refs)
    lines.append("")
    return "\n".join(lines)


def serialize_proposal_manifest(manifest: ProposalExportManifest) -> str:
    payload = {
        "project_id": manifest.project_id,
        "project_name": manifest.project_name,
        "proposal_version_id": manifest.proposal_version_id,
        "proposal_stage_run_id": manifest.proposal_stage_run_id,
        "decision_id": manifest.decision_id,
        "title": manifest.title,
        "narrative": manifest.narrative,
        "sections": manifest.sections,
        "asset_refs": manifest.asset_refs,
        "generated_at": manifest.generated_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_proposal_zip(
    manifest: ProposalExportManifest,
    *,
    assets: list[ProposalExportAsset] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w") as archive:
        _write_zip_text(
            archive,
            filename="品牌说明.md",
            content=render_proposal_markdown(manifest),
            generated_at=manifest.generated_at,
        )
        _write_zip_text(
            archive,
            filename="proposal-manifest.json",
            content=serialize_proposal_manifest(manifest),
            generated_at=manifest.generated_at,
        )
        for asset in assets or []:
            _write_zip_binary(
                archive,
                filename=asset.filename,
                content=asset.content,
                generated_at=manifest.generated_at,
            )
    return buffer.getvalue()


def _write_zip_text(
    archive: ZipFile,
    *,
    filename: str,
    content: str,
    generated_at: datetime,
) -> None:
    info = ZipInfo(filename=filename)
    info.compress_type = ZIP_DEFLATED
    info.date_time = (
        generated_at.year,
        generated_at.month,
        generated_at.day,
        generated_at.hour,
        generated_at.minute,
        generated_at.second,
    )
    info.external_attr = 0o644 << 16
    archive.writestr(info, content.encode("utf-8"))


def _write_zip_binary(
    archive: ZipFile,
    *,
    filename: str,
    content: bytes,
    generated_at: datetime,
) -> None:
    info = ZipInfo(filename=filename)
    info.compress_type = ZIP_DEFLATED
    info.date_time = (
        generated_at.year,
        generated_at.month,
        generated_at.day,
        generated_at.hour,
        generated_at.minute,
        generated_at.second,
    )
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)
