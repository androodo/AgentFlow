# AgentFlow evaluation

The versioned development catalog and separate held-out catalog defines a natural-language question, UTC windows, segment, expected route, reference source IDs, hand-calculated funnel totals, and an expected evidence-based finding. The task hash covers the catalog row and dataset version. Expected answers are authored from the source profiles.

## Paired procedure

1. Start the local stack and open **Evaluations**. Select **Compare both** and **Demo (no LLM)**.
2. Each case runs with the same scoped inputs, provider, read-only tool calls, verifier, composer rules, and checkpoint. The baseline analyst queries selected domains sequentially. Specialist nodes query their selected domains in the same LangGraph superstep.
3. Presentation order alternates which strategy runs first for each case. Each strategy gets up to twelve tool calls, including one model-selected follow-up per domain, and one transport retry per collection. The total attempted tool budget is twenty-four. Both receive the same logical model-call and response budgets. The benchmark answers the approval interrupt in an isolated checkpoint thread. That review is a named fixture and creates zero investigation reports.
4. Inspect arithmetic and coverage, evidence IDs, expected route and time windows, key findings, uncertainty, tool boundaries, and the approval gate. Support-only cases report arithmetic as N/A. Failed calls and model parsing errors remain visible.
5. Export JSON for exact timings, strategy, dataset and task hashes, observed values, references and checks. A live local experiment also records model ID, prompt templates, step limits, and provider-reported tokens where observed.

The elapsed time includes graph execution and checkpoint access. It excludes queue wait, optional scoring, and trace upload. Comparisons for this small, fixed suite are descriptive. Demo variants share calculation and interpretation rules, so their passing results primarily measure routing and execution correctness. Live variants compose their own explanations from actual evidence and can fail the reference graders. Three additional held-out fixtures were authored separately after the original implementation, with expected results derived from source counts. Their results are displayed separately. They still need independent review.

## Optional model judge

Configure `OLLAMA_JUDGE_MODEL` and opt in per benchmark or run **Judge calibration** on its own. The configured model returns integer scores from 1–5 for groundedness, completeness, and clarity, along with a rationale and supporting evidence IDs. Each axis has five explicit anchors in the implementation. The scorecard must parse strictly and can cite only supplied IDs. Invalid results are shown as errors. Deterministic checks and judge scores are reported independently.

The calibration set has 20 project-authored reference annotations over four evidence contexts. Reviewers can inspect each score and replace the reference annotations with independently human-reviewed labels in a new reference version. Reported agreement consists of exact-match counts and mean absolute score error among successfully scored cases, with per-snippet rationales. The current references have no independent human review. Without a configured judge, the dashboard reads **Not run: configure an LLM judge**.
