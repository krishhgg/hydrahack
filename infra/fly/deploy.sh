#!/usr/bin/env bash
# Deploys the single-machine Fly app (HydraDB and the API in one container, HydraDB data on a
# volume at /data). Needs FLY_API_TOKEN in the environment; flyctl is installed into ~/.fly if missing.
#
#   infra/fly/deploy.sh setup   # first time: app, 3 GB volume, secrets, deploy (safe to re-run)
#   infra/fly/deploy.sh app     # redeploy from the current checkout (after each merge)
#   infra/fly/deploy.sh status  # machine state and a live /health check
#
# Secrets are read from the environment and never printed: FLY_API_TOKEN, and optionally
# OPENAI_API_KEY (stored as a Fly secret). HYDRADB_TOKEN is generated once and stored only as a
# Fly secret. FLY_APP_NAME (default hydrahack-live), FLY_REGION (default sjc) and FLY_ORG are optional.
set -euo pipefail
cd "$(dirname "$0")/../.."

APP="${FLY_APP_NAME:-hydrahack-live}"
REGION="${FLY_REGION:-sjc}"
: "${FLY_API_TOKEN:?FLY_API_TOKEN is not set}"
export PATH="$HOME/.fly/bin:$PATH"
if ! command -v flyctl >/dev/null; then
  curl -fsSL https://fly.io/install.sh | sh >/dev/null
fi
export FLY_NO_UPDATE_CHECK=1 FLY_NO_TELEMETRY=1

deploy() {
  flyctl deploy --app "$APP" --config fly.toml --remote-only --ha=false --yes
}

setup() {
  if ! flyctl apps list --json | grep -Eqi "\"name\": *\"$APP\""; then
    flyctl apps create "$APP" ${FLY_ORG:+--org "$FLY_ORG"} >/dev/null
  fi

  if ! flyctl volumes list --app "$APP" --json | grep -Eqi '"name": *"hydradb_data"'; then
    flyctl volumes create hydradb_data --app "$APP" --region "$REGION" --size 3 --yes >/dev/null
  fi

  secrets="$(flyctl secrets list --app "$APP" --json)"
  if ! grep -q HYDRADB_TOKEN <<<"$secrets"; then
    printf 'HYDRADB_TOKEN=%s' "$(openssl rand -hex 24)" | flyctl secrets import --app "$APP" --stage >/dev/null
  fi
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    printf 'OPENAI_API_KEY=%s' "$OPENAI_API_KEY" | flyctl secrets import --app "$APP" --stage >/dev/null
  fi

  deploy
}

case "${1:-}" in
  setup) setup ;;
  app) deploy ;;
  status)
    flyctl status --app "$APP"
    curl -fsS --max-time 20 "https://$APP.fly.dev/health" && echo
    ;;
  *) echo "usage: $0 {setup|app|status}" >&2; exit 2 ;;
esac
