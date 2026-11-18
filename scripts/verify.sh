#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
bash scripts/demo.sh
docker compose --profile verify run --build --rm --no-deps verify
if python3 --version >/dev/null 2>&1; then
    python3 scripts/proof.py
elif python --version >/dev/null 2>&1; then
    python scripts/proof.py
else
    printf '%s\n' 'Host Python is unavailable. Seed fingerprint, restart, and outage proof skipped.'
fi
if command -v npm >/dev/null; then
    export AGENTFLOW_WEB_URL="http://$(docker compose port web 8080)"
    npm --prefix web ci --no-audit --no-fund
    npm --prefix web run build
    if [[ "${AGENTFLOW_BROWSER_WITH_DEPS:-0}" == 1 ]]; then
        npm --prefix web exec -- playwright install --with-deps chromium
    else
        npm --prefix web exec -- playwright install chromium
    fi
    npm --prefix web test
else
    printf '%s\n' 'Host Node/npm is unavailable. Docker built the frontend. Playwright skipped.'
fi
printf '%s\n' 'AgentFlow verification finished. Review the command results and any explicit skips above.'
