"""Probe which OpenCypher features the running HydraDB engine supports.

Usage: uv run python scripts/probe_hydradb.py   (needs docker compose up -d --wait hydradb)
Prints one line per probe: ok / REJECTED with the engine's message. Uses ids from 870_000_000.
"""

import time

from hydrahack.db import HydraDB, HydraDBError

B = 870_000_000
L = "Probe"
db = HydraDB()


def probe(name, fn):
    try:
        out = fn()
        print(f"ok        {name}: {out}")
    except HydraDBError as e:
        print(f"REJECTED  {name}: {str(e)[:150]}")


def seed():
    db.reset(labels=[L], ids=range(B, B + 3000))
    db.write_nodes([{"id": B + i, "name": f"n{i}"} for i in range(8)], L)
    # chain 0->1->2->3->4->5, shortcut 0->3, branch 2->6, cycle 5->0, 7 isolated
    for s, d, w in [
        (0, 1, 1.0),
        (1, 2, 1.0),
        (2, 3, 1.0),
        (3, 4, 1.0),
        (4, 5, 1.0),
        (0, 3, 5.0),
        (2, 6, 1.0),
        (5, 0, 1.0),
    ]:
        db.write(
            "MERGE (a:Probe {id: $a})-[:E {w: $w, hits: 0}]->(b:Probe {id: $b})",
            {"a": B + s, "b": B + d, "w": w},
        )


def q(c, p=None, **kw):
    return db.query(c, p, **kw)


seed()
probe(
    "var-length *1..3",
    lambda: sorted(
        r["i"] - B
        for r in q("MATCH (a {id: $a})-[:E*1..3]->(b) RETURN DISTINCT b.id AS i", {"a": B})
    ),
)
probe(
    "var-length unbounded *", lambda: q("MATCH (a {id: $a})-[:E*]->(b) RETURN b.id AS i", {"a": B})
)
probe(
    "var-length *2..2 + WHERE on target",
    lambda: [
        r["i"] - B
        for r in q("MATCH (a {id: $a})-[:E*2..2]->(b) WHERE b.id <> $a RETURN b.id AS i", {"a": B})
    ],
)
probe(
    "var-length with rel-property filter",
    lambda: q("MATCH (a {id: $a})-[r:E*1..2]->(b) WHERE r.w > 2 RETURN b.id AS i", {"a": B}),
)
probe(
    "two-hop explicit, rel props on both hops",
    lambda: [
        (r["w1"], r["w2"])
        for r in q(
            "MATCH (a {id: $a})-[r1:E]->(m)-[r2:E]->(b) RETURN r1.w AS w1, r2.w AS w2", {"a": B}
        )
    ],
)
probe(
    "SET rel property (param)",
    lambda: (
        db.write(
            "MATCH (a {id: $a})-[r:E]->(b {id: $b}) SET r.w = $w", {"a": B, "b": B + 1, "w": 2.5}
        )
        and "set"
    ),
)
probe(
    "read back SET rel property",
    lambda: q("MATCH (a {id: $a})-[r:E]->(b {id: $b}) RETURN r.w AS w", {"a": B, "b": B + 1}),
)
probe(
    "SET rel property = expression r.w + 1",
    lambda: db.write(
        "MATCH (a {id: $a})-[r:E]->(b {id: $b}) SET r.w = r.w + 1", {"a": B, "b": B + 1}
    ),
)
probe(
    "SET rel property on many edges at once (anchor by src)",
    lambda: db.write("MATCH (a {id: $a})-[r:E]->(b) SET r.hits = $h", {"a": B, "h": 7}),
)
probe(
    "REMOVE rel property",
    lambda: db.write("MATCH (a {id: $a})-[r:E]->(b {id: $b}) REMOVE r.hits", {"a": B, "b": B + 1}),
)
probe(
    "DELETE single rel",
    lambda: db.write("MATCH (a {id: $a})-[r:E]->(b {id: $b}) DELETE r", {"a": B + 2, "b": B + 6}),
)
probe(
    "MERGE edge idempotent x3",
    lambda: (
        [
            db.write("MERGE (a:Probe {id: $a})-[:M]->(b:Probe {id: $b})", {"a": B + 7, "b": B + 6})
            for _ in range(3)
        ]
        and q("MATCH (a {id: $a})-[:M]->(b) RETURN count(*) AS c", {"a": B + 7})
    ),
)
probe(
    "MERGE ... SET",
    lambda: db.write(
        "MERGE (a:Probe {id: $a})-[r:E]->(b:Probe {id: $b}) SET r.w = 3", {"a": B + 7, "b": B + 1}
    ),
)
probe(
    "MERGE with ON CREATE",
    lambda: db.write("MERGE (a {id: 1})-[r:E]->(b {id: 2}) ON CREATE SET r.w = 3"),
)
probe("CREATE INDEX", lambda: db.write("CREATE INDEX FOR (n:Probe) ON (n.name)"))
probe(
    "CREATE CONSTRAINT", lambda: db.write("CREATE CONSTRAINT FOR (n:Probe) REQUIRE n.id IS UNIQUE")
)
probe(
    "property filter on label (no id)",
    lambda: q("MATCH (n:Probe {name: $n}) RETURN n.id AS i", {"n": "n3"}),
)
probe(
    "CONTAINS / STARTS WITH",
    lambda: q("MATCH (n:Probe) WHERE n.name CONTAINS 'n1' RETURN n.id AS i"),
)
probe(
    "shortestPath returning endpoint props",
    lambda: q(
        "MATCH p = shortestPath((a {id: $a})-[:E*1..6]->(b {id: $b})) RETURN b.id AS i",
        {"a": B, "b": B + 5},
    ),
)
probe(
    "algo.SPpaths shortest (hops)",
    lambda: [
        [n["id"] - B for n in r["path"]["nodes"]]
        for r in q(
            "CALL algo.SPpaths({sourceNode: $s, targetNode: $t, relTypes: ['E'], "
            "relDirection: 'outgoing', maxLen: 6, pathCount: 1}) YIELD path RETURN path",
            {"s": B, "t": B + 5},
        )
    ],
)
probe(
    "algo.SPpaths weighted by rel property",
    lambda: [
        [n["id"] - B for n in r["path"]["nodes"]]
        for r in q(
            "CALL algo.SPpaths({sourceNode: $s, targetNode: $t, relTypes: ['E'], "
            "relDirection: 'outgoing', maxLen: 6, pathCount: 1, weightProp: 'w'}) "
            "YIELD path RETURN path",
            {"s": B, "t": B + 3},
        )
    ],
)
probe(
    "algo.SSpaths from one source",
    lambda: len(
        q(
            "CALL algo.SSpaths({sourceNode: $s, relTypes: ['E'], relDirection: 'outgoing', maxLen: 3}) "
            "YIELD path RETURN path",
            {"s": B},
        )
    ),
)
probe(
    "count + collect",
    lambda: q("MATCH (a:Probe)-[r:E]->(b) RETURN count(*) AS c, collect(b.id) AS ids"),
)
probe("sum over float property", lambda: q("MATCH (a:Probe)-[r:E]->(b) RETURN sum(r.w) AS s"))
probe("sum over integer property", lambda: q("MATCH (a:Probe)-[r:E]->(b) RETURN sum(r.hits) AS s"))
probe("avg over float property", lambda: q("MATCH (a:Probe)-[r:E]->(b) RETURN avg(r.w) AS a"))
probe("min/max aggregate", lambda: q("MATCH (a:Probe)-[r:E]->(b) RETURN min(r.w) AS lo"))
probe(
    "grouped aggregation + ORDER BY alias + LIMIT",
    lambda: q(
        "MATCH (a:Probe)-[r:E]->(b) RETURN a.id AS id, count(*) AS n ORDER BY n DESC, id ASC LIMIT 3"
    ),
)
probe("RETURN bare node", lambda: q("MATCH (n:Probe {id: $i}) RETURN n", {"i": B}))
probe(
    "RETURN labels(n) / id(n)",
    lambda: q("MATCH (n:Probe {id: $i}) RETURN labels(n) AS l", {"i": B}),
)
probe("RETURN expression", lambda: q("MATCH (n:Probe {id: $i}) RETURN n.id + 1 AS x", {"i": B}))
probe(
    "toLower / coalesce in WHERE",
    lambda: q("MATCH (n:Probe) WHERE toLower(n.name) = 'n1' RETURN n.id AS i"),
)
probe("undirected edge", lambda: q("MATCH (a {id: $a})-[:E]-(b) RETURN b.id AS i", {"a": B}))
probe(
    "incoming edge direction",
    lambda: sorted(
        r["i"] - B for r in q("MATCH (a {id: $a})<-[:E]-(b) RETURN b.id AS i", {"a": B + 3})
    ),
)
probe(
    "multi-type rel [:E|M]", lambda: q("MATCH (a {id: $a})-[:E|M]->(b) RETURN b.id AS i", {"a": B})
)
probe(
    "OPTIONAL MATCH",
    lambda: q(
        "MATCH (a:Probe {id: $a}) OPTIONAL MATCH (a)-[:E]->(b) RETURN b.id AS i", {"a": B + 7}
    ),
)
probe(
    "UNION ALL",
    lambda: len(
        q(
            "MATCH (a {id: $a})-[:E]->(b) RETURN b.id AS i UNION ALL "
            "MATCH (a {id: $c})-[:E]->(b) RETURN b.id AS i",
            {"a": B, "c": B + 1},
        )
    ),
)
probe(
    "WITH aggregation + filter",
    lambda: q("MATCH (a:Probe)-[:E]->(b) WITH a, count(*) AS n WHERE n > 1 RETURN a.id AS i"),
)
probe(
    "parameter: int/float/bool/string/null in property write",
    lambda: (
        db.write(
            "MERGE (a:Probe {id: $a, name: $s})-[:T {i: $i, f: $f, b: $b}]->(c:Probe {id: $c})",
            {"a": B + 20, "s": "héllo \"q\" 'x'", "i": 7, "f": 0.25, "b": True, "c": B + 21},
        ),
        q("MATCH (a {id: $a})-[r:T]->(c) RETURN r.i AS i, r.f AS f, r.b AS b", {"a": B + 20}),
    )[1],
)
probe(
    "parameter: unicode/quotes round trip",
    lambda: q("MATCH (n:Probe {id: $a}) RETURN n.name AS n", {"a": B + 20}),
)
probe(
    "parameter: list value stored as property",
    lambda: (
        db.write("MATCH (a:Probe {id: $a}) SET a.tags = $t", {"a": B, "t": ["x", "y"]}),
        q("MATCH (a:Probe {id: $a}) RETURN a.tags AS t", {"a": B}),
    )[1],
)
probe(
    "parameter: map value as property",
    lambda: db.write("MATCH (a:Probe {id: $a}) SET a.m = $m", {"a": B, "m": {"k": 1}}),
)
probe(
    "parameter: list in WHERE IN",
    lambda: q("MATCH (n:Probe) WHERE n.id IN $ids RETURN n.id AS i", {"ids": [B, B + 1]}),
)
probe(
    "float property ORDER BY rel prop",
    lambda: [
        r["w"] for r in q("MATCH (a {id: $a})-[r:E]->(b) RETURN r.w AS w ORDER BY w DESC", {"a": B})
    ],
)
probe(
    "long string property (20 KB)",
    lambda: (
        db.write("MATCH (a:Probe {id: $a}) SET a.blob = $s", {"a": B + 1, "s": "x" * 20_000}),
        len(q("MATCH (a:Probe {id: $a}) RETURN a.blob AS s", {"a": B + 1})[0]["s"]),
    )[1],
)
probe(
    "strong consistency read",
    lambda: q("MATCH (n:Probe {id: $i}) RETURN n.name AS n", {"i": B}, consistency="strong"),
)


def throughput():
    n = 20_000
    nodes = [{"id": B + 1000 + i, "name": f"b{i}"} for i in range(n)]
    edges = [{"src": B + 1000 + i, "dst": B + 1000 + (i * 7 + 1) % n} for i in range(n)]
    t = time.perf_counter()
    db.write_nodes(nodes, L)
    t1 = time.perf_counter()
    db.write_edges(edges, "BATCH")
    t2 = time.perf_counter()
    out = {"nodes_per_s": round(n / (t1 - t)), "edges_per_s": round(n / (t2 - t1))}
    t = time.perf_counter()
    for i in range(200):
        db.write(
            "MERGE (a:Probe {id: $a})-[:SINGLE]->(b:Probe {id: $b})",
            {"a": B + 1000 + i, "b": B + 1500 + i},
        )
    out["single_merge_per_s"] = round(200 / (time.perf_counter() - t))
    t = time.perf_counter()
    for i in range(200):
        db.write("MATCH (a {id: $a})-[r:BATCH]->(b) SET r.w = $w", {"a": B + 1000 + i, "w": 1.5})
    out["rel_set_per_s"] = round(200 / (time.perf_counter() - t))
    t = time.perf_counter()
    for i in range(200):
        q("MATCH (a {id: $a})-[:BATCH*1..3]->(b) RETURN b.id AS i", {"a": B + 1000 + i})
    out["3hop_read_per_s"] = round(200 / (time.perf_counter() - t))
    return out


probe("batch write throughput (sequential, single client)", throughput)
db.reset(labels=[L], ids=range(B, B + 3000))
