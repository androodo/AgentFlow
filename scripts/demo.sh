#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ -f .env ]] || cp .env.example .env
docker compose up --build -d --wait --wait-timeout 180
web=$(docker compose port web 8080)
api=$(docker compose port api 8001)
mcp=$(docker compose port mcp 8002)
curl --fail --silent --show-error "http://${api}/readyz"
printf '\nOpen http://%s\nAPI docs http://%s/docs\nMCP endpoint http://%s/mcp\n' "$web" "$api" "$mcp"
printf '%s\n' 'Click Try demo: Checkout Conversion Drop, open the cited draft, approve it, and download Markdown.'
