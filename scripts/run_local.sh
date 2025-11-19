#!/usr/bin/env bash
export $(grep -v '^#' .env | xargs)
uvicorn server.main:app --host ${MCP_HOST:-0.0.0.0} --port ${MCP_PORT:-9999} --reload
