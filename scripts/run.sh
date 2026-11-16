#!/usr/bin/env bash
# Start the Whyscope hub on 0.0.0.0:${WHYSCOPE_PORT:-8000}. Serves HTTPS when certs/cert.pem and certs/key.pem exist
# (create them with: python3 scripts/make_cert.py), so phones can use the microphone and camera.
cd "$(dirname "$0")/.."
PORT="${WHYSCOPE_PORT:-8000}"
SSL=()
if [ -f certs/cert.pem ] && [ -f certs/key.pem ]; then
  SSL=(--ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem)
  echo "HTTPS on port $PORT"
else
  echo "HTTP on port $PORT (phones cannot use the microphone; run scripts/make_cert.py for HTTPS)"
fi
exec .venv/bin/python -m uvicorn hub.server:app --host 0.0.0.0 --port "$PORT" "${SSL[@]}"
