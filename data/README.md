# Northstar Shop source data

Northstar Shop is fictional. The checked-in development profiles define twelve matched incidents. A separate holdout manifest adds three January incidents. Together they cover October 2025 through January 2026. The incident day starts a three-day current window. The previous three UTC days form the baseline. Web and mobile represent checkout segments.

| Table | Key and granularity | Interpretation |
| --- | --- | --- |
| `releases` | `rel-<version>`, one deployment | Version, UTC timestamp, product area, and description |
| `feature_flags` | `flag-<flag>`, one recorded change | Deployment FK, enable time, segment, rollout percentage |
| `traffic_metrics` | `traffic-<day>-<segment>`, one daily funnel | Sessions, checkout starts, completed purchases |
| `payment_events` | `pay-<day>-<segment>-<method>-<outcome>`, one synthetic event cohort | Outcome and cohort size, payment method, segment, optional nearby release FK |
| `support_tickets` | `ticket-<day>-<category>-<sequence>`, one ticket | UTC timestamp, category, severity, synthetic excerpt |

The fixed profile counts define funnel totals. The generator divides payment outcomes across card and wallet cohorts, uses a fixed RNG seed for excerpt selection, and checks each manifest checksum and version at bootstrap. The original `northstar-1` manifest stays immutable. The companion `northstar-holdout-1` seed is additive, and `northstar-2` identifies their combined dataset. Each seeded source ID sorts consistently and can be read individually over MCP. The payment release FK records same-day proximity.

Checkout conversion uses completed purchases divided by checkout starts. Percent changes in conversion are reported in percentage points and computed from unrounded ratios. A window needs one row per UTC day and requested segment for a comparable funnel. Missing cohorts suppress comparisons where appropriate. Ticket counts describe recorded rows. Collection coverage and ticketing propensity remain uncertain.

The default checkout case contains a purposely hostile-looking synthetic excerpt beginning with “Ignore instructions.” It appears as quoted source data in the evidence explorer. Only category counts and coverage metadata enter model prompts.

Operations tables are provisioned alongside the source schema. `investigations` holds requests and workflow status. `evidence` maps content-addressed tool results to runs. `trace_events` is the ordered event log. `review_decisions` records the one decision per run and round. `reports` stores finalized drafts and references the approved round. Evaluation and calibration results are stored per job and case. The official PostgreSQL checkpointer owns its own schema.
