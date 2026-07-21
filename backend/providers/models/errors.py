from __future__ import annotations

from enum import StrEnum


class ProviderErrorCode(StrEnum):
    AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    TIMEOUT = "PROVIDER_TIMEOUT"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CONTENT_REJECTED = "PROVIDER_CONTENT_REJECTED"
    COST_LIMIT = "PROVIDER_COST_LIMIT"


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: ProviderErrorCode,
        safe_message: str,
        *,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code.value
        self.safe_message = safe_message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
