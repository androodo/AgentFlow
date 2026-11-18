# AgentFlow contributor notes

AgentFlow analyzes synthetic Northstar Shop data. Keep the first run deterministic and label that mode in storage, API responses, traces, and the UI.

- Run Docker Compose from the repository root. Use scripts/doctor.ps1, scripts/demo.ps1, and scripts/verify.ps1 on Windows.
- Keep tool inputs bounded and read-only. Never pass raw ticket excerpts to a model or let a model construct SQL, URLs, or dispatch tool names.
- Preserve decimal/denominator semantics and reproducible source IDs. Treat missing days as unknown data.
- Use a unique LangGraph thread per investigation. Store decisions before calling Command and finalize approved reports in a database transaction. Add a migration for schema changes.
- Keep optional model and tracing integrations disabled by default. Record only executed verification in docs/VERIFICATION.md. Keep local secrets and generated caches out of Git.
