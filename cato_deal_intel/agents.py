import json
from dataclasses import dataclass

from .llm import LLMAdapter, evidence_payload
from .models import AgentOutput, DealSnapshot, EvidenceItem, Opportunity, StrategyOutput
from .observability import observed
from .tools import (
    CONVERSATION_TOOLS,
    DEAL_CONTEXT_TOOLS,
    STAKEHOLDER_TOOLS,
    STRATEGY_TOOLS,
    ToolSpec,
)


@dataclass(frozen=True)
class AgentContext:
    opportunity: Opportunity
    evidence: list[EvidenceItem]


class DealContextAgent:
    name = "Deal Context Agent"
    tools: tuple[ToolSpec, ...] = DEAL_CONTEXT_TOOLS

    def run(self, context: AgentContext) -> DealSnapshot:
        return run_deal_context(context)


class ConversationIntelligenceAgent:
    name = "Conversation Intelligence Agent"
    tools: tuple[ToolSpec, ...] = CONVERSATION_TOOLS

    def __init__(self, llm: LLMAdapter) -> None:
        self.llm = llm

    def run(self, context: AgentContext) -> AgentOutput:
        return run_conversation_intelligence(context, self.llm)


class StakeholderMapAgent:
    name = "Stakeholder Map Agent"
    tools: tuple[ToolSpec, ...] = STAKEHOLDER_TOOLS

    def __init__(self, llm: LLMAdapter) -> None:
        self.llm = llm

    def run(self, context: AgentContext) -> AgentOutput:
        return run_stakeholder_map(context, self.llm)


class NegotiationStrategyAgent:
    name = "Negotiation Strategy Agent"
    tools: tuple[ToolSpec, ...] = STRATEGY_TOOLS

    def __init__(self, llm: LLMAdapter) -> None:
        self.llm = llm

    def run(self, context: AgentContext, specialists: list[AgentOutput]) -> StrategyOutput:
        return run_strategy(context, specialists, self.llm)


@observed(agent_name="deal_context", prompt_version="v1")
def run_deal_context(context: AgentContext) -> DealSnapshot:
    opportunity = context.opportunity
    ids = [item.evidence_id for item in context.evidence if item.source_type == "salesforce"]
    return DealSnapshot(
        opportunity_id=opportunity.opportunity_id,
        account_name=opportunity.account_name,
        stage=opportunity.stage,
        amount_acv=opportunity.acv,
        close_date=opportunity.close_date,
        owner=opportunity.owner,
        risk_level=opportunity.risk_level,
        evidence_ids=ids[:5],
    )


@observed(agent_name="conversation_intelligence", prompt_version="v1")
def run_conversation_intelligence(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Conversation Intelligence Agent", context, llm)


@observed(agent_name="stakeholder_map", prompt_version="v1")
def run_stakeholder_map(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Stakeholder Map Agent", context, llm)


def run_buyer_goals(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Buyer Goals Agent", context, llm)


@observed(agent_name="negotiation_strategy", prompt_version="v1")
def run_strategy(
    context: AgentContext,
    specialists: list[AgentOutput],
    llm: LLMAdapter,
) -> StrategyOutput:
    prompt = {
        "opportunity": context.opportunity.model_dump(mode="json"),
        "evidence": evidence_payload(context.evidence),
        "specialists": [output.model_dump(mode="json") for output in specialists],
    }
    return llm.complete(
        system=(
            "You are the Negotiation Strategy Agent. Return only grounded, typed recommendations."
        ),
        user=json.dumps(prompt),
        output_type=StrategyOutput,
    )


def _run_specialist(name: str, context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    prompt = {
        "agent": name,
        "opportunity": context.opportunity.model_dump(mode="json"),
        "evidence": evidence_payload(context.evidence),
    }
    return llm.complete(
        system=f"You are the {name}. Cite only evidence IDs supplied in the input.",
        user=json.dumps(prompt),
        output_type=AgentOutput,
    )
