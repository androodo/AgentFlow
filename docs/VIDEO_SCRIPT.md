# AgentFlow video narration

The captions are part of the video, so narration is optional. Leave short pauses while the viewer reads the interface. Use the chapter times in the generated video details file.

**Opening.** AgentFlow investigates operations incidents using evidence, from the initial question through a reviewed report.

**Start an investigation.** This case is set at Northstar Shop, a fictional retailer. Checkout conversion fell around a mobile checkout release. The recording uses synthetic records and rule-based decisions with no LLM calls.

**Workflow and MCP calls.** LangGraph routes the case to metrics, release, and support specialists. Here is the actual MCP call comparing two checkout windows. The activity log shows the dates requested and the evidence identifier returned. The audit checks the arithmetic, scope, and provenance before the draft appears.

**Trace a finding to its source.** Conversion moved from 82.86 percent to 68.86 percent. Follow the citation to an original mobile traffic record. The release record puts the deployment on the timeline. Payment authentication failures are the leading hypothesis, and we would need exposure data or a controlled test to establish cause.

**Human review.** The final report stays locked while the draft waits at a saved checkpoint. The reviewer can open the evidence, request a revision, reject the report, or approve it. This approval is recorded in the review history.

**Approved report.** The approved report preserves the findings, citations, and limitations. The Markdown export contains both the source evidence and the approval.

**Reproducible evaluation.** The comparison runs the same 15 cases under the sequential baseline and the parallel graph. This run scores both workflows with deterministic checks. No LLM judge was used.

**Engineering takeaway.** AgentFlow brings together LangGraph orchestration, read-only MCP tools, evidence validation, and durable human review.
