#!/usr/bin/env bash
# Deploys the Render free web service from the GHCR image (infra/render/Dockerfile).
# Needs RENDER_API_KEY (Account Settings, API Keys); secrets are never printed.
#
#   infra/render/deploy.sh setup    # create the service if missing, then deploy
#   infra/render/deploy.sh deploy   # redeploy (re-pulls ghcr.io/krishhgg/hydrahack-render:latest)
#   infra/render/deploy.sh status   # service state, URL and live /health
set -euo pipefail
: "${RENDER_API_KEY:?RENDER_API_KEY is not set}"
NAME="${RENDER_SERVICE_NAME:-hydrahack-live}"
IMAGE="${RENDER_IMAGE:-ghcr.io/krishhgg/hydrahack-render:latest}"
API=https://api.render.com/v1
call() { curl -fsS -H "Authorization: Bearer $RENDER_API_KEY" -H 'Accept: application/json' -H 'Content-Type: application/json' "$@"; }
service_id() {
  call "$API/services?name=$NAME&limit=20" | python3 -c '
import json, sys
for row in json.load(sys.stdin):
    s = row.get("service", row)
    if s.get("name") == sys.argv[1]:
        print(s["id"])
        break' "$NAME"
}

setup() {
  id="$(service_id)"
  if [ -z "$id" ]; then
    owner="$(call "$API/owners?limit=20" | python3 -c 'import json,sys; d=json.load(sys.stdin)[0]; print(d.get("owner", d)["id"])')"
    body="$(OWNER="$owner" NAME="$NAME" IMAGE="$IMAGE" python3 -c '
import json, os, secrets
env = [{"key": "HYDRADB_TOKEN", "value": secrets.token_hex(24)}]
if os.environ.get("OPENAI_API_KEY"):
    env.append({"key": "OPENAI_API_KEY", "value": os.environ["OPENAI_API_KEY"]})
print(json.dumps({
    "type": "web_service", "name": os.environ["NAME"], "ownerId": os.environ["OWNER"],
    "image": {"ownerId": os.environ["OWNER"], "imagePath": os.environ["IMAGE"]},
    "autoDeploy": "no",
    "serviceDetails": {"runtime": "image", "plan": "free", "region": "oregon", "healthCheckPath": "/health", "envVars": env},
}))')"
    printf '%s' "$body" | call -X POST "$API/services" -d @- | python3 -c 'import json,sys; d=json.load(sys.stdin); print("created", d.get("service", d)["id"])'
  else
    deploy
  fi
}

deploy() {
  id="$(service_id)"
  call -X POST "$API/services/$id/deploys" -d '{"clearCache":"do_not_clear"}' | python3 -c 'import json,sys; d=json.load(sys.stdin); print("deploy", d.get("id"), d.get("status"))'
}

status() {
  id="$(service_id)"
  call "$API/services/$id" | python3 -c '
import json, sys
s = json.load(sys.stdin)
print(s["name"], s.get("suspended"), s.get("serviceDetails", {}).get("url"))'
  url="$(call "$API/services/$id" | python3 -c 'import json,sys; print(json.load(sys.stdin)["serviceDetails"]["url"])')"
  curl -fsS --max-time 60 "$url/health" && echo
}

case "${1:-}" in
  setup) setup ;;
  deploy) deploy ;;
  status) status ;;
  *) echo "usage: $0 {setup|deploy|status}" >&2; exit 2 ;;
esac
