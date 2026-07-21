import asyncio
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver

from apps.api.app.celery_app import celery_app
from backend.agents.workflow import build_brand_workflow
from backend.application.stage_runs import execute_stage_run, recover_stuck_stage_runs
from backend.infrastructure.database.invocations import SqlAlchemyInvocationRecorder
from backend.infrastructure.database.models import Project, StageRun
from backend.infrastructure.database.session import async_session_factory, engine
from backend.infrastructure.storage.reference_images import ReferenceImageResolver
from backend.infrastructure.storage.s3_artifacts import S3ArtifactWriter
from backend.providers.models.factory import build_model_providers

_AUTO_STAGE_RETRY_DELAYS_SECONDS = (60, 180, 300)
_STUCK_QUEUED_AFTER_SECONDS = 3 * 60
# Must stay above the Celery task_time_limit so a run this old cannot still be
# executing on a healthy worker.
_STUCK_RUNNING_AFTER_SECONDS = 35 * 60


@celery_app.task(name="dev.health_ping")
def health_ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "payload": payload or {}}


def _auto_stage_retry_delay(retry_count: int) -> int | None:
    if retry_count < 0 or retry_count >= len(_AUTO_STAGE_RETRY_DELAYS_SECONDS):
        return None
    return _AUTO_STAGE_RETRY_DELAYS_SECONDS[retry_count]


def _is_retryable_stage_error(error: Exception) -> bool:
    return bool(getattr(error, "retryable", False))


async def _mark_stage_run_auto_retry(
    stage_run_id: str,
    *,
    retry_count: int,
    delay_seconds: int,
    error: Exception,
) -> None:
    try:
        async with async_session_factory() as session:
            stage_run = await session.get(StageRun, stage_run_id)
            if stage_run is None or stage_run.status in {"SUCCEEDED", "WAITING_USER"}:
                return
            stage_run.status = "QUEUED"
            stage_run.error_code = getattr(error, "code", "STAGE_AUTO_RETRY")
            stage_run.error_message = (
                f"{str(error)[:360]}；系统将在 {delay_seconds} 秒后自动重试"
                f"（第 {retry_count + 1}/{len(_AUTO_STAGE_RETRY_DELAYS_SECONDS)} 次自动重试）。"
            )
            await session.commit()
    finally:
        # This runs in a fresh asyncio.run() loop; asyncpg connections are
        # loop-affine, so dispose the pool before the loop closes to avoid
        # leaking connections bound to a dead loop into the next task/retry.
        await engine.dispose()


async def _execute_agent_stage(stage_run_id: str) -> dict[str, Any]:
    from apps.api.app.config import get_settings

    settings = get_settings()
    reference_image_resolver = ReferenceImageResolver(
        database_conninfo=settings.database_url,
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    text_provider, image_provider = build_model_providers(
        text_provider_name=settings.text_model_provider,
        image_provider_name=settings.image_model_provider,
        reference_image_resolver=reference_image_resolver,
    )
    try:
        with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
            checkpointer.setup()
            async with async_session_factory() as session:
                queued_run = await session.get(StageRun, stage_run_id)
                if queued_run is None:
                    raise ValueError("Stage run not found")
                project = await session.get(Project, queued_run.project_id)
                if project is None:
                    raise ValueError("Project not found")
                invocation_recorder = SqlAlchemyInvocationRecorder(
                    session,
                    stage_run_id=stage_run_id,
                )
                artifact_writer = S3ArtifactWriter(
                    session,
                    workspace_id=project.workspace_id,
                    project_id=project.id,
                    stage_run_id=stage_run_id,
                    bucket=settings.s3_bucket,
                    endpoint_url=settings.s3_endpoint_url,
                    access_key_id=settings.s3_access_key_id,
                    secret_access_key=settings.s3_secret_access_key,
                    region=settings.s3_region,
                    use_ssl=settings.s3_use_ssl,
                    on_stored=reference_image_resolver.register_stored_artifact,
                )
                workflow = build_brand_workflow(
                    text_provider=text_provider,
                    image_provider=image_provider,
                    artifact_writer=artifact_writer,
                    invocation_recorder=invocation_recorder,
                    checkpointer=checkpointer,
                    interrupt_before=(
                        ("generate_directions",) if queued_run.stage == "INTAKE" else ()
                    ),
                )
                stage_run = await execute_stage_run(
                    session,
                    stage_run_id=stage_run_id,
                    workflow=workflow,
                    invocation_recorder=invocation_recorder,
                )
            return {
                "stage_run_id": stage_run.id,
                "status": stage_run.status,
                "result_version_id": stage_run.result_version_id,
            }
    finally:
        await engine.dispose()


async def _recover_stuck_stage_runs() -> list[str]:
    try:
        async with async_session_factory() as session:
            recovered = await recover_stuck_stage_runs(
                session,
                queued_stale_after_seconds=_STUCK_QUEUED_AFTER_SECONDS,
                running_stale_after_seconds=_STUCK_RUNNING_AFTER_SECONDS,
            )
            return [stage_run.id for stage_run in recovered]
    finally:
        await engine.dispose()


@celery_app.task(name="agent.recover_stuck_stage_runs")
def recover_stuck_agent_stages() -> dict[str, Any]:
    recovered_ids = asyncio.run(_recover_stuck_stage_runs())
    for stage_run_id in recovered_ids:
        execute_agent_stage.delay(stage_run_id)
    return {"recovered_stage_run_ids": recovered_ids}


@celery_app.task(bind=True, name="agent.execute_stage_run")
def execute_agent_stage(self: Any, stage_run_id: str) -> dict[str, Any]:
    try:
        return asyncio.run(_execute_agent_stage(stage_run_id))
    except Exception as error:
        delay_seconds = _auto_stage_retry_delay(self.request.retries)
        if delay_seconds is not None and _is_retryable_stage_error(error):
            asyncio.run(
                _mark_stage_run_auto_retry(
                    stage_run_id,
                    retry_count=self.request.retries,
                    delay_seconds=delay_seconds,
                    error=error,
                )
            )
            raise self.retry(exc=error, countdown=delay_seconds) from error
        raise
