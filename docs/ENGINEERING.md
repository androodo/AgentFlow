# Engineering walkthrough

## A 90-second explanation

AgentFlow is a local operations investigation platform for the fictional Northstar Shop. A user selects a scoped incident and asks a question. A planner routes to metrics, release, and support specialists. Those nodes use the official MCP Python SDK across a real HTTP service boundary to read PostgreSQL through an isolated source role.

The graph merges the resulting evidence by specialist. A deterministic auditor recomputes arithmetic from daily rows and checks source IDs and time windows. The composer produces observations, hypotheses, and evidence gaps. A LangGraph interrupt stores a draft for review. The review API commits a unique decision against the interrupt before the worker resumes. An approval and the finalized report are linked in PostgreSQL, so repeated requests and process restarts have bounded effects.

The default app uses rule-based decisions. Optional Ollama, OpenAI, or Claude inference selects routes, analyzes evidence, chooses bounded follow-up checks, and composes competing explanations within the same verification and approval constraints. A paired benchmark applies the same gold scenarios, tools, and policy to sequential and parallel variants. It isolates architecture in a small reproducible suite.

## Design tradeoffs

Sequential data collection is easier to debug and serves as the baseline. Parallel nodes reduce dependency waiting when inputs are independent, at the cost of reducer rules, trace ordering, and more simultaneous upstream work. The deterministic verifier provides a narrow, testable correctness envelope. The system represents ambiguous cases explicitly because combining signals into a narrative can otherwise overstate causes.

A durable queue in the application database reduces local setup and gives the scheduler a recoverable source of work. A broker with leases and delayed delivery would help run many cases and teams concurrently, at the cost of a second persistence system. The design favors a PostgreSQL session lock and idempotent mutations for this single-workstation stack.

## Interview questions

### 1. How does the planner decide what can run in parallel?

The plan selects domains and freezes the case's UTC windows before any query. The metrics, timeline, and support branches have disjoint evidence keys and independent read-only requests, so they can run in the same superstep. Single-domain cases execute only their selected node.

### 2. How do the branches join deterministically?

A reducer merges the branch dictionaries by disjoint keys. The next superstep audits the merged set. Observation order and tie-breaking use explicit domain logic instead of tool completion order. The benchmark changes scheduling while sharing the same evidence and audit logic.

### 3. Why give MCP its own process and credential?

The service boundary makes tool discovery, schema errors, network timeouts, and permissions measurable. Its database role reads only source tables. Client code limits which predefined calls each specialist can make.

### 4. How does the approval gate survive a restart?

The graph stores its review interrupt in a PostgreSQL checkpoint keyed by run UUID. Review decisions persist before resume. A restarted worker checks the snapshot and ledger to decide whether to resume or reconcile a completed graph into application state.

### 5. What happens if two reviewers click simultaneously?

The API locks the investigation row to verify status and the supplied interrupt. The ledger permits one decision per round and one per interrupt. The second request returns a conflict. Finalization references the actual approval ledger row.

### 6. How are percentage points and missing data handled?

Conversion uses summed purchases divided by summed starts. The delta uses unrounded ratios. The auditor recomputes it from daily rows. Coverage requires all expected UTC dates and segments. A missing window or zero denominator yields an unavailable rate.

### 7. How do the tools handle hostile source text?

The MCP service returns bounded source data. The UI renders excerpts as text. Model prompts operate on allowlisted facts and typed choices. Tool names and query parameters come from code and case scope, and the MCP credential limits the possible reads.

### 8. How would you measure agent quality fairly?

Use the same versioned case, windows, model, tool access, guardrails and budgets. Counterbalance which strategy runs first. Compare deterministic checks and measured timings and inspect failures. Evaluate model score agreement against separate rubric references and disclose their provenance.

### 9. What if a worker dies after inference or approval?

A graph node around a crash can replay external reads or inference. Decisions persist under unique constraints and the report write is idempotent. On resume the worker examines the checkpoint before deciding whether to invoke again. Extending the design across workers would require explicit ownership and retry accounting.

### 10. What evidence would establish causality for checkout?

Compare exposed and unexposed cohorts with the same segment and traffic mix. Align order and payment data at a finer time resolution. Use a controlled experiment or carefully designed rollback comparison when feasible. The report records temporal association and marks attribution as a hypothesis.
