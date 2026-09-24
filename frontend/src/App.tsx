import { useState } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, FileSearch, ShieldCheck, Sparkles } from "lucide-react";
import { BriefResponse, BriefResult, DeniedResponse, generateBrief } from "./api";

const initialBrief: BriefResponse | null = null;

function App() {
  const [opportunityId, setOpportunityId] = useState("OPP-1001");
  const [userId, setUserId] = useState("USR-5001");
  const [approval, setApproval] = useState<"approved" | "rejected" | "pending">("pending");
  const [result, setResult] = useState<BriefResult | null>(initialBrief);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approvalRequested, setApprovalRequested] = useState(false);
  const [approvalComplete, setApprovalComplete] = useState(false);

  const runBrief = async (decision = approval) => {
    setLoading(true);
    setError(null);
    try {
      const nextResult = await generateBrief({ opportunity_id: opportunityId, user_id: userId, approval_decision: decision });
      setResult(nextResult);
      const needsApproval = "status" in nextResult === false
        && nextResult.recommended_next_actions.some((action) => action.requires_approval);
      setApprovalRequested(decision === "pending" && needsApproval);
      setApprovalComplete(decision !== "pending" && needsApproval);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#07111f] text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl gap-8 px-6 py-8 lg:px-10">
        <aside className="hidden w-56 shrink-0 flex-col lg:flex">
          <div className="mb-12 flex items-center gap-3">
            <div className="rounded-xl bg-cyan-400/15 p-2 text-cyan-300"><Sparkles size={20} /></div>
            <div><p className="font-semibold tracking-tight">Deal Intel</p><p className="text-xs text-slate-500">Command Center</p></div>
          </div>
          <nav className="space-y-2 text-sm">
            {[["Deal overview", CheckCircle2], ["Evidence", FileSearch], ["Stakeholders", ShieldCheck]].map(([label, Icon]) => (
              <div key={label as string} className="flex items-center gap-3 rounded-xl bg-white/[0.06] px-4 py-3 text-cyan-200">
                <Icon size={17} /> {label as string}
              </div>
            ))}
          </nav>
          <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.04] p-4 text-xs text-slate-400">
            <p className="mb-2 text-slate-200">Local prototype</p>
            CLI · API · React UI
          </div>
        </aside>

        <section className="flex-1">
          <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div><p className="mb-2 text-xs font-medium uppercase tracking-[0.25em] text-cyan-300">Deal intelligence</p><h1 className="text-3xl font-semibold tracking-tight">Executive deal room</h1></div>
            <div className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-300"><span className="h-2 w-2 rounded-full bg-emerald-300" /> API ready</div>
          </header>

          <div className="mb-6 grid gap-4 md:grid-cols-3">
            <label className="rounded-2xl border border-white/10 bg-white/[0.04] p-4"><span className="text-xs text-slate-500">Opportunity</span><input className="mt-2 w-full bg-transparent text-lg outline-none" value={opportunityId} onChange={(event) => setOpportunityId(event.target.value)} /></label>
            <label className="rounded-2xl border border-white/10 bg-white/[0.04] p-4"><span className="text-xs text-slate-500">Requester</span><input className="mt-2 w-full bg-transparent text-lg outline-none" value={userId} onChange={(event) => setUserId(event.target.value)} /></label>
            <label className="rounded-2xl border border-white/10 bg-white/[0.04] p-4"><span className="text-xs text-slate-500">Approval mode</span><select className="mt-2 w-full bg-transparent text-lg outline-none" value={approval} onChange={(event) => setApproval(event.target.value as typeof approval)}><option className="bg-[#101d30]" value="pending">Pending review</option><option className="bg-[#101d30]" value="approved">Approved</option><option className="bg-[#101d30]" value="rejected">Rejected</option></select></label>
          </div>
          <button onClick={() => runBrief()} disabled={loading} className="mb-8 inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-5 py-3 font-semibold text-[#07111f] transition hover:bg-cyan-200 disabled:cursor-wait disabled:opacity-50">{loading ? "Generating…" : "Generate brief"}<ArrowUpRight size={17} /></button>

          {error && <div className="mb-6 rounded-2xl border border-rose-400/30 bg-rose-400/10 p-4 text-rose-200">{error}</div>}
          {approvalRequested && result && <ApprovalPanel loading={loading} onDecision={(decision) => runBrief(decision)} />}
          {result ? <ResultView result={result} approvalComplete={approvalComplete} /> : <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.02] p-16 text-center text-slate-500"><Sparkles className="mx-auto mb-4 text-cyan-300" /><p>Generate a brief to open the deal room.</p></div>}
        </section>
      </div>
    </main>
  );
}

function ResultView({ result, approvalComplete }: { result: BriefResult; approvalComplete: boolean }) {
  return "status" in result ? <DeniedView result={result} /> : <BriefView brief={result} approvalComplete={approvalComplete} />;
}

function DeniedView({ result }: { result: DeniedResponse }) {
  return <div className="rounded-3xl border border-rose-400/25 bg-rose-400/[0.08] p-8">
    <div className="mb-4 flex items-center gap-3 text-rose-200"><ShieldCheck size={22} /><h2 className="text-xl font-semibold">Access denied</h2></div>
    <p className="text-slate-300">{result.message}</p>
    <p className="mt-4 text-xs text-slate-500">Request {result.run_id.slice(0, 8)} · {result.opportunity_id}</p>
  </div>;
}

function ApprovalPanel({ loading, onDecision }: { loading: boolean; onDecision: (decision: "approved" | "rejected") => void }) {
  return <div className="mb-5 rounded-3xl border border-amber-300/30 bg-amber-300/[0.1] p-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><div className="mb-2 flex items-center gap-2 text-amber-200"><AlertTriangle size={18} /><p className="font-semibold">Human approval required</p></div><p className="text-sm text-amber-100/75">Review the recommended actions below before continuing.</p></div>
      <div className="flex gap-3"><button disabled={loading} onClick={() => onDecision("rejected")} className="rounded-xl border border-rose-300/30 px-4 py-2 text-sm text-rose-200 hover:bg-rose-300/10 disabled:opacity-50">Reject</button><button disabled={loading} onClick={() => onDecision("approved")} className="rounded-xl bg-emerald-300 px-4 py-2 text-sm font-semibold text-[#07111f] hover:bg-emerald-200 disabled:opacity-50">Approve</button></div>
    </div>
  </div>;
}

function BriefView({ brief, approvalComplete }: { brief: BriefResponse; approvalComplete: boolean }) {
  return <div className="space-y-5">
    <div className="grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
      <article className="rounded-3xl border border-white/10 bg-white/[0.05] p-6"><div className="mb-5 flex items-center justify-between"><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Executive summary</p><span className="text-xs text-slate-500">Run {brief.run_id.slice(0, 8)}</span></div><p className="text-xl leading-relaxed text-slate-200">{brief.executive_summary}</p>{approvalComplete && <p className="mt-5 text-sm text-emerald-300">Approval decision recorded.</p>}</article>
      <article className="rounded-3xl border border-amber-300/20 bg-amber-300/[0.07] p-6"><div className="mb-4 flex items-center gap-2 text-amber-200"><AlertTriangle size={18} /><p className="font-medium">Review warnings</p></div><ul className="space-y-3 text-sm text-amber-100/80">{brief.confidence_and_review_warnings.map((warning) => <li key={warning}>• {warning}</li>)}</ul></article>
    </div>
    <article className="rounded-3xl border border-white/10 bg-white/[0.04] p-6"><p className="mb-5 text-xs uppercase tracking-[0.2em] text-cyan-300">Recommended next actions</p><div className="grid gap-3 md:grid-cols-2">{brief.recommended_next_actions.map((action) => <div key={action.action} className="rounded-2xl border border-white/10 bg-[#0b1829] p-4"><div className="flex justify-between gap-4"><p className="font-medium">{action.action}</p>{action.requires_approval && <span className="text-xs text-amber-300">Approval</span>}</div><p className="mt-2 text-sm text-slate-400">{action.rationale}</p><p className="mt-3 text-xs text-slate-600">Owner · {action.owner}</p></div>)}</div></article>
  </div>;
}

export default App;
