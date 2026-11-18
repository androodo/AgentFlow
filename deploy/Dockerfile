FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home agentflow
COPY backend backend
COPY mcp-server mcp-server
COPY data data
COPY eval eval
COPY deploy/serve.py deploy/serve.py
COPY --from=web /web/dist /app/static
ENV AGENTFLOW_STATIC_DIR=/app/static MCP_URL=http://127.0.0.1:8002/mcp
USER agentflow
EXPOSE 10000
CMD ["python", "deploy/serve.py"]
