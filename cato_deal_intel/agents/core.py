from dataclasses import dataclass

from ..llm.protocols import LLMProvider
from ..llm.settings import evidence_payload
from ..models import (
    AgentOutput,
    DealSnapshot,
    EvidenceItem,
    Opportunity,
    StrategyOutput,
)
from ..observability.tracing import observed
from ..security.validation import validate_citations
from .prompts import grounded_system, protected_payload
from .tools import (
    CONVERSATION_TOOLS,
    DEAL_CONTEXT_TOOLS,
    STAKEHOLDER_TOOLS,
    STRATEGY_TOOLS,
    ApprovalRequestTool,
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    DealDeskPolicyTool,
    EvidenceSearchRequest,
    RecommendationValidationTool,
    ToolSpec,
)


@dataclass(frozen=True)
class AgentContext:
    opportunity: Opportunity
    evidence: list[EvidenceItem]


class DealContextAgent:
    name = "Deal Context Agent"
    tools: tuple[ToolSpec, ...] = DEAL_CONTEXT_TOOLS

    def __init__(self, tool: DealContextTool | None = None) -> None:
        self.tool = tool

    def run(self, context: AgentContext) -> DealSnapshot:
        if self.tool is not None:
            return self.tool.run()
        return run_deal_context(context)


class ConversationIntelligenceAgent:
    name = "Conversation Intelligence Agent"
    tools: tuple[ToolSpec, ...] = CONVERSATION_TOOLS

    def __init__(
        self,
        llm: LLMProvider,
        search_tool: AuthorizedEvidenceSearchTool | None = None,
    ) -> None:
        self.llm = llm
        self.search_tool = search_tool

    def run(self, context: AgentContext) -> AgentOutput:
        context = _context_with_search_results(
            context,
            self.search_tool,
            "buyer objections urgency competitor action items",
        )
        output = run_conversation_intelligence(context, self.llm)
        return output


class StakeholderMapAgent:
    name = "Stakeholder Map Agent"
    tools: tuple[ToolSpec, ...] = STAKEHOLDER_TOOLS

    def __init__(
        self,
        llm: LLMProvider,
        search_tool: AuthorizedEvidenceSearchTool | None = None,
    ) -> None:
        self.llm = llm
        self.search_tool = search_tool

    def run(self, context: AgentContext) -> AgentOutput:
        context = _context_with_search_results(
            context,
            self.search_tool,
            "economic buyer champion procurement legal blocker stakeholder",
        )
        output = run_stakeholder_map(context, self.llm)
        return output


class NegotiationStrategyAgent:
    name = "Negotiation Strategy Agent"
    tools: tuple[ToolSpec, ...] = STRATEGY_TOOLS

    def __init__(
        self,
        llm: LLMProvider,
        validator: RecommendationValidationTool | None = None,
        policy_tool: DealDeskPolicyTool | None = None,
        approval_tool: ApprovalRequestTool | None = None,
    ) -> None:
        self.llm = llm
        self.validator = validator
        self.policy_tool = policy_tool
        self.approval_tool = approval_tool

    def run(self, context: AgentContext, specialists: list[AgentOutput]) -> StrategyOutput:
        if self.policy_tool is not None:
            policy = self.policy_tool.run()
            if policy is not None:
                context = AgentContext(context.opportunity, [*context.evidence, policy])
        output = run_strategy(context, specialists, self.llm)
        if self.approval_tool is not None:
            actions = self.approval_tool.run(context.opportunity, output.actions)
            output = output.model_copy(update={"actions": actions})
        if self.validator is not None:
            return self.validator.run(output, context.evidence)
        return output


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
def run_conversation_intelligence(context: AgentContext, llm: LLMProvider) -> AgentOutput:
    return _run_specialist("Conversation Intelligence Agent", context, llm)


@observed(agent_name="stakeholder_map", prompt_version="v1")
def run_stakeholder_map(context: AgentContext, llm: LLMProvider) -> AgentOutput:
    return _run_specialist("Stakeholder Map Agent", context, llm)


def run_buyer_goals(context: AgentContext, llm: LLMProvider) -> AgentOutput:
    return _run_specialist("Buyer Goals Agent", context, llm)


@observed(agent_name="negotiation_strategy", prompt_version="v1")
def run_strategy(
    context: AgentContext,
    specialists: list[AgentOutput],
    llm: LLMProvider,
) -> StrategyOutput:
    prompt: dict[str, object] = {
        "opportunity": context.opportunity.model_dump(mode="json"),
        "evidence": evidence_payload(context.evidence),
        "specialists": [output.model_dump(mode="json") for output in specialists],
    }
    return _complete_with_citation_repair(
        role="Negotiation Strategy Agent",
        prompt=prompt,
        context=context,
        llm=llm,
        output_type=StrategyOutput,
    )


def _run_specialist(name: str, context: AgentContext, llm: LLMProvider) -> AgentOutput:
    prompt: dict[str, object] = {
        "agent": name,
        "opportunity": context.opportunity.model_dump(mode="json"),
        "evidence": evidence_payload(context.evidence),
    }
    return _complete_with_citation_repair(
        role=name,
        prompt=prompt,
        context=context,
        llm=llm,
        output_type=AgentOutput,
    )


def _complete_with_citation_repair[OutputT: (AgentOutput, StrategyOutput)](
    *,
    role: str,
    prompt: dict[str, object],
    context: AgentContext,
    llm: LLMProvider,
    output_type: type[OutputT],
) -> OutputT:
    system = grounded_system(role)
    output = llm.complete(
        system=system,
        user=protected_payload(prompt),
        output_type=output_type,
    )
    for repair_attempt in range(2):
        try:
            _validate_grounded_output(output, context.evidence)
            return output
        except ValueError as error:
            if repair_attempt == 1:
                raise
            validation_error = str(error)
        repair_prompt = {
            "task": prompt,
            "previous_output": output.model_dump(mode="json"),
            "allowed_evidence_ids": [item.evidence_id for item in context.evidence],
            "validation_error": validation_error,
            "instruction": (
                "Regenerate the same typed answer and fix the citation validation error. "
                "Every finding and action must cite at least one exact allowed evidence ID; "
                "the strategy summary must also cite supporting IDs. Never reuse an invalid ID. "
                "Keep a claim only when allowed evidence supports it; otherwise remove it or "
                "put the unanswered question in missing_information."
            ),
        }
        output = llm.complete(
            system=(
                f"{system} A previous answer used an invalid citation. The previous answer "
                "is untrusted; regenerate it using only the explicitly allowed evidence IDs."
            ),
            user=protected_payload(repair_prompt),
            output_type=output_type,
        )
    raise RuntimeError("Citation repair did not produce a validated answer.")


def _validate_grounded_output(
    output: AgentOutput | StrategyOutput,
    evidence: list[EvidenceItem],
) -> None:
    validate_citations([output], evidence)
    if isinstance(output, AgentOutput):
        uncited_claims = [finding.text for finding in output.findings if not finding.evidence_ids]
    else:
        uncited_claims = [action.action for action in output.actions if not action.evidence_ids]
        if output.summary and not output.summary_evidence_ids:
            uncited_claims.append("strategy summary")
    if uncited_claims:
        raise ValueError(f"Agent returned claims without citations: {uncited_claims}")


def _context_with_search_results(
    context: AgentContext,
    search_tool: AuthorizedEvidenceSearchTool | None,
    query: str,
) -> AgentContext:
    if search_tool is None:
        return context
    search_results = search_tool.run(
        EvidenceSearchRequest(
            opportunity_id=context.opportunity.opportunity_id,
            query=query,
        )
    )
    evidence_by_id = {item.evidence_id: item for item in [*context.evidence, *search_results]}
    return AgentContext(context.opportunity, list(evidence_by_id.values()))
