from __future__ import annotations

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agents.schemas.intake import IntakeResumePayload
from backend.agents.testing import InMemoryArtifactWriter
from backend.agents.workflow import build_brand_workflow
from backend.application.projects import (
    CreateProjectCommand,
    create_project,
    request_stage_control,
)
from backend.application.stage_runs import (
    create_intake_resume_run,
    create_stage_decision,
    execute_stage_run,
)
from backend.infrastructure.database.invocations import SqlAlchemyInvocationRecorder
from backend.infrastructure.database.models import Base, Project, StageRun, StageVersion
from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider

WORKSPACE = "workspace-one"
ACTOR = "developer-one"


class RecordingTextProvider:
    provider_name = "fake"
    model_name = "fake-text-v1"

    def __init__(self) -> None:
        self._inner = FakeTextModelProvider()
        self.user_messages: list[tuple[str, str]] = []

    def generate_structured(self, request):
        self.user_messages.append((request.capability.value, request.messages[-1].content))
        return self._inner.generate_structured(request)


class RecordingImageProvider:
    provider_name = "fake"
    model_name = "fake-image-v1"

    def __init__(self) -> None:
        self._inner = FakeImageModelProvider()
        self.request_ids: list[str] = []

    def generate(self, request):
        self.request_ids.append(request.request_id)
        return self._inner.generate(request)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


class RedoHarness:
    """Drives the fake three-agent flow the same way the Celery worker does."""

    def __init__(self, session) -> None:
        self.session = session
        self.checkpointer = InMemorySaver()
        self.text_provider = RecordingTextProvider()
        self.image_provider = RecordingImageProvider()

    async def execute(self, stage_run_id: str, *, interrupt_before=()) -> StageRun:
        recorder = SqlAlchemyInvocationRecorder(self.session, stage_run_id=stage_run_id)
        workflow = build_brand_workflow(
            text_provider=self.text_provider,
            image_provider=self.image_provider,
            artifact_writer=InMemoryArtifactWriter(),
            invocation_recorder=recorder,
            checkpointer=self.checkpointer,
            interrupt_before=interrupt_before,
        )
        return await execute_stage_run(
            self.session,
            stage_run_id=stage_run_id,
            workflow=workflow,
            invocation_recorder=recorder,
        )

    async def run_until_logo(self) -> tuple[Project, StageRun]:
        project, intake_run, _ = await create_project(
            self.session,
            CreateProjectCommand(
                workspace_id=WORKSPACE,
                actor_id=ACTOR,
                name="重做测试品牌",
                requirement_text="测试 Logo 与 IP 重新生成。",
                structured_fields={
                    "industry": "精品烘焙",
                    "brand_background": "城市里的高端手作面包房。",
                    "target_audiences": ["22-35 岁城市白领"],
                    "price_positioning": "中高端",
                    "brand_personality": ["专业", "温暖"],
                    "style_keywords": ["轻奢", "现代"],
                },
                reference_artifact_ids=[],
            ),
        )
        completed_intake = await self.execute(
            intake_run.id,
            interrupt_before=("generate_directions",),
        )
        assert completed_intake.status == "SUCCEEDED"
        directions_run, _ = await create_intake_resume_run(
            self.session,
            source_stage_run_id=intake_run.id,
            workspace_id=WORKSPACE,
            resume_payload=IntakeResumePayload(answers=[]),
        )
        completed_directions = await self.execute(directions_run.id)
        assert completed_directions.status == "SUCCEEDED"
        directions_version = await self.session.get(
            StageVersion, completed_directions.result_version_id
        )
        direction_id = directions_version.output_json["directions"][0]["id"]
        logo_run, _, _ = await create_stage_decision(
            self.session,
            project_id=project.id,
            workspace_id=WORKSPACE,
            actor_id=ACTOR,
            stage_key="directions",
            version_id=completed_directions.result_version_id,
            selected_item_id=direction_id,
        )
        completed_logo = await self.execute(logo_run.id)
        assert completed_logo.status == "SUCCEEDED"
        return project, completed_logo

    async def redo(self, project_id: str, stage_key: str, version_id: str, reason: str):
        result = await request_stage_control(
            self.session,
            project_id=project_id,
            workspace_id=WORKSPACE,
            actor_id=ACTOR,
            stage_key=stage_key,
            action="REDO",
            source_version_id=version_id,
            reason=reason,
        )
        assert result.outbox_event is not None
        redo_run_id = result.outbox_event.payload_json["stage_run_id"]
        return await self.execute(redo_run_id)


@pytest.mark.asyncio
async def test_logo_redo_regenerates_with_feedback_without_touching_directions(session) -> None:
    harness = RedoHarness(session)
    project, logo_run = await harness.run_until_logo()

    image_calls_before = len(harness.image_provider.request_ids)
    redo_run = await harness.redo(
        project.id, "logo", logo_run.result_version_id, "太复杂了，要更简洁的字标"
    )

    assert redo_run.status == "SUCCEEDED"
    assert redo_run.stage == "LOGO"
    new_version = await session.get(StageVersion, redo_run.result_version_id)
    assert new_version.stage == "LOGO"
    assert new_version.version_no == 2
    assert new_version.status == "GENERATED"
    old_version = await session.get(StageVersion, logo_run.result_version_id)
    assert old_version.status == "STALE"

    # The redo run only generated logo images; directions were not re-billed.
    redo_image_calls = harness.image_provider.request_ids[image_calls_before:]
    assert redo_image_calls
    assert all(":logo:" in request_id for request_id in redo_image_calls)

    # The user's feedback reached the logo text model.
    logo_messages = [
        content for capability, content in harness.text_provider.user_messages
        if capability == "LOGO"
    ]
    assert "太复杂了，要更简洁的字标" in logo_messages[-1]
    assert "user_feedback" in logo_messages[-1]

    refreshed_project = await session.get(Project, project.id)
    assert refreshed_project.current_stage == "LOGO"


@pytest.mark.asyncio
async def test_ip_redo_after_completion_reopens_project(session) -> None:
    harness = RedoHarness(session)
    project, logo_run = await harness.run_until_logo()

    logo_version = await session.get(StageVersion, logo_run.result_version_id)
    logo_id = logo_version.output_json["concepts"][0]["id"]
    ip_run, _, _ = await create_stage_decision(
        session,
        project_id=project.id,
        workspace_id=WORKSPACE,
        actor_id=ACTOR,
        stage_key="logo",
        version_id=logo_run.result_version_id,
        selected_item_id=logo_id,
    )
    completed_ip = await harness.execute(ip_run.id)
    assert completed_ip.status == "SUCCEEDED"

    await create_stage_decision(
        session,
        project_id=project.id,
        workspace_id=WORKSPACE,
        actor_id=ACTOR,
        stage_key="ip",
        version_id=completed_ip.result_version_id,
        confirmed=True,
        action="CONFIRM_VERSION",
    )
    completed_project = await session.get(Project, project.id)
    assert completed_project.status == "COMPLETED"

    image_calls_before = len(harness.image_provider.request_ids)
    redo_run = await harness.redo(
        project.id, "ip", completed_ip.result_version_id, "希望更成熟一点"
    )

    assert redo_run.status == "SUCCEEDED"
    assert redo_run.stage == "IP"
    new_version = await session.get(StageVersion, redo_run.result_version_id)
    assert new_version.version_no == 2
    assert len(new_version.output_json["views"]) == 2

    # Only IP images (main + two views) were generated during the redo.
    redo_image_calls = harness.image_provider.request_ids[image_calls_before:]
    assert len(redo_image_calls) == 3
    assert all(":ip:" in request_id for request_id in redo_image_calls)

    ip_messages = [
        content for capability, content in harness.text_provider.user_messages
        if capability == "IP"
    ]
    assert "希望更成熟一点" in ip_messages[-1]

    reopened_project = await session.get(Project, project.id)
    assert reopened_project.status == "ACTIVE"
    assert reopened_project.current_stage == "IP"

    # A version produced by a redo can itself be redone: the upstream
    # selection is resolved from the logo version, not the redo decision.
    second_redo = await harness.redo(
        project.id, "ip", redo_run.result_version_id, "再换一个方向试试"
    )
    assert second_redo.status == "SUCCEEDED"
    third_version = await session.get(StageVersion, second_redo.result_version_id)
    assert third_version.version_no == 3


@pytest.mark.asyncio
async def test_logo_redo_thread_continues_to_ip_generation(session) -> None:
    harness = RedoHarness(session)
    project, logo_run = await harness.run_until_logo()

    redo_run = await harness.redo(project.id, "logo", logo_run.result_version_id, "换一批")
    new_logo_version = await session.get(StageVersion, redo_run.result_version_id)
    logo_id = new_logo_version.output_json["concepts"][0]["id"]

    ip_run, _, _ = await create_stage_decision(
        session,
        project_id=project.id,
        workspace_id=WORKSPACE,
        actor_id=ACTOR,
        stage_key="logo",
        version_id=redo_run.result_version_id,
        selected_item_id=logo_id,
    )
    completed_ip = await harness.execute(ip_run.id)

    assert completed_ip.status == "SUCCEEDED"
    ip_version = await session.get(StageVersion, completed_ip.result_version_id)
    assert ip_version.stage == "IP"
    assert len(ip_version.output_json["views"]) == 2

    stale_count = await session.scalar(
        select(StageVersion).where(
            StageVersion.project_id == project.id,
            StageVersion.stage == "LOGO",
            StageVersion.status == "STALE",
        ).with_only_columns(StageVersion.id).limit(1)
    )
    assert stale_count is not None
