#!/usr/bin/env bash
# make up / make down: Docker Compose for this box's role (decision 124, docs/DEPLOY.md). Reads the env file, picks
# the Compose profiles from PETPOP_DEPLOY and from whether the stores and TLS are local, then runs compose.
#   scripts/compose.sh up      build and start, wait for health
#   scripts/compose.sh down    stop everything this project started, whatever the profiles
#   scripts/compose.sh config  print the resolved configuration (a dry run)
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env}"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE: cp .env.example $ENV_FILE and fill it in" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

files=(-f infra/docker-compose.yml)
[ "${GENAI_PROFILE:-mock}" = "nvidia-24gb" ] && files+=(-f infra/docker-compose.nvidia.yml)
compose() { PETPOP_ENV_FILE="../$ENV_FILE" docker compose "${files[@]}" --env-file "$ENV_FILE" "$@"; }

if [ "${1:-up}" = "down" ]; then
  COMPOSE_PROFILES='*' compose down
  exit 0
fi

role="${PETPOP_DEPLOY:-all}"
case "$role" in
  all) profiles=(studio kiosk) ;;
  cloud) profiles=(kiosk) ;;
  studio) profiles=(studio) ;;
  *) echo "PETPOP_DEPLOY=$role: use all, cloud or studio" >&2; exit 1 ;;
esac
[ -z "${DATABASE_URL:-}" ] && profiles+=(local-db)
case "${S3_ENDPOINT:-}" in "" | http://minio:*) profiles+=(local-s3) ;; esac
[ -n "${PETPOP_TLS_DOMAIN:-}" ] && profiles+=(tls)

missing=()
[ "$role" = "studio" ] && for v in PETPOP_CLOUD_URL PETPOP_SYNC_TOKEN; do [ -n "${!v:-}" ] || missing+=("$v"); done
[ "$role" = "cloud" ] && for v in PETPOP_SYNC_TOKEN PETPOP_PUBLIC_URL; do [ -n "${!v:-}" ] || missing+=("$v"); done
[ "$role" != "all" ] && { [ -n "${PETPOP_RELEASE_KEY:-}" ] || missing+=(PETPOP_RELEASE_KEY); }
if [ ${#missing[@]} -gt 0 ]; then
  echo "PETPOP_DEPLOY=$role needs ${missing[*]} in $ENV_FILE (docs/DEPLOY.md)" >&2
  exit 1
fi

export COMPOSE_PROFILES
COMPOSE_PROFILES="$(IFS=,; echo "${profiles[*]}")"
echo "PetPop $role: profiles $COMPOSE_PROFILES"
case "${1:-up}" in
  up) compose up -d --build --wait --remove-orphans ;;
  config) compose config ;;
  *) compose "$@" ;;
esac
