#!/bin/bash
# Build-time seeding: start the engine, let the app ingest the catalog and training runs into it
# (hydrahack.api.State.start), then stop the engine gracefully so its writer lease is released.
set -euo pipefail
mkdir -p /data/store /data/cache /run/hydradb /data/waypoint /data/tiktoken
chown -R 10001:10001 /data /run/hydradb
drop=(setpriv --reuid=10001 --regid=10001 --clear-groups)
export HYDRADB_TOKEN="seed-build-token-not-used-at-runtime-0001"

"${drop[@]}" /usr/local/bin/hydradb-entrypoint &
db=$!
for _ in $(seq 1 120); do
  "${drop[@]}" /usr/local/bin/hydradb-healthcheck >/dev/null 2>&1 && break
  sleep 1
done
"${drop[@]}" /usr/local/bin/hydradb-healthcheck

cd /app
"${drop[@]}" env HYDRADB_URL=http://127.0.0.1:8443 HYDRADB_ADMIN_URL=http://127.0.0.1:9090 \
  python -c '
import sys
from hydrahack.api import state
state.start()
if not state.ready:
    sys.exit(f"seeding failed: {state.error}")
print("seeded", len(state.texts), "learned tasks")
'

kill -TERM "$db"
wait "$db" || true
du -sh /data/store /data/waypoint /data/tiktoken
