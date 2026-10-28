#!/usr/bin/env bash
# make dev: API and worker as two Python processes plus the SPA via Vite (no Docker), PETPOP_MODE=mock.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PETPOP_MODE="${PETPOP_MODE:-mock}" PYTHONPATH="$ROOT:$ROOT/mock-server"
PY="${PY:-$ROOT/.venv/bin/python}"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
"$PY" -m backend.api --port "${API_PORT:-8000}" & pids+=($!)
"$PY" -m backend.worker & pids+=($!)
(cd apps/kiosk && npm run -s dev -- --port 5173) & pids+=($!)
echo "PetPop dev: kiosk http://127.0.0.1:5173  API http://127.0.0.1:${API_PORT:-8000}/api/v1/docs  (mode $PETPOP_MODE)"
wait -n
