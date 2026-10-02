from datetime import date

from cato_deal_intel.agents.core import (
    ConversationIntelligenceAgent,
    DealContextAgent,
    DealContextTool,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from cato_deal_intel.llm.fake_provider import FakeLLMProvider
from cato_deal_intel.models import Opportunity


def test_each_agent_exposes_only_its_declared_tools() -> None:
    deal_context = DealContextAgent(DealContextTool(sample_opportunity()))
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

def sample_opportunity() -> Opportunity:
    return Opportunity(
        opportunity_id="OPP-TEST",
        opportunity_name="Test opportunity",
        account_id="ACC-TEST",
        account_name="Test account",
        stage="Negotiation",
        type="New Business",
        region="EMEA",
        country="Israel",
        industry="Technology",
        owner="Test Owner",
        close_date=date(2026, 12, 31),
        acv=100_000,
        tcv=300_000,
        renewal_term_months=36,
        probability=60,
        forecast_category="Best Case",
        next_step="Confirm requirements",
        primary_competitor="Competitor",
        risk_level="Medium",
        approval_required=False,
        restricted_access=False,
    )
