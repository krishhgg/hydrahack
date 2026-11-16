"""Where Waypoint's catalog and experience live.

`GraphStore` is the real store: HydraDB, with the catalog as (:Category)-[:HAS_TOOL]->(:Tool)
-[:HAS_API]->(:Api) and experience as (:Task)-[:USED]->(:Api), (:Task)-[:REJECTED]->(:Api) and
(:Task)-[:HAS_CLAUSE]->(:Clause)-[:NEEDS]->(:Api), where a Clause is one sub-request of a task and
NEEDS records which of the task's tools served it.

`MemoryStore` answers the same questions from Python dicts. It exists for unit tests and the
in-memory parity check, never for the live app.
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
CLAUSE_BASE = 100_000_000


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


@dataclass
class Clause:
    """One sub-request of a run and the tools it needed."""

    clause_id: int
    task_id: int
    text: str
    needs: set[int]


def clause_node(clause_id: int) -> int:
    return CLAUSE_BASE + clause_id


class MemoryStore:
    def __init__(self) -> None:
        self.tool_of: dict[int, tuple[str, str]] = {}
        self.by_tool: dict[tuple[str, str], set[int]] = defaultdict(set)
        self.task_used: dict[int, set[int]] = {}
        self.api_tasks: dict[int, set[int]] = defaultdict(set)
        self.rejected: Counter[int] = Counter()
        self.needs: dict[int, set[int]] = {}
        self.clause_task: dict[int, int] = {}

    def load_catalog(self, apis: Sequence[Api]) -> None:
        for a in apis:
            self.tool_of[a.idx] = (a.category, a.tool)
            self.by_tool[(a.category, a.tool)].add(a.idx)

    def add_runs(self, runs: Sequence[Run]) -> None:
        for r in runs:
            self.task_used[r.task_id] = set(r.used)
            for a in r.used:
                self.api_tasks[a].add(r.task_id)
            for a in r.rejected:
                self.rejected[a] += 1

    def task_tools(self, task_ids: Iterable[int]) -> dict[int, set[int]]:
        return {t: self.task_used[t] for t in task_ids if t in self.task_used}

    def add_clauses(self, parts: Sequence[Clause]) -> None:
        for c in parts:
            self.needs[c.clause_id] = set(c.needs)
            self.clause_task[c.clause_id] = c.task_id

    def clause_needs(self, clause_ids: Iterable[int]) -> dict[int, set[int]]:
        return {c: self.needs[c] for c in clause_ids if c in self.needs}

    def outcomes(self, api_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
        return {a: (len(self.api_tasks.get(a, ())), self.rejected[a]) for a in api_ids}

    def cold_siblings(self, api_ids: Iterable[int]) -> dict[int, set[int]]:
        out: dict[int, set[int]] = {}
        for a in api_ids:
            tool = self.by_tool[self.tool_of[a]]
            cold = {s for s in tool if s != a and not self.api_tasks.get(s)}
            if cold:
                out[a] = cold
        return out

    def runs(self) -> list[tuple[int, str]]:
        return []

    def clause_texts(self) -> list[tuple[int, str]]:
        return []


class GraphStore:
    """Waypoint's state in HydraDB. Every read below is one Cypher traversal."""

    def __init__(self, db: HydraDB | None = None) -> None:
        self.db = db or HydraDB()
        self.lock = threading.Lock()

    def reset(self) -> None:
        """Forget all experience: Task nodes, their edges and the Api outcome counters."""
        self.db.reset(labels=["Task", "Clause"])
        rows = self.db.query("MATCH (a:Api) RETURN a.id AS id")
        self.db.write_nodes([{"id": r["id"], "used": 0, "rejected": 0} for r in rows], "Api")

    def reset_all(self) -> None:
        self.db.reset(labels=["Task", "Clause", "Api", "Tool", "Category"])

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

    def add_clauses(self, parts: Sequence[Clause]) -> None:
        self.db.write_nodes(
            [{"id": clause_node(c.clause_id), "text": c.text[:1000]} for c in parts], "Clause"
        )
        self.db.write_edges(
            [{"src": task_node(c.task_id), "dst": clause_node(c.clause_id)} for c in parts],
            "HAS_CLAUSE",
        )
        self.db.write_edges(
            [{"src": clause_node(c.clause_id), "dst": api_node(a)} for c in parts for a in c.needs],
            "NEEDS",
        )

    def clause_needs(self, clause_ids: Iterable[int]) -> dict[int, set[int]]:
        ids = [clause_node(c) for c in clause_ids]
        out: dict[int, set[int]] = defaultdict(set)
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (c:Clause)-[:NEEDS]->(a:Api) WHERE c.id IN $ids RETURN c.id AS c, a.idx AS a",
            {"ids": ids},
        )
        for r in rows:
            out[r["c"] - CLAUSE_BASE].add(r["a"])
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

    def cold_siblings(self, api_ids: Iterable[int]) -> dict[int, set[int]]:
        """Two hops through the catalog: other endpoints of the same Tool that no run has used
        yet, such as endpoints added after deployment."""
        ids = [api_node(a) for a in api_ids]
        out: dict[int, set[int]] = defaultdict(set)
        if not ids:
            return out
        rows = self.db.query(
            "MATCH (a:Api)<-[:HAS_API]-(t:Tool)-[:HAS_API]->(s:Api) "
            "WHERE a.id IN $ids AND s.id <> a.id AND (s.used IS NULL OR s.used = 0) "
            "RETURN a.idx AS a, s.idx AS s",
            {"ids": ids},
        )
        for r in rows:
            out[r["a"]].add(r["s"])
        return out

    def clause_texts(self) -> list[tuple[int, str]]:
        rows = self.db.query("MATCH (c:Clause) RETURN c.id AS id, c.text AS text")
        return [(r["id"] - CLAUSE_BASE, r["text"] or "") for r in rows]

    def runs(self) -> list[tuple[int, str]]:
        rows = self.db.query("MATCH (t:Task) RETURN t.id AS id, t.text AS text")
        return [(r["id"] - TASK_BASE, r["text"] or "") for r in rows]
