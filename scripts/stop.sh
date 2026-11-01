#!/usr/bin/env bash
# make stop: stop every `make dev` process of this checkout (API, workers, Vite and its esbuild), including ones a
# crashed or interrupted run left behind. Matches on this repo's own paths, so other projects' servers are safe.
# Works on macOS (bash 3.2, BSD pkill) and Linux. `make dev` runs it first.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATTERN="$ROOT/(\.venv/bin/python[0-9.]* -m (backend|mock_server)|node_modules/)"
quiet="${1:-}"
list() { pgrep -f "$PATTERN" 2>/dev/null | grep -v "^$$\$" || true; }
pids="$(list)"
if [ -z "$pids" ]; then
  [ "$quiet" = "--quiet" ] || echo "PetPop: nothing running"
  exit 0
fi
echo "PetPop: stopping $(echo "$pids" | wc -l | tr -d ' ') process(es) from a previous run"
kill $pids 2>/dev/null || true
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -z "$(list)" ] && exit 0
  sleep 0.5
done
left="$(list)"
[ -n "$left" ] && kill -9 $left 2>/dev/null || true
exit 0
