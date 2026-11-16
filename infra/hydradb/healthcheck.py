"""Readiness probe for the engine: the steps of healthcheck.sh with a hard timeout on every call.

The shell version reads until the engine closes the socket, so a stalled engine leaves it hanging;
this one fails the step and says which one and how long it took.
"""

import http.client
import json
import os
import random
import sys
import time

TOKEN = os.environ.get("HYDRADB_TOKEN", "local-development-token-32-bytes")
TIMEOUT = 15


def call(port, method, path, body=None):
    started = time.monotonic()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        text = response.read().decode("utf-8", "replace")
        status = response.status
    except OSError as exc:
        status, text = 0, repr(exc)
    finally:
        conn.close()
    print(f"{method} {path[:40]} -> {status} in {time.monotonic() - started:.1f}s", file=sys.stderr)
    return status, text


def query(cypher):
    body = json.dumps(
        {
            "cell_id": "cell-0",
            "query_id": f"hc-{time.time_ns()}-{random.randrange(10**6)}",
            "query": cypher,
        }
    )
    return call(8443, "POST", "/v1/graphs/default/query", body)


def main():
    src = random.randrange(900_000_000, 1_900_000_000)
    dst = src + 1
    if call(9090, "GET", "/readyz")[0] != 200:
        return 1
    if '"columns"' not in query(f"MERGE (a {{id: {src}}})-[:HEALTHCHECK]->(b {{id: {dst}}})")[1]:
        return 1
    ok = (
        f'"value":{dst}'
        in query(f"MATCH (a {{id: {src}}})-[:HEALTHCHECK]->(b) RETURN b.id AS id")[1]
    )
    query(f"MATCH (a {{id: {src}}}) DETACH DELETE a")
    query(f"MATCH (a {{id: {dst}}}) DETACH DELETE a")
    return 0 if ok else 1


sys.exit(main())
