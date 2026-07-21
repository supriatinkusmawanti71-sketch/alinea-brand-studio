from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import get_settings
from backend.agents.schemas.intake import IntakeResumePayload
from backend.application.stage_runs import (
    StageDecisionConflictError,
    StageDecisionNotFoundError,
    StageResumeConflictError,
    StageResumeNotFoundError,
    create_direction_selection_run,
    create_intake_resume_run,
    get_stage_run,
    mark_outbox_published,
)
from backend.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/stage-runs", tags=["stage-runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


class StageRunDetailResponse(BaseModel):
    id: str
    project_id: str
    stage: str
    status: str
    attempt: int
    error_code: str | None
    error_message: str | None
    result_version_id: str | None
    result: dict[str, Any] | None


class ResumeStageRunResponse(BaseModel):
    id: str
    parent_stage_run_id: str | None
    workflow_thread_id: str
    project_id: str
    stage: str
    status: str


class DirectionSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID
    direction_id: str = Field(min_length=1, max_length=120)


@router.post(
    "/{stage_run_id}/direction-selection",
    response_model=ResumeStageRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_direction_selection(
    stage_run_id: str,
    payload: DirectionSelectionRequest,
    session: SessionDependency,
) -> ResumeStageRunResponse:
    settings = get_settings()
    try:
        resumed_run, _, outbox_event = await create_direction_selection_run(
            session,
            source_stage_run_id=stage_run_id,
            workspace_id=settings.default_workspace_id,
            actor_id=settings.default_actor_id,
            version_id=str(payload.version_id),
            direction_id=payload.direction_id,
        )
    except StageDecisionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StageDecisionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if outbox_event is not None:
        from apps.api.app.tasks import execute_agent_stage

        execute_agent_stage.delay(resumed_run.id)
        await mark_outbox_published(session, event_id=outbox_event.id)
    return ResumeStageRunResponse.model_validate(resumed_run, from_attributes=True)


@router.post(
    "/{stage_run_id}/intake-answers",
    response_model=ResumeStageRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_intake_answers(
    stage_run_id: str,
    payload: IntakeResumePayload,
    session: SessionDependency,
) -> ResumeStageRunResponse:
    try:
        resumed_run, outbox_event = await create_intake_resume_run(
            session,
            source_stage_run_id=stage_run_id,
            workspace_id=get_settings().default_workspace_id,
            resume_payload=payload,
        )
    except StageResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StageResumeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if outbox_event is not None:
        from apps.api.app.tasks import execute_agent_stage

        execute_agent_stage.delay(resumed_run.id)
        await mark_outbox_published(session, event_id=outbox_event.id)
    return ResumeStageRunResponse.model_validate(resumed_run, from_attributes=True)


@router.get("/{stage_run_id}", response_model=StageRunDetailResponse)
async def get_stage_run_route(
    stage_run_id: str,
    session: SessionDependency,
    include_result: bool = Query(default=True),
) -> StageRunDetailResponse:
    found = await get_stage_run(
        session,
        stage_run_id=stage_run_id,
        workspace_id=get_settings().default_workspace_id,
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Stage run not found")
    stage_run, version = found
    return StageRunDetailResponse(
        id=stage_run.id,
        project_id=stage_run.project_id,
        stage=stage_run.stage,
        status=stage_run.status,
        attempt=stage_run.attempt,
        error_code=stage_run.error_code,
        error_message=stage_run.error_message,
        result_version_id=stage_run.result_version_id,
        result=version.output_json if include_result and version else None,
    )
