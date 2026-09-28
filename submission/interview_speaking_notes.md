# Strategic Deal Intelligence: 15-minute interview script

Prepared for Oded Goldberg's Cato Networks interview. Matches the nine slides in
`interview_walkthrough.pdf` and `interview_walkthrough.pptx`.

Read the quoted paragraphs aloud. Presenter notes, the glossary, and the follow-up
answers are rehearsal material, not part of the speech. Timing includes pointing
at diagrams and operating the demo. Rehearse once with a timer; do not read every
label on a slide.

## Timing

| Slide | Topic | Time | Finish by |
|---|---|---|---|
| 1 | Introduction | 0:45 | 0:45 |
| 2 | Business problem | 1:00 | 1:45 |
| 3 | Architecture | 2:00 | 3:45 |
| 4 | Authorization | 1:45 | 5:30 |
| 5 | Agents and their connections | 2:00 | 7:30 |
| 6 | Evaluation | 1:45 | 9:15 |
| 7 | Production evolution | 2:00 | 11:15 |
| 8 | Demonstration | 3:00 | 14:15 |
| 9 | Closing | 0:45 | 15:00 |

## Slide 1: Strategic Deal Intelligence Assistant

> Hi, I'm Oded. I'll walk you through the Strategic Deal Intelligence Assistant I built for this assignment.
>
> The user selects an opportunity, and the system prepares a negotiation brief using the information that user is allowed to access.
>
> My main engineering focus was controlling the model's environment: which evidence it receives, how its outputs become structured recommendations, and when a human must review them.
>
> I'll explain the architecture and the security boundary, show how the agents collaborate, and finish with three different outcomes in the demo. I'll also separate what works in the local prototype from what I would add for production.

Presenter cue: Establish the purpose before naming frameworks. Speak calmly. This
is an engineering walkthrough, not a claim that the prototype is production-ready.

## Slide 2: From Fragmented Context to Decision Support

> The starting problem is that the information about a deal lives in different places.
>
> Salesforce provides structured facts about the opportunity. Gong provides conversations. Slack contains updates that may change our understanding of those conversations. Pricing information and Deal Desk policy constrain possible recommendations.
>
> A salesperson needs to combine these sources before deciding what to do next. The assistant produces a brief with the deal state, buyer concerns, stakeholders, risks, and recommended actions. It also identifies missing information and provides evidence references.
>
> For example, a Slack update may say there is uncertainty about whether a dashboard was accepted. A useful brief should surface that uncertainty and recommend clarification, rather than quietly choose a convenient version.
>
> The current sources are a static, synthetic dataset. The reasoning can use a live model. Those are separate properties of the system.

Presenter cue: Point once to the source list and once to the brief. Avoid implying
that live Salesforce, Gong, or Slack connectors are implemented.

## Slide 3: Local Prototype Architecture

> Let me follow one request through the system.
>
> The CLI, API, or demo UI provides an opportunity ID and a requester ID. The application creates fresh state for that run and invokes a compiled LangGraph workflow.
>
> The graph controls the execution order. First it checks authorization. If access is denied, it stops before evidence retrieval and model generation.
>
> For an authorized request, an evidence service searches Qdrant with permission and deal filters. Within that permitted scope, retrieval combines semantic similarity with lexical relevance. The implementation takes a dense candidate shortlist, applies BM25-style lexical scoring, and combines ranks using reciprocal rank fusion, or RRF. It also considers freshness and source reliability.
>
> That gives the agents evidence records with text, metadata, and stable IDs. The model later uses those IDs when citing its findings.
>
> Specialist branches analyze the deal. The strategy stage combines their outputs, then validation and approval handling determine the final result. The application saves the brief and execution traces.
>
> I separated orchestration from services, and services from repositories. The graph expresses the business flow without managing Qdrant clients or file paths.
>
> The compiled graph and appropriate read dependencies are reusable, while evidence diagnostics and request state stay isolated per run. Local approval records persist, but durable graph checkpointing is a production extension.

Presenter cue: Say **RRF**, even though the slide says “RAF.” Do not describe the
current ranker as a learned cross-encoder or claim independent corpus-wide sparse
and dense searches. The exact parallel branch structure is clearer on slide 5.

## Slide 4: Authorization Before Evidence Reaches the Model

> This is the most important boundary in the design.
>
> The system loads the opportunity and the requester's permission profile. It checks whether the user can access that account and, if applicable, restricted information.
>
> A successful check creates an authorization decision. Retrieval uses that decision to enforce the opportunity ID, account ID, allowed source types, and permitted access levels together.
>
> Finding an opportunity ID alone is not enough. Relevance and permission are different questions. A document can be highly relevant and still be forbidden for this user.
>
> Shared policy documents follow an explicit policy retrieval path. They do not give the search unrestricted access to other opportunities.
>
> Tools retain the authorization decision when they perform additional searches. A model-generated query cannot choose its own permissions.
>
> This is least privilege in practice: each request receives only the evidence its authorization allows. An unauthorized request gets a clean denial rather than a partial answer containing protected information.
>
> The prototype uses supplied user IDs for demonstration. In production, authenticated identity would come from a trusted identity layer, and current permissions would come from an authoritative service.

Presenter cue: Point to DENY first, then ALLOW. Do not confuse permission checking
with implemented SSO or authentication of the supplied demo user ID.

## Slide 5: Specialized Agents, One Strategic Brief

> After retrieval, the graph passes an opportunity and an initial evidence list into the specialist branches.
>
> Deal Context produces canonical CRM facts. This part is deterministic. I do not need a language model to repeat the opportunity's stage or owner.
>
> Conversation Intelligence uses the model to identify buyer goals, objections, and unresolved issues. Stakeholder Map uses the model to identify decision makers, champions, blockers, and gaps in our knowledge.
>
> The branches can enrich their context through authorized tools. For example, an evidence search tool calls the evidence service, records the search trace, and remembers the evidence it returned. Tracing is an additional responsibility; the tool actually retrieves data.
>
> The graph waits for the specialist outputs and merges their evidence by evidence ID. Negotiation Strategy then receives those findings and the combined evidence. It can also receive the applicable shared policy before asking the model for recommended actions.
>
> We normally have three generation calls: conversation analysis, stakeholder analysis, and strategy. Repairs or retries can add calls.
>
> The model returns structured content that we parse into Pydantic models. Code checks citations and applies approval handling before assembling the final brief.
>
> Tool execution is controlled by Python and the graph. This implementation does not let the model freely choose and execute arbitrary tools. That makes the behavior easier to inspect and test.

Presenter cue: Trace the parallel branches, their join, and the strategy stage.
Do not say that each agent shares and mutates one global context.

## Slide 6: Evaluation, Can I Trust the Behavior?

> I evaluate specific failure modes, because a fluent answer by itself tells us very little about system correctness.
>
> The golden suite covers authorized and denied workflows, required evidence, and quality scenarios such as conflicts, sensitive recommendations, and prompt injection attempts.
>
> The reported ten out of ten result is the deterministic golden evaluation. Seven synthetic Slack updates were indexed, and the checks verified Slack citations where required. The denied scenario returned no restricted evidence.
>
> These numbers describe the tested cases. They are not a claim of universal security or perfect answer accuracy.
>
> Citation validation checks that referenced evidence IDs belong to the evidence available to the run, and checks required citation presence. That gives us traceability. It does not prove that every sentence logically follows from the cited text. Semantic support needs a separate evaluation layer.
>
> FakeLLM makes control-flow regression tests fast and repeatable without generation charges. Separate saved live-provider runs demonstrate real model execution. Passing the fake tests does not establish live model quality.
>
> I would keep fast deterministic checks on each change and use a budgeted live evaluation suite for model or prompt changes. Production evaluation would also measure retrieval recall, unsupported claims, latency, and cost.

Presenter cue: Do not read “10/10 citations validated” as exactly ten individual
citations. The results document reports evaluation cases. The backend pytest count
is a separate metric: 62 tests passed locally after the cold-start fix.

## Slide 7: What Breaks in Production?

> The local prototype validates the workflow. Production introduces a continuously changing data environment.
>
> I would separate the online request path from background ingestion. Connectors would receive source updates through webhooks or polling, and workers would consume queued events to update the index.
>
> The ingestion design must handle duplicate events, retries, deletes, and changes to permissions. Idempotency means that processing the same update twice does not create two conflicting records. Checkpoints and replay make recovery possible after a failure.
>
> That creates eventual consistency: a source update may take time to become searchable. I would expose freshness and monitor ingestion lag. Sensitive access decisions require stronger safeguards, including current authorization checks and prompt cache invalidation when access changes.
>
> Older information should remain available. A hot index can serve frequent searches, while historical search can use a separate index or an explicit restore path. Saving raw files in S3 alone does not make them semantically searchable.
>
> For long-running requests, the API can acknowledge quickly and let a worker deliver the result later. In Slack, that means a later message or update, not holding a socket open for the whole generation.
>
> The proposed AWS components support those responsibilities. They are a production target, not infrastructure deployed by this assignment. I would also add durable workflow state, tenant isolation, and operational alerts before calling this production-ready.

Presenter cue: Point to the online and ingestion paths. Do not spend the time
reading every AWS service name. Keep the focus on failure recovery and freshness.

## Slide 8: Live Demo, Three Requests, Three Deliberate Outcomes

Allow approximately 90 seconds for the spoken text and 90 seconds for navigation,
response time, and pointing at evidence. If generation takes too long, use a saved
live run and explicitly identify it as a saved run.

### First request: authorized standard opportunity

Operator: Select `USR-5001` and `OPP-1001`. Show the brief, a recommendation,
and its source evidence. Use a prepared result if needed.

> First, this requester is authorized for the standard opportunity. The system produces a brief and lets us inspect the evidence behind its recommendations.
>
> Here is the concrete chain I want to demonstrate: a synthetic Slack update becomes a retrieved evidence item, and the generated output cites that item. In the saved live example, the strategy recommends clarifying the dashboard's delivery status because the Slack update flags a possible conflict.
>
> That example demonstrates retrieval and use of the update. It does not claim that the model independently discovered a contradiction that was never stated in the source.

### Second request: authorized restricted opportunity

Operator: Select `USR-5003` and `OPP-1003` in the normal API/UI flow. Show
pending approval. If time permits, switch to eligible reviewer `USR-5005` and
show the approval decision. Do not use a pre-approved artifact as proof of a
reviewer interaction.

> This user can access the restricted opportunity, but access to information and authority to approve an action are separate decisions.
>
> The result requires human review. An eligible reviewer can approve or reject it through the approval flow. The application records that decision. The prototype does not execute an external commercial action such as updating Salesforce or sending a customer offer.

### Third request: unauthorized requester

Operator: Select `USR-5007` and `OPP-1003`. Show denial. Do not display another
user's previous brief as if it belongs to the denied response.

> Now I keep the opportunity the same and change the user. This request is denied before evidence retrieval and model generation.
>
> So the same application deliberately supports three outcomes: an ordinary brief, a result requiring review, and a clean denial. Those outcomes come from explicit workflow rules.

Demo fallback: Open the relevant files in `submission/sample_runs/` and say,
“This is a saved execution with the live provider.” The restricted saved run
`openai-approved-opp-1003` supplied approval explicitly to the workflow. It is not
a recording of the API reviewer interaction. The Slack-style UI is a demo UI,
not a connected Slack application.

## Slide 9: Questions

> To summarize, the project turns permitted evidence into a structured negotiation brief with traceable recommendations.
>
> The main design decisions were to enforce access before retrieval, isolate specialist responsibilities, and validate the outputs before presenting a result or requesting human review.
>
> The tests and saved live runs give us concrete examples to inspect, while the production plan identifies the remaining work around changing data and distributed execution.
>
> For this interview, I would be happy to go deeper into the authorization filters, the agent context and tool flow, or the trade-offs in moving from a local snapshot to production. Thank you.

## Buzzwords you can explain with your own code

Use a term when it helps answer a question. Follow it with what it means here.

| Term | Plain explanation | Project connection |
|---|---|---|
| RAG | Retrieve relevant evidence before generation | Qdrant results become model context |
| Least privilege | Give the request only the access it needs and is entitled to | Account, opportunity, source, and access filters |
| Fail closed | Stop when permission cannot be established | Denial before evidence search and generation |
| Deterministic orchestration | Code decides which steps run and in what order | LangGraph nodes and conditional edges |
| Fan-out / fan-in | Run independent branches, then wait and combine | Specialists join before strategy |
| Typed contracts | Explicit shapes for inputs and outputs | TypedDict graph state and Pydantic domain/output models |
| Dependency injection | Supply collaborators from outside the workflow | Injected services and repository provider |
| Evidence provenance | Preserve where a statement's supporting material came from | Evidence IDs and source metadata |
| RRF | Combine ranked lists using positions instead of comparing incompatible scores directly | Semantic and lexical rankings within the candidate set |
| Human in the loop | Require a person for a decision the system should not finalize alone | Approval records and reviewer decisions |
| Observability | Make an execution explainable after it happens | Run IDs, tool/agent traces, usage and artifacts |
| Idempotency | Repeating an operation has the same intended effect | Proposed safe replay of ingestion updates |
| Eventual consistency | Updates reach the search index after some delay | Proposed asynchronous ingestion |
| Cache invalidation | Stop reusing data when it is no longer valid | Production permission revocations and source refresh |
| Golden set | A fixed collection of representative cases with expectations | Ten deterministic evaluation cases |

## Likely follow-up questions and precise answers

### Why multiple agents instead of one large prompt?

“They separate responsibilities and give me outputs I can test independently.
Conversation analysis and stakeholder analysis can run concurrently, and strategy
combines them afterward. The trade-off is extra calls and orchestration complexity.
I would compare against a single-prompt baseline before claiming higher quality.”

### Are these autonomous agents?

“They are specialized components in a controlled workflow. Some use an LLM and one
produces deterministic facts. Python controls the tools and graph transitions.
I did not implement unrestricted autonomous tool selection.”

### If opportunity ID already selects the records, why semantic search?

“Metadata filters determine the permitted candidate scope. Ranking selects the
most useful evidence within it. With a tiny dataset we could send everything,
but a larger deal can contain more text than the useful context and token budget.
Retrieval trades off recall against context size.”

### Does your citation validator prevent hallucinations?

“It rejects missing or unauthorized evidence references and enforces citation
requirements. A valid ID does not prove that the associated claim is supported.
I would add semantic-support evaluation and review failure cases separately.”

### Does the newest document always win a conflict?

“No. Freshness is a ranking signal where event dates are available. A newer source
can still be wrong or describe a different scope. The system should surface
uncertainty and ask for clarification when the evidence does not resolve it.
Date coverage also needs to be consistent across ingestion loaders.”

### Why FakeLLM if the system is supposed to use a real model?

“It makes workflow tests repeatable and avoids generation charges during ordinary
regression checks. It cannot measure real model reasoning. That is why live runs
and a budgeted live evaluation set are a separate part of verification.”

### Could recorded model responses replace live tests?

“They could accelerate regression checks, provided fixtures are versioned against
the relevant request, prompt and model configuration. Replay validates behavior
with an old response, not current provider behavior. I would retain live canaries
and deliberately refresh recordings after changes. FakeLLM is not a recording.”

### What caused the latest CI failure?

“A refactor initialized the evidence repository during module import. My machine
already had an index, but a clean runner did not, so test collection failed before
fixtures could run. I changed setup to supply a lazy, cached repository provider.
I also added subprocess tests for cold startup, fresh ingestion, and repeated
missing-index errors. The fix removes the hidden dependency on developer state.”

### Does a cached repository mix users' data?

“The reusable repository is a read dependency, not a cache of authorized answers.
Each operation receives its own authorization decision, and each run has separate
state and diagnostics. Production refresh and resource lifetime need explicit
management. A process-local cache is not a distributed consistency mechanism.”

### What is the first production security change?

“Bind requests to authenticated identity rather than accepting a demo user ID,
and use authoritative permissions. Cache those decisions only with bounded
staleness and revocation handling. Carry tenant and authorization boundaries
through retrieval, artifacts, approval access, and diagnostic endpoints.”

## Accuracy reminders before presenting

- Say **RRF**, not the slide's “RAF.”
- The diagram's local “checkpoints” label is too broad: current approval/artifact
  persistence does not establish durable LangGraph checkpoint/resume support.
- The golden result uses FakeLLM. Saved live samples are separate evidence.
- Zero leakage means zero in the evaluated denial scenario, not a universal proof.
- No deployed AWS architecture, real Slack connector, or external action execution
  is demonstrated by this prototype.
- The source dates belong to a fixed synthetic snapshot. Do not describe its
  April deadlines as upcoming real-world deadlines.
- Keep the explanations concrete. You do not need to name every design pattern.
