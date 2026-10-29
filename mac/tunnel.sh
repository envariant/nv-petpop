#!/usr/bin/env bash
# Expose the Mac GenAI services to the cloud VM: Caddy (token check, path routing) on 127.0.0.1:8787, then a
# Cloudflare tunnel to it. Prints the four lines to set in the cloud environment.
#
#   mac/tunnel.sh                 # quick tunnel: random https://<words>.trycloudflare.com, changes every run
#   CF_TUNNEL=petpop CF_HOSTNAME=genai.example.com mac/tunnel.sh   # named tunnel: stable hostname (needs a
#                                 # Cloudflare account; once: cloudflared tunnel login; cloudflared tunnel create petpop;
#                                 # cloudflared tunnel route dns petpop genai.example.com)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PETPOP_GENAI="${PETPOP_GENAI:-$HOME/petpop-genai}"
set -a; . "$PETPOP_GENAI/genai.env"; set +a
BIN="$PETPOP_GENAI/bin"   # caddy and cloudflared at the releases pinned in mac/tools.lock (installed by setup.sh)
PORT="${PETPOP_PROXY_PORT:-8787}"
LOG="$PETPOP_GENAI/logs"
mkdir -p "$LOG"

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$BIN/caddy" run --config "$REPO/mac/Caddyfile" --adapter caddyfile >"$LOG/caddy.log" 2>&1 & pids+=($!)
for _ in $(seq 1 20); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/comfy/system_stats")" = "401" ] && break; sleep 0.5
done

if [ -n "${CF_TUNNEL:-}" ] && [ -n "${CF_HOSTNAME:-}" ]; then
  "$BIN/cloudflared" tunnel --no-autoupdate run --url "http://127.0.0.1:$PORT" "$CF_TUNNEL" >"$LOG/cloudflared.log" 2>&1 & pids+=($!)
  BASE="https://$CF_HOSTNAME"
else
  "$BIN/cloudflared" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG/cloudflared.log" 2>&1 & pids+=($!)
  BASE=""
  for _ in $(seq 1 60); do
    BASE="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG/cloudflared.log" | head -1 || true)"
    [ -n "$BASE" ] && break; sleep 1
  done
  [ -n "$BASE" ] || { echo "no tunnel URL; see $LOG/cloudflared.log"; exit 1; }
fi

# Check the whole path (tunnel -> proxy -> services) before printing anything.
for _ in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $GENAI_TOKEN" "$BASE/comfy/system_stats" || true)"
  [ "$code" = "200" ] && break; sleep 2
done
for svc in "comfy/system_stats" "shape/health" "ollama/api/tags"; do
  printf '  %-20s %s\n' "$svc" "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $GENAI_TOKEN" "$BASE/$svc")"
done

cat <<OUT

Set these in the cloud environment (environment settings > Environment variables), then start a new session.
GENAI_TOKEN is in $PETPOP_GENAI/genai.env: copy it from there, do not paste it into a chat.

GENAI_PROFILE=mac-m4pro
COMFY_URL=$BASE/comfy
SHAPE_URL=$BASE/shape
OLLAMA_URL=$BASE/ollama
GENAI_TOKEN=<value of GENAI_TOKEN in $PETPOP_GENAI/genai.env>

Allow the tunnel host in the environment's network settings if access is Limited: ${BASE#https://}
Tunnel running; Ctrl-C to stop.
OUT
wait
