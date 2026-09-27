# Interview Submission Artifacts

## Sample runs

- `sample_runs/openai-approved-opp-1003/` contains a real OpenAI-backed run using
  `gpt-4o-mini`, including its structured brief, approval records, authorized evidence, and trace.
  The approval records show the human decision as `approved`.
- `sample_runs/openai-slack-opp-1001/` contains a fresh real OpenAI-backed run using
  `gpt-4o-mini`. Its brief includes generated Slack evidence and cites
  `slack:SLACK-1001-03`.
- `sample_runs/golden-slack-citation-opp-1001/` is explicitly a deterministic `FakeLLMProvider` golden
  case, not a live-model output. It verifies that a generated account-team update can support a
  finding and that the brief cites its stable `SLACK-1001-*` evidence ID.
- `sample_runs/unauthorized-denial.md` records the safe denial response. No run directory is
  created for this case because authorization stops the graph before retrieval.
- The complete candidate-generated synthetic update dataset remains at
  `../synthetic_data/slack/account_team_updates.tsv`.

The live samples demonstrate both the normal brief path with a generated Slack citation and the
restricted-opportunity approval path. The deterministic golden case remains separately so the
same behavior can be regression-tested without spending tokens. Never include `.env` or API keys
in these artifacts.

## 15-minute walkthrough

See [interview-walkthrough.pdf](interview-walkthrough.pdf). The deck distinguishes the
live-provider samples from deterministic evaluation results.
