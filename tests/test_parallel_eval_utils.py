import asyncio
import pytest

from src.wis.parallel_eval_utils import (
    is_retryable_error,
    is_token_or_rate_limit_error,
    with_exponential_backoff,
)


class RetryableError(Exception):
    pass


class NonRetryableError(Exception):
    pass


def test_with_exponential_backoff_retries_then_succeeds(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        "src.wis.parallel_eval_utils.random.uniform", lambda _a, _b: 1.0
    )

    attempts = {"count": 0}

    async def flaky_operation():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableError("429 rate limit")
        return "ok"

    result = asyncio.run(
        with_exponential_backoff(
            op_name="test_op",
            row_idx=7,
            operation=flaky_operation,
            max_retries=5,
            initial_backoff_seconds=1.0,
            max_backoff_seconds=30.0,
            retryable_exception_types=(RetryableError,),
        )
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 2.0]


def test_with_exponential_backoff_raises_non_retryable(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def bad_operation():
        raise NonRetryableError("some unrelated failure")

    with pytest.raises(NonRetryableError):
        asyncio.run(
            with_exponential_backoff(
                op_name="test_op",
                row_idx=1,
                operation=bad_operation,
                max_retries=5,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=30.0,
                retryable_exception_types=(RetryableError,),
            )
        )

    assert sleep_calls == []


def test_with_exponential_backoff_exhausts_max_retries(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        "src.wis.parallel_eval_utils.random.uniform", lambda _a, _b: 1.0
    )

    async def always_fails():
        raise RetryableError("429 rate limit")

    with pytest.raises(RetryableError):
        asyncio.run(
            with_exponential_backoff(
                op_name="test_op",
                row_idx=3,
                operation=always_fails,
                max_retries=3,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=30.0,
                retryable_exception_types=(RetryableError,),
            )
        )

    # 3 retries → 3 sleep calls (after attempts 0, 1, 2; attempt 3 raises)
    assert len(sleep_calls) == 3


def test_is_token_or_rate_limit_error_matches_common_messages():
    assert is_token_or_rate_limit_error(Exception("429 Too Many Requests"))
    assert is_token_or_rate_limit_error(Exception("maximum context length exceeded"))
    assert is_token_or_rate_limit_error(Exception("tokens per minute exceeded"))
    assert not is_token_or_rate_limit_error(Exception("file not found"))


def test_is_retryable_error_with_types_or_token_messages():
    assert is_retryable_error(RetryableError("temporary outage"), (RetryableError,))
    assert is_retryable_error(
        NonRetryableError("429 too many requests"), (RetryableError,)
    )
    assert not is_retryable_error(
        NonRetryableError("validation failed"), (RetryableError,)
    )
