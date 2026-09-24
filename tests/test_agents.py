import time
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from cato_deal_intel.agent_runner import AgentRunner
from cato_deal_intel.agents import (
    AgentContext,
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from cato_deal_intel.data import SourceData
from cato_deal_intel.llm import FakeLLM, LLMAdapter


def test_each_agent_exposes_only_its_declared_tools() -> None:
    deal_context = DealContextAgent()
    conversation = ConversationIntelligenceAgent(FakeLLM())
    stakeholders = StakeholderMapAgent(FakeLLM())
    strategy = NegotiationStrategyAgent(FakeLLM())

    assert deal_context.name == "Deal Context Agent"
    assert conversation.name == "Conversation Intelligence Agent"
    assert stakeholders.name == "Stakeholder Map Agent"
    assert strategy.name == "Negotiation Strategy Agent"
    assert deal_context.tools
    assert conversation.tools
    assert stakeholders.tools
    assert strategy.tools


def test_specialist_agents_run_in_parallel() -> None:
    class SlowFakeLLM(FakeLLM):
        def complete(  # type: ignore[override]
            self,
            *,
            system: str,
            user: str,
            output_type: type[BaseModel],
        ) -> BaseModel:
            time.sleep(0.1)
            return super().complete(system=system, user=user, output_type=output_type)

    source = SourceData(Path(__file__).parents[1] / "synthetic_data")
    opportunity = source.opportunities()[0]
    started = time.perf_counter()

    AgentRunner(cast(LLMAdapter, SlowFakeLLM())).run(
        AgentContext(opportunity, []), "parallel-test"
    )

    elapsed = time.perf_counter() - started
    assert elapsed < 0.28
