import json
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import Any, Protocol, TypeVar

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import BaseModel

from .models import CostSummary

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


class LLMBudgetExceeded(RuntimeError):
    """Raised when a run exceeds its configured model budget."""


@dataclass(frozen=True)
class UsageSnapshot:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class CostController:
    """Track model usage and stop subsequent calls after the configured budget."""

    def __init__(
        self,
        *,
        budget_usd: float | None = None,
        input_cost_per_million: float = 0.15,
        output_cost_per_million: float = 0.60,
        ledger: "BudgetLedger | None" = None,
    ) -> None:
        self.budget_usd = budget_usd
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.ledger = ledger
        self.total_cost_usd = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.snapshots: list[UsageSnapshot] = []

    def record(self, *, model: str, prompt_tokens: int, completion_tokens: int) -> UsageSnapshot:
        cost = (
            prompt_tokens * self.input_cost_per_million
            + completion_tokens * self.output_cost_per_million
        ) / 1_000_000
        snapshot = UsageSnapshot(model, prompt_tokens, completion_tokens, cost)
        self.snapshots.append(snapshot)
        self.total_cost_usd += cost
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        period_spent = self.ledger.record(cost) if self.ledger is not None else self.total_cost_usd
        if self.budget_usd is not None and period_spent > self.budget_usd:
            raise LLMBudgetExceeded(
                f"LLM budget exceeded: ${period_spent:.4f} > ${self.budget_usd:.4f}"
            )
        return snapshot

    def can_call(self) -> None:
        spent = self.ledger.spent_usd if self.ledger is not None else self.total_cost_usd
        if self.budget_usd is not None and spent >= self.budget_usd:
            raise LLMBudgetExceeded(f"LLM budget exhausted at ${spent:.4f}")

    def summary(self) -> CostSummary:
        spent = self.ledger.spent_usd if self.ledger is not None else self.total_cost_usd
        remaining = None if self.budget_usd is None else max(0.0, self.budget_usd - spent)
        return CostSummary(
            budget_usd=self.budget_usd,
            spent_usd=round(spent, 6),
            run_spent_usd=round(self.total_cost_usd, 6),
            remaining_usd=None if remaining is None else round(remaining, 6),
            prompt_tokens=self.total_prompt_tokens,
            completion_tokens=self.total_completion_tokens,
            call_count=len(self.snapshots),
            models=sorted({snapshot.model for snapshot in self.snapshots}),
            period_key=self.ledger.period_key if self.ledger is not None else None,
        )


class BudgetLedger:
    """Persist budget usage across requests and process restarts."""

    def __init__(self, path: Path, period: str = "month") -> None:
        self.path = path
        self.period = period
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def period_key(self) -> str:
        now = datetime.now(UTC)
        return now.strftime("%Y-%m") if self.period == "month" else now.strftime("%Y-%m-%d")

    @property
    def spent_usd(self) -> float:
        return float(self._read()["spent_usd"])

    def record(self, amount: float) -> float:
        import fcntl

        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            state = self._read()
            state["spent_usd"] += amount
            self.path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return float(state["spent_usd"])

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"period_key": self.period_key, "spent_usd": 0.0}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("period_key") != self.period_key:
            return {"period_key": self.period_key, "spent_usd": 0.0}
        return {"period_key": self.period_key, "spent_usd": float(state.get("spent_usd", 0.0))}


class FakeLLM:
    """Small deterministic adapter used by tests and offline development."""

    def __init__(self) -> None:
        self.cost_controller = configured_cost_controller()

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        del system
        payload = json.loads(_unwrap_protected_payload(user))
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
        self.specialist_model = os.getenv("CATO_LLM_SPECIALIST_MODEL", self.model)
        self.strategy_model = os.getenv("CATO_LLM_STRATEGY_MODEL", self.model)
        self.cost_controller = configured_cost_controller()

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        return _retry_call(
            lambda: self._complete_once(system, user, output_type),
            config=self.retry_config,
        )

    def _complete_once(self, system: str, user: str, output_type: type[T]) -> T:
        self.cost_controller.can_call()
        model = self._model_for(output_type)
        response = self.client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=output_type,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        usage = response.usage
        if usage is not None:
            snapshot = self.cost_controller.record(
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
            LOGGER.info(
                "llm.usage model=%s prompt_tokens=%s completion_tokens=%s "
                "cost_usd=%.6f total_cost_usd=%.6f",
                snapshot.model,
                snapshot.prompt_tokens,
                snapshot.completion_tokens,
                snapshot.cost_usd,
                self.cost_controller.total_cost_usd,
            )
        return parsed

    def _model_for(self, output_type: type[T]) -> str:
        return (
            self.strategy_model
            if output_type.__name__ == "StrategyOutput"
            else self.specialist_model
        )


def configured_retry_config() -> RetryConfig:
    return RetryConfig(
        max_retries=_env_int("CATO_LLM_MAX_RETRIES", 2),
        timeout_seconds=_env_float("CATO_LLM_TIMEOUT_SECONDS", 30.0),
        backoff_seconds=_env_float("CATO_LLM_BACKOFF_SECONDS", 0.5),
    )


def configured_cost_controller() -> CostController:
    return CostController(
        budget_usd=_optional_env_float("CATO_LLM_BUDGET_USD"),
        input_cost_per_million=_env_float("CATO_LLM_INPUT_COST_PER_1M", 0.15),
        output_cost_per_million=_env_float("CATO_LLM_OUTPUT_COST_PER_1M", 0.60),
        ledger=BudgetLedger(
            Path(os.getenv("CATO_LLM_BUDGET_LEDGER_PATH", "artifacts/llm_budget.json")),
            period=os.getenv("CATO_LLM_BUDGET_PERIOD", "month"),
        ),
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


def _optional_env_float(name: str) -> float | None:
    value = os.getenv(name)
    return None if value in {None, "", "0"} else _env_float(name, 0.0)


def configured_llm() -> LLMAdapter:
    if os.getenv("CATO_FAKE_LLM") == "1":
        return FakeLLM()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY or CATO_FAKE_LLM=1 for deterministic tests.")
    return OpenAIAdapter()


def usage_summary(adapter: LLMAdapter) -> CostSummary:
    controller = getattr(adapter, "cost_controller", None)
    return controller.summary() if isinstance(controller, CostController) else CostSummary()


def evidence_payload(evidence: Iterable[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in evidence]


def _unwrap_protected_payload(user: str) -> str:
    start = "<untrusted_data>\n"
    end = "\n</untrusted_data>"
    if user.startswith(start) and user.endswith(end):
        return user[len(start) : -len(end)]
    return user
