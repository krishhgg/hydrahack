#!/usr/bin/env bash
# Deploys HydraDB (with a persistent volume) and the app to Railway, connected over the private
# network. Needs the Railway CLI and RAILWAY_API_TOKEN (an account token) in the environment.
#
#   infra/railway/deploy.sh setup   # first time: project, hydradb service + volume, app service, domain
#   infra/railway/deploy.sh app     # redeploy the app from the current checkout (after each merge)
#   infra/railway/deploy.sh status  # services, domain and a live health check
#
# Secrets are read from the environment and never printed: RAILWAY_API_TOKEN, and optionally
# OPENAI_API_KEY (forwarded to the app service). The HydraDB bearer token is generated once and
# stored only as a Railway variable.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROJECT="${RAILWAY_PROJECT_NAME:-hydrahack}"
HYDRADB_IMAGE="${HYDRADB_IMAGE:-ghcr.io/krishhgg/hydrahack-hydradb:latest}"
: "${RAILWAY_API_TOKEN:?RAILWAY_API_TOKEN is not set}"
command -v railway >/dev/null || npm i -g @railway/cli >/dev/null

setup() {
  if ! railway link --project "$PROJECT" >/dev/null 2>&1; then
    railway init --name "$PROJECT" ${RAILWAY_WORKSPACE:+--workspace "$RAILWAY_WORKSPACE"} --json >/dev/null
  fi

  if ! railway variable list --service hydradb --json >/dev/null 2>&1; then
    token="$(openssl rand -hex 24)"
    # RAILWAY_RUN_UID=0: Railway mounts volumes root-owned and the engine image runs as uid 10001.
    railway add --service hydradb --image "$HYDRADB_IMAGE" \
      --variables "HYDRADB_TOKEN=$token" \
      --variables "RAILWAY_RUN_UID=0" \
      --json >/dev/null
    railway volume add --service hydradb --mount-path /data --json >/dev/null
  fi

  if ! railway variable list --service app --json >/dev/null 2>&1; then
    railway add --service app --json >/dev/null
  fi
  railway variable set --service app --skip-deploys \
    'HYDRADB_URL=http://${{hydradb.RAILWAY_PRIVATE_DOMAIN}}:8443' \
    'HYDRADB_ADMIN_URL=http://${{hydradb.RAILWAY_PRIVATE_DOMAIN}}:9090' \
    'HYDRADB_TOKEN=${{hydradb.HYDRADB_TOKEN}}' >/dev/null
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    printf '%s' "$OPENAI_API_KEY" | railway variable set OPENAI_API_KEY --stdin --service app --skip-deploys >/dev/null
  fi

  railway up --service app --detach --ci >/dev/null
  railway domain --service app --json || true
}

case "${1:-}" in
  setup) setup ;;
  app) railway up --service app --detach --ci ;;
  status)
    railway status
    url="$(railway domain --service app --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("domain") or d.get("domains",[""])[0])' || true)"
    [ -n "$url" ] && curl -fsS "https://${url#https://}/health" && echo
    ;;
  *) echo "usage: $0 {setup|app|status}" >&2; exit 2 ;;
esac
