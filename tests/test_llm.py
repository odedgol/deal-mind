import pytest
from httpx import Request
from openai import APITimeoutError

from cato_deal_intel.llm import (
    BudgetLedger,
    CostController,
    LLMBudgetExceeded,
    RetryConfig,
    _retry_call,
)


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


def test_cost_controller_tracks_tokens_and_enforces_budget() -> None:
    controller = CostController(
        budget_usd=0.001,
        input_cost_per_million=1.0,
        output_cost_per_million=1.0,
    )

    snapshot = controller.record(model="test-model", prompt_tokens=400, completion_tokens=300)

    assert snapshot.cost_usd == 0.0007
    assert controller.total_prompt_tokens == 400
    assert controller.total_completion_tokens == 300
    with pytest.raises(LLMBudgetExceeded):
        controller.record(model="test-model", prompt_tokens=400, completion_tokens=700)


def test_budget_ledger_survives_new_controller(tmp_path) -> None:
    ledger_path = tmp_path / "budget.json"
    first = BudgetLedger(ledger_path)
    first.record(0.25)

    second = BudgetLedger(ledger_path)

    assert second.spent_usd == 0.25
