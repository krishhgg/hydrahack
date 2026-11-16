"""Waypoint's router: text entry points, then a weighted traversal of the experience graph."""

from __future__ import annotations

import re
import threading
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from hydrahack.data import Api
from hydrahack.store import Clause, Run
from hydrahack.text import BM25

MAX_PARTS = 10


@dataclass
class Params:
    lex_top: int = 30
    task_top: int = 8
    clause_top: int = 6
    w_lex: float = 1.0
    w_exp: float = 4.0
    w_needs: float = 1.0
    w_rej: float = 0.3
    sim_power: float = 1.0
    w_new: float = 0.5
    new_tau: float = 0.3
    new_top: int = 10


_CLAUSE = re.compile(
    r"(?<=[.?!])\s+|\b(?:also|additionally|furthermore|moreover|and then)\b,?", re.IGNORECASE
)


def clauses(text: str) -> list[str]:
    """Split a multi-part task into its sub-requests ("...? Also, ..."). A single-part task returns
    itself, so every task has at least one clause."""
    parts = [p.strip() for p in _CLAUSE.split(text) if p and len(p.strip()) > 15]
    return parts[:MAX_PARTS] if len(parts) > 1 else [text.strip()]


@dataclass
class Route:
    tools: list[int]
    scores: dict[int, float]
    tasks: list[tuple[int, float]] = field(default_factory=list)
    clauses: list[dict] = field(default_factory=list)
    paths: dict[int, list[dict]] = field(default_factory=dict)
    factors: dict[int, float] = field(default_factory=dict)


class Router:
    def __init__(self, apis: Sequence[Api], store, params: Params | None = None, learn=True):
        self.apis = {a.idx: a for a in apis}
        self.store = store
        self.p = params or Params()
        self.learn = learn
        self.api_index = BM25()
        for a in apis:
            self.api_index.add(a.idx, f"{a.category} {a.tool} {a.name} {a.description}")
        self.task_index = BM25()
        self.clause_index = BM25()
        self.index_lock = threading.Lock()

    def remember(self, task_id: int, text: str) -> None:
        with self.index_lock:
            self.task_index.add(task_id, text)

    def remember_clause(self, clause_id: int, text: str) -> None:
        with self.index_lock:
            self.clause_index.add(clause_id, text)

    def _search(self, index: BM25, text: str, top: int):
        with self.index_lock:
            return index.search_scaled(text, top)

    def split(self, run: Run) -> list[Clause]:
        """Learn which sub-request each needed tool served: assign every used tool to the clause
        whose text matches the tool best. These become (Clause)-[:NEEDS]->(Api) edges."""
        parts = clauses(run.text)
        if len(parts) == 1:
            return [Clause(run.task_id * MAX_PARTS, run.task_id, parts[0], set(run.used))]
        needs: list[set[int]] = [set() for _ in parts]
        part_scores = []
        for part in parts:
            hits, ceiling = self.api_index.search_scaled(part, self.p.lex_top)
            part_scores.append({a: s / ceiling for a, s in hits})
        for a in run.used:
            best = max(range(len(parts)), key=lambda i: part_scores[i].get(a, 0.0))
            needs[best].add(a)
        return [
            Clause(run.task_id * MAX_PARTS + i, run.task_id, part, needs[i])
            for i, part in enumerate(parts)
            if needs[i]
        ]

    def route(self, text: str, k: int = 5) -> Route:
        p = self.p
        score: Counter[int] = Counter()
        paths: dict[int, list[dict]] = {}
        lex = self.api_index.search(text, p.lex_top)
        top_lex = lex[0][1] if lex else 1.0
        for a, s in lex:
            score[a] += p.w_lex * s / top_lex
            paths.setdefault(a, []).append(
                {"via": "text", "w": round(s / top_lex, 3), "c": p.w_lex * s / top_lex}
            )
        if not self.learn or not len(self.task_index):
            return self._finish(score, k, [], [], paths)

        hits, ceiling = self._search(self.task_index, text, p.task_top)
        tasks = [(t, (s / ceiling) ** p.sim_power) for t, s in hits]
        used = self.store.task_tools([t for t, _ in tasks])
        for t, sim in tasks:
            for a in used.get(t, ()):
                score[a] += p.w_exp * sim
                paths.setdefault(a, []).append(
                    {"via": "task", "task": t, "w": round(sim, 3), "c": p.w_exp * sim}
                )

        matched: list[dict] = []
        if p.w_needs and len(self.clause_index):
            for i, part in enumerate(clauses(text)):
                c_hits, c_ceiling = self._search(self.clause_index, part, p.clause_top)
                matched += [{"clause": c, "part": i, "w": s / c_ceiling} for c, s in c_hits]
            needs = self.store.clause_needs([m["clause"] for m in matched])
            for m in matched:
                for a in needs.get(m["clause"], ()):
                    score[a] += p.w_needs * m["w"]
                    paths.setdefault(a, []).append(
                        {
                            "via": "clause",
                            "clause": m["clause"],
                            "part": m["part"],
                            "w": round(m["w"], 3),
                            "c": p.w_needs * m["w"],
                        }
                    )

        if p.w_new:
            self._transfer_to_cold(text, score, paths)

        factor: dict[int, float] = {}
        if p.w_rej:
            cand = [a for a, _ in score.most_common(k * 3)]
            for a, (u, r) in self.store.outcomes(cand).items():
                if r:
                    factor[a] = 1 - p.w_rej * r / (u + r + 1)
                    score[a] *= factor[a]
        route = self._finish(score, k, tasks, matched, paths)
        route.factors = {a: factor.get(a, 1.0) for a in route.tools}
        return route

    def _transfer_to_cold(self, text: str, score: Counter, paths: dict) -> None:
        """Hand a share of a tool's learned vote to endpoints of the same Tool that no run has used
        yet, when the task's text matches the new endpoint at least as well as the voted one.
        A store of past runs has nothing to copy for such an endpoint; the graph reaches it
        through (:Api)<-[:HAS_API]-(:Tool)-[:HAS_API]->(:Api)."""
        p = self.p
        learned = {
            a: sum(x["c"] for x in ps if x["via"] in ("task", "clause")) for a, ps in paths.items()
        }
        top = sorted((a for a, e in learned.items() if e > 0), key=score.__getitem__, reverse=True)
        learned = {a: learned[a] for a in top[: p.new_top]}
        siblings = self.store.cold_siblings(list(learned))
        if not siblings:
            return
        lex = self.api_index.search(text, len(self.apis))
        ceiling = lex[0][1] if lex else 1.0
        rel = {a: s / ceiling for a, s in lex}
        for a, cold in siblings.items():
            for s in cold:
                rs = rel.get(s, 0.0)
                if rs < p.new_tau or rs <= rel.get(a, 0.0):
                    continue
                c = p.w_new * learned[a] * rs
                score[s] += c
                paths.setdefault(s, []).append({"via": "tool", "api": a, "w": round(rs, 3), "c": c})

    def _finish(self, score, k, tasks, matched, paths) -> Route:
        top = [a for a, _ in score.most_common(k)]
        return Route(
            top, {a: score[a] for a in top}, tasks, matched, {a: paths.get(a, []) for a in top}
        )

    def feedback(self, runs: Sequence[Run]) -> list[Clause]:
        parts = [c for r in runs for c in self.split(r)]
        self.store.add_runs(runs)
        self.store.add_clauses(parts)
        for r in runs:
            self.remember(r.task_id, r.text)
        for c in parts:
            self.remember_clause(c.clause_id, c.text)
        return parts
