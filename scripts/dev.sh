#!/usr/bin/env bash
# make dev: the API and the studio and kiosk workers as three Python processes, plus both SPAs via Vite (no
# Docker), GENAI_PROFILE=mock unless set. Works with macOS's bash 3.2. Kiosk http://127.0.0.1:5173, Studio http://127.0.0.1:5174/studio/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export GENAI_PROFILE="${GENAI_PROFILE:-mock}" PYTHONPATH="$ROOT:$ROOT/mock-server:$ROOT/packages/core/python:$ROOT/packages/library/python"
PY="${PY:-$ROOT/.venv/bin/python}"
"$ROOT/scripts/stop.sh" --quiet   # a previous run's leftovers would hold the ports
EXITED="$(mktemp -t petpop-dev.XXXXXX)"
# Stop everything we started, Vite's node processes included (they run below npm, so kill the process group).
cleanup() { trap - EXIT INT TERM; rm -f "$EXITED"; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM
# Each process notes its own exit in $EXITED; the loop below watches that file.
start() { local name="$1"; shift; ( "$@" || true; echo "$name" >> "$EXITED" ) & }
start api "$PY" -m backend.api --port "${API_PORT:-8000}"
start "studio worker" "$PY" -m backend.worker --queue studio
start "kiosk worker" "$PY" -m backend.worker --queue kiosk
start kiosk bash -c 'cd apps/kiosk && exec npm run -s dev -- --port 5173'
start studio bash -c 'cd apps/studio && exec npm run -s dev -- --port 5174'
echo "PetPop dev: kiosk http://127.0.0.1:5173  studio http://127.0.0.1:5174/studio/  API http://127.0.0.1:${API_PORT:-8000}/api/v1/docs  (GenAI profile $GENAI_PROFILE)"
echo "Studio logins: operator, curator, admin; password in var/.petpop_studio_password unless PETPOP_STUDIO_PASSWORD is set"
# Run until any process exits, then stop the rest. A polling loop, not `wait -n`: macOS ships bash 3.2, which has
# no `wait -n` (it failed at once there and left the SPAs running without an API).
while [ ! -s "$EXITED" ]; do sleep 1; done
echo "PetPop dev: the $(head -1 "$EXITED") process stopped; stopping the rest (its error is above)" >&2
exit 1
