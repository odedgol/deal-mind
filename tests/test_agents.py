from cato_deal_intel.agents.core import (
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from cato_deal_intel.llm.fake_provider import FakeLLMProvider


def test_each_agent_exposes_only_its_declared_tools() -> None:
    deal_context = DealContextAgent()
    conversation = ConversationIntelligenceAgent(FakeLLMProvider())
    stakeholders = StakeholderMapAgent(FakeLLMProvider())
    strategy = NegotiationStrategyAgent(FakeLLMProvider())

    assert deal_context.name == "Deal Context Agent"
    assert conversation.name == "Conversation Intelligence Agent"
    assert stakeholders.name == "Stakeholder Map Agent"
    assert strategy.name == "Negotiation Strategy Agent"
    assert [tool.name for tool in deal_context.tools] == ["get_opportunity_snapshot"]
    assert [tool.name for tool in conversation.tools] == ["search_authorized_evidence"]
    assert [tool.name for tool in stakeholders.tools] == ["search_authorized_evidence"]
    assert [tool.name for tool in strategy.tools] == [
        "get_deal_desk_policy",
        "validate_recommendation",
        "request_approval",
    ]
