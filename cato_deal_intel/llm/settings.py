import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..models import CostSummary
from .budget import BudgetLedger, CostController
from .protocols import LLMProvider, RetryConfig

load_dotenv()


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


def configured_llm() -> LLMProvider:
    if os.getenv("CATO_FAKE_LLM") == "1":
        from .fake_provider import FakeLLMProvider

        return FakeLLMProvider()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY or CATO_FAKE_LLM=1 for deterministic tests.")
    from .providers import OpenAIProvider

    return OpenAIProvider()


def usage_summary(adapter: LLMProvider) -> CostSummary:
    controller = getattr(adapter, "cost_controller", None)
    return controller.summary() if isinstance(controller, CostController) else CostSummary()


def evidence_payload(evidence: Iterable[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in evidence]


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
