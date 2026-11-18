FROM python:3.13-slim AS runtime
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home agentflow
COPY backend backend
COPY mcp-server mcp-server
COPY data data
COPY eval eval
USER agentflow

FROM runtime AS verify
USER root
COPY requirements-dev.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests tests
COPY scripts/verify-backend.sh scripts/verify-backend.sh
ENV RUFF_NO_CACHE=true MYPY_CACHE_DIR=/tmp/mypy
USER agentflow
