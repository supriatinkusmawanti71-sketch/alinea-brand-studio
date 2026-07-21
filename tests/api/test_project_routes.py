from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.app.main import app
from backend.application.projects import CreateProjectCommand, create_project
from backend.infrastructure.database.models import (
    Artifact,
    Base,
    Decision,
    OutboxEvent,
    Project,
    StageRun,
    StageVersion,
)
from backend.infrastructure.database.session import get_db_session


@dataclass(frozen=True)
class SeededIntakeProject:
    project_id: str
    intake_run_id: str
    intake_version_id: str


@dataclass(frozen=True)
class SeededDirectionsProject:
    project_id: str
    directions_run_id: str
    directions_version_id: str
    direction_ids: list[str]


@dataclass(frozen=True)
class SeededIpChoiceProject:
    project_id: str
    ip_choice_run_id: str
    vi_version_id: str


@dataclass(frozen=True)
class SeededIpReadyProject:
    project_id: str
    directions_version_id: str
    logo_version_id: str
    ip_run_id: str
    ip_version_id: str
    direction_asset_id: str
    logo_asset_id: str
    ip_asset_id: str


@pytest.fixture
def api_client(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    database_path = tmp_path / "api-test.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    asyncio.run(create_schema())
    previous_override = app.dependency_overrides.get(get_db_session)
    app.dependency_overrides[get_db_session] = override_db_session

    with TestClient(app) as client:
        yield client, session_factory

    if previous_override is None:
        app.dependency_overrides.pop(get_db_session, None)
    else:
        app.dependency_overrides[get_db_session] = previous_override
    asyncio.run(engine.dispose())


async def seed_directions_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededDirectionsProject:
    async with session_factory() as session:
        project, intake_run, _ = await create_project(
            session,
            CreateProjectCommand(
                workspace_id="local-workspace",
                actor_id="local-developer",
                name="API 契约测试品牌",
                requirement_text=None,
                structured_fields={"industry": "茶饮"},
                reference_artifact_ids=[],
            ),
        )
        directions_run = StageRun(
            workflow_thread_id=intake_run.workflow_thread_id,
            parent_stage_run_id=intake_run.id,
            project_id=project.id,
            stage="DIRECTIONS",
            status="SUCCEEDED",
            idempotency_key=f"api-test-directions:{project.id}",
            input_json={},
        )
        session.add(directions_run)
        await session.flush()

        direction_ids = ["direction-a", "direction-b", "direction-c"]
        directions_version = StageVersion(
            project_id=project.id,
            stage_run_id=directions_run.id,
            stage="DIRECTIONS",
            version_no=1,
            schema_version=1,
            input_refs_json={"brand_spec_version": 1},
            output_json=build_direction_output(direction_ids),
            status="GENERATED",
        )
        session.add(directions_version)
        await session.flush()
        directions_run.result_version_id = directions_version.id
        project.current_stage = "DIRECTIONS"
        await session.commit()

        return SeededDirectionsProject(
            project_id=project.id,
            directions_run_id=directions_run.id,
            directions_version_id=directions_version.id,
            direction_ids=direction_ids,
        )


async def seed_stage_version(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    stage: str,
) -> str:
    async with session_factory() as session:
        run = StageRun(
            workflow_thread_id=str(uuid4()),
            project_id=project_id,
            stage=stage,
            status="SUCCEEDED",
            idempotency_key=f"api-test-{stage.lower()}:{project_id}",
            input_json={},
        )
        session.add(run)
        await session.flush()

        version = StageVersion(
            project_id=project_id,
            stage_run_id=run.id,
            stage=stage,
            version_no=1,
            schema_version=1,
            input_refs_json={},
            output_json=build_stage_output(stage),
            status="GENERATED",
        )
        session.add(version)
        await session.flush()
        run.result_version_id = version.id
        await session.commit()
        return version.id


async def seed_logo_version(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
) -> str:
    return await seed_stage_version(session_factory, project_id=project_id, stage="LOGO")


async def seed_ip_ready_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededIpReadyProject:
    seeded = await seed_directions_project(session_factory)
    async with session_factory() as session:
        project = await session.get(Project, seeded.project_id)
        assert project is not None
        directions_version = await session.get(StageVersion, seeded.directions_version_id)
        assert directions_version is not None
        direction_asset_id = directions_version.output_json["directions"][0]["preview_asset_id"]

        logo_run = StageRun(
            workflow_thread_id=str(uuid4()),
            project_id=seeded.project_id,
            parent_stage_run_id=seeded.directions_run_id,
            stage="LOGO",
            status="SUCCEEDED",
            idempotency_key=f"api-test-logo-ready:{seeded.project_id}",
            input_json={},
        )
        session.add(logo_run)
        await session.flush()
        direction_decision = Decision(
            project_id=seeded.project_id,
            stage="DIRECTIONS",
            action="SELECT_VERSION",
            source_version_id=seeded.directions_version_id,
            selected_item_id=seeded.direction_ids[0],
            resulting_stage_run_id=logo_run.id,
            created_by="local-developer",
            payload_json={
                "version_id": seeded.directions_version_id,
                "selected_item_id": seeded.direction_ids[0],
            },
        )
        session.add(direction_decision)
        await session.flush()
        logo_output = build_logo_output()
        logo_asset_id = logo_output["concepts"][0]["preview_asset_id"]
        logo_version = StageVersion(
            project_id=seeded.project_id,
            stage_run_id=logo_run.id,
            stage="LOGO",
            version_no=1,
            schema_version=1,
            input_refs_json={
                "brand_spec_version": 1,
                "direction_version_id": seeded.directions_version_id,
                "decision_id": direction_decision.id,
            },
            output_json=logo_output,
            status="GENERATED",
        )
        session.add(logo_version)
        await session.flush()
        logo_run.result_version_id = logo_version.id

        ip_run = StageRun(
            workflow_thread_id=str(uuid4()),
            project_id=seeded.project_id,
            parent_stage_run_id=logo_run.id,
            stage="IP",
            status="SUCCEEDED",
            idempotency_key=f"api-test-ip-ready:{seeded.project_id}",
            input_json={},
        )
        session.add(ip_run)
        await session.flush()
        logo_decision = Decision(
            project_id=seeded.project_id,
            stage="LOGO",
            action="SELECT_VERSION",
            source_version_id=logo_version.id,
            selected_item_id="logo-wordmark",
            resulting_stage_run_id=ip_run.id,
            created_by="local-developer",
            payload_json={
                "version_id": logo_version.id,
                "selected_item_id": "logo-wordmark",
            },
        )
        session.add(logo_decision)
        await session.flush()
        ip_output = build_ip_output()
        ip_asset_id = ip_output["preview_asset_id"]
        ip_version = StageVersion(
            project_id=seeded.project_id,
            stage_run_id=ip_run.id,
            stage="IP",
            version_no=1,
            schema_version=1,
            input_refs_json={
                "brand_spec_version": 1,
                "logo_version_id": logo_version.id,
                "decision_id": logo_decision.id,
            },
            output_json=ip_output,
            status="GENERATED",
        )
        session.add(ip_version)
        await session.flush()
        ip_run.result_version_id = ip_version.id
        image_body = b"fake-png"
        image_digest = sha256(image_body).hexdigest()
        session.add_all(
            [
                Artifact(
                    id=asset_id,
                    workspace_id="local-workspace",
                    project_id=seeded.project_id,
                    stage_run_id=stage_run_id,
                    kind="GENERATED_IMAGE",
                    storage_provider="S3",
                    bucket="test-bucket",
                    object_key=f"test-assets/{asset_id}.png",
                    mime_type="image/png",
                    size_bytes=len(image_body),
                    width=1024,
                    height=1024,
                    sha256=image_digest,
                    status="STORED",
                    metadata_json={},
                )
                for asset_id, stage_run_id in (
                    (direction_asset_id, seeded.directions_run_id),
                    (logo_asset_id, logo_run.id),
                    (ip_asset_id, ip_run.id),
                )
            ]
        )
        project.current_stage = "IP"
        await session.commit()
        return SeededIpReadyProject(
            project_id=seeded.project_id,
            directions_version_id=seeded.directions_version_id,
            logo_version_id=logo_version.id,
            ip_run_id=ip_run.id,
            ip_version_id=ip_version.id,
            direction_asset_id=direction_asset_id,
            logo_asset_id=logo_asset_id,
            ip_asset_id=ip_asset_id,
        )


async def seed_completed_three_agent_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededIpReadyProject:
    seeded = await seed_ip_ready_project(session_factory)
    async with session_factory() as session:
        project = await session.get(Project, seeded.project_id)
        assert project is not None
        final_run = StageRun(
            workflow_thread_id=str(uuid4()),
            project_id=seeded.project_id,
            parent_stage_run_id=seeded.ip_run_id,
            stage="IP",
            status="SUCCEEDED",
            idempotency_key=f"api-test-ip-final:{seeded.project_id}",
            input_json={},
            result_version_id=seeded.ip_version_id,
        )
        session.add(final_run)
        await session.flush()
        session.add(
            Decision(
                project_id=seeded.project_id,
                stage="IP",
                action="CONFIRM_VERSION",
                source_version_id=seeded.ip_version_id,
                selected_item_id=None,
                resulting_stage_run_id=final_run.id,
                created_by="local-developer",
                payload_json={
                    "version_id": seeded.ip_version_id,
                    "confirmed": True,
                },
            )
        )
        project.current_stage = "IP"
        project.status = "COMPLETED"
        await session.commit()
        return seeded


async def mark_stage_version_stale(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    version_id: str,
) -> None:
    async with session_factory() as session:
        version = await session.get(StageVersion, version_id)
        assert version is not None
        version.status = "STALE"
        await session.commit()


async def mark_project_completed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
) -> None:
    async with session_factory() as session:
        project = await session.get(Project, project_id)
        assert project is not None
        project.current_stage = "IP"
        project.status = "COMPLETED"
        await session.commit()


async def seed_ip_choice_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededIpChoiceProject:
    seeded = await seed_directions_project(session_factory)
    vi_version_id = await seed_stage_version(
        session_factory,
        project_id=seeded.project_id,
        stage="VI",
    )
    async with session_factory() as session:
        ip_choice_run = StageRun(
            workflow_thread_id=str(uuid4()),
            project_id=seeded.project_id,
            stage="IP",
            status="WAITING_USER",
            idempotency_key=f"api-test-ip-choice:{seeded.project_id}",
            input_json={
                "vi_version_id": vi_version_id,
                "decision_id": str(uuid4()),
            },
        )
        session.add(ip_choice_run)
        await session.flush()
        await session.commit()
        return SeededIpChoiceProject(
            project_id=seeded.project_id,
            ip_choice_run_id=ip_choice_run.id,
            vi_version_id=vi_version_id,
        )


async def seed_succeeded_intake_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> SeededIntakeProject:
    async with session_factory() as session:
        project, intake_run, _ = await create_project(
            session,
            CreateProjectCommand(
                workspace_id="local-workspace",
                actor_id="local-developer",
                name="Intake API 契约测试品牌",
                requirement_text=None,
                structured_fields={},
                reference_artifact_ids=[],
            ),
        )
        intake_run.status = "SUCCEEDED"
        intake_version = StageVersion(
            project_id=project.id,
            stage_run_id=intake_run.id,
            stage="INTAKE",
            version_no=1,
            schema_version=1,
            input_refs_json={},
            output_json={
                "schema_version": 1,
                "ready": False,
                "questions": [
                    {
                        "id": "q-industry",
                        "field_path": "industry",
                        "prompt": "请补充行业。",
                        "reason": "用于生成品牌方向。",
                        "required": True,
                        "answer_type": "TEXT",
                        "options": [],
                    }
                ],
                "brand_spec_patch": {},
                "suggestions": [],
                "conflicts": [],
            },
            status="GENERATED",
        )
        session.add(intake_version)
        await session.flush()
        intake_run.result_version_id = intake_version.id
        await session.commit()

        return SeededIntakeProject(
            project_id=project.id,
            intake_run_id=intake_run.id,
            intake_version_id=intake_version.id,
        )


def build_direction_output(direction_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "brief": {
            "positioning": "城市茶饮品牌",
            "audience_insight": "年轻消费者需要清爽、有记忆点的日常茶饮。",
            "brand_promise": "用东方茶香提供轻盈的城市片刻。",
            "tone": "清爽、现代、可信赖",
        },
        "directions": [
            {
                "id": direction_id,
                "name": f"方向 {index}",
                "concept": "以东方茶叶和城市线条构建现代视觉。",
                "keywords": ["现代", "东方", "清爽"],
                "palette": [
                    {"name": "Tea Green", "hex": "#2F8F5B", "usage": "主品牌色"},
                    {"name": "Rice White", "hex": "#F6F1E6", "usage": "背景色"},
                    {"name": "Ink Black", "hex": "#1E1E1E", "usage": "文字色"},
                ],
                "typography": {
                    "heading_style": "几何无衬线标题",
                    "body_style": "高可读性无衬线正文",
                },
                "composition": "使用垂直中轴和留白强化识别。",
                "rationale": "平衡东方感和城市效率。",
                "risks": [],
                "image_prompt": "modern tea brand visual direction",
                "preview_asset_id": str(uuid4()),
            }
            for index, direction_id in enumerate(direction_ids, start=1)
        ],
    }


def build_logo_output() -> dict[str, object]:
    return {
        "schema_version": 1,
        "concepts": [
            {
                "id": "logo-wordmark",
                "name": "结构字标",
                "rationale": "以清晰字形建立稳定识别。",
                "symbolism": "通过字形比例表达品牌可靠感。",
                "shape_language": "克制几何和开放留白。",
                "color_strategy": "优先使用方向主色。",
                "image_prompt": "modern wordmark logo",
                "preview_asset_id": str(uuid4()),
            },
            {
                "id": "logo-symbol",
                "name": "抽象符号",
                "rationale": "提升图标场景辨识度。",
                "symbolism": "抽象连接形态。",
                "shape_language": "简洁轮廓和单一重心。",
                "color_strategy": "主色与深色高对比。",
                "image_prompt": "modern symbol logo",
                "preview_asset_id": str(uuid4()),
            },
            {
                "id": "logo-combination",
                "name": "组合标识",
                "rationale": "兼顾完整表达和拆分使用。",
                "symbolism": "文字负责名称，符号承载概念。",
                "shape_language": "横版与竖版均可延展。",
                "color_strategy": "主色与中性色组合。",
                "image_prompt": "modern combination logo",
                "preview_asset_id": str(uuid4()),
            },
            {
                "id": "logo-emblem",
                "name": "徽章图标",
                "rationale": "提升包装、头像和活动场景存在感。",
                "symbolism": "封装品牌核心识别元素。",
                "shape_language": "圆角边界、中心符号、简洁层次。",
                "color_strategy": "方向主色配合浅底和深色描边。",
                "image_prompt": "modern emblem logo",
                "preview_asset_id": str(uuid4()),
            },
        ],
    }


def build_stage_output(stage: str) -> dict[str, object]:
    if stage == "LOGO":
        return build_logo_output()
    if stage == "IP":
        return build_ip_output()
    if stage == "PROPOSAL":
        return build_proposal_output()
    return {}


def build_ip_output() -> dict[str, object]:
    return {
        "schema_version": 1,
        "character": {
            "name": "API 契约测试品牌伙伴",
            "role": "作为品牌内容与服务场景中的友好引导者。",
            "personality": ["可靠", "好奇", "亲和"],
            "appearance": "由品牌主色、简洁圆润轮廓和清晰面部表情构成。",
            "brand_connection": "延续已确认 Logo 的几何语言与方向色彩。",
        },
        "pose": {
            "name": "正面欢迎姿态",
            "description": "正面站立并以开放手势欢迎用户，背景简洁。",
        },
        "image_prompt": "brand mascot character sheet",
        "preview_asset_id": str(uuid4()),
    }


def build_proposal_output() -> dict[str, object]:
    direction_asset_id = str(uuid4())
    logo_asset_id = str(uuid4())
    material_asset_ids = [str(uuid4()), str(uuid4())]
    return {
        "schema_version": 1,
        "title": "API 契约测试品牌 品牌概念提案",
        "narrative": "从品牌需求出发，形成方向、标识、规范与应用的一致叙事。",
        "sections": [
            {
                "type": "BRIEF",
                "title": "品牌简报",
                "summary": "用东方茶香提供轻盈的城市片刻。",
                "version_id": str(uuid4()),
                "asset_ids": [],
            },
            {
                "type": "DIRECTION",
                "title": "方向 1",
                "summary": "以东方茶叶和城市线条构建现代视觉。",
                "version_id": str(uuid4()),
                "asset_ids": [direction_asset_id],
            },
            {
                "type": "LOGO",
                "title": "结构字标",
                "summary": "以清晰字形建立稳定识别。",
                "version_id": str(uuid4()),
                "asset_ids": [logo_asset_id],
            },
            {
                "type": "VI",
                "title": "基础视觉规范",
                "summary": "包含色板、字体、Logo 使用规则和基础版式。",
                "version_id": str(uuid4()),
                "asset_ids": [logo_asset_id],
            },
            {
                "type": "MATERIALS",
                "title": "品牌应用物料",
                "summary": "展示两个预设场景中的品牌应用。",
                "version_id": str(uuid4()),
                "asset_ids": material_asset_ids,
            },
            {
                "type": "REVIEW_SUMMARY",
                "title": "审稿摘要",
                "summary": "所有已确认阶段的结构、约束和资产引用已完成检查。",
                "version_id": str(uuid4()),
                "asset_ids": [],
            },
        ],
        "asset_refs": [direction_asset_id, logo_asset_id, *material_asset_ids],
    }


def test_get_project_state_returns_latest_stage_data(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == seeded.project_id
    assert payload["brand_spec"]["industry"] == "茶饮"
    assert payload["current_stage"] == "DIRECTIONS"
    assert payload["stage_runs"]["DIRECTIONS"]["status"] == "SUCCEEDED"
    assert payload["versions"]["DIRECTIONS"]["id"] == seeded.directions_version_id
    assert payload["decisions"] == []


def test_get_project_state_missing_project_returns_404(api_client) -> None:
    client, _ = api_client

    response = client.get(f"/api/v1/projects/{uuid4()}/state")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_get_stage_run_returns_result_by_default(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.get(f"/api/v1/stage-runs/{seeded.directions_run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == seeded.directions_run_id
    assert payload["status"] == "SUCCEEDED"
    assert payload["result"]["directions"][0]["id"] == "direction-a"


def test_get_stage_run_can_omit_result_for_polling(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.get(
        f"/api/v1/stage-runs/{seeded.directions_run_id}?include_result=false",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == seeded.directions_run_id
    assert payload["status"] == "SUCCEEDED"
    assert payload["result_version_id"] == seeded.directions_version_id
    assert payload["result"] is None


def test_list_stage_versions_returns_versions_for_project_stage(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/versions",
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [seeded.directions_version_id]
    assert payload[0]["stage"] == "DIRECTIONS"
    assert payload[0]["output"]["directions"][0]["id"] == "direction-a"


def test_list_stage_versions_missing_project_returns_404(api_client) -> None:
    client, _ = api_client

    response = client.get(f"/api/v1/projects/{uuid4()}/stages/directions/versions")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_list_stage_versions_invalid_stage_returns_422(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.get(f"/api/v1/projects/{seeded.project_id}/stages/nope/versions")

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid stage key: nope"}


def test_create_stage_decision_dispatches_logo_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": seeded.directions_version_id,
        "selected_item_id": seeded.direction_ids[0],
        "action": "SELECT_VERSION",
    }

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json=request_payload,
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "LOGO"
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == [first_payload["stage_run"]["id"]]

    async def load_outbox_statuses() -> list[tuple[str, int]]:
        async with session_factory() as session:
            events = list(await session.scalars(select(OutboxEvent)))
            return sorted((event.status, event.attempt) for event in events)

    assert asyncio.run(load_outbox_statuses()) == [
        ("PENDING", 0),
        ("PUBLISHED", 1),
    ]


def test_create_stage_decision_conflicting_selection_returns_409(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    endpoint = f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions"
    first_payload = {
        "version_id": seeded.directions_version_id,
        "selected_item_id": seeded.direction_ids[0],
    }
    conflicting_payload = {
        "version_id": seeded.directions_version_id,
        "selected_item_id": seeded.direction_ids[1],
    }

    assert client.post(endpoint, json=first_payload).status_code == 202
    response = client.post(endpoint, json=conflicting_payload)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This Directions version already has another selection",
    }


def test_create_stage_decision_missing_project_returns_404(api_client) -> None:
    client, _ = api_client

    response = client.post(
        f"/api/v1/projects/{uuid4()}/stages/directions/decisions",
        json={
            "version_id": str(uuid4()),
            "selected_item_id": "direction-a",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_create_stage_decision_missing_version_returns_404(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json={
            "version_id": str(uuid4()),
            "selected_item_id": "direction-a",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage version not found"}


def test_create_stage_decision_invalid_stage_returns_422(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/nope/decisions",
        json={
            "version_id": seeded.directions_version_id,
            "selected_item_id": "direction-a",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid stage key: nope"}


def test_create_logo_stage_decision_dispatches_ip_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": logo_version_id,
        "selected_item_id": "logo-wordmark",
    }

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json=request_payload,
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "IP"
    assert first_payload["decision"]["stage"] == "LOGO"
    assert first_payload["decision"]["selected_item_id"] == "logo-wordmark"
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == [first_payload["stage_run"]["id"]]


def test_create_logo_stage_decision_conflicting_selection_returns_409(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    endpoint = f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions"
    first_payload = {
        "version_id": logo_version_id,
        "selected_item_id": "logo-wordmark",
    }
    conflicting_payload = {
        "version_id": logo_version_id,
        "selected_item_id": "logo-symbol",
    }

    assert client.post(endpoint, json=first_payload).status_code == 202
    response = client.post(endpoint, json=conflicting_payload)

    assert response.status_code == 409
    assert response.json() == {"detail": "This Logo version already has another selection"}


def test_create_stage_decision_invalid_logo_selection_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": logo_version_id,
            "selected_item_id": "missing-logo",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Selected logo does not exist in current version",
    }


def test_create_logo_stage_decision_confirm_version_skeleton_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": logo_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "LOGO CONFIRM_VERSION decisions are not supported by this worker milestone",
    }


@pytest.mark.skip(reason="旧 VI 阶段流程已移除，Logo 选择后直接进入 IP")
def test_confirm_vi_stage_decision_dispatches_ip_choice_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    vi_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="VI",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": vi_version_id,
        "action": "CONFIRM_VERSION",
        "confirmed": True,
    }
    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/vi/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/vi/decisions",
        json=request_payload,
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "IP"
    assert first_payload["stage_run"]["status"] == "QUEUED"
    assert first_payload["decision"]["stage"] == "VI"
    assert first_payload["decision"]["action"] == "CONFIRM_VERSION"
    assert first_payload["decision"]["selected_item_id"] is None
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == [first_payload["stage_run"]["id"]]


def test_confirm_ip_stage_decision_completes_project_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_ready_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": seeded.ip_version_id,
        "action": "CONFIRM_VERSION",
        "confirmed": True,
    }
    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json=request_payload,
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "IP"
    assert first_payload["stage_run"]["status"] == "SUCCEEDED"
    assert first_payload["stage_run"]["result_version_id"] == seeded.ip_version_id
    assert first_payload["decision"]["stage"] == "IP"
    assert first_payload["decision"]["action"] == "CONFIRM_VERSION"
    assert first_payload["decision"]["selected_item_id"] is None
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == []
    state_payload = state_response.json()
    assert state_payload["project"]["status"] == "COMPLETED"
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["IP"]["status"] == "SUCCEEDED"
    assert state_payload["versions"]["IP"]["id"] == seeded.ip_version_id


def test_three_agent_api_contract_smoke_reaches_export(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    async def attach_generated_version(
        *,
        stage_run_id: str,
        stage: str,
        output_json: dict[str, object],
        input_refs_json: dict[str, object],
    ) -> str:
        async with session_factory() as session:
            stage_run = await session.get(StageRun, stage_run_id)
            assert stage_run is not None
            project = await session.get(Project, stage_run.project_id)
            assert project is not None
            stage_run.status = "SUCCEEDED"
            version = StageVersion(
                project_id=stage_run.project_id,
                stage_run_id=stage_run.id,
                stage=stage,
                version_no=1,
                schema_version=1,
                input_refs_json=input_refs_json,
                output_json=output_json,
                status="GENERATED",
            )
            session.add(version)
            await session.flush()
            stage_run.result_version_id = version.id
            project.current_stage = stage
            await session.commit()
            return version.id

    direction_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json={
            "version_id": seeded.directions_version_id,
            "selected_item_id": seeded.direction_ids[0],
        },
    )
    direction_payload = direction_response.json()
    assert direction_response.status_code == 202
    assert direction_payload["stage_run"]["stage"] == "LOGO"

    logo_version_id = asyncio.run(
        attach_generated_version(
            stage_run_id=direction_payload["stage_run"]["id"],
            stage="LOGO",
            output_json=build_logo_output(),
            input_refs_json={
                "brand_spec_version": 1,
                "direction_version_id": seeded.directions_version_id,
                "decision_id": direction_payload["decision"]["id"],
            },
        )
    )

    logo_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": logo_version_id,
            "selected_item_id": "logo-wordmark",
        },
    )
    logo_payload = logo_response.json()
    assert logo_response.status_code == 202
    assert logo_payload["stage_run"]["stage"] == "IP"

    ip_version_id = asyncio.run(
        attach_generated_version(
            stage_run_id=logo_payload["stage_run"]["id"],
            stage="IP",
            output_json=build_ip_output(),
            input_refs_json={
                "brand_spec_version": 1,
                "logo_version_id": logo_version_id,
                "decision_id": logo_payload["decision"]["id"],
            },
        )
    )

    ip_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json={
            "version_id": ip_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    export_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal-manifest",
    )

    assert ip_response.status_code == 202
    assert state_response.json()["project"]["status"] == "COMPLETED"
    assert export_response.status_code == 200
    assert [section["type"] for section in export_response.json()["sections"]] == [
        "BRIEF",
        "DIRECTION",
        "LOGO",
        "IP",
    ]
    assert dispatched_stage_run_ids == [
        direction_payload["stage_run"]["id"],
        logo_payload["stage_run"]["id"],
    ]


@pytest.mark.skip(reason="旧 MATERIALS 阶段流程已移除，IP 确认后直接完成")
def test_confirm_materials_stage_decision_dispatches_review_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    materials_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="MATERIALS",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": materials_version_id,
        "action": "CONFIRM_VERSION",
        "confirmed": True,
    }
    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/materials/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/materials/decisions",
        json=request_payload,
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "REVIEW"
    assert first_payload["stage_run"]["status"] == "QUEUED"
    assert first_payload["decision"]["stage"] == "MATERIALS"
    assert first_payload["decision"]["action"] == "CONFIRM_VERSION"
    assert first_payload["decision"]["selected_item_id"] is None
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == [first_payload["stage_run"]["id"]]


@pytest.mark.skip(reason="旧 REVIEW 阶段流程已移除，IP 确认后直接完成")
def test_confirm_review_stage_decision_dispatches_proposal_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    review_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="REVIEW",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    request_payload = {
        "version_id": review_version_id,
        "action": "CONFIRM_VERSION",
        "confirmed": True,
    }
    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/review/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/review/decisions",
        json=request_payload,
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "PROPOSAL"
    assert first_payload["stage_run"]["status"] == "QUEUED"
    assert first_payload["decision"]["stage"] == "REVIEW"
    assert first_payload["decision"]["action"] == "CONFIRM_VERSION"
    assert first_payload["decision"]["selected_item_id"] is None
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == [first_payload["stage_run"]["id"]]


@pytest.mark.skip(reason="旧 PROPOSAL 阶段流程已移除，导出由 IP 确认结果组装")
def test_confirm_proposal_stage_decision_completes_project_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    proposal_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="PROPOSAL",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    request_payload = {
        "version_id": proposal_version_id,
        "action": "CONFIRM_VERSION",
        "confirmed": True,
    }
    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/proposal/decisions",
        json=request_payload,
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/proposal/decisions",
        json=request_payload,
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload["stage_run"]["stage"] == "PROPOSAL"
    assert first_payload["stage_run"]["status"] == "SUCCEEDED"
    assert first_payload["stage_run"]["result_version_id"] == proposal_version_id
    assert first_payload["decision"]["stage"] == "PROPOSAL"
    assert first_payload["decision"]["action"] == "CONFIRM_VERSION"
    assert first_payload["decision"]["selected_item_id"] is None
    assert repeated_payload["stage_run"]["id"] == first_payload["stage_run"]["id"]
    assert repeated_payload["decision"]["id"] == first_payload["decision"]["id"]
    assert dispatched_stage_run_ids == []

    state_payload = state_response.json()
    assert state_response.status_code == 200
    assert state_payload["project"]["status"] == "COMPLETED"
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["PROPOSAL"]["id"] == first_payload["stage_run"]["id"]
    assert state_payload["stage_runs"]["PROPOSAL"]["status"] == "SUCCEEDED"
    assert state_payload["versions"]["PROPOSAL"]["id"] == proposal_version_id


def test_completed_project_rejects_non_final_stage_decisions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_ready_project(session_factory))
    logo_version_id = seeded.logo_version_id
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    completion_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json={
            "version_id": seeded.ip_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    logo_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": logo_version_id,
            "selected_item_id": "logo-symbol",
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert completion_response.status_code == 202
    assert logo_response.status_code == 409
    assert logo_response.json() == {
        "detail": "Completed project cannot accept stage decisions",
    }
    assert dispatched_stage_run_ids == []
    state_payload = state_response.json()
    assert state_payload["project"]["status"] == "COMPLETED"
    assert state_payload["current_stage"] == "IP"


def test_completed_project_redo_reopens_project(
    api_client,
    monkeypatch,
) -> None:
    """REDO is allowed on a completed project and reopens it; other stage
    controls remain rejected."""

    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    asyncio.run(mark_project_completed(session_factory, project_id=seeded.project_id))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    skip_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/skip",
        json={"reason": "completed projects reject non-redo controls"},
    )
    assert skip_response.status_code == 409
    assert skip_response.json() == {
        "detail": "Completed project cannot accept stage controls",
    }

    redo_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/redo",
        json={
            "source_version_id": seeded.directions_version_id,
            "reason": "重新打磨方向",
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert redo_response.status_code == 202
    assert len(dispatched_stage_run_ids) == 1
    state_payload = state_response.json()
    assert state_payload["project"]["status"] == "ACTIVE"
    assert state_payload["current_stage"] == "DIRECTIONS"


def test_get_proposal_export_manifest_returns_completed_project_manifest(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_completed_three_agent_project(session_factory))
    manifest_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal-manifest",
    )

    manifest_payload = manifest_response.json()
    assert manifest_response.status_code == 200
    assert manifest_payload["project_id"] == seeded.project_id
    assert manifest_payload["project_name"] == "API 契约测试品牌"
    assert manifest_payload["proposal_version_id"] == seeded.ip_version_id
    assert manifest_payload["title"] == "API 契约测试品牌 品牌交付包"
    assert [section["type"] for section in manifest_payload["sections"]] == [
        "BRIEF",
        "DIRECTION",
        "LOGO",
        "IP",
    ]
    assert set(manifest_payload["asset_refs"]) == {
        seeded.direction_asset_id,
        seeded.logo_asset_id,
        seeded.ip_asset_id,
    }


def test_download_proposal_markdown_returns_completed_project_file(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_completed_three_agent_project(session_factory))
    download_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal.md",
    )

    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("text/markdown")
    assert download_response.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''%E5%93%81%E7%89%8C%E8%AF%B4%E6%98%8E.md"
    )
    assert "# API 契约测试品牌 品牌说明" in download_response.text
    assert "## 交付文件" in download_response.text
    assert f"- Proposal version: `{seeded.ip_version_id}`" in download_response.text
    assert "### 品牌简报" in download_response.text
    assert "### API 契约测试品牌伙伴" in download_response.text
    assert "## Asset References" in download_response.text


def test_download_proposal_zip_returns_completed_project_bundle(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_completed_three_agent_project(session_factory))

    class FakeS3Client:
        def get_object(self, *, Bucket: str, Key: str) -> dict[str, io.BytesIO]:
            assert Bucket == "test-bucket"
            assert Key.startswith("test-assets/")
            return {"Body": io.BytesIO(b"fake-png")}

    from apps.api.app.routers import projects

    monkeypatch.setattr(projects.boto3, "client", lambda *args, **kwargs: FakeS3Client())

    bundle_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal.zip",
    )

    assert bundle_response.status_code == 200
    assert bundle_response.headers["content-type"].startswith("application/zip")
    assert bundle_response.headers["content-disposition"] == (
        f'attachment; filename="proposal-{seeded.project_id}.zip"'
    )
    with ZipFile(io.BytesIO(bundle_response.content)) as bundle:
        assert bundle.namelist() == [
            "品牌说明.md",
            "proposal-manifest.json",
            "品牌方向.png",
            "Logo方案.png",
            "IP形象.png",
        ]
        markdown = bundle.read("品牌说明.md").decode("utf-8")
        manifest_payload = json.loads(bundle.read("proposal-manifest.json"))
        assert bundle.read("品牌方向.png") == b"fake-png"
        assert bundle.read("Logo方案.png") == b"fake-png"
        assert bundle.read("IP形象.png") == b"fake-png"

    assert "# API 契约测试品牌 品牌说明" in markdown
    assert manifest_payload["project_id"] == seeded.project_id
    assert manifest_payload["proposal_version_id"] == seeded.ip_version_id
    assert set(manifest_payload["asset_refs"]) == {
        seeded.direction_asset_id,
        seeded.logo_asset_id,
        seeded.ip_asset_id,
    }


def test_get_proposal_export_manifest_requires_completed_project(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="PROPOSAL",
        ),
    )

    response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal-manifest",
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Project is not completed"}


def test_get_proposal_export_manifest_rejects_stale_completed_proposal(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_completed_three_agent_project(session_factory))
    asyncio.run(mark_stage_version_stale(session_factory, version_id=seeded.ip_version_id))

    response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal-manifest",
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Completed project has no IP version"}


def test_get_proposal_export_manifest_requires_final_confirmation(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_ready_project(session_factory))
    asyncio.run(mark_project_completed(session_factory, project_id=seeded.project_id))

    response = client.get(
        f"/api/v1/projects/{seeded.project_id}/exports/proposal-manifest",
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Completed project has no IP confirmation"}


def test_confirm_stage_decision_foreign_version_returns_404(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    other_project = asyncio.run(seed_directions_project(session_factory))
    other_ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=other_project.project_id,
            stage="IP",
        ),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json={
            "version_id": other_ip_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage version not found"}


def test_confirm_stage_decision_mismatched_stage_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="IP",
        ),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": ip_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Stage version does not belong to requested stage",
    }


def test_create_stage_decision_select_version_requires_selected_item(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json={
            "version_id": seeded.directions_version_id,
            "action": "SELECT_VERSION",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "selected_item_id is required for SELECT_VERSION decisions",
    }


def test_create_stage_decision_confirm_version_requires_confirmation(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_ready_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json={
            "version_id": seeded.ip_version_id,
            "action": "CONFIRM_VERSION",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "confirmed=true is required for CONFIRM_VERSION decisions",
    }


def test_stage_decision_exposes_stale_downstream_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    stale_logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json={
            "version_id": seeded.directions_version_id,
            "selected_item_id": seeded.direction_ids[0],
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    logo_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    logo_versions_payload = logo_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "LOGO"
    assert state_payload["stage_runs"]["LOGO"]["status"] == "QUEUED"
    assert state_payload["versions"]["LOGO"]["id"] == stale_logo_version_id
    assert state_payload["versions"]["LOGO"]["status"] == "STALE"
    assert logo_versions_response.status_code == 200
    assert logo_versions_payload[0]["id"] == stale_logo_version_id
    assert logo_versions_payload[0]["status"] == "STALE"


def test_stage_decision_rejects_stale_stage_version(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    stale_logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    direction_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/decisions",
        json={
            "version_id": seeded.directions_version_id,
            "selected_item_id": seeded.direction_ids[0],
        },
    )
    stale_logo_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": stale_logo_version_id,
            "selected_item_id": "logo-wordmark",
        },
    )

    assert direction_response.status_code == 202
    assert stale_logo_response.status_code == 409
    assert stale_logo_response.json() == {
        "detail": "Only a generated Stage version can be decided",
    }


def test_logo_stage_decision_exposes_stale_ip_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )
    stale_ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="IP",
        ),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/decisions",
        json={
            "version_id": logo_version_id,
            "selected_item_id": "logo-wordmark",
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    ip_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    ip_versions_payload = ip_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["IP"]["status"] == "QUEUED"
    assert state_payload["versions"]["IP"]["id"] == stale_ip_version_id
    assert state_payload["versions"]["IP"]["status"] == "STALE"
    assert ip_versions_response.status_code == 200
    assert ip_versions_payload[0]["id"] == stale_ip_version_id
    assert ip_versions_payload[0]["status"] == "STALE"


@pytest.mark.skip(reason="旧 VI 阶段流程已移除")
def test_vi_stage_decision_exposes_stale_downstream_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    vi_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="VI",
        ),
    )
    stale_ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="IP",
        ),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/vi/decisions",
        json={
            "version_id": vi_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    ip_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    ip_versions_payload = ip_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["IP"]["status"] == "QUEUED"
    assert state_payload["versions"]["IP"]["id"] == stale_ip_version_id
    assert state_payload["versions"]["IP"]["status"] == "STALE"
    assert ip_versions_response.status_code == 200
    assert ip_versions_payload[0]["id"] == stale_ip_version_id
    assert ip_versions_payload[0]["status"] == "STALE"


@pytest.mark.skip(reason="旧 IP->MATERIALS 下游流程已移除，IP 确认后直接完成")
def test_ip_stage_decision_exposes_stale_downstream_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="IP",
        ),
    )
    stale_materials_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="MATERIALS",
        ),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/decisions",
        json={
            "version_id": ip_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    materials_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/materials/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    materials_versions_payload = materials_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "MATERIALS"
    assert state_payload["stage_runs"]["MATERIALS"]["status"] == "QUEUED"
    assert state_payload["versions"]["MATERIALS"]["id"] == stale_materials_version_id
    assert state_payload["versions"]["MATERIALS"]["status"] == "STALE"
    assert materials_versions_response.status_code == 200
    assert materials_versions_payload[0]["id"] == stale_materials_version_id
    assert materials_versions_payload[0]["status"] == "STALE"


@pytest.mark.skip(reason="旧 MATERIALS 阶段流程已移除")
def test_materials_stage_decision_exposes_stale_downstream_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    materials_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="MATERIALS",
        ),
    )
    stale_review_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="REVIEW",
        ),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/materials/decisions",
        json={
            "version_id": materials_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    review_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/review/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    review_versions_payload = review_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "REVIEW"
    assert state_payload["stage_runs"]["REVIEW"]["status"] == "QUEUED"
    assert state_payload["versions"]["REVIEW"]["id"] == stale_review_version_id
    assert state_payload["versions"]["REVIEW"]["status"] == "STALE"
    assert review_versions_response.status_code == 200
    assert review_versions_payload[0]["id"] == stale_review_version_id
    assert review_versions_payload[0]["status"] == "STALE"


@pytest.mark.skip(reason="旧 REVIEW 阶段流程已移除")
def test_review_stage_decision_exposes_stale_downstream_versions(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    review_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="REVIEW",
        ),
    )
    stale_proposal_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="PROPOSAL",
        ),
    )

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    decision_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/review/decisions",
        json={
            "version_id": review_version_id,
            "action": "CONFIRM_VERSION",
            "confirmed": True,
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    proposal_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/proposal/versions",
    )

    assert decision_response.status_code == 202
    state_payload = state_response.json()
    proposal_versions_payload = proposal_versions_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["PROPOSAL"]["status"] == "QUEUED"
    assert state_payload["versions"]["PROPOSAL"]["id"] == stale_proposal_version_id
    assert state_payload["versions"]["PROPOSAL"]["status"] == "STALE"
    assert proposal_versions_response.status_code == 200
    assert proposal_versions_payload[0]["id"] == stale_proposal_version_id
    assert proposal_versions_payload[0]["status"] == "STALE"


def test_intake_answers_dispatches_directions_run(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_succeeded_intake_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    response = client.post(
        f"/api/v1/stage-runs/{seeded.intake_run_id}/intake-answers",
        json={
            "answers": [
                {
                    "field_path": "industry",
                    "value": "茶饮",
                }
            ]
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["stage"] == "DIRECTIONS"
    assert payload["parent_stage_run_id"] == seeded.intake_run_id
    assert dispatched_stage_run_ids == [payload["id"]]


def test_empty_intake_answers_are_rejected_when_intake_needs_answers(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_succeeded_intake_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    response = client.post(
        f"/api/v1/stage-runs/{seeded.intake_run_id}/intake-answers",
        json={"answers": []},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Intake requires answers before generating directions"}
    assert dispatched_stage_run_ids == []


def test_intake_answers_missing_stage_run_returns_404(api_client) -> None:
    client, _ = api_client

    response = client.post(
        f"/api/v1/stage-runs/{uuid4()}/intake-answers",
        json={
            "answers": [
                {
                    "field_path": "industry",
                    "value": "茶饮",
                }
            ]
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage run not found"}


def test_intake_answers_conflicting_stage_run_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/stage-runs/{seeded.directions_run_id}/intake-answers",
        json={
            "answers": [
                {
                    "field_path": "industry",
                    "value": "茶饮",
                }
            ]
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only a succeeded Intake run can accept answers"}


def test_intake_answers_stale_intake_version_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_succeeded_intake_project(session_factory))
    asyncio.run(mark_stage_version_stale(session_factory, version_id=seeded.intake_version_id))

    response = client.post(
        f"/api/v1/stage-runs/{seeded.intake_run_id}/intake-answers",
        json={
            "answers": [
                {
                    "field_path": "industry",
                    "value": "茶饮",
                }
            ]
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only a generated Intake version can accept answers"}


def test_completed_project_rejects_intake_answers(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_succeeded_intake_project(session_factory))
    asyncio.run(mark_project_completed(session_factory, project_id=seeded.project_id))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    response = client.post(
        f"/api/v1/stage-runs/{seeded.intake_run_id}/intake-answers",
        json={
            "answers": [
                {
                    "field_path": "industry",
                    "value": "茶饮",
                }
            ]
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Completed project cannot accept intake answers",
    }
    assert dispatched_stage_run_ids == []
    state_payload = state_response.json()
    assert state_payload["project"]["status"] == "COMPLETED"
    assert state_payload["current_stage"] == "IP"


def test_legacy_direction_selection_dispatches_logo_run(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    response = client.post(
        f"/api/v1/stage-runs/{seeded.directions_run_id}/direction-selection",
        json={
            "version_id": seeded.directions_version_id,
            "direction_id": seeded.direction_ids[0],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["stage"] == "LOGO"
    assert payload["parent_stage_run_id"] == seeded.directions_run_id
    assert dispatched_stage_run_ids == [payload["id"]]


def test_legacy_direction_selection_missing_stage_run_returns_404(api_client) -> None:
    client, _ = api_client

    response = client.post(
        f"/api/v1/stage-runs/{uuid4()}/direction-selection",
        json={
            "version_id": str(uuid4()),
            "direction_id": "direction-a",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage run not found"}


def test_legacy_direction_selection_stale_version_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    asyncio.run(mark_stage_version_stale(session_factory, version_id=seeded.directions_version_id))

    response = client.post(
        f"/api/v1/stage-runs/{seeded.directions_run_id}/direction-selection",
        json={
            "version_id": seeded.directions_version_id,
            "direction_id": seeded.direction_ids[0],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only a generated Stage version can be decided"}


def test_completed_project_rejects_legacy_direction_selection(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    asyncio.run(mark_project_completed(session_factory, project_id=seeded.project_id))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    response = client.post(
        f"/api/v1/stage-runs/{seeded.directions_run_id}/direction-selection",
        json={
            "version_id": seeded.directions_version_id,
            "direction_id": seeded.direction_ids[0],
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Completed project cannot accept stage decisions",
    }
    assert dispatched_stage_run_ids == []
    state_payload = state_response.json()
    assert state_payload["project"]["status"] == "COMPLETED"
    assert state_payload["current_stage"] == "IP"


def test_legacy_direction_selection_conflicting_selection_returns_409(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    endpoint = f"/api/v1/stage-runs/{seeded.directions_run_id}/direction-selection"
    first_payload = {
        "version_id": seeded.directions_version_id,
        "direction_id": seeded.direction_ids[0],
    }
    conflicting_payload = {
        "version_id": seeded.directions_version_id,
        "direction_id": seeded.direction_ids[1],
    }

    assert client.post(endpoint, json=first_payload).status_code == 202
    response = client.post(endpoint, json=conflicting_payload)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This Directions version already has another selection",
    }


@pytest.mark.parametrize("action", ["redo", "skip", "generate"])
def test_stage_control_missing_project_returns_404(api_client, action: str) -> None:
    client, _ = api_client

    response = client.post(f"/api/v1/projects/{uuid4()}/stages/directions/{action}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.parametrize("action", ["redo", "skip", "generate"])
def test_stage_control_invalid_stage_returns_422(api_client, action: str) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/nope/{action}")

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid stage key: nope"}


@pytest.mark.parametrize(
    ("stage_key", "stage"),
    [
        ("intake", "INTAKE"),
        ("directions", "DIRECTIONS"),
        ("logo", "LOGO"),
        ("ip", "IP"),
    ],
)
@pytest.mark.parametrize("action", ["skip", "generate"])
def test_stage_control_supported_stage_returns_current_milestone_error(
    api_client,
    stage_key: str,
    stage: str,
    action: str,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    source_version_id = (
        seeded.directions_version_id
        if stage == "DIRECTIONS"
        else asyncio.run(
            seed_stage_version(
                session_factory,
                project_id=seeded.project_id,
                stage=stage,
            ),
        )
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/{stage_key}/{action}",
        json={
            "source_version_id": source_version_id,
            "reason": "try another option",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            f"{action.upper()} is not supported for {stage}; "
            "the current flow runs IP automatically after Logo"
        ),
    }


@pytest.mark.parametrize(
    "action",
    [
        "skip",
        "generate",
    ],
)
def test_ip_stage_control_missing_source_version_returns_404(
    api_client,
    action: str,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/{action}",
        json={
            "source_version_id": str(uuid4()),
            "reason": "client sent an unsupported field",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage version not found"}


def test_stage_redo_requires_source_version(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/directions/redo")

    assert response.status_code == 409
    assert response.json() == {"detail": "REDO requires source_version_id"}


@pytest.mark.parametrize(
    ("stage_key", "stage"),
    [
        ("logo", "LOGO"),
        ("ip", "IP"),
    ],
)
def test_stage_redo_later_stages_requires_upstream_references(
    api_client,
    stage_key: str,
    stage: str,
) -> None:
    """LOGO/IP redo seeds upstream state from the version's input_refs; a
    version without those references is rejected instead of replayed."""

    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    source_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage=stage,
        ),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/{stage_key}/redo",
        json={
            "source_version_id": source_version_id,
            "reason": "try another output",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": f"{stage} version is missing upstream references",
    }


def test_intake_redo_dispatches_new_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_succeeded_intake_project(session_factory))
    stale_directions_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="DIRECTIONS",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/intake/redo",
        json={
            "source_version_id": seeded.intake_version_id,
            "reason": "intake answers changed",
        },
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/intake/redo",
        json={
            "source_version_id": seeded.intake_version_id,
            "reason": "intake answers changed",
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    intake_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/intake/versions",
    )
    directions_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/versions",
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload == {
        "project_id": seeded.project_id,
        "stage": "INTAKE",
        "action": "REDO",
        "status": "QUEUED",
    }
    assert repeated_payload == first_payload

    state_payload = state_response.json()
    assert state_response.status_code == 200
    assert dispatched_stage_run_ids == [state_payload["stage_runs"]["INTAKE"]["id"]]
    assert state_payload["current_stage"] == "INTAKE"
    assert state_payload["project"]["status"] == "ACTIVE"
    assert state_payload["stage_runs"]["INTAKE"]["status"] == "QUEUED"
    assert state_payload["versions"]["INTAKE"]["id"] == seeded.intake_version_id
    assert state_payload["versions"]["INTAKE"]["status"] == "STALE"
    assert state_payload["versions"]["DIRECTIONS"]["id"] == stale_directions_version_id
    assert state_payload["versions"]["DIRECTIONS"]["status"] == "STALE"
    assert state_payload["decisions"][0]["stage"] == "INTAKE"
    assert state_payload["decisions"][0]["action"] == "REDO"
    assert state_payload["decisions"][0]["source_version_id"] == seeded.intake_version_id
    assert state_payload["decisions"][0]["payload"] == {
        "source_version_id": seeded.intake_version_id,
        "reason": "intake answers changed",
    }

    intake_versions_payload = intake_versions_response.json()
    directions_versions_payload = directions_versions_response.json()
    assert intake_versions_response.status_code == 200
    assert intake_versions_payload[0]["id"] == seeded.intake_version_id
    assert intake_versions_payload[0]["status"] == "STALE"
    assert directions_versions_response.status_code == 200
    assert directions_versions_payload[0]["id"] == stale_directions_version_id
    assert directions_versions_payload[0]["status"] == "STALE"


def test_directions_redo_dispatches_new_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    stale_logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/redo",
        json={
            "source_version_id": seeded.directions_version_id,
            "reason": "directions need another pass",
        },
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/redo",
        json={
            "source_version_id": seeded.directions_version_id,
            "reason": "directions need another pass",
        },
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")
    directions_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/versions",
    )
    logo_versions_response = client.get(
        f"/api/v1/projects/{seeded.project_id}/stages/logo/versions",
    )

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload == {
        "project_id": seeded.project_id,
        "stage": "DIRECTIONS",
        "action": "REDO",
        "status": "QUEUED",
    }
    assert repeated_payload == first_payload

    state_payload = state_response.json()
    assert state_response.status_code == 200
    assert dispatched_stage_run_ids == [state_payload["stage_runs"]["DIRECTIONS"]["id"]]
    assert state_payload["current_stage"] == "DIRECTIONS"
    assert state_payload["project"]["status"] == "ACTIVE"
    assert state_payload["stage_runs"]["DIRECTIONS"]["status"] == "QUEUED"
    assert state_payload["versions"]["DIRECTIONS"]["id"] == seeded.directions_version_id
    assert state_payload["versions"]["DIRECTIONS"]["status"] == "STALE"
    assert state_payload["versions"]["LOGO"]["id"] == stale_logo_version_id
    assert state_payload["versions"]["LOGO"]["status"] == "STALE"
    assert state_payload["decisions"][0]["stage"] == "DIRECTIONS"
    assert state_payload["decisions"][0]["action"] == "REDO"
    assert state_payload["decisions"][0]["source_version_id"] == seeded.directions_version_id
    assert state_payload["decisions"][0]["payload"] == {
        "source_version_id": seeded.directions_version_id,
        "reason": "directions need another pass",
    }

    directions_versions_payload = directions_versions_response.json()
    logo_versions_payload = logo_versions_response.json()
    assert directions_versions_response.status_code == 200
    assert directions_versions_payload[0]["id"] == seeded.directions_version_id
    assert directions_versions_payload[0]["status"] == "STALE"
    assert logo_versions_response.status_code == 200
    assert logo_versions_payload[0]["id"] == stale_logo_version_id
    assert logo_versions_payload[0]["status"] == "STALE"


@pytest.mark.skip(reason="旧 IP skip 控制已移除，新流程自动生成 IP")
def test_ip_skip_dispatches_materials_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_choice_project(session_factory))
    stale_materials_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="MATERIALS",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/skip",
        json={"reason": "no mascot needed"},
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/skip",
        json={"reason": "no mascot needed"},
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload == {
        "project_id": seeded.project_id,
        "stage": "MATERIALS",
        "action": "SKIP",
        "status": "QUEUED",
    }
    assert repeated_payload == first_payload
    assert dispatched_stage_run_ids == [state_response.json()["stage_runs"]["MATERIALS"]["id"]]

    state_payload = state_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "MATERIALS"
    assert state_payload["stage_runs"]["IP"]["status"] == "WAITING_USER"
    assert state_payload["stage_runs"]["MATERIALS"]["status"] == "QUEUED"
    assert state_payload["versions"]["MATERIALS"]["id"] == stale_materials_version_id
    assert state_payload["versions"]["MATERIALS"]["status"] == "STALE"
    assert state_payload["decisions"][0]["stage"] == "IP"
    assert state_payload["decisions"][0]["action"] == "SKIP"
    assert state_payload["decisions"][0]["source_version_id"] == seeded.vi_version_id


@pytest.mark.skip(reason="旧 IP skip 控制已移除，新流程自动生成 IP")
def test_ip_skip_without_waiting_choice_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/ip/skip")

    assert response.status_code == 409
    assert response.json() == {"detail": "No waiting IP choice found"}


@pytest.mark.skip(reason="旧 IP choice 控制已移除，新流程自动生成 IP")
@pytest.mark.parametrize("action", ["skip", "generate"])
def test_ip_choice_control_rejects_stale_source_vi_version(
    api_client,
    monkeypatch,
    action: str,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_choice_project(session_factory))
    asyncio.run(mark_stage_version_stale(session_factory, version_id=seeded.vi_version_id))
    dispatched_stage_run_ids: list[str] = []

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", dispatched_stage_run_ids.append)

    response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/ip/{action}")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Only a generated VI version can choose IP handling",
    }
    assert dispatched_stage_run_ids == []


@pytest.mark.skip(reason="旧 IP generate 控制已移除，Logo 选择后自动生成 IP")
def test_ip_generate_dispatches_ip_run_and_is_idempotent(
    api_client,
    monkeypatch,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_choice_project(session_factory))
    stale_ip_version_id = asyncio.run(
        seed_stage_version(
            session_factory,
            project_id=seeded.project_id,
            stage="IP",
        ),
    )
    dispatched_stage_run_ids: list[str] = []

    def fake_delay(stage_run_id: str) -> None:
        dispatched_stage_run_ids.append(stage_run_id)

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", fake_delay)

    first_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/generate",
        json={"reason": "mascot will help the brand"},
    )
    repeated_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/generate",
        json={"reason": "mascot will help the brand"},
    )
    state_response = client.get(f"/api/v1/projects/{seeded.project_id}/state")

    assert first_response.status_code == 202
    assert repeated_response.status_code == 202
    first_payload = first_response.json()
    repeated_payload = repeated_response.json()
    assert first_payload == {
        "project_id": seeded.project_id,
        "stage": "IP",
        "action": "GENERATE",
        "status": "QUEUED",
    }
    assert repeated_payload == first_payload
    assert dispatched_stage_run_ids == [state_response.json()["stage_runs"]["IP"]["id"]]

    state_payload = state_response.json()
    assert state_response.status_code == 200
    assert state_payload["current_stage"] == "IP"
    assert state_payload["stage_runs"]["IP"]["status"] == "QUEUED"
    assert state_payload["versions"]["IP"]["id"] == stale_ip_version_id
    assert state_payload["versions"]["IP"]["status"] == "STALE"
    assert state_payload["decisions"][0]["stage"] == "IP"
    assert state_payload["decisions"][0]["action"] == "GENERATE"
    assert state_payload["decisions"][0]["source_version_id"] == seeded.vi_version_id


@pytest.mark.skip(reason="旧 IP generate 控制已移除，Logo 选择后自动生成 IP")
def test_ip_generate_without_waiting_choice_returns_409(api_client) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/ip/generate")

    assert response.status_code == 409
    assert response.json() == {"detail": "No waiting IP choice found"}


@pytest.mark.skip(reason="旧 IP skip/generate 控制已移除，新流程自动生成 IP")
def test_ip_generate_after_skip_returns_409(api_client, monkeypatch) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_ip_choice_project(session_factory))

    from apps.api.app import tasks

    monkeypatch.setattr(tasks.execute_agent_stage, "delay", lambda _: None)

    skip_response = client.post(f"/api/v1/projects/{seeded.project_id}/stages/ip/skip")
    generate_response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/ip/generate",
    )

    assert skip_response.status_code == 202
    assert generate_response.status_code == 409
    assert generate_response.json() == {"detail": "IP choice already has another action"}


@pytest.mark.parametrize("action", ["redo", "skip", "generate"])
def test_stage_control_missing_source_version_returns_404(api_client, action: str) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/{action}",
        json={
            "source_version_id": str(uuid4()),
            "reason": "version disappeared",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage version not found"}


@pytest.mark.parametrize("action", ["redo", "skip", "generate"])
def test_stage_control_foreign_source_version_returns_404(api_client, action: str) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    other_project = asyncio.run(seed_directions_project(session_factory))

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/{action}",
        json={
            "source_version_id": other_project.directions_version_id,
            "reason": "wrong project",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Stage version not found"}


@pytest.mark.parametrize("action", ["redo", "skip", "generate"])
def test_stage_control_mismatched_source_version_returns_409(
    api_client,
    action: str,
) -> None:
    client, session_factory = api_client
    seeded = asyncio.run(seed_directions_project(session_factory))
    logo_version_id = asyncio.run(
        seed_logo_version(session_factory, project_id=seeded.project_id),
    )

    response = client.post(
        f"/api/v1/projects/{seeded.project_id}/stages/directions/{action}",
        json={
            "source_version_id": logo_version_id,
            "reason": "wrong stage",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Stage version does not belong to requested stage",
    }
