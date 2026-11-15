"""Runs against a real HydraDB: docker compose up -d --wait hydradb && pytest -m integration"""

import pytest

from hydrahack.db import HydraDB, HydraDBError

pytestmark = pytest.mark.integration

BASE = 880_000_000
LABEL = "ItTest"


@pytest.fixture()
def db():
    client = HydraDB()
    client.reset(labels=[LABEL], ids=range(BASE, BASE + 3000))
    yield client
    client.reset(labels=[LABEL], ids=range(BASE, BASE + 3000))
    client.close()


def test_health_roundtrip(db):
    health = db.health()
    assert health["ok"] and health["roundtrip"] is True


def test_parameterised_write_and_read(db):
    db.write(
        "MERGE (a:ItTest {id: $a, name: $an})-[:KNOWS {w: $w}]->(b:ItTest {id: $b})",
        {"a": BASE, "an": "alice", "b": BASE + 1, "w": 0.5},
    )
    rows = db.query(
        "MATCH (a:ItTest {id: $a})-[r:KNOWS]->(b) RETURN b.id AS id, r.w AS w", {"a": BASE}
    )
    assert rows == [{"id": BASE + 1, "w": 0.5}]


def test_set_relationship_property(db):
    db.write(
        "MERGE (a:ItTest {id: $a})-[:KNOWS {w: 0.1}]->(b:ItTest {id: $b})",
        {"a": BASE, "b": BASE + 1},
    )
    db.write(
        "MATCH (a {id: $a})-[r:KNOWS]->(b {id: $b}) SET r.w = $w",
        {"a": BASE, "b": BASE + 1, "w": 0.9},
    )
    rows = db.query("MATCH (a {id: $a})-[r:KNOWS]->(b) RETURN r.w AS w", {"a": BASE})
    assert rows == [{"w": 0.9}]


def test_batch_pagination_and_reset(db):
    n = 2500
    db.write_nodes([{"id": BASE + i, "name": f"n{i}"} for i in range(n + 1)], LABEL)
    db.write_edges([{"src": BASE + i, "dst": BASE + i + 1} for i in range(n)], "NEXT")
    db.write_edges([{"src": BASE + i, "dst": BASE + i + 1} for i in range(n)], "NEXT")  # idempotent
    rows = db.query("MATCH (a:ItTest)-[:NEXT]->(b) RETURN a.id AS s, b.id AS d", page_size=100)
    assert len(rows) == n
    assert len({r["s"] for r in rows}) == n
    db.reset(labels=[LABEL])
    assert db.query("MATCH (a:ItTest) RETURN count(*) AS c") == [{"c": 0}]


def test_bounded_variable_length_path(db):
    db.write_nodes([{"id": BASE + i, "name": f"p{i}"} for i in range(4)], LABEL)
    db.write_edges([{"src": BASE + i, "dst": BASE + i + 1} for i in range(3)], "NEXT")
    rows = db.query("MATCH (a {id: $a})-[:NEXT*3..3]->(b) RETURN b.id AS id", {"a": BASE})
    assert rows == [{"id": BASE + 3}]


def test_error_surfaces_as_exception(db):
    with pytest.raises(HydraDBError) as err:
        db.query("MATCH (a) RETURN a.id AS id")
    assert err.value.code == "invalid_request"
