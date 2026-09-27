import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUp,
  Bookmark,
  Bot,
  Check,
  ChevronDown,
  CircleHelp,
  FileText,
  Hash,
  Info,
  LockKeyhole,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  Plus,
  Search,
  ShieldCheck,
  Smile,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { generateBrief, getApprovalInbox, getApprovalInboxCount, getRequesterRuns, submitApprovalDecision } from "./api";
import type {
  ApprovalDecision,
  ApprovalInboxItem,
  BriefResponse,
  BriefResult,
  DeniedResponse,
  Finding,
  RecommendedAction,
} from "./api";

type Persona = {
  userId: string;
  name: string;
  initials: string;
  role: string;
  accounts: string[];
  restricted: boolean;
  color: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "bot" | "system" | "approval";
  text: string;
  time: string;
  brief?: BriefResponse;
  approval?: ApprovalInboxItem;
  opportunityOptions?: typeof demoOpportunities;
};

const demoOpportunities = [
  { id: "OPP-1001", label: "Northstar Foods Cooperative · renewal" },
  { id: "OPP-1002", label: "Meridian Appliances Group · expansion" },
  { id: "OPP-1003", label: "Eclipse BioMaterials Ltd · restricted renewal" },
] as const;

const briefSectionKeys = [
  "dealSnapshot",
  "executiveSummary",
  "buyerGoals",
  "stakeholderMap",
  "negotiationState",
  "recommendedActions",
  "missingInformation",
  "sourceEvidence",
  "reviewWarnings",
] as const;

type BriefSectionKey = typeof briefSectionKeys[number];
type BriefSectionState = Record<BriefSectionKey, boolean>;

const allSectionsExpanded = (): BriefSectionState =>
  Object.fromEntries(briefSectionKeys.map((key) => [key, true])) as BriefSectionState;

const personas: Persona[] = [
  { userId: "USR-5001", name: "Maya Levin", initials: "ML", role: "Account Owner", accounts: ["ACC-2001"], restricted: false, color: "bg-teal-700" },
  { userId: "USR-5002", name: "Owen Patel", initials: "OP", role: "Account Owner", accounts: ["ACC-2002"], restricted: false, color: "bg-blue-700" },
  { userId: "USR-5003", name: "Nora Chen", initials: "NC", role: "Restricted Account Owner", accounts: ["ACC-2003"], restricted: true, color: "bg-violet-700" },
  { userId: "USR-5004", name: "Sam Hale", initials: "SH", role: "Sales Leader", accounts: ["ACC-2001", "ACC-2002"], restricted: false, color: "bg-amber-700" },
  { userId: "USR-5005", name: "Rina Vale", initials: "RV", role: "Deal Desk Approver", accounts: ["ACC-2001", "ACC-2002", "ACC-2003"], restricted: true, color: "bg-rose-700" },
  { userId: "USR-5007", name: "Harper Noor", initials: "HN", role: "Unauthorized Requester", accounts: ["ACC-2001"], restricted: false, color: "bg-slate-600" },
];

const welcomeMessage = (name: string): ChatMessage => ({
  id: "welcome",
  role: "bot",
  text: `Hi ${name} — I can prepare a grounded negotiation brief from the deal evidence you’re authorized to see. Tell me which opportunity to review. You can also ask first and I’ll request the opportunity ID if it’s missing.`,
  time: currentTime(),
});

function App() {
  const [userId, setUserId] = useState("USR-5003");
  const [messages, setMessages] = useState<ChatMessage[]>(() => [welcomeMessage("Nora Chen")]);
  const [hiddenRunIdsByUser, setHiddenRunIdsByUser] = useState<Record<string, string[]>>({});
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [awaitingOpportunity, setAwaitingOpportunity] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [directMessage, setDirectMessage] = useState<"channel" | "deal-desk">("channel");
  const [reviewerUnreadCount, setReviewerUnreadCount] = useState(0);
  const endOfMessages = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const conversations = useRef<Record<string, ChatMessage[]>>({});
  const user = personas.find((persona) => persona.userId === userId) ?? personas[2]!;

  useEffect(() => {
    endOfMessages.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(composer.scrollHeight, 144)}px`;
  }, [draft]);

  useEffect(() => {
    conversations.current[userId] = messages;
  }, [messages, userId]);

  useEffect(() => {
    let active = true;
    const refreshInbox = async () => {
      try {
        const [inbox, requesterRuns, reviewerCount] = await Promise.all([
          getApprovalInbox(userId),
          getRequesterRuns(userId),
          getApprovalInboxCount("USR-5005"),
        ]);
        if (!active) return;
        setReviewerUnreadCount(reviewerCount);
        setMessages((current) => {
          let updated = [...current];
          const hiddenRunIds = new Set(hiddenRunIdsByUser[userId] ?? []);
          const currentSessionRunIds = new Set(
            (conversations.current[userId] ?? []).flatMap((message) =>
              message.brief ? [message.brief.run_id] : [],
            ),
          );
          for (const brief of requesterRuns) {
            if (hiddenRunIds.has(brief.run_id) || !currentSessionRunIds.has(brief.run_id)) continue;
            const existingIndex = updated.findIndex((message) => message.brief?.run_id === brief.run_id);
            const existing = existingIndex >= 0 ? updated[existingIndex] : undefined;
            const update = {
              id: existing?.id ?? `request-${brief.run_id}`,
              role: "bot" as const,
              text: requesterStatusMessage(brief),
              time: existing?.time ?? currentTime(),
              brief,
            };
            if (existingIndex >= 0) updated[existingIndex] = { ...existing, ...update };
            else updated.push(update);
          }
          for (const item of inbox) {
            const existingIndex = updated.findIndex(
              (message) => message.approval?.approval_request.run_id === item.approval_request.run_id,
            );
            const approvalMessage = {
              id: `approval-${item.approval_request.run_id}`,
              role: "approval" as const,
              text: `Approval requested for ${item.approval_request.opportunity_id} by ${item.approval_request.requester_name}.`,
              time: currentTime(),
              approval: item,
            };
            if (existingIndex >= 0) updated[existingIndex] = { ...updated[existingIndex], approval: item };
            else updated.push(approvalMessage);
          }
          return updated;
        });
      } catch {
        // Inbox refresh is best-effort while the API starts or restarts.
      }
    };
    void refreshInbox();
    const timer = window.setInterval(() => void refreshInbox(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [userId, hiddenRunIdsByUser]);

  const addMessage = (message: Omit<ChatMessage, "id" | "time">) => {
    setMessages((current) => [...current, { ...message, id: crypto.randomUUID(), time: currentTime() }]);
  };

  const submitMessage = async (event?: FormEvent, suggestedText?: string) => {
    event?.preventDefault();
    const text = (suggestedText ?? draft).trim();
    if (!text || loading) return;
    setError(null);
    setDraft("");
    addMessage({ role: "user", text });

    const opportunityId = findOpportunityId(text);
    if (!opportunityId) {
      setAwaitingOpportunity(true);
      addMessage({
        role: "bot",
        text: "Which opportunity should I use? These are the three demo opportunities. Choose one below or type its ID; I’ll check your access before retrieving deal evidence.",
        opportunityOptions: demoOpportunities,
      });
      return;
    }

    setAwaitingOpportunity(false);
    await requestBrief(opportunityId);
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submitMessage();
  };

  const requestBrief = async (opportunityId: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await generateBrief({
        opportunity_id: opportunityId,
        user_id: user.userId,
      });
      if (isDenied(result)) {
        addMessage({
          role: "bot",
          text: "I’m sorry, but you are not authorized to access this opportunity. I can’t show deal details or source information for this request.",
        });
        return;
      }
      addMessage({
        role: "bot",
        text: result.run_status === "awaiting_approval"
          ? `I’ve prepared the brief for ${result.deal_snapshot.account_name}. It is now waiting for Deal Desk review.`
          : `I’ve prepared the brief for ${result.deal_snapshot.account_name}. It includes the evidence, recommended actions, and any information that still needs confirmation.`,
        brief: result,
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "The request failed.";
      setError(message);
      addMessage({ role: "bot", text: "I couldn’t complete that request. Check that the local API is running, then try again." });
    } finally {
      setLoading(false);
    }
  };

  const decideApproval = async (request: ApprovalInboxItem, decision: ApprovalDecision) => {
    if (approvalBusy) return;
    setApprovalBusy(true);
    try {
      const result = await submitApprovalDecision(
        request.approval_request.run_id,
        user.userId,
        decision,
      );
      setMessages((current) => current.map((message) =>
        message.approval?.approval_request.run_id === result.approval_request.run_id
          ? { ...message, approval: result }
          : message,
      ));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not submit the approval decision.");
    } finally {
      setApprovalBusy(false);
    }
  };

  const quickRequest = (opportunityId: string) => {
    void submitMessage(undefined, `Please prepare a negotiation brief for ${opportunityId}.`);
  };

  const changeDemoUser = (nextUserId: string) => {
    const nextUser = personas.find((persona) => persona.userId === nextUserId) ?? personas[2]!;
    conversations.current[userId] = messages;
    setUserId(nextUser.userId);
    setMessages(conversations.current[nextUser.userId] ?? [welcomeMessage(nextUser.name)]);
    setDirectMessage(nextUser.userId === "USR-5005" ? "deal-desk" : "channel");
    setAwaitingOpportunity(false);
    setError(null);
  };

  const selectDemoIdentity = (nextUserId: string) => {
    setDetailsOpen(true);
    if (nextUserId !== userId) {
      changeDemoUser(nextUserId);
      return;
    }
    setDirectMessage(nextUserId === "USR-5005" ? "deal-desk" : "channel");
  };

  const startFreshConversation = async () => {
    const savedRuns = await getRequesterRuns(userId).catch(() => []);
    const hiddenRunIds = new Set([
      ...(hiddenRunIdsByUser[userId] ?? []),
      ...savedRuns.map((brief) => brief.run_id),
      ...messages.flatMap((message) => message.brief ? [message.brief.run_id] : []),
    ]);
    setHiddenRunIdsByUser((current) => ({
      ...current,
      [userId]: [...hiddenRunIds],
    }));
    const freshConversation = [welcomeMessage(user.name)];
    conversations.current[userId] = freshConversation;
    setMessages(freshConversation);
    setDirectMessage("channel");
    setAwaitingOpportunity(false);
    setDraft("");
    setError(null);
  };

  const visibleMessages = directMessage === "deal-desk"
    ? messages.filter((message) => message.role === "approval")
    : messages.filter((message) => message.role !== "approval");

  return (
    <main className="slack-shell">
      <nav className="workspace-rail" aria-label="Workspace navigation">
        <button className="workspace-logo" title="Cato GTM Lab">C</button>
        <button className="rail-action active" title="Messages"><MessageSquare size={19} /></button>
        <button className="rail-action" title="Activity"><Activity size={19} /></button>
        <button className="rail-action" title="Saved items"><Bookmark size={19} /></button>
        <div className="rail-spacer" />
        <button className="rail-action" title="Add workspace"><Plus size={20} /></button>
        <Avatar persona={user} size="small" />
      </nav>

      <aside className="channel-sidebar">
        <div className="workspace-heading">
          <div className="workspace-name">Cato GTM Lab <ChevronDown size={15} /></div>
          <div className="workspace-caption">Local demo workspace</div>
        </div>
        <div className="channel-navigation">
          <NavItem icon={<MessageSquare size={15} />} label="Direct messages" muted />
          <NavItem icon={<Activity size={15} />} label="Activity" muted />
          <NavItem icon={<Bookmark size={15} />} label="Later" muted />
          <div className="nav-section-title"><ChevronDown size={13} /> Channels <Plus size={14} /></div>
          <NavItem hash label="general" muted />
          <NavItem hash label="sales-team" muted />
          <NavItem hash label="deal-intel-demo" selected />
          <NavItem hash label="deal-desk" muted />
          <div className="nav-section-title"><ChevronDown size={13} /> Direct messages / demo identities <Plus size={14} /></div>
          <NavItem icon={<span className="online-dot" />} label="Deal Intel Bot" />
          {personas.map((persona) => (
            <NavItem
              key={persona.userId}
              icon={<Avatar persona={persona} size="small" />}
              label={persona.name}
              selected={userId === persona.userId}
              badge={persona.userId === "USR-5005" ? reviewerUnreadCount : undefined}
              onClick={() => selectDemoIdentity(persona.userId)}
            />
          ))}
          <div className="nav-section-title"><ChevronDown size={13} /> Apps</div>
          <NavItem icon={<Sparkles size={14} />} label="Deal Intel" muted />
        </div>
        <div className="sidebar-footer">
          <button className="new-conversation-button" type="button" onClick={() => void startFreshConversation()}>
            <Plus size={14} /> New conversation
          </button>
          <div className="session-note">Previous runs remain saved.</div>
          <div>Synthetic deal data only</div>
          <div className="demo-status"><span /> Local simulator</div>
        </div>
      </aside>

      <section className="conversation-panel">
        <header className="conversation-header">
          <div className="conversation-heading">
            <div className="channel-name">{directMessage === "deal-desk" ? <MessageSquare size={18} /> : <Hash size={18} />} {directMessage === "deal-desk" ? "Rina Vale · Direct message" : "deal-intel-demo"} <ChevronDown size={13} /></div>
            <div className="channel-description">{directMessage === "deal-desk" ? "Private Deal Desk approval inbox · local simulator" : "Prepare and review grounded deal briefs with Deal Intel"}</div>
          </div>
          <div className="conversation-tools">
            <div className="member-stack"><span className="member-avatar bot-avatar">✦</span><span className="member-avatar nora-avatar">NC</span><span className="member-count">3</span></div>
            <button className="header-icon" title="Search"><Search size={17} /></button>
            <button className="header-icon" title="Conversation details" onClick={() => setDetailsOpen((open) => !open)}><Info size={17} /></button>
            <button className="header-icon" title="More"><MoreHorizontal size={18} /></button>
          </div>
        </header>

        <div className="message-scroll" aria-live="polite">
          <div className="day-divider"><span>Today</span></div>
          {visibleMessages.map((message) => (
            <MessageRow
              key={message.id}
              message={message}
              user={user}
              approvalBusy={approvalBusy}
              onDecision={decideApproval}
              onOpportunitySelect={quickRequest}
            />
          ))}
          {directMessage === "deal-desk" && visibleMessages.length === 0 && (
            <div className="awaiting-note"><CircleHelp size={14} /> No pending Deal Desk approval messages.</div>
          )}
          {loading && <TypingIndicator />}
          {error && <div className="inline-error"><AlertTriangle size={15} /> {error}</div>}
          {directMessage === "channel" && !loading && visibleMessages.length === 1 && (
            <div className="quick-prompts">
              <span>Try a demo request</span>
              <button onClick={() => quickRequest("OPP-1003")}>Restricted renewal · OPP-1003</button>
              <button onClick={() => quickRequest("OPP-1001")}>Standard renewal · OPP-1001</button>
              <button onClick={() => void submitMessage(undefined, "Can you prepare a negotiation brief for me?")}>Ask without an opportunity ID</button>
            </div>
          )}
          {awaitingOpportunity && <div className="awaiting-note"><CircleHelp size={14} /> Waiting for an opportunity ID</div>}
          <div ref={endOfMessages} />
        </div>

        <form className="composer-area" onSubmit={(event) => void submitMessage(event)}>
          <div className="composer-box">
            <textarea
              ref={composerRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={directMessage === "deal-desk" ? "Approval decisions are handled on the request card" : "Message #deal-intel-demo"}
              aria-label="Write a message"
              rows={1}
              disabled={loading || directMessage === "deal-desk"}
            />
            <div className="composer-controls">
              <div className="composer-tools">
                <button type="button" title="Format"><strong>B</strong></button>
                <button type="button" title="Add link">↗</button>
                <button type="button" title="Add emoji"><Smile size={16} /></button>
                <button type="button" title="Attach file"><Paperclip size={16} /></button>
                <button type="button" title="More actions"><Plus size={16} /></button>
              </div>
              <div className="send-controls"><span>{directMessage === "deal-desk" ? "Review requests above" : "Shift + Enter for new line"}</span><button type="submit" aria-label="Send message" disabled={!draft.trim() || loading || directMessage === "deal-desk"}><ArrowUp size={17} /></button></div>
            </div>
          </div>
          <p className="composer-caption">Demo identity: {user.name} · {directMessage === "deal-desk" ? "Approval card contains the brief and evidence to review" : awaitingOpportunity ? "Reply with an opportunity ID to continue" : "Messages run through the local deal workflow"}</p>
        </form>
      </section>

      {detailsOpen && (
        <aside className="details-panel">
          <div className="details-header"><span>Details</span><button onClick={() => setDetailsOpen(false)} aria-label="Close details"><X size={17} /></button></div>
          <div className="details-content">
            <div className="profile-card">
              <div className="profile-main"><Avatar persona={user} /><div><div className="profile-name">{user.name}</div><div className="profile-role">{user.role} · Demo identity</div></div></div>
              <div className="profile-presence"><span className="online-dot" /> Active in this local demo</div>
            </div>
            <div className="details-rule" />
            <div className="details-label">Demo identity</div>
            <select value={userId} disabled={loading || approvalBusy} onChange={(event) => changeDemoUser(event.target.value)} aria-label="Select demo user">
              {personas.map((persona) => <option key={persona.userId} value={persona.userId}>{persona.name} · {persona.userId}</option>)}
            </select>
            <p className="details-note">This selector is for demonstrating permission behavior. A real Slack integration would map the authenticated Slack user automatically.</p>
            <div className="details-rule" />
            <div className="details-label">In this conversation</div>
            <DetailRow icon={<Hash size={15} />} title="deal-intel-demo" subtitle="Local Slack-style demo channel" />
            <DetailRow icon={<Users size={15} />} title="3 members" subtitle="You, Deal Intel, Deal Desk" />
            <div className="details-rule" />
            <div className="details-label">Demo safety</div>
            <div className="safety-note"><ShieldCheck size={16} /><span>Synthetic deal data only. The Slack-style approval message is simulated in this screen; it does not send real Slack, CRM, or customer messages.</span></div>
            <div className="details-rule" />
            <div className="details-label">Available demo identities</div>
            <div className="identity-list">{personas.map((persona) => <div key={persona.userId}><span>{persona.name}</span><small>{persona.role}</small></div>)}</div>
          </div>
        </aside>
      )}
      {!detailsOpen && <button className="show-details" onClick={() => setDetailsOpen(true)}><Menu size={16} /> Details</button>}
    </main>
  );
}

function MessageRow({
  message,
  user,
  approvalBusy,
  onDecision,
  onOpportunitySelect,
}: {
  message: ChatMessage;
  user: Persona;
  approvalBusy: boolean;
  onDecision: (request: ApprovalInboxItem, decision: ApprovalDecision) => void;
  onOpportunitySelect: (opportunityId: string) => void;
}) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const isApproval = message.role === "approval";
  const sender = isUser ? user.name : isSystem ? "Workflow update" : isApproval ? "Deal Intel · approval request" : "Deal Intel";
  return (
    <article className={`chat-message ${isSystem ? "system-message" : ""}`}>
      <div className={`message-avatar ${isUser ? user.color : isSystem ? "system-avatar" : "bot-avatar"}`}>
        {isUser ? user.initials : isSystem ? <Check size={16} /> : <Sparkles size={18} />}
      </div>
      <div className="message-content">
        <div className="message-meta"><strong>{sender}</strong>{!isUser && !isSystem && <span className="app-badge">APP</span>}<time>{message.time}</time></div>
        <p className="chat-copy">{message.text}</p>
        {message.opportunityOptions && <div className="opportunity-options">{message.opportunityOptions.map((opportunity) => <button key={opportunity.id} onClick={() => onOpportunitySelect(opportunity.id)}>{opportunity.id}<span>{opportunity.label}</span></button>)}</div>}
        {message.brief && <BriefCard brief={message.brief} />}
        {message.approval && <ApprovalCard request={message.approval} busy={approvalBusy} onDecision={onDecision} />}
      </div>
    </article>
  );
}

function BriefCard({
  brief,
}: {
  brief: BriefResponse;
}) {
  const needsApproval = brief.recommended_next_actions.some((action) => action.requires_approval);
  const snapshot = brief.deal_snapshot;
  const [expandedSections, setExpandedSections] = useState<BriefSectionState>(allSectionsExpanded);
  const everySectionExpanded = briefSectionKeys.every((key) => expandedSections[key]);

  const setSectionExpanded = (key: BriefSectionKey, expanded: boolean) => {
    setExpandedSections((current) => ({ ...current, [key]: expanded }));
  };

  const toggleAllSections = () => {
    const expand = !everySectionExpanded;
    setExpandedSections(Object.fromEntries(briefSectionKeys.map((key) => [key, expand])) as BriefSectionState);
  };

  return (
    <div className="brief-card">
      <div className="brief-card-heading">
        <div><div className="brief-eyebrow">Strategic deal brief · {brief.opportunity_id}</div><h2>{snapshot.account_name}</h2><p>{snapshot.stage} · Close {snapshot.close_date} · Owner {snapshot.owner}</p></div>
        <div className="brief-header-actions"><button type="button" className="sections-toggle" onClick={toggleAllSections} aria-expanded={everySectionExpanded}>{everySectionExpanded ? "Collapse all" : "Expand all"}</button><span className={`risk-badge ${snapshot.risk_level.toLowerCase()}`}>{snapshot.risk_level} risk</span></div>
      </div>
      <div className="brief-card-body">
        <BriefSection sectionKey="dealSnapshot" title="Deal Snapshot" expanded={expandedSections.dealSnapshot} onToggle={setSectionExpanded}>
          <div className="snapshot-row">
            <SnapshotMetric label="Opportunity" value={snapshot.opportunity_id} />
            <SnapshotMetric label="ACV" value={new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(snapshot.amount_acv)} />
            <SnapshotMetric label="Stage" value={snapshot.stage} />
          </div>
        </BriefSection>
        <BriefSection sectionKey="executiveSummary" title="Executive Summary" expanded={expandedSections.executiveSummary} onToggle={setSectionExpanded}><p>{brief.executive_summary}</p></BriefSection>
        <FindingSection sectionKey="buyerGoals" title="Buyer Goals and Business Drivers" findings={brief.buyer_goals} expanded={expandedSections.buyerGoals} onToggle={setSectionExpanded} />
        <FindingSection sectionKey="stakeholderMap" title="Stakeholder Map" findings={brief.stakeholder_map} expanded={expandedSections.stakeholderMap} onToggle={setSectionExpanded} />
        <FindingSection sectionKey="negotiationState" title="Negotiation State" findings={brief.negotiation_state} expanded={expandedSections.negotiationState} onToggle={setSectionExpanded} />
        <BriefSection sectionKey="recommendedActions" title="Recommended Next Actions" expanded={expandedSections.recommendedActions} onToggle={setSectionExpanded}>
          {brief.recommended_next_actions.length ? <ol className="action-list">{brief.recommended_next_actions.map((action) => <ActionItem key={`${action.action}-${action.owner}`} action={action} />)}</ol> : <p>No recommended actions were returned.</p>}
        </BriefSection>
        <BriefSection sectionKey="missingInformation" title="Missing Information" expanded={expandedSections.missingInformation} onToggle={setSectionExpanded}>
          {brief.missing_information.length ? <ul className="missing-list">{brief.missing_information.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No material information gaps identified.</p>}
        </BriefSection>
        <BriefSection sectionKey="sourceEvidence" title="Source Evidence" expanded={expandedSections.sourceEvidence} onToggle={setSectionExpanded}>
          <div className="evidence-chips">{brief.source_evidence.map((item) => <span className="evidence-chip" key={item.evidence_id}><FileText size={12} /> {item.source_type} · {item.source_id}</span>)}</div>
        </BriefSection>
        <BriefSection sectionKey="reviewWarnings" title="Confidence and Review Warnings" expanded={expandedSections.reviewWarnings} onToggle={setSectionExpanded}>
          {brief.confidence_and_review_warnings.length ? <ul className="warning-list">{brief.confidence_and_review_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No additional review warnings.</p>}
        </BriefSection>
      </div>
      <div className="brief-card-footer"><span>Run <strong>{brief.run_id.slice(0, 8)}</strong> · {brief.source_evidence.length} evidence items</span>{needsApproval && <span className="review-required"><LockKeyhole size={13} /> Human review required</span>}</div>
      <CostSummary brief={brief} />
      {needsApproval && <div className="approval-box pending"><div className="approval-heading"><AlertTriangle size={16} /> {brief.run_status === "awaiting_approval" ? "Waiting for Deal Desk approval" : brief.run_status === "rejected" ? "Deal Desk rejected this recommendation" : "Deal Desk approval recorded"}</div><p>The requester can review the proposed actions but cannot approve them. No CRM update or customer message will happen in this demo.</p></div>}
      <details className="citation-details"><summary>Inspect citations and evidence IDs</summary><div className="citation-list">{brief.source_evidence.map((item) => <div key={item.evidence_id}><strong>{item.evidence_id}</strong><span>{item.text}</span></div>)}</div></details>
    </div>
  );
}

function ApprovalCard({ request, busy, onDecision }: {
  request: ApprovalInboxItem;
  busy: boolean;
  onDecision: (request: ApprovalInboxItem, decision: ApprovalDecision) => void;
}) {
  const { approval_request: approvalRequest, brief } = request;
  const decided = approvalRequest.status !== "pending";
  return <div className="approval-box pending slack-approval-card">
    <div className="approval-heading"><LockKeyhole size={16} /> Review requested · {approvalRequest.opportunity_id}</div>
    <p><strong>{approvalRequest.requester_name}</strong> requested Deal Desk review. Review the proposed actions below.</p>
    <p>The complete brief is included below so the decision can be made with the deal context, risks, recommendations, and source evidence.</p>
    <BriefCard brief={brief} />
    {decided
      ? <p className="approval-result">Decision recorded: <strong>{approvalRequest.status}</strong>. No external CRM or customer-facing action was taken.</p>
      : <div className="approval-buttons"><button type="button" className="reject-button" disabled={busy} onClick={() => onDecision(request, "rejected")}>Reject</button><button type="button" className="approve-button" disabled={busy} onClick={() => onDecision(request, "approved")}><Check size={14} /> {busy ? "Submitting…" : "Approve"}</button></div>}
    <small>Run {brief.run_id.slice(0, 8)} · decision updates this run; it does not rerun the agents.</small>
  </div>;
}

function BriefSection({ sectionKey, title, children, expanded, onToggle }: { sectionKey: BriefSectionKey; title: string; children: ReactNode; expanded: boolean; onToggle: (key: BriefSectionKey, expanded: boolean) => void }) {
  return <details className="brief-section" open={expanded} onToggle={(event) => onToggle(sectionKey, event.currentTarget.open)}><summary><span>{title}</span><ChevronDown size={14} /></summary><div className="brief-section-content">{children}</div></details>;
}

function FindingSection({ sectionKey, title, findings, expanded, onToggle }: { sectionKey: BriefSectionKey; title: string; findings: Finding[]; expanded: boolean; onToggle: (key: BriefSectionKey, expanded: boolean) => void }) {
  return <BriefSection sectionKey={sectionKey} title={title} expanded={expanded} onToggle={onToggle}>
    {findings.length ? <ul className="finding-list">{findings.map((finding, index) => <li key={`${finding.text}-${index}`}><span>{finding.text}</span><div className="finding-meta"><span>Confidence {Math.round(finding.confidence * 100)}%</span>{finding.evidence_ids.map((id) => <code key={id}>{id}</code>)}</div>{finding.uncertainty && <em>{finding.uncertainty}</em>}</li>)}</ul> : <p>No findings returned.</p>}
  </BriefSection>;
}

function ActionItem({ action }: { action: RecommendedAction }) {
  return <li><div className="action-title">{action.action}{action.requires_approval && <span>Approval</span>}</div><p>{action.rationale}</p><small>Owner · {action.owner}</small><div className="finding-meta">{action.evidence_ids.map((id) => <code key={id}>{id}</code>)}</div></li>;
}

function CostSummary({ brief }: { brief: BriefResponse }) {
  const cost = brief.cost_summary;
  const money = (value: number | null) => value === null ? "Unlimited" : `$${value.toFixed(4)}`;
  return <div className="cost-summary"><div className="cost-title">Model usage <span>{cost.call_count} calls</span></div><div className="cost-grid"><Metric label="Spent this run" value={money(cost.run_spent_usd)} /><Metric label="Period spend" value={money(cost.spent_usd)} /><Metric label="Remaining" value={money(cost.remaining_usd)} /><Metric label="Tokens" value={(cost.prompt_tokens + cost.completion_tokens).toLocaleString()} /></div><div className="model-names">Models · {cost.models.length ? cost.models.join(", ") : "Fake / offline mode"}</div></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function SnapshotMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function TypingIndicator() {
  return <div className="typing-row"><div className="message-avatar bot-avatar"><Bot size={17} /></div><div><strong>Deal Intel</strong><div className="typing-copy"><span className="typing-dots"><i /><i /><i /></span> Checking access, retrieving evidence, and preparing your brief…</div></div></div>;
}

function Avatar({ persona, size }: { persona: Persona; size?: "small" }) {
  return <div className={`profile-avatar ${persona.color} ${size === "small" ? "small" : ""}`}>{persona.initials}</div>;
}

function NavItem({ icon, hash, label, selected, muted, badge, onClick }: { icon?: ReactNode; hash?: boolean; label: string; selected?: boolean; muted?: boolean; badge?: number; onClick?: () => void }) {
  const contents = <>{hash ? <Hash size={15} /> : icon}<span>{label}</span>{badge ? <span className="nav-badge">+{badge}</span> : null}</>;
  const className = `nav-item ${selected ? "selected" : ""} ${muted ? "muted" : ""}`;
  if (onClick) return <button type="button" className={className} onClick={onClick} aria-pressed={selected}>{contents}</button>;
  return <div className={className}>{contents}</div>;
}

function DetailRow({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle: string }) {
  return <div className="detail-row"><span>{icon}</span><div><strong>{title}</strong><small>{subtitle}</small></div></div>;
}

function currentTime() {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(new Date());
}

function findOpportunityId(text: string) {
  return text.match(/\bOPP-\d{4}\b/i)?.[0].toUpperCase() ?? null;
}

function requesterStatusMessage(brief: BriefResponse) {
  if (brief.run_status === "awaiting_approval") {
    return `Your brief for ${brief.opportunity_id} is waiting for Deal Desk approval.`;
  }
  if (brief.run_status === "completed") {
    return `Deal Desk approved the recommendations for ${brief.opportunity_id}. Your original brief is updated below.`;
  }
  return `Deal Desk rejected the recommendations for ${brief.opportunity_id}. Your original brief is updated below.`;
}

function isDenied(result: BriefResult): result is DeniedResponse {
  return "status" in result && result.status === "denied";
}

export default App;
