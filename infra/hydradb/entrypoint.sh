#!/bin/bash
# Writes the auth token file from HYDRADB_TOKEN, then runs the engine in the foreground.
set -euo pipefail
token="${HYDRADB_TOKEN:-local-development-token-32-bytes}"
if [ "${#token}" -lt 32 ]; then
  echo "HYDRADB_TOKEN must be at least 32 characters" >&2
  exit 1
fi
# One node owns this store exclusively, so no other writer can hold a lease. After a hard kill
# (OOM, host failure, docker kill) the previous process leaves an unreleased writer lease, and the
# engine cannot take over a stale lease on a local-filesystem store (it needs a conditional put the
# local store lacks), so every write would fail forever. Clearing the leases at boot is safe here.
find "${LOCAL_PATH:-/data/store}" -path '*/_writer_leases/*' -type f -delete 2>/dev/null || true

umask 077
printf '%s\n' "$token" > /run/hydradb/auth-token
export GRAPH_AUTH_TOKEN_FILE=/run/hydradb/auth-token
exec /usr/local/bin/graph-node "$@"
