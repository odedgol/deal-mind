import logging
from collections.abc import Callable
from time import sleep
from typing import TypeVar

from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from .protocols import RetryConfig

T = TypeVar("T")
LOGGER = logging.getLogger("cato_deal_intel")
RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)


def retry_call[T](
    operation: Callable[[], T],
    *,
    config: RetryConfig,
    sleep_function: Callable[[float], None] = sleep,
) -> T:
    for attempt in range(config.max_retries + 1):
        try:
            return operation()
        except RETRYABLE_ERRORS as error:
            if attempt >= config.max_retries:
                raise
            delay = config.backoff_seconds * (2**attempt)
            LOGGER.warning(
                "llm.retry attempt=%s next_attempt=%s error=%s delay_seconds=%s",
                attempt + 1,
                attempt + 2,
                type(error).__name__,
                delay,
            )
            sleep_function(delay)
    raise RuntimeError("Retry loop exited unexpectedly")
