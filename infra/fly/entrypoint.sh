#!/bin/bash
# Runs HydraDB and the app in one container. If either exits, the container exits so Fly restarts it.
set -euo pipefail

# Fly volumes are mounted root-owned; the engine runs as uid 10001.
mkdir -p /data/store /data/cache /run/hydradb
chown -R 10001:10001 /data /run/hydradb
drop=(setpriv --reuid=10001 --regid=10001 --clear-groups)

# HYDRADB_TOKEN comes from a Fly secret; generate one if absent (valid for this boot only).
export HYDRADB_TOKEN="${HYDRADB_TOKEN:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
export HYDRADB_URL=http://127.0.0.1:8443
export HYDRADB_ADMIN_URL=http://127.0.0.1:9090

"${drop[@]}" /usr/local/bin/hydradb-entrypoint &
db=$!

ready=0
for _ in $(seq 1 120); do
  kill -0 "$db" 2>/dev/null || { echo "hydradb exited during startup" >&2; exit 1; }
  if "${drop[@]}" /usr/local/bin/hydradb-healthcheck >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "hydradb did not become healthy in 120s" >&2; exit 1; }
echo "hydradb healthy"

cd /app
if [ "$APP_MODULE" = "hydrahack.api:app" ] && ! python -c 'import importlib.util as u; raise SystemExit(u.find_spec("hydrahack.api") is None)'; then
  echo "hydrahack.api not found, serving the infra.app_stub health app instead" >&2
  APP_MODULE=infra.app_stub:app
fi
echo "starting app: $APP_MODULE on :${PORT:-8080}"
"${drop[@]}" uvicorn "$APP_MODULE" --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers &
app=$!

trap 'kill "$db" "$app" 2>/dev/null || true' TERM INT
status=0
wait -n "$db" "$app" || status=$?
echo "a process exited (status $status), stopping container" >&2
kill "$db" "$app" 2>/dev/null || true
wait || true
exit 1
