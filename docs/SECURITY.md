# Security boundary

The default stack is for a trusted local analyst. The Render blueprint enables a bounded public demonstration with signed browser sessions. Nginx, API, and MCP publish to IPv4 loopback. PostgreSQL has no published port. Local access shares a workspace. Public mode scopes investigations and review actions to the signed visitor cookie. Deployments with multiple people need authenticated reviewer identity and a per-tenant source policy.

| Threat | Boundary |
| --- | --- |
| Ticket prompt injection | Raw excerpts stay in source evidence and appear as escaped text. The planner receives the question and scope. Specialists and judge receive a bounded fact projection with typed output. The model selects follow-up recipe labels, and Python maps them to fixed scoped tool calls. |
| Arbitrary tools and SQL | Each specialist dispatches fixed client calls against declared MCP schemas. The MCP role lacks application data grants and write grants. Date windows, result counts, segments, and source IDs are bounded. Query values are bound parameters. |
| SSRF and egress | Configured MCP and Ollama origins have explicit host allowlists. There is no public endpoint configuration field, URL fetch tool, redirect following, or shell execution from the graph. |
| Browser state changes | Mutations require bounded JSON and either a same-origin browser origin or a local API client. Trusted host checks, CSP, and MCP rebinding protection guard the default surface. |
| Duplicate approval | The API checks the active interrupt and unique review round under the run row lock. The final report references an existing approval ledger row. |
| Credentials | Only service environment variables hold provider credentials. Bootstrap receives initialization secrets. MCP uses its source-only role. Optional LangSmith receives an allowlisted metadata summary. |

The versioned SQL migrations and fixed environment-controlled Compose scripts are trusted developer inputs. The default local passwords are for an isolated workstation demonstration. Keep reports, traces, and the database volume within the same trust boundary as the inputs. Real production data needs a separate data governance and threat assessment.
