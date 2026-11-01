# Shared helpers for scripts/gates/gate-N. Each step prints PASS/FAIL; the gate fails on the first FAIL.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export GENAI_PROFILE="${GENAI_PROFILE:-mock}"
export PYTHONPATH="$ROOT:$ROOT/mock-server:$ROOT/packages/core/python:$ROOT/packages/library/python"
PY="${PY:-$ROOT/.venv/bin/python}"
LOG_DIR="$ROOT/var/gates"
mkdir -p "$LOG_DIR"

step() {
  local name="$1"; shift
  local log="$LOG_DIR/$(echo "$name" | tr -c 'a-zA-Z0-9' '_' | cut -c1-60).log"
  local t0=$SECONDS
  # A stuck step fails after PETPOP_GATE_STEP_TIMEOUT seconds (default 30 min) instead of hanging the gate. macOS
  # has no `timeout` unless coreutils is installed (gtimeout); without either, steps run unbounded.
  local limit="${PETPOP_GATE_STEP_TIMEOUT:-1800}" tmo=()
  if command -v timeout >/dev/null; then tmo=(timeout -k 15 "$limit"); elif command -v gtimeout >/dev/null; then tmo=(gtimeout -k 15 "$limit"); fi
  if ${tmo[@]+"${tmo[@]}"} "$@" >"$log" 2>&1; then
    printf '  [PASS] %s (%ss)\n' "$name" "$((SECONDS - t0))"
  else
    printf '  [FAIL] %s (%ss) - log: %s\n' "$name" "$((SECONDS - t0))" "${log#$ROOT/}"
    [ "$((SECONDS - t0))" -ge "$limit" ] && [ -n "${tmo[*]-}" ] && echo "        (stopped after ${limit} s: PETPOP_GATE_STEP_TIMEOUT)"
    tail -n 25 "$log" | sed 's/^/        /'
    echo "GATE FAILED"
    exit 1
  fi
}

skip_without_genai_host() {
  if [ "$GENAI_PROFILE" = "mock" ]; then
    echo "gate-$1: SKIPPED (needs a GenAI host)"
    exit 0
  fi
}

wait_http() {  # wait_http URL SECONDS
  for _ in $(seq 1 "$2"); do curl -fsS "$1" >/dev/null 2>&1 && return 0; sleep 1; done
  return 1
}
