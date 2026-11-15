# HydraDB engine notes

What we verified against the running engine (v0.4.0, the pinned image in `infra/hydradb/Dockerfile`), so nobody discovers a gap late. Everything below was run with `scripts/probe_hydradb.py` (re-run it after any engine bump) and `hydrahack/db.py`. The upstream guide `USING-HYDRADB.md` in github.com/hydra-db/hydradb is worth reading too; where our results differ from it, ours are listed.

## Connecting

- HTTP query API on 8443: `POST /v1/graphs/default/query`, body `{"cell_id": "cell-0", "query": ..., "parameters": {...}}`, header `Authorization: Bearer <token>`. `/healthz` on 8443, `/readyz` on 9090 (200, empty body). Bolt on 7687 works with the `neo4j` driver (`bolt://`, password = token, `database="default"`), but **explicit transactions are rejected** (`explicit transactions are not supported`), so Bolt buys nothing over HTTP.
- The graph id and cell are fixed by the node's env (`GRAPH_ID`, `GRAPH_CELL_ID`). A different graph id is `permission_denied`; a wrong `cell_id` is an opaque 500. So there is **no per-test graph**: isolate tests with a label plus a high id range, and wipe everything with `docker compose down -v`.
- `hydrahack.db.HydraDB` is a thin wrapper over this: `query` (typed cells decoded, pagination followed), `write`, `write_nodes`, `write_edges`, `reset(labels, ids)`, `health`.

## Data model quirks (these produce wrong numbers silently)

- Node identity is the integer `id` property: an upsert key, no auto ids. Nodes dedupe on `id`; **a plain single `CREATE` of the same edge duplicates it**, `MERGE` and the `UNWIND` edge batch dedupe on (src, dst, type). Always use `MERGE` or the batch.
- Ids come back as `vertex_id` cells, aggregates as `integer`, nulls have no `value` key. `db.py` handles all of this.
- Every `MATCH` needs an id, label or property anchor. An unlabelled node is invisible to label-anchored queries, so **label nodes when you create them** (`write_nodes` first, then `write_edges`).
- Cannot create an edgeless node with a plain statement; use the node batch (`UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Label, n.prop = row.prop`, exactly one label).

## Verified supported

| Feature | Result |
|---|---|
| Variable-length paths | `[:E*1..3]` works, returns every reachable node within the bound (nodes can repeat across paths, use `RETURN DISTINCT`). Hop bounds are inclusive; `*2..2` is exactly two hops. Cycles revisit nodes (a 3-cycle `*3..3` returns the start), filter with `WHERE b.id <> $start`. |
| Multi-hop with edge properties | Explicit chains work and expose per-hop edge props: `(a)-[r1:E]->(m)-[r2:E]->(b) RETURN r1.w, r2.w`. |
| **SET on relationship properties** | Works, with parameters: `MATCH (a {id:$a})-[r:E]->(b {id:$b}) SET r.w = $w, r.hits = $h`. Floats, ints, bools, strings, flat lists persist with their types. `REMOVE r.prop` and `DELETE r` work. |
| MERGE | Idempotent for edges with inline properties (`MERGE (a:L {id:$a})-[:R {w:$w}]->(b:L {id:$b})`), 3 runs = 1 edge. |
| Shortest path | `shortestPath((a)-[:E*1..6]->(b))` executes (return endpoint properties only). `CALL algo.SPpaths({sourceNode, targetNode, relTypes:['E'], relDirection:'outgoing', maxLen, pathCount}) YIELD path RETURN path` returns the path (write it as `RETURN path`, an alias after RETURN is a parse error). **`weightProp: 'w'` is honoured**: with w(0→3)=5 and the chain 0→1→2→3 summing to 4.5 it picked the chain. This is the way to make an edge weight change what a traversal returns. `algo.SSpaths` (one source) works too. |
| Aggregation | `count(*)`, `count(x)`, `collect(x)`, grouped aggregates with several group keys, `ORDER BY alias DESC, other ASC`, `LIMIT`, `SKIP`, `DISTINCT` as a projection. |
| Parameters | int, float, bool, string (unicode, quotes), flat list as a property value, list in `WHERE n.id IN $ids`, 20 KB strings. |
| Other | `OPTIONAL MATCH`, `UNION [ALL]`, undirected edges (`-[:E]-`, works in v0.4.0 although the upstream guide says it does not), incoming direction, `strong` consistency reads, label-anchored property filters (`MATCH (n:L {name: $n})`). |

## Verified NOT supported (design around these)

- **Float `sum`/`avg`**: `sum aggregate requires integer values`. Same for `min`/`max`. Compute them client-side, or store scaled integers.
- `RETURN` takes only `binding.property`, aliases and aggregates: no bare nodes, `labels(n)`, arithmetic, `n.id + 1`.
- `SET r.w = r.w + 0.1`: SET only accepts literals or parameters, not expressions. **Read, compute, write back.**
- Filtering on relationship properties inside a variable-length pattern (`[r:E*1..2] WHERE r.w > 2`): rejected. Use `weightProp` on `algo.SPpaths`, or explicit fixed-hop chains.
- `MERGE ... SET`, `MERGE ... ON CREATE/ON MATCH`: rejected. Two statements.
- `WITH` only as pass-through (no aggregation then filter, no DISTINCT/WHERE/ORDER BY), `CONTAINS`/`STARTS WITH`/`toLower` in `WHERE`, multi-type patterns (`[:A|B]`), unbounded `*`, map-valued parameters, list parameters outside `UNWIND`.
- **Indexes and constraints**: `CREATE INDEX`/`CREATE CONSTRAINT` do not parse. There is no index DDL; the id and label are what is indexed, so key lookups by `id` are fast and property scans are not. Put anything you look up by in the node `id` (hash a string key to an int) or accept a label scan.
- Batch relationship property writes: the edge batch carries no properties and `UNWIND ... MATCH ... SET` is rejected, so changing N edge weights costs N requests.

## Performance (one ultra cloud VM, single node, local disk, HTTP, httpx client)

| Workload | Result |
|---|---|
| Node batch upsert (1000 rows/request) | about 22k nodes/s |
| Edge batch (1000 rows/request) | about 6k edges/s |
| Single `MERGE` edge, sequential | 45/s at the default WAL flush (p50 22 ms) |
| Relationship `SET`, 8 concurrent clients | 87/s default (p50 89 ms) |
| 3-hop variable-length read, 1 / 8 / 32 clients | 438 / 1419 / 1052 req/s; p50 2.1 / 5.2 / 25.8 ms |

Writes are the bottleneck: every write waits for a WAL flush (default 10 ms) and they serialise. We set `GRAPH_WAL_FLUSH_INTERVAL_MS=2` in the wrapper image (still durable, flushes more often): relationship `SET` went to 123/s sequential (p50 8.5 ms) and 319/s with 8 or more clients. Consequences for the learning loop: **batch node and edge ingestion**, and treat per-edge weight updates as roughly 8 ms each, so update only the edges a feedback step actually touched. Reads are cheap, so the live query path should not write.
