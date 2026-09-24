from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """The small, explicit tool contract exposed to an agent."""

    name: str
    description: str


DEAL_CONTEXT_TOOLS = (
    ToolSpec("get_opportunity_snapshot", "Read the canonical opportunity facts."),
    ToolSpec("get_account_snapshot", "Read the authorized account facts."),
    ToolSpec("get_contacts", "Read authorized contacts for the account."),
)

CONVERSATION_TOOLS = (
    ToolSpec("search_authorized_evidence", "Search authorized Gong and Slack evidence."),
    ToolSpec("get_call_transcript", "Read an authorized call transcript."),
)

STAKEHOLDER_TOOLS = (
    ToolSpec("get_contacts", "Read authorized contacts and deal roles."),
    ToolSpec("get_call_participants", "Read authorized call participants."),
    ToolSpec("search_authorized_evidence", "Search authorized stakeholder signals."),
)

STRATEGY_TOOLS = (
    ToolSpec("get_deal_desk_policy", "Read the relevant approval policy."),
    ToolSpec("validate_recommendation", "Validate citations and approval requirements."),
    ToolSpec("request_approval", "Create a human approval request."),
)
