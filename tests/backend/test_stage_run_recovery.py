from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.application.projects import CreateProjectCommand, create_project
from backend.application.stage_runs import execute_stage_run, recover_stuck_stage_runs
from backend.infrastructure.database.models import Base, OutboxEvent, StageRun

QUEUED_THRESHOLD = 3 * 60
RUNNING_THRESHOLD = 35 * 60


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _create_project_with_run(session) -> tuple[str, StageRun]:
    project, stage_run, _ = await create_project(
        session,
        CreateProjectCommand(
            workspace_id="workspace-one",
            actor_id="developer-one",
            name="恢复测试品牌",
            requirement_text="测试卡死恢复。",
            structured_fields={},
            reference_artifact_ids=[],
        ),
    )
    return project.id, stage_run


def _age(stage_run: StageRun, *, seconds: int) -> None:
    stage_run.updated_at = datetime.now(UTC) - timedelta(seconds=seconds)


async def _recover(session) -> list[StageRun]:
    return await recover_stuck_stage_runs(
        session,
        queued_stale_after_seconds=QUEUED_THRESHOLD,
        running_stale_after_seconds=RUNNING_THRESHOLD,
    )


@pytest.mark.asyncio
async def test_stale_queued_run_is_redispatched_and_outbox_settled(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    _age(stage_run, seconds=QUEUED_THRESHOLD + 60)
    await session.commit()

    recovered = await _recover(session)

    assert [run.id for run in recovered] == [stage_run.id]
    assert stage_run.status == "QUEUED"
    assert stage_run.error_code == "STAGE_RUN_REDISPATCHED"
    events = (await session.scalars(select(OutboxEvent))).all()
    assert all(event.status == "PUBLISHED" for event in events)


@pytest.mark.asyncio
async def test_fresh_queued_run_is_left_alone(session) -> None:
    _, stage_run = await _create_project_with_run(session)

    recovered = await _recover(session)

    assert recovered == []
    assert stage_run.error_code is None


@pytest.mark.asyncio
async def test_stale_running_run_is_requeued(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    stage_run.status = "RUNNING"
    _age(stage_run, seconds=RUNNING_THRESHOLD + 60)
    await session.commit()

    recovered = await _recover(session)

    assert [run.id for run in recovered] == [stage_run.id]
    assert stage_run.status == "QUEUED"
    assert stage_run.error_code == "STAGE_RUN_STALLED"


@pytest.mark.asyncio
async def test_recently_started_running_run_is_left_alone(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    stage_run.status = "RUNNING"
    _age(stage_run, seconds=QUEUED_THRESHOLD + 60)
    await session.commit()

    recovered = await _recover(session)

    assert recovered == []
    assert stage_run.status == "RUNNING"


@pytest.mark.asyncio
async def test_recovery_bumps_updated_at_to_avoid_hot_loop(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    _age(stage_run, seconds=QUEUED_THRESHOLD + 60)
    await session.commit()

    first = await _recover(session)
    second = await _recover(session)

    assert len(first) == 1
    assert second == []


@pytest.mark.asyncio
async def test_terminal_and_failed_runs_are_ignored(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    for status in ("SUCCEEDED", "FAILED", "WAITING_USER"):
        stage_run.status = status
        _age(stage_run, seconds=RUNNING_THRESHOLD + 60)
        await session.commit()

        assert await _recover(session) == []


@pytest.mark.asyncio
async def test_execute_stage_run_skips_run_owned_by_another_worker(session) -> None:
    _, stage_run = await _create_project_with_run(session)
    stage_run.status = "RUNNING"
    original_attempt = stage_run.attempt
    await session.commit()

    result = await execute_stage_run(
        session,
        stage_run_id=stage_run.id,
        workflow=None,
        invocation_recorder=None,
    )

    assert result.status == "RUNNING"
    assert result.attempt == original_attempt
