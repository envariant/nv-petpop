#!/usr/bin/env bash
# Prove the production infrastructure on this machine (M2.5 item 6): build and start the Compose stack on the
# mock GenAI profile (no GPU services), push one job through Redis/arq, the worker, Postgres and MinIO, check
# it end to end, then tear everything down. Secrets are generated into var/stack.env (never committed).
#   scripts/smoke_stack.sh            PETPOP_BUILD_CA=/path/ca.pem for builds behind a TLS-inspecting proxy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$ROOT/.venv/bin/python}"
mkdir -p var
umask 077
"$PY" - <<'PYEOF'
import secrets
open("var/stack.env", "w").write(f"""GENAI_PROFILE=mock
PETPOP_QUALITY=test
PETPOP_MOCK_SPEED=0
PETPOP_SECRET={secrets.token_hex(32)}
PETPOP_STAFF_TOKEN={secrets.token_hex(12)}
POSTGRES_PASSWORD={secrets.token_hex(16)}
S3_ACCESS_KEY=petpop{secrets.token_hex(4)}
S3_SECRET_KEY={secrets.token_hex(20)}
""")
PYEOF
set -a; . var/stack.env; set +a
export API_PORT="${API_PORT:-8099}" GENAI_PROFILE=mock
[ -n "${PETPOP_BUILD_CA:-}" ] && cp "$PETPOP_BUILD_CA" var/build-ca.pem && export PETPOP_BUILD_CA=../var/build-ca.pem
trap 'make -s down ENV_FILE=var/stack.env >/dev/null 2>&1; docker compose -f infra/docker-compose.yml --env-file var/stack.env down -v >/dev/null 2>&1 || true' EXIT
make -s up ENV_FILE=var/stack.env
"$PY" scripts/smoke_stack.py --base "http://127.0.0.1:$API_PORT" --staff-token "$PETPOP_STAFF_TOKEN"
