from __future__ import annotations

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agents.schemas.intake import IntakeAnswer, IntakeResumePayload
from backend.agents.testing import InMemoryArtifactWriter
from backend.agents.workflow import build_brand_workflow
from backend.application.projects import CreateProjectCommand, create_project
from backend.application.stage_runs import (
    create_intake_resume_run,
    execute_stage_run,
)
from backend.infrastructure.database.invocations import SqlAlchemyInvocationRecorder
from backend.infrastructure.database.models import Base, StageVersion
from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


def _build_workflow(session, stage_run_id, checkpointer, *, interrupt_before=()):
    recorder = SqlAlchemyInvocationRecorder(session, stage_run_id=stage_run_id)
    workflow = build_brand_workflow(
        text_provider=FakeTextModelProvider(),
        image_provider=FakeImageModelProvider(),
        artifact_writer=InMemoryArtifactWriter(),
        invocation_recorder=recorder,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
    return workflow, recorder


@pytest.mark.asyncio
async def test_answered_intake_goes_straight_to_directions(session) -> None:
    """Intake asks at most one round: after the user answers (even partially),
    the flow proceeds to directions instead of asking again."""

    _, intake_run, _ = await create_project(
        session,
        CreateProjectCommand(
            workspace_id="workspace-one",
            actor_id="developer-one",
            name="单轮追问品牌",
            requirement_text="信息很少的需求。",
            structured_fields={},
            reference_artifact_ids=[],
        ),
    )
    checkpointer = InMemorySaver()

    workflow, recorder = _build_workflow(
        session,
        intake_run.id,
        checkpointer,
        interrupt_before=("generate_directions",),
    )
    completed_intake = await execute_stage_run(
        session,
        stage_run_id=intake_run.id,
        workflow=workflow,
        invocation_recorder=recorder,
    )
    assert completed_intake.status == "SUCCEEDED"
    round_one = await session.get(StageVersion, completed_intake.result_version_id)
    assert round_one.output_json["ready"] is False
    assert len(round_one.output_json["questions"]) > 1

    # Answer only one of several questions: the flow must still move on.
    resumed_run, _ = await create_intake_resume_run(
        session,
        source_stage_run_id=intake_run.id,
        workspace_id="workspace-one",
        resume_payload=IntakeResumePayload(
            answers=[IntakeAnswer(field_path="industry", value="精品烘焙")]
        ),
    )
    workflow, recorder = _build_workflow(session, resumed_run.id, checkpointer)
    completed_directions = await execute_stage_run(
        session,
        stage_run_id=resumed_run.id,
        workflow=workflow,
        invocation_recorder=recorder,
    )

    assert completed_directions.status == "SUCCEEDED"
    assert completed_directions.stage == "DIRECTIONS"
    directions_version = await session.get(
        StageVersion, completed_directions.result_version_id
    )
    assert directions_version.stage == "DIRECTIONS"
    assert len(directions_version.output_json["directions"]) == 3

    # No second intake round was created.
    intake_versions = await session.scalar(
        select(func.count())
        .select_from(StageVersion)
        .where(StageVersion.stage == "INTAKE")
    )
    assert intake_versions == 1
