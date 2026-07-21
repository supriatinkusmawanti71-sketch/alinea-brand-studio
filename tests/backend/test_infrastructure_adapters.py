from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agents.ports import (
    InvocationStatus,
    ModelInvocationRecord,
)
from backend.application.projects import CreateProjectCommand, create_project
from backend.infrastructure.database.invocations import SqlAlchemyInvocationRecorder
from backend.infrastructure.database.models import Artifact, Base, ModelInvocation
from backend.infrastructure.storage.s3_artifacts import S3ArtifactWriter
from backend.providers.models.base import GeneratedImage, ModelCapability


class FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []
        self.deletes: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.puts.append(kwargs)

    def delete_object(self, **kwargs: Any) -> None:
        self.deletes.append(kwargs)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def create_project_run(session):
    _, stage_run, _ = await create_project(
        session,
        CreateProjectCommand(
            workspace_id="workspace-one",
            actor_id="developer-two",
            name="适配器测试品牌",
            requirement_text=None,
            structured_fields={},
            reference_artifact_ids=[],
        ),
    )
    return stage_run


@pytest.mark.asyncio
async def test_s3_artifact_writer_stores_metadata_and_discards_object(session) -> None:
    stage_run = await create_project_run(session)
    client = FakeS3Client()
    writer = S3ArtifactWriter(
        session,
        workspace_id="workspace-one",
        project_id=stage_run.project_id,
        stage_run_id=stage_run.id,
        bucket="private-assets",
        endpoint_url="http://minio:9000",
        access_key_id="test",
        secret_access_key="test-secret",
        region="us-east-1",
        use_ssl=False,
        client=client,
    )
    image = GeneratedImage(
        provider="fake",
        model="fake-image-v1",
        content=b"fake-png-content",
        mime_type="image/png",
        width=1024,
        height=1024,
        provider_request_id="provider-image-1",
        latency_ms=12,
    )

    stored = writer.store_generated_image(request_id="image-request-1", image=image)
    await session.flush()
    artifact = await session.get(Artifact, str(stored.artifact_id))

    assert stored.size_bytes == len(image.content)
    assert artifact is not None
    assert artifact.workspace_id == "workspace-one"
    assert artifact.stage_run_id == stage_run.id
    assert artifact.status == "STORED"
    assert artifact.mime_type == "image/png"
    assert artifact.width == 1024
    assert len(artifact.sha256) == 64
    assert client.puts[0]["Bucket"] == "private-assets"
    assert client.puts[0]["Key"] == artifact.object_key
    assert "workspace-one" not in artifact.object_key

    writer.discard_temporary_artifacts([stored.artifact_id])

    assert artifact.status == "DISCARDED"
    assert client.deletes == [{"Bucket": "private-assets", "Key": artifact.object_key}]


@pytest.mark.asyncio
async def test_invocation_recorder_uses_caller_transaction(session) -> None:
    stage_run = await create_project_run(session)
    recorder = SqlAlchemyInvocationRecorder(session, stage_run_id=stage_run.id)

    recorder.record_model_invocation(
        ModelInvocationRecord(
            request_id="directions-image-1",
            capability=ModelCapability.DIRECTIONS,
            prompt_version="directions-image-v1",
            provider="fake",
            model="fake-image-v1",
            status=InvocationStatus.SUCCEEDED,
            image_count=1,
            latency_ms=25,
        )
    )
    await session.flush()
    recorded = await session.scalar(
        select(ModelInvocation).where(ModelInvocation.stage_run_id == stage_run.id)
    )

    assert recorded is not None
    assert recorded.status == "SUCCEEDED"
    assert recorded.usage_json["image_count"] == 1
