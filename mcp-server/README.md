# Northstar Shop MCP

This is an independent Streamable HTTP endpoint using the official Python SDK. It uses the source-only PostgreSQL role. Start just PostgreSQL, the bootstrap, and MCP with docker compose up --build -d --wait mcp. Then connect a Streamable HTTP client to http://127.0.0.1:8002/mcp. Host port is configurable through MCP_PORT.

Every tools/call takes an outer request object. Windows contain inclusive UTC start and end ISO dates. Metric queries accept an optional segment of all, web, or mobile. Compare accepts nonoverlapping baseline and current windows. Tool output includes stable content-addressed evidence IDs and source IDs. Get a specific row with get_evidence_record and an evidence_id equal to its source ID.

For a host Python process, install requirements.txt, set PYTHONPATH to backend and DB_HOST, DB_PORT, DB_USER=agentflow_reader, and DB_PASSWORD to the bootstrapped credentials. Run python mcp-server/server.py from the repo root. Compose keeps PostgreSQL internal by default.
