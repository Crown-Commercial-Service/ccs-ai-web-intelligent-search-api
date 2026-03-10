import asyncio
import random
from typing import Any, Awaitable, Callable, Iterable, Type


def is_token_or_rate_limit_error(error: Exception) -> bool:
    """Detect token/rate-limit rejection messages for explicit reporting."""
    message = str(error).lower()
    keywords = (
        "rate limit",
        "429",
        "too many requests",
        "tokens per minute",
        "requests per minute",
        "context_length_exceeded",
        "maximum context length",
        "too many tokens",
    )
    return any(keyword in message for keyword in keywords)


def is_retryable_error(
    error: Exception, retryable_exception_types: Iterable[Type[BaseException]]
) -> bool:
    """Retry transient API failures and throttling/token-limit responses."""
    if isinstance(error, tuple(retryable_exception_types)):
        return True
    return is_token_or_rate_limit_error(error)


async def with_exponential_backoff(
    op_name: str,
    row_idx: int,
    operation: Callable[[], Awaitable[object]],
    max_retries: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    retryable_exception_types: Iterable[Type[BaseException]],
) -> Any:
    """Run operation with jittered exponential backoff for retryable errors."""
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as error:
            can_retry = is_retryable_error(error, retryable_exception_types)
            if not can_retry or attempt >= max_retries:
                raise

            backoff_seconds = min(
                max_backoff_seconds, initial_backoff_seconds * (2**attempt)
            )
            jittered = backoff_seconds * random.uniform(0.8, 1.2)
            print(
                f"Retrying {op_name} for row {row_idx} in {jittered:.2f}s "
                f"(attempt {attempt + 1}/{max_retries}) due to: {error}"
            )
            await asyncio.sleep(jittered)
