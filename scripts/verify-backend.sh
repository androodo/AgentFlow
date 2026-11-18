#!/usr/bin/env sh
set -eu
python -m ruff check backend mcp-server tests
python -m ruff format --check backend mcp-server tests
python -m mypy backend mcp-server
python -m pip check
python -m pytest -q -p no:cacheprovider
