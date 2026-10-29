#!/usr/bin/env bash
# make dev: the API and the studio and kiosk workers as three Python processes, plus both SPAs via Vite (no
# Docker), GENAI_PROFILE=mock. Kiosk http://127.0.0.1:5173, Studio http://127.0.0.1:5174/studio/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export GENAI_PROFILE="${GENAI_PROFILE:-mock}" PYTHONPATH="$ROOT:$ROOT/mock-server:$ROOT/packages/core/python:$ROOT/packages/library/python"
PY="${PY:-$ROOT/.venv/bin/python}"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
"$PY" -m backend.api --port "${API_PORT:-8000}" & pids+=($!)
"$PY" -m backend.worker --queue studio & pids+=($!)
"$PY" -m backend.worker --queue kiosk & pids+=($!)
(cd apps/kiosk && npm run -s dev -- --port 5173) & pids+=($!)
(cd apps/studio && npm run -s dev -- --port 5174) & pids+=($!)
echo "PetPop dev: kiosk http://127.0.0.1:5173  studio http://127.0.0.1:5174/studio/  API http://127.0.0.1:${API_PORT:-8000}/api/v1/docs  (GenAI profile $GENAI_PROFILE)"
echo "Studio logins: operator, curator, admin; password in var/.petpop_studio_password unless PETPOP_STUDIO_PASSWORD is set"
wait -n
