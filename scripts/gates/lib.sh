# Shared helpers for scripts/gates/gate-N. Each step prints PASS/FAIL; the gate fails on the first FAIL.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export GENAI_PROFILE="${GENAI_PROFILE:-mock}"
export PYTHONPATH="$ROOT:$ROOT/mock-server"
PY="${PY:-$ROOT/.venv/bin/python}"
LOG_DIR="$ROOT/var/gates"
mkdir -p "$LOG_DIR"

step() {
  local name="$1"; shift
  local log="$LOG_DIR/$(echo "$name" | tr -c 'a-zA-Z0-9' '_' | cut -c1-60).log"
  local t0=$SECONDS
  if "$@" >"$log" 2>&1; then
    printf '  [PASS] %s (%ss)\n' "$name" "$((SECONDS - t0))"
  else
    printf '  [FAIL] %s (%ss) - log: %s\n' "$name" "$((SECONDS - t0))" "${log#$ROOT/}"
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
