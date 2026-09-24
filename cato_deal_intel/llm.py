import json
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from time import sleep
from typing import Any, Protocol, TypeVar

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
LOGGER = logging.getLogger("cato_deal_intel")
RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)

load_dotenv()


class LLMAdapter(Protocol):
    def complete(self, *, system: str, user: str, output_type: type[T]) -> T: ...


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 2
    timeout_seconds: float = 30.0
    backoff_seconds: float = 0.5


class FakeLLM:
    """Small deterministic adapter used by tests and offline development."""

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        del system
        payload = json.loads(user)
        evidence_ids = [item["evidence_id"] for item in payload.get("evidence", [])[:3]]
        if output_type.__name__ == "AgentOutput":
            result: dict[str, Any] = {
                "findings": [
                    {
                        "text": "The retrieved evidence shows an active negotiation dependency.",
                        "evidence_ids": evidence_ids,
                        "confidence": 0.82,
                    }
                ],
                "missing_information": [
                    "Confirm the final decision date with the buying committee."
                ],
            }
        else:
            result = {
                "summary": (
                    "The deal is actionable but requires owners for open buyer and "
                    "approval dependencies."
                ),
                "actions": [
                    {
                        "action": "Confirm open dependencies and document the negotiation path.",
                        "owner": "Account owner",
                        "rationale": "Open dependencies are the main remaining execution risk.",
                        "evidence_ids": evidence_ids,
                        "requires_approval": False,
                    }
                ],
                "warnings": ["Validate all customer-facing language before sharing externally."],
            }
        return output_type.model_validate(result)


class OpenAIAdapter:
    def __init__(self, model: str | None = None, retry_config: RetryConfig | None = None) -> None:
        self.retry_config = retry_config or configured_retry_config()
        self.client = OpenAI(
            timeout=self.retry_config.timeout_seconds,
            max_retries=0,
        )
        configured_model = os.getenv("CATO_LLM_MODEL")
        self.model: str = model or configured_model or "gpt-4o-mini"

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        return _retry_call(
            lambda: self._complete_once(system, user, output_type),
            config=self.retry_config,
        )

    def _complete_once(self, system: str, user: str, output_type: type[T]) -> T:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=output_type,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        return parsed


def configured_retry_config() -> RetryConfig:
    return RetryConfig(
        max_retries=_env_int("CATO_LLM_MAX_RETRIES", 2),
        timeout_seconds=_env_float("CATO_LLM_TIMEOUT_SECONDS", 30.0),
        backoff_seconds=_env_float("CATO_LLM_BACKOFF_SECONDS", 0.5),
    )


def _retry_call[T](
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


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(0, int(value))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(0.0, float(value))
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error


def configured_llm() -> LLMAdapter:
    if os.getenv("CATO_FAKE_LLM") == "1":
        return FakeLLM()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY or CATO_FAKE_LLM=1 for deterministic tests.")
    return OpenAIAdapter()


def evidence_payload(evidence: Iterable[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in evidence]
