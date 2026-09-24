from cato_deal_intel.agents import (
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from cato_deal_intel.llm import FakeLLM


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
