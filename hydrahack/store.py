"""Where Waypoint's catalog and experience live.

`GraphStore` is the real store: HydraDB, with the catalog as (:Category)-[:HAS_TOOL]->(:Tool)
-[:HAS_API]->(:Api) and experience as (:Task)-[:USED]->(:Api) and (:Task)-[:REJECTED]->(:Api).
Co-usage is never stored as a counter: it is the number of Task paths Api<-USED-Task-USED->Api,
counted by a 2-hop traversal at query time, so it grows the moment a run is written back.

`MemoryStore` answers the same four questions from Python dicts. It exists for unit tests and for
the "flat store" comparison in eval/, never for the live app.
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from hydrahack.data import Api
from hydrahack.db import HydraDB

API_BASE = 1_000_000
TOOL_BASE = 2_000_000
CAT_BASE = 3_000_000
TASK_BASE = 10_000_000


def api_node(idx: int) -> int:
    return API_BASE + idx


def task_node(task_id: int) -> int:
    return TASK_BASE + task_id


@dataclass
class Run:
    """One finished agent run: the task, the tools it needed, and tools offered but not needed."""

    task_id: int
    text: str
    used: set[int]
    rejected: set[int]


class MemoryStore:
    def __init__(self) -> None:
        self.tool_of: dict[int, str] = {}
        self.by_tool: dict[str, set[int]] = defaultdict(set)
        self.task_used: dict[int, set[int]] = {}
        self.api_tasks: dict[int, set[int]] = defaultdict(set)
        self.rejected: Counter[int] = Counter()

    def load_catalog(self, apis: Sequence[Api]) -> None:
        for a in apis:
            self.tool_of[a.idx] = a.tool
            self.by_tool[a.tool].add(a.idx)

    def add_runs(self, runs: Sequence[Run]) -> None:
        for r in runs:
            self.task_used[r.task_id] = set(r.used)
            for a in r.used:
                self.api_tasks[a].add(r.task_id)
            for a in r.rejected:
                self.rejected[a] += 1

    def task_tools(self, task_ids: Iterable[int]) -> dict[int, set[int]]:
        return {t: self.task_used[t] for t in task_ids if t in self.task_used}

    def coused(self, api_ids: Iterable[int]) -> dict[int, Counter[int]]:
        out: dict[int, Counter[int]] = {}
        for s in api_ids:
            c: Counter[int] = Counter()
            for t in self.api_tasks.get(s, ()):
                for b in self.task_used[t]:
                    if b != s:
                        c[b] += 1
            out[s] = c
        return out

    def siblings(self, api_ids: Iterable[int]) -> dict[int, set[int]]:
        return {s: self.by_tool[self.tool_of[s]] - {s} for s in api_ids if s in self.tool_of}

    def outcomes(self, api_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
        return {a: (len(self.api_tasks.get(a, ())), self.rejected[a]) for a in api_ids}

    def runs(self) -> list[tuple[int, str]]:
        return []


class GraphStore:
    """Waypoint's state in HydraDB. Every read below is one Cypher traversal."""

    def __init__(self, db: HydraDB | None = None) -> None:
        self.db = db or HydraDB()
        self.lock = threading.Lock()

    def reset(self) -> None:
        """Forget all experience: Task nodes, their edges and the Api outcome counters."""
        self.db.reset(labels=["Task"])
        rows = self.db.query("MATCH (a:Api) RETURN a.id AS id")
        self.db.write_nodes([{"id": r["id"], "used": 0, "rejected": 0} for r in rows], "Api")

    def reset_all(self) -> None:
        self.db.reset(labels=["Task", "Api", "Tool", "Category"])

    def load_catalog(self, apis: Sequence[Api]) -> None:
        cats = sorted({a.category for a in apis})
        tools = sorted({(a.category, a.tool) for a in apis})
        cat_id = {c: CAT_BASE + i for i, c in enumerate(cats)}
        tool_id = {t: TOOL_BASE + i for i, t in enumerate(tools)}
        self.db.write_nodes([{"id": cat_id[c], "name": c} for c in cats], "Category")
        self.db.write_nodes(
            [{"id": tool_id[t], "name": t[1], "category": t[0]} for t in tools], "Tool"
        )
        self.db.write_nodes(
            [
                {
                    "id": api_node(a.idx),
                    "idx": a.idx,
                    "name": a.name,
                    "tool": a.tool,
                    "category": a.category,
                    "description": a.description[:400],
                }
                for a in apis
            ],
            "Api",
        )
        self.db.write_edges([{"src": cat_id[t[0]], "dst": tool_id[t]} for t in tools], "HAS_TOOL")
        self.db.write_edges(
            [{"src": tool_id[(a.category, a.tool)], "dst": api_node(a.idx)} for a in apis],
            "HAS_API",
        )

    def catalog_size(self) -> int:
        rows = self.db.query("MATCH (a:Api) RETURN count(*) AS n")
        return rows[0]["n"] if rows else 0

    def add_runs(self, runs: Sequence[Run]) -> None:
        """Write runs as Task nodes with USED and REJECTED edges, then fold the outcome counts into
        each touched Api node. Edge counting at query time grows with the number of Tasks, so the
        hot path reads these node counters instead; the edges stay the source of truth."""
        self.db.write_nodes(
            [{"id": task_node(r.task_id), "text": r.text[:2000]} for r in runs], "Task"
        )
        self.db.write_edges(
            [{"src": task_node(r.task_id), "dst": api_node(a)} for r in runs for a in r.used],
            "USED",
        )
        self.db.write_edges(
            [{"src": task_node(r.task_id), "dst": api_node(a)} for r in runs for a in r.rejected],
            "REJECTED",
        )
        delta: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        for r in runs:
            for a in r.used:
                delta[a][0] += 1
            for a in r.rejected:
                delta[a][1] += 1
        with self.lock:
            current = self.outcomes(list(delta))
            self.db.write_nodes(
                [
                    {
                        "id": api_node(a),
                        "used": current[a][0] + d[0],
                        "rejected": current[a][1] + d[1],
                    }
                    for a, d in delta.items()
                ],
                "Api",
            )

    def task_tools(self, task_ids: Iterable[int]) -> dict[int, set[int]]:
        ids = [task_node(t) for t in task_ids]
        out: dict[int, set[int]] = defaultdict(set)
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (t:Task)-[:USED]->(a:Api) WHERE t.id IN $ids RETURN t.id AS t, a.idx AS a",
            {"ids": ids},
        )
        for r in rows:
            out[r["t"] - TASK_BASE].add(r["a"])
        return out

    def coused(self, api_ids: Iterable[int]) -> dict[int, Counter[int]]:
        ids = [api_node(a) for a in api_ids]
        out: dict[int, Counter[int]] = defaultdict(Counter)
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (s:Api)<-[:USED]-(t:Task)-[:USED]->(b:Api) WHERE s.id IN $ids "
            "RETURN s.idx AS s, b.idx AS b, count(*) AS n",
            {"ids": ids},
        )
        for r in rows:
            if r["s"] != r["b"]:
                out[r["s"]][r["b"]] += r["n"]
        return out

    def siblings(self, api_ids: Iterable[int]) -> dict[int, set[int]]:
        ids = [api_node(a) for a in api_ids]
        out: dict[int, set[int]] = defaultdict(set)
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (s:Api)<-[:HAS_API]-(x:Tool)-[:HAS_API]->(b:Api) WHERE s.id IN $ids "
            "RETURN s.idx AS s, b.idx AS b",
            {"ids": ids},
        )
        for r in rows:
            if r["s"] != r["b"]:
                out[r["s"]].add(r["b"])
        return out

    def outcomes(self, api_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
        ids = [api_node(a) for a in api_ids]
        out = {a: (0, 0) for a in api_ids}
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (a:Api) WHERE a.id IN $ids RETURN a.idx AS a, a.used AS u, a.rejected AS r",
            {"ids": ids},
        )
        for r in rows:
            out[r["a"]] = (r["u"] or 0, r["r"] or 0)
        return out

    def runs(self) -> list[tuple[int, str]]:
        rows = self.db.query("MATCH (t:Task) RETURN t.id AS id, t.text AS text")
        return [(r["id"] - TASK_BASE, r["text"] or "") for r in rows]
