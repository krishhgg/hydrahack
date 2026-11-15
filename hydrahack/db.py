"""Low-level HydraDB client over the HTTP query API.

Why HTTP and not Bolt: the node advertises one Bolt address and a routed driver follows it, so
the same URL cannot work from the host and from another container. HTTP has no such problem and
needs only httpx. The engine's dialect is narrow; see docs/hydradb-notes.md before writing Cypher.
"""

from __future__ import annotations

import os
import random
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import httpx

DEFAULT_TOKEN = "local-development-token-32-bytes"
BATCH_LIMIT = 1000  # the engine rejects batches above 1024 items


class HydraDBError(RuntimeError):
    """The engine rejected a query or answered with something that is not a result."""

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def decode_cell(cell: dict[str, Any]) -> Any:
    """Turn a typed result cell into a plain Python value.

    Node ids come back as `vertex_id` (an int), aggregates as `integer`, a null has no `value`.
    Path cells use a third encoding where property values are tagged by capitalised type name.
    """
    kind = cell.get("type")
    value = cell.get("value")
    if kind == "null" or value is None:
        return None
    if kind == "list":
        return [decode_cell(item) for item in value]
    if kind == "path":
        return {
            "nodes": [
                {
                    "id": n["id"],
                    "labels": n.get("labels", []),
                    "properties": {k: _untag(v) for k, v in n.get("properties", {}).items()},
                }
                for n in value["nodes"]
            ],
            "relationships": [
                {
                    "type": r["edge_type"],
                    "src": r["src"],
                    "dst": r["dst"],
                    "properties": {k: _untag(v) for k, v in r.get("properties", {}).items()},
                }
                for r in value["relationships"]
            ],
        }
    return value


def _untag(tagged: Any) -> Any:
    if isinstance(tagged, dict) and len(tagged) == 1:
        return next(iter(tagged.values()))
    return tagged


def cypher_strings(values: Iterable[str]) -> str:
    """Inline a list of strings as a Cypher literal (list parameters are rejected by the engine,
    e.g. in algo.MSpaths). Backslashes are escaped before quotes."""
    return (
        "["
        + ", ".join("'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'" for v in values)
        + "]"
    )


class HydraDB:
    """Client for one graph and one cell of a HydraDB node."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        graph: str = "default",
        cell_id: str = "cell-0",
        admin_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.url = (url or os.environ.get("HYDRADB_URL", "http://127.0.0.1:8443")).rstrip("/")
        self.admin_url = (
            admin_url or os.environ.get("HYDRADB_ADMIN_URL", "http://127.0.0.1:9090")
        ).rstrip("/")
        self.graph = graph
        self.cell_id = cell_id
        token = token or os.environ.get("HYDRADB_TOKEN", DEFAULT_TOKEN)
        self._http = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=64),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HydraDB:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        body = {"cell_id": self.cell_id, **body}
        resp = self._http.post(f"{self.url}/v1/graphs/{self.graph}/query", json=body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if "error" in payload:
            err = payload["error"]
            raise HydraDBError(err.get("message", str(err)), err.get("code"), resp.status_code)
        if resp.status_code != 200 or "rows" not in payload:
            # 422 on a malformed body is a bare string with neither rows nor error
            raise HydraDBError(
                f"unexpected response {resp.status_code}: {resp.text[:300]}",
                status=resp.status_code,
            )
        return payload

    def execute(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 1024,
        consistency: str | None = None,
        bookmark: str | None = None,
    ) -> dict[str, Any]:
        """Run one query and return the raw first page (columns, rows, bookmark, next_cursor)."""
        body: dict[str, Any] = {"query": cypher, "page_size": page_size}
        if params:
            body["parameters"] = params
        if consistency:
            body["consistency"] = consistency
        if bookmark:
            body["bookmark"] = bookmark
        return self._post(body)

    def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 1024,
        consistency: str | None = None,
        bookmark: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a query and return every row as a dict keyed by column, following pagination.

        Each page is fetched exactly once: the engine's cursor is a consuming iterator, so a
        retried page fetch would silently skip rows.
        """
        return list(
            self.iter_rows(
                cypher, params, page_size=page_size, consistency=consistency, bookmark=bookmark
            )
        )

    def iter_rows(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 1024,
        consistency: str | None = None,
        bookmark: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = self.execute(
            cypher, params, page_size=page_size, consistency=consistency, bookmark=bookmark
        )
        while True:
            columns = page["columns"]
            for row in page["rows"]:
                yield {c: decode_cell(cell) for c, cell in zip(columns, row, strict=True)}
            cursor = page.get("next_cursor")
            if cursor is None:
                return
            body: dict[str, Any] = {
                "query": cypher,
                "page_size": page_size,  # must be resent on every page
                "cursor": cursor,
                "query_id": page["query_id"],
            }
            if params:
                body["parameters"] = params
            page = self._post(body)

    def write(self, cypher: str, params: dict[str, Any] | None = None) -> str | None:
        """Run a mutation; returns the bookmark for read-your-writes on a later read."""
        return self.execute(cypher, params).get("bookmark")

    def write_nodes(self, rows: Sequence[dict[str, Any]], label: str) -> None:
        """Upsert labelled nodes with properties. Each row needs `id`; other keys become
        properties. All rows must have the same keys. Label comes first: the engine requires
        exactly one SET label and edges-first leaves a window with unlabelled nodes."""
        if not rows:
            return
        props = [k for k in rows[0] if k != "id"]
        assignments = ", ".join(
            [f"n:{_ident(label)}"] + [f"n.{_ident(k)} = row.{_ident(k)}" for k in props]
        )
        cypher = f"UNWIND $rows AS row MERGE (n {{id: row.id}}) SET {assignments}"
        for chunk in _chunks(rows):
            self.write(cypher, {"rows": chunk})

    def write_edges(self, rows: Sequence[dict[str, int]], rel_type: str) -> None:
        """Idempotently create edges from {src, dst} rows (batched, deduplicated on src,dst,type).
        Endpoint nodes are created unlabelled if absent, so call write_nodes first."""
        if not rows:
            return
        cypher = (
            f"UNWIND $rows AS row CREATE (a {{id: row.src}})-"
            f"[:{_ident(rel_type)}]->(b {{id: row.dst}})"
        )
        for chunk in _chunks(rows):
            self.write(cypher, {"rows": chunk})

    def delete_ids(self, ids: Iterable[int]) -> None:
        for chunk in _chunks([{"id": i} for i in ids]):
            self.write(
                "UNWIND $rows AS row MATCH (n {id: row.id}) DETACH DELETE n", {"rows": chunk}
            )

    def reset(self, labels: Iterable[str] = (), ids: Iterable[int] = ()) -> None:
        """Delete every node carrying one of `labels` and every node in `ids`, with their edges.

        The engine has no unanchored scan and a node cannot be enumerated without a label, so a
        full wipe is `docker compose down -v`. Applications should label what they write.
        """
        for label in labels:
            self.write(f"MATCH (n:{_ident(label)}) DETACH DELETE n")
        self.delete_ids(ids)

    def health(self, roundtrip: bool = True) -> dict[str, Any]:
        """Liveness (/healthz), readiness (/readyz) and, by default, a write/read/delete round
        trip on a throwaway id pair. A listening port is not proof the store accepts writes."""
        result: dict[str, Any] = {"healthz": False, "readyz": False, "roundtrip": None}
        try:
            result["healthz"] = self._http.get(f"{self.url}/healthz").status_code == 200
            result["readyz"] = self._http.get(f"{self.admin_url}/readyz").status_code == 200
            if roundtrip and result["healthz"]:
                src = random.randrange(900_000_000, 999_000_000)
                dst = src + 1
                try:
                    self.write(
                        "MERGE (a {id: $s})-[:HEALTHCHECK]->(b {id: $d})", {"s": src, "d": dst}
                    )
                    rows = self.query(
                        "MATCH (a {id: $s})-[:HEALTHCHECK]->(b) RETURN b.id AS id",
                        {"s": src},
                        consistency="strong",
                    )
                    result["roundtrip"] = rows == [{"id": dst}]
                finally:
                    self.delete_ids([src, dst])
        except (httpx.HTTPError, HydraDBError):
            pass
        result["ok"] = (
            result["healthz"] and result["readyz"] and result["roundtrip"] in (True, None)
        )
        return result


def _ident(name: str) -> str:
    if not name.replace("_", "").isalnum() or name[0].isdigit():
        raise ValueError(f"unsafe Cypher identifier: {name!r}")
    return name


def _chunks(
    rows: Sequence[dict[str, Any]], size: int = BATCH_LIMIT
) -> Iterator[list[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield list(rows[i : i + size])
