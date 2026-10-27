#!/usr/bin/env bash
cd "$(dirname "$0")/.."
exec .venv/bin/python -m uvicorn hub.server:app --host 0.0.0.0 --port 8000
