#!/bin/bash
# Writes the auth token file from HYDRADB_TOKEN, then runs the engine in the foreground.
set -euo pipefail
token="${HYDRADB_TOKEN:-local-development-token-32-bytes}"
if [ "${#token}" -lt 32 ]; then
  echo "HYDRADB_TOKEN must be at least 32 characters" >&2
  exit 1
fi
umask 077
printf '%s\n' "$token" > /run/hydradb/auth-token
export GRAPH_AUTH_TOKEN_FILE=/run/hydradb/auth-token
exec /usr/local/bin/graph-node "$@"
