from apps.api.app.tasks import _auto_stage_retry_delay, _is_retryable_stage_error


def test_auto_stage_retry_delay_is_bounded() -> None:
    assert _auto_stage_retry_delay(0) == 60
    assert _auto_stage_retry_delay(1) == 180
    assert _auto_stage_retry_delay(2) == 300
    assert _auto_stage_retry_delay(3) is None
    assert _auto_stage_retry_delay(-1) is None


def test_retryable_stage_error_detection() -> None:
    retryable_error = RuntimeError("temporary overload")
    retryable_error.retryable = True  # type: ignore[attr-defined]

    permanent_error = RuntimeError("bad request")

    assert _is_retryable_stage_error(retryable_error) is True
    assert _is_retryable_stage_error(permanent_error) is False
