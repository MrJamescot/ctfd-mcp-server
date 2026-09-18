#!/usr/bin/env bash
# Run the optional FastAPI REST interface locally.
# Usage: ./scripts/run_local.sh   (reads .env if present)
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a
exec uvicorn server.main:app --host "${MCP_HOST:-0.0.0.0}" --port "${MCP_PORT:-8000}" --reload