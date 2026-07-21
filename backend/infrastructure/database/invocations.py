from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.ports import ModelInvocationRecord
from backend.infrastructure.database.models import ModelInvocation


class SqlAlchemyInvocationRecorder:
    """Attach model audit rows to the caller's existing business transaction."""

    def __init__(self, session: AsyncSession, *, stage_run_id: str) -> None:
        self._session = session
        self._stage_run_id = stage_run_id
        self._records: list[ModelInvocationRecord] = []

    def record_model_invocation(self, record: ModelInvocationRecord) -> None:
        self._records.append(record)
        self._session.add(self._build_model(record))

    def restore_after_rollback(self) -> None:
        for record in self._records:
            self._session.add(self._build_model(record))

    def _build_model(self, record: ModelInvocationRecord) -> ModelInvocation:
        return ModelInvocation(
            stage_run_id=self._stage_run_id,
            request_id=record.request_id,
            capability=record.capability.value,
            provider=record.provider,
            model=record.model,
            prompt_version=record.prompt_version,
            status=record.status.value,
            usage_json={
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "image_count": record.image_count,
            },
            latency_ms=record.latency_ms,
            error_code=record.error_code,
        )
