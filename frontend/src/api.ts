export type BriefRequest = {
  opportunity_id: string;
  user_id: string;
};

export type ApprovalDecision = "approved" | "rejected";

export type Finding = {
  text: string;
  evidence_ids: string[];
  confidence: number;
  uncertainty: string | null;
};

export type RecommendedAction = {
  action: string;
  owner: string;
  rationale: string;
  evidence_ids: string[];
  requires_approval: boolean;
};

export type EvidenceItem = {
  evidence_id: string;
  opportunity_id: string;
  account_id: string | null;
  source_type: string;
  source_file: string;
  source_id: string;
  access_level: string;
  event_date: string | null;
  text: string;
  metadata: Record<string, string>;
};

export type BriefResponse = {
  run_id: string;
  opportunity_id: string;
  run_status: "completed" | "awaiting_approval" | "rejected";
  deal_snapshot: {
    opportunity_id: string;
    account_name: string;
    stage: string;
    amount_acv: number;
    close_date: string;
    owner: string;
    risk_level: string;
    evidence_ids: string[];
  };
  executive_summary: string;
  buyer_goals: Finding[];
  stakeholder_map: Finding[];
  negotiation_state: Finding[];
  recommended_next_actions: RecommendedAction[];
  missing_information: string[];
  source_evidence: EvidenceItem[];
  confidence_and_review_warnings: string[];
  cost_summary: {
    budget_usd: number | null;
    spent_usd: number;
    run_spent_usd: number;
    remaining_usd: number | null;
    prompt_tokens: number;
    completion_tokens: number;
    call_count: number;
    models: string[];
    period_key: string | null;
  };
};

export type DeniedResponse = {
  status: "denied";
  run_id: string;
  opportunity_id: string;
  user_id: string;
  message: string;
};

export type BriefResult = BriefResponse | DeniedResponse;

export type ApprovalInboxItem = {
  approval_request: {
    run_id: string;
    opportunity_id: string;
    requester_user_id: string;
    requester_name: string;
    status: "pending" | "approved" | "rejected";
    requested_actions: string[];
    requested_at: string;
  };
  brief: BriefResponse;
};

const apiBase = "http://127.0.0.1:8000";

export const generateBrief = async (request: BriefRequest): Promise<BriefResult> => {
  const response = await fetch(`${apiBase}/brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `API request failed with status ${response.status}`);
  }

  return response.json() as Promise<BriefResult>;
};

export const getApprovalInbox = async (userId: string): Promise<ApprovalInboxItem[]> => {
  const query = new URLSearchParams({ user_id: userId });
  const response = await fetch(`${apiBase}/approvals/inbox?${query}`);
  if (!response.ok) throw new Error(`Approval inbox request failed with status ${response.status}`);
  return response.json() as Promise<ApprovalInboxItem[]>;
};

export const getApprovalInboxCount = async (userId: string): Promise<number> => {
  const query = new URLSearchParams({ user_id: userId });
  const response = await fetch(`${apiBase}/approvals/inbox/count?${query}`);
  if (!response.ok) throw new Error(`Approval count request failed with status ${response.status}`);
  const result = await response.json() as { count: number };
  return result.count;
};

export const getRequesterRuns = async (userId: string): Promise<BriefResponse[]> => {
  const query = new URLSearchParams({ user_id: userId });
  const response = await fetch(`${apiBase}/runs/requests?${query}`);
  if (!response.ok) throw new Error(`Request history failed with status ${response.status}`);
  return response.json() as Promise<BriefResponse[]>;
};

export const submitApprovalDecision = async (
  runId: string,
  reviewerUserId: string,
  decision: ApprovalDecision,
): Promise<ApprovalInboxItem> => {
  const response = await fetch(`${apiBase}/approvals/${runId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer_user_id: reviewerUserId, decision }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Approval decision failed with status ${response.status}`);
  }
  return response.json() as Promise<ApprovalInboxItem>;
};
