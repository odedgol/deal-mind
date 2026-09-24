from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from .agents import (
    AgentContext,
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from .llm import LLMAdapter
from .models import AgentOutput, AgentTrace, DealSnapshot, StrategyOutput
from .observability import observability_enabled
from .tools import (
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    RecommendationValidationTool,
)

T = TypeVar("T", AgentOutput, StrategyOutput)


@dataclass(frozen=True)
class AgentRun:
    deal_snapshot: DealSnapshot
    conversation: AgentOutput
    stakeholders: AgentOutput
    strategy: StrategyOutput
    traces: list[AgentTrace]


class AgentRunner:
    """Runs the agents and returns their typed outputs as one application result."""

    def __init__(
        self,
        llm: LLMAdapter,
        *,
        deal_context_tool: DealContextTool | None = None,
        search_tool: AuthorizedEvidenceSearchTool | None = None,
        recommendation_validator: RecommendationValidationTool | None = None,
    ) -> None:
        self.deal_context = DealContextAgent(deal_context_tool)
        self.conversation = ConversationIntelligenceAgent(llm, search_tool)
        self.stakeholders = StakeholderMapAgent(llm, search_tool)
        self.strategy = NegotiationStrategyAgent(llm, recommendation_validator)

    def run(self, context: AgentContext, run_id: str) -> AgentRun:
        traces: list[AgentTrace] = []
        deal_snapshot = self.deal_context.run(context)
        conversation = self._run_agent_output(
            run_id,
            "Conversation Intelligence Agent",
            lambda: self.conversation.run(context),
            traces,
        )
        stakeholders = self._run_agent_output(
            run_id,
            "Stakeholder Map Agent",
            lambda: self.stakeholders.run(context),
            traces,
        )
        strategy = self._run_strategy(
            run_id,
            lambda: self.strategy.run(context, [conversation, stakeholders]),
            traces,
        )
        return AgentRun(deal_snapshot, conversation, stakeholders, strategy, traces)

    def _run_agent_output(
        self,
        run_id: str,
        name: str,
        call: Callable[[], AgentOutput],
        traces: list[AgentTrace],
    ) -> AgentOutput:
        return self._run_with_trace(run_id, name, call, traces)

    def _run_strategy(
        self,
        run_id: str,
        call: Callable[[], StrategyOutput],
        traces: list[AgentTrace],
    ) -> StrategyOutput:
        return self._run_with_trace(run_id, "Negotiation Strategy Agent", call, traces)

    def _run_with_trace(
        self,
        run_id: str,
        name: str,
        call: Callable[[], T],
        traces: list[AgentTrace],
    ) -> T:
        started = datetime.now(UTC)
        try:
            output = call()
        except Exception as error:
            self._record_trace(
                traces,
                AgentTrace(
                    run_id=run_id,
                    agent_name=name,
                    prompt_version="v1",
                    status="failed",
                    started_at=started,
                    completed_at=datetime.now(UTC),
                    error=str(error),
                ),
            )
            raise
        self._record_trace(
            traces,
            AgentTrace(
                run_id=run_id,
                agent_name=name,
                prompt_version="v1",
                status="completed",
                started_at=started,
                completed_at=datetime.now(UTC),
            ),
        )
        return output

    @staticmethod
    def _record_trace(traces: list[AgentTrace], trace: AgentTrace) -> None:
        if observability_enabled():
            traces.append(trace)
