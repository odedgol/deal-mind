import pytest
from httpx import Request
from openai import APITimeoutError

from cato_deal_intel.llm import RetryConfig, _retry_call


def test_retry_call_retries_transient_timeout_with_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise APITimeoutError(request=Request("POST", "https://api.openai.com"))
        return "ok"

    result = _retry_call(
        operation,
        config=RetryConfig(max_retries=2, backoff_seconds=0.5),
        sleep_function=delays.append,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_retry_call_does_not_retry_non_transient_errors() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise ValueError("malformed structured output")

    with pytest.raises(ValueError, match="malformed structured output"):
        _retry_call(operation, config=RetryConfig(max_retries=2))

    assert attempts == 1
