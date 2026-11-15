import pytest

from hydrahack.db import _chunks, _ident, cypher_strings, decode_cell


def test_decode_cells():
    assert decode_cell({"type": "vertex_id", "value": 7}) == 7
    assert decode_cell({"type": "null"}) is None
    assert decode_cell({"type": "list", "value": [{"type": "integer", "value": 1}]}) == [1]


def test_decode_path_untags_properties():
    cell = {
        "type": "path",
        "value": {
            "nodes": [{"id": 1, "labels": ["P"], "properties": {"name": {"String": "a"}}}],
            "relationships": [{"id": None, "edge_type": "R", "src": 1, "dst": 2, "properties": {}}],
        },
    }
    path = decode_cell(cell)
    assert path["nodes"][0]["properties"] == {"name": "a"}
    assert path["relationships"][0] == {"type": "R", "src": 1, "dst": 2, "properties": {}}


def test_cypher_strings_escapes_backslash_before_quote():
    assert cypher_strings(["o'brien"]) == "['o\\'brien']"
    assert cypher_strings(["a\\b"]) == "['a\\\\b']"


def test_ident_rejects_injection():
    assert _ident("Person_1") == "Person_1"
    with pytest.raises(ValueError):
        _ident("x) DETACH DELETE (n")


def test_chunks_respect_batch_limit():
    sizes = [len(c) for c in _chunks([{"id": i} for i in range(2500)])]
    assert sizes == [1000, 1000, 500]


def test_health_fails_when_round_trip_raises(monkeypatch):
    from hydrahack.db import HydraDB, HydraDBError

    db = HydraDB()
    monkeypatch.setattr(db._http, "get", lambda *a, **k: type("R", (), {"status_code": 200})())

    def boom(*a, **k):
        raise HydraDBError("rejected")

    monkeypatch.setattr(db, "write", boom)
    monkeypatch.setattr(db, "delete_ids", lambda ids: None)
    result = db.health()
    assert result["roundtrip"] is False
    assert result["ok"] is False
    assert db.health(roundtrip=False)["ok"] is True
