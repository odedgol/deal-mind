# Interview Submission Artifacts

## Sample runs

- `sample_runs/openai-approved-opp-1003/` contains a real OpenAI-backed run using
  `gpt-4o-mini`, including its structured brief, approval records, authorized evidence, and trace.
  The approval records show the human decision as `approved`.
- `sample_runs/golden-slack-citation-opp-1001/` is explicitly a deterministic `FakeLLMProvider` golden
  case, not a live-model output. It verifies that a generated account-team update can support a
  finding and that the brief cites its stable `SLACK-1001-*` evidence ID.
- `sample_runs/unauthorized-denial.md` records the safe denial response. No run directory is
  created for this case because authorization stops the graph before retrieval.
- The complete candidate-generated synthetic update dataset remains at
  `../synthetic_data/slack/account_team_updates.tsv`.

The OpenAI sample predates the strengthened Slack-citation prompt and therefore demonstrates the
live brief and approval workflow, not a live Slack citation. Before the interview, rotate the
local API key and create a fresh live `OPP-1001` sample to replace or supplement the deterministic
golden case. Never include `.env` or API keys in these artifacts.

## 15-minute walkthrough

See [interview-walkthrough.pptx](interview-walkthrough.pptx). The deck includes timing and
speaker notes, and distinguishes the live-provider sample from deterministic evaluation results.
