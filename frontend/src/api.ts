export type ApprovalDecision = "approved" | "rejected" | "pending";

export type BriefRequest = {
  opportunity_id: string;
  user_id: string;
  approval_decision: ApprovalDecision;
};

export type BriefResponse = {
  run_id: string;
  opportunity_id: string;
  executive_summary: string;
  confidence_and_review_warnings: string[];
  missing_information: string[];
  recommended_next_actions: Array<{
    action: string;
    owner: string;
    rationale: string;
    requires_approval: boolean;
  }>;
};

export const generateBrief = async (request: BriefRequest): Promise<BriefResponse> => {
  const response = await fetch("http://127.0.0.1:8000/brief", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json() as Promise<BriefResponse>;
};
