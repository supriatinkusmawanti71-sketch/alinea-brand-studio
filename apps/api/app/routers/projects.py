from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import get_settings
from backend.application.exports import (
    ProjectExportConflictError,
    ProjectExportNotFoundError,
    ProposalExportAsset,
    ProposalExportManifest,
    get_proposal_export_manifest,
    render_proposal_markdown,
    render_proposal_zip,
)
from backend.application.projects import (
    CreateProjectCommand,
    InvalidStageKeyError,
    ProjectNotFoundError,
    StageControlConflictError,
    StageControlNotFoundError,
    UnsupportedStageControlError,
    create_project,
    get_project,
    get_project_state,
    list_projects,
    list_stage_versions,
    request_stage_control,
)
from backend.application.stage_runs import (
    InvalidStageDecisionError,
    StageDecisionConflictError,
    StageDecisionNotFoundError,
    UnsupportedStageDecisionError,
    create_stage_decision,
    mark_outbox_published,
)
from backend.infrastructure.database.models import Artifact
from backend.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/projects", tags=["projects"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    requirement_text: str | None = Field(default=None, max_length=10_000)
    structured_fields: dict[str, Any] = Field(default_factory=dict)
    reference_artifact_ids: list[str] = Field(default_factory=list, max_length=20)


class StageRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    status: str
    attempt: int
    error_code: str | None
    result_version_id: str | None


class StageRunStateResponse(StageRunResponse):
    parent_stage_run_id: str | None
    workflow_thread_id: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class StageVersionStateResponse(BaseModel):
    id: str
    project_id: str
    stage_run_id: str
    stage: str
    version_no: int
    schema_version: int
    input_refs: dict[str, Any]
    output: dict[str, Any]
    status: str
    created_at: datetime


class DecisionStateResponse(BaseModel):
    id: str
    project_id: str
    stage: str
    action: str
    source_version_id: str
    selected_item_id: str | None
    resulting_stage_run_id: str
    created_by: str
    payload: dict[str, Any]
    created_at: datetime


class StageDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID
    selected_item_id: str | None = Field(default=None, min_length=1, max_length=120)
    confirmed: Literal[True] | None = None
    action: Literal["SELECT_VERSION", "CONFIRM_VERSION"] = "SELECT_VERSION"


class StageDecisionResponse(BaseModel):
    decision: DecisionStateResponse
    stage_run: StageRunStateResponse


class StageControlResponse(BaseModel):
    project_id: str
    stage: str
    action: Literal["REDO", "SKIP", "GENERATE"]
    status: str


class StageControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class ErrorDetailResponse(BaseModel):
    detail: str


NOT_FOUND_RESPONSE = {"model": ErrorDetailResponse, "description": "Not found"}
CONFLICT_RESPONSE = {"model": ErrorDetailResponse, "description": "Conflict"}


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    current_stage: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectCreateResponse(BaseModel):
    project: ProjectResponse
    stage_run: StageRunResponse


class ProjectDetailResponse(ProjectResponse):
    brand_spec: dict[str, Any]
    stage_runs: list[StageRunResponse]


class ProjectStateResponse(BaseModel):
    project: ProjectResponse
    brand_spec: dict[str, Any]
    current_stage: str
    stage_runs: dict[str, StageRunStateResponse]
    versions: dict[str, StageVersionStateResponse]
    decisions: list[DecisionStateResponse]


class ProposalExportManifestResponse(BaseModel):
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


@router.post("", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_project_route(
    payload: ProjectCreateRequest,
    session: SessionDependency,
) -> ProjectCreateResponse:
    settings = get_settings()
    try:
        project, stage_run, outbox_event = await create_project(
            session,
            CreateProjectCommand(
                workspace_id=settings.default_workspace_id,
                actor_id=settings.default_actor_id,
                name=payload.name,
                requirement_text=payload.requirement_text,
                structured_fields=payload.structured_fields,
                reference_artifact_ids=payload.reference_artifact_ids,
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    from apps.api.app.tasks import execute_agent_stage

    execute_agent_stage.delay(stage_run.id)
    await mark_outbox_published(session, event_id=outbox_event.id)
    return ProjectCreateResponse(
        project=ProjectResponse.model_validate(project),
        stage_run=StageRunResponse.model_validate(stage_run),
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects_route(session: SessionDependency) -> list[ProjectResponse]:
    projects = await list_projects(
        session,
        workspace_id=get_settings().default_workspace_id,
    )
    return [ProjectResponse.model_validate(project) for project in projects]


@router.get(
    "/{project_id}/state",
    response_model=ProjectStateResponse,
    responses={404: NOT_FOUND_RESPONSE},
)
async def get_project_state_route(
    project_id: str,
    session: SessionDependency,
) -> ProjectStateResponse:
    state = await get_project_state(
        session,
        project_id=project_id,
        workspace_id=get_settings().default_workspace_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectStateResponse(
        project=ProjectResponse.model_validate(state.project),
        brand_spec={
            **state.project.brand_spec.data_json,
            "source_map": state.project.brand_spec.source_map_json,
        },
        current_stage=state.project.current_stage,
        stage_runs={
            run.stage: StageRunStateResponse.model_validate(run, from_attributes=True)
            for run in state.stage_runs
        },
        versions={
            version.stage: StageVersionStateResponse(
                id=version.id,
                project_id=version.project_id,
                stage_run_id=version.stage_run_id,
                stage=version.stage,
                version_no=version.version_no,
                schema_version=version.schema_version,
                input_refs=version.input_refs_json,
                output=version.output_json,
                status=version.status,
                created_at=version.created_at,
            )
            for version in state.stage_versions
        },
        decisions=[
            DecisionStateResponse(
                id=decision.id,
                project_id=decision.project_id,
                stage=decision.stage,
                action=decision.action,
                source_version_id=decision.source_version_id,
                selected_item_id=decision.selected_item_id,
                resulting_stage_run_id=decision.resulting_stage_run_id,
                created_by=decision.created_by,
                payload=decision.payload_json,
                created_at=decision.created_at,
            )
            for decision in state.decisions
        ],
    )


@router.get(
    "/{project_id}/exports/proposal-manifest",
    response_model=ProposalExportManifestResponse,
    responses={404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
)
async def get_proposal_export_manifest_route(
    project_id: str,
    session: SessionDependency,
) -> ProposalExportManifestResponse:
    try:
        manifest = await get_proposal_export_manifest(
            session,
            project_id=project_id,
            workspace_id=get_settings().default_workspace_id,
        )
    except ProjectExportNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ProjectExportConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ProposalExportManifestResponse(
        project_id=manifest.project_id,
        project_name=manifest.project_name,
        proposal_version_id=manifest.proposal_version_id,
        proposal_stage_run_id=manifest.proposal_stage_run_id,
        decision_id=manifest.decision_id,
        title=manifest.title,
        narrative=manifest.narrative,
        sections=manifest.sections,
        asset_refs=manifest.asset_refs,
        generated_at=manifest.generated_at,
    )


@router.get(
    "/{project_id}/assets/{asset_id}",
    response_class=Response,
    responses={404: NOT_FOUND_RESPONSE},
)
async def download_project_asset_route(
    project_id: str,
    asset_id: str,
    session: SessionDependency,
    download: bool = Query(default=False),
    filename: str | None = Query(default=None, max_length=80),
) -> Response:
    settings = get_settings()
    artifact = await session.scalar(
        select(Artifact).where(
            Artifact.id == asset_id,
            Artifact.project_id == project_id,
            Artifact.workspace_id == settings.default_workspace_id,
            Artifact.status == "STORED",
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    try:
        obj = client.get_object(Bucket=artifact.bucket, Key=artifact.object_key)
        content = obj["Body"].read()
    except Exception as error:
        raise HTTPException(status_code=404, detail="Artifact file not found") from error

    headers = {"Cache-Control": "private, max-age=300"}
    if download:
        headers["Content-Disposition"] = _asset_content_disposition(
            filename,
            artifact.mime_type,
            fallback_stem=asset_id,
        )
    return Response(
        content=content,
        media_type=artifact.mime_type,
        headers=headers,
    )


def _asset_content_disposition(
    filename: str | None,
    mime_type: str,
    *,
    fallback_stem: str,
) -> str:
    extension_by_mime_type = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    extension = extension_by_mime_type.get(mime_type, "")
    stem = (filename or "").strip() or fallback_stem
    # Drop path separators and control characters from the user-supplied stem.
    stem = re.sub(r"[\\/\x00-\x1f\"';]", "", stem)[:60] or fallback_stem
    full_name = f"{stem}{extension}"
    encoded = quote(full_name, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


@router.get(
    "/{project_id}/exports/proposal.md",
    response_class=Response,
    responses={
        200: {
            "content": {"text/markdown": {"schema": {"type": "string"}}},
            "description": "Markdown proposal export",
        },
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
    },
)
async def download_proposal_markdown_route(
    project_id: str,
    session: SessionDependency,
) -> Response:
    try:
        manifest = await get_proposal_export_manifest(
            session,
            project_id=project_id,
            workspace_id=get_settings().default_workspace_id,
        )
    except ProjectExportNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ProjectExportConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return Response(
        content=render_proposal_markdown(manifest),
        media_type="text/markdown; charset=utf-8",
        headers={
            # RFC 5987 encoding of 品牌说明.md
            "Content-Disposition": (
                "attachment; filename*=UTF-8''%E5%93%81%E7%89%8C%E8%AF%B4%E6%98%8E.md"
            ),
        },
    )


@router.get(
    "/{project_id}/exports/proposal.zip",
    response_class=Response,
    responses={
        200: {
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            "description": "ZIP proposal export bundle",
        },
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
    },
)
async def download_proposal_zip_route(
    project_id: str,
    session: SessionDependency,
) -> Response:
    try:
        manifest = await get_proposal_export_manifest(
            session,
            project_id=project_id,
            workspace_id=get_settings().default_workspace_id,
        )
    except ProjectExportNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ProjectExportConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    assets = await _load_proposal_export_assets(session, manifest)
    return Response(
        content=render_proposal_zip(manifest, assets=assets),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="proposal-{project_id}.zip"',
        },
    )


async def _load_proposal_export_assets(
    session: AsyncSession,
    manifest: ProposalExportManifest,
) -> list[ProposalExportAsset]:
    if not manifest.asset_refs:
        return []

    settings = get_settings()
    artifacts = (
        await session.scalars(
            select(Artifact).where(
                Artifact.id.in_(manifest.asset_refs),
                Artifact.project_id == manifest.project_id,
                Artifact.workspace_id == settings.default_workspace_id,
                Artifact.status == "STORED",
            )
        )
    ).all()
    artifact_by_id = {artifact.id: artifact for artifact in artifacts}
    missing = [asset_id for asset_id in manifest.asset_refs if asset_id not in artifact_by_id]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Export assets are missing: {', '.join(missing)}",
        )

    section_type_by_asset_id = _section_type_by_asset_id(manifest.sections)
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    export_assets: list[ProposalExportAsset] = []
    used_filenames: set[str] = set()
    for asset_id in manifest.asset_refs:
        artifact = artifact_by_id[asset_id]
        try:
            obj = client.get_object(Bucket=artifact.bucket, Key=artifact.object_key)
            content = obj["Body"].read()
        except Exception as error:
            raise HTTPException(
                status_code=409,
                detail=f"Export asset file is missing: {asset_id}",
            ) from error
        filename = _proposal_asset_filename(
            section_type_by_asset_id.get(asset_id, "ASSET"),
            artifact.mime_type,
            used_filenames,
        )
        export_assets.append(
            ProposalExportAsset(
                asset_id=asset_id,
                filename=filename,
                content=content,
                mime_type=artifact.mime_type,
            )
        )
    return export_assets


def _section_type_by_asset_id(sections: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for section in sections:
        section_type = str(section.get("type", "ASSET"))
        for asset_id in section.get("asset_ids", []):
            mapping[str(asset_id)] = section_type
    return mapping


def _proposal_asset_filename(section_type: str, mime_type: str, used_filenames: set[str]) -> str:
    stem_by_type = {
        "DIRECTION": "品牌方向",
        "LOGO": "Logo方案",
        "IP": "IP形象",
    }
    extension_by_mime_type = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    stem = stem_by_type.get(section_type, "资产")
    extension = extension_by_mime_type.get(mime_type, ".bin")
    filename = f"{stem}{extension}"
    if filename not in used_filenames:
        used_filenames.add(filename)
        return filename
    index = 2
    while f"{stem}-{index}{extension}" in used_filenames:
        index += 1
    filename = f"{stem}-{index}{extension}"
    used_filenames.add(filename)
    return filename


@router.get(
    "/{project_id}/stages/{stage_key}/versions",
    response_model=list[StageVersionStateResponse],
    responses={404: NOT_FOUND_RESPONSE},
)
async def list_stage_versions_route(
    project_id: str,
    stage_key: str,
    session: SessionDependency,
) -> list[StageVersionStateResponse]:
    try:
        versions = await list_stage_versions(
            session,
            project_id=project_id,
            workspace_id=get_settings().default_workspace_id,
            stage_key=stage_key,
        )
    except InvalidStageKeyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if versions is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return [
        StageVersionStateResponse(
            id=version.id,
            project_id=version.project_id,
            stage_run_id=version.stage_run_id,
            stage=version.stage,
            version_no=version.version_no,
            schema_version=version.schema_version,
            input_refs=version.input_refs_json,
            output=version.output_json,
            status=version.status,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.post(
    "/{project_id}/stages/{stage_key}/decisions",
    response_model=StageDecisionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
)
async def create_stage_decision_route(
    project_id: str,
    stage_key: str,
    payload: StageDecisionRequest,
    session: SessionDependency,
) -> StageDecisionResponse:
    settings = get_settings()
    try:
        stage_run, decision, outbox_event = await create_stage_decision(
            session,
            project_id=project_id,
            workspace_id=settings.default_workspace_id,
            actor_id=settings.default_actor_id,
            stage_key=stage_key,
            version_id=str(payload.version_id),
            selected_item_id=payload.selected_item_id,
            confirmed=payload.confirmed,
            action=payload.action,
        )
    except StageDecisionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStageDecisionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (StageDecisionConflictError, UnsupportedStageDecisionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if outbox_event is not None:
        from apps.api.app.tasks import execute_agent_stage

        execute_agent_stage.delay(stage_run.id)
        await mark_outbox_published(session, event_id=outbox_event.id)

    return StageDecisionResponse(
        decision=DecisionStateResponse(
            id=decision.id,
            project_id=decision.project_id,
            stage=decision.stage,
            action=decision.action,
            source_version_id=decision.source_version_id,
            selected_item_id=decision.selected_item_id,
            resulting_stage_run_id=decision.resulting_stage_run_id,
            created_by=decision.created_by,
            payload=decision.payload_json,
            created_at=decision.created_at,
        ),
        stage_run=StageRunStateResponse.model_validate(stage_run, from_attributes=True),
    )


@router.post(
    "/{project_id}/stages/{stage_key}/redo",
    response_model=StageControlResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
)
async def redo_stage_route(
    project_id: str,
    stage_key: str,
    session: SessionDependency,
    payload: StageControlRequest | None = None,
) -> StageControlResponse:
    return await _request_stage_control_route(
        project_id=project_id,
        stage_key=stage_key,
        action="REDO",
        session=session,
        payload=payload,
    )


@router.post(
    "/{project_id}/stages/{stage_key}/skip",
    response_model=StageControlResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
)
async def skip_stage_route(
    project_id: str,
    stage_key: str,
    session: SessionDependency,
    payload: StageControlRequest | None = None,
) -> StageControlResponse:
    return await _request_stage_control_route(
        project_id=project_id,
        stage_key=stage_key,
        action="SKIP",
        session=session,
        payload=payload,
    )


@router.post(
    "/{project_id}/stages/{stage_key}/generate",
    response_model=StageControlResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
)
async def generate_stage_route(
    project_id: str,
    stage_key: str,
    session: SessionDependency,
    payload: StageControlRequest | None = None,
) -> StageControlResponse:
    return await _request_stage_control_route(
        project_id=project_id,
        stage_key=stage_key,
        action="GENERATE",
        session=session,
        payload=payload,
    )


async def _request_stage_control_route(
    *,
    project_id: str,
    stage_key: str,
    action: Literal["REDO", "SKIP", "GENERATE"],
    session: AsyncSession,
    payload: StageControlRequest | None,
) -> StageControlResponse:
    try:
        settings = get_settings()
        result = await request_stage_control(
            session,
            project_id=project_id,
            workspace_id=settings.default_workspace_id,
            actor_id=settings.default_actor_id,
            stage_key=stage_key,
            action=action,
            source_version_id=str(payload.source_version_id)
            if payload and payload.source_version_id
            else None,
            reason=payload.reason if payload else None,
        )
    except (ProjectNotFoundError, StageControlNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStageKeyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except StageControlConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except UnsupportedStageControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if result.outbox_event is not None:
        from apps.api.app.tasks import execute_agent_stage

        execute_agent_stage.delay(result.outbox_event.payload_json["stage_run_id"])
        await mark_outbox_published(session, event_id=result.outbox_event.id)

    return StageControlResponse(
        project_id=result.project_id,
        stage=result.stage,
        action=action,
        status=result.status,
    )


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project_route(
    project_id: str,
    session: SessionDependency,
) -> ProjectDetailResponse:
    project = await get_project(
        session,
        project_id=project_id,
        workspace_id=get_settings().default_workspace_id,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetailResponse(
        **ProjectResponse.model_validate(project).model_dump(),
        brand_spec={
            **project.brand_spec.data_json,
            "source_map": project.brand_spec.source_map_json,
        },
        stage_runs=[StageRunResponse.model_validate(run) for run in project.stage_runs],
    )
