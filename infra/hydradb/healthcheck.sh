#!/bin/bash
# Readiness = /readyz is 200 AND a write/read/delete round trip through the query API succeeds.
# A listening port is not proof the store accepts writes.
set -euo pipefail
token="${HYDRADB_TOKEN:-local-development-token-32-bytes}"
id=$(( (RANDOM << 15 | RANDOM) + 900000000 ))
dst=$(( id + 1 ))

http() { # host port request-line body [extra header]
  local host=$1 port=$2 method=$3 path=$4 body=${5:-} resp
  exec 3<>"/dev/tcp/$host/$port"
  printf '%s %s HTTP/1.0\r\nHost: %s\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' \
    "$method" "$path" "$host" "$token" "${#body}" "$body" >&3
  resp=$(cat <&3)
  exec 3>&-
  printf '%s' "$resp"
}
# A unique query_id per request: the engine's own http-query-N counter restarts from 1 on every
# start, and a reused id on a write fails with "idempotency identity was reused".
q() { http 127.0.0.1 8443 POST /v1/graphs/default/query "{\"cell_id\":\"cell-0\",\"query_id\":\"hc-$(date +%s%N)-$RANDOM\",\"query\":\"$1\"}"; }

http 127.0.0.1 9090 GET /readyz | head -n1 | grep -q ' 200'
q "MERGE (a {id: $id})-[:HEALTHCHECK]->(b {id: $dst})" | grep -q '"columns"'
q "MATCH (a {id: $id})-[:HEALTHCHECK]->(b) RETURN b.id AS id" | grep -q "\"value\":$dst"
q "MATCH (a {id: $id}) DETACH DELETE a" >/dev/null
q "MATCH (a {id: $dst}) DETACH DELETE a" >/dev/null
