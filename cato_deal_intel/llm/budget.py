import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import CostSummary
from .protocols import UsageSnapshot


class LLMBudgetExceeded(RuntimeError):
    """Raised when a run exceeds its configured model budget."""


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
