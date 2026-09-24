import json
from dataclasses import dataclass

from .llm import LLMAdapter, evidence_payload
from .models import AgentOutput, DealSnapshot, EvidenceItem, Opportunity, StrategyOutput


@dataclass(frozen=True)
class AgentContext:
    opportunity: Opportunity
    evidence: list[EvidenceItem]


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


def run_conversation_intelligence(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Conversation Intelligence Agent", context, llm)


def run_stakeholder_map(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Stakeholder Map Agent", context, llm)


def run_buyer_goals(context: AgentContext, llm: LLMAdapter) -> AgentOutput:
    return _run_specialist("Buyer Goals Agent", context, llm)


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
