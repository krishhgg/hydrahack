"""Waypoint's router: text entry points, then a weighted traversal of the experience graph."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from hydrahack.data import Api
from hydrahack.store import Run
from hydrahack.text import BM25


@dataclass
class Params:
    lex_top: int = 30
    task_top: int = 8
    seeds: int = 6
    w_lex: float = 1.0
    w_exp: float = 4.0
    w_co: float = 0.0
    w_sib: float = 0.0
    w_rej: float = 0.3
    sim_power: float = 1.0


@dataclass
class Route:
    tools: list[int]
    scores: dict[int, float]
    tasks: list[tuple[int, float]] = field(default_factory=list)
    paths: dict[int, list[dict]] = field(default_factory=dict)


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

    def remember(self, task_id: int, text: str) -> None:
        self.task_index.add(task_id, text)

    def route(self, text: str, k: int = 5) -> Route:
        p = self.p
        score: Counter[float] = Counter()
        paths: dict[int, list[dict]] = {}
        lex = self.api_index.search(text, p.lex_top)
        top_lex = lex[0][1] if lex else 1.0
        for a, s in lex:
            score[a] += p.w_lex * s / top_lex
            paths.setdefault(a, []).append({"via": "text", "w": round(s / top_lex, 3)})
        tasks: list[tuple[int, float]] = []
        if self.learn and len(self.task_index):
            hits, ceiling = self.task_index.search_scaled(text, p.task_top)
            if hits:
                tasks = [(t, (s / ceiling) ** p.sim_power) for t, s in hits]
                used = self.store.task_tools([t for t, _ in tasks])
                for t, sim in tasks:
                    for a in used.get(t, ()):
                        score[a] += p.w_exp * sim
                        paths.setdefault(a, []).append(
                            {"via": "task", "task": t, "w": round(sim, 3)}
                        )
        if not self.learn:
            return self._finish(score, k, tasks, paths)
        seeds = [a for a, _ in score.most_common(p.seeds)]
        base = dict(score)
        co = self.store.coused(seeds)
        sib = self.store.siblings(seeds)
        for s in seeds:
            c = co.get(s)
            if c:
                total = sum(c.values())
                for b, n in c.items():
                    w = base[s] * n / total
                    score[b] += p.w_co * w
                    paths.setdefault(b, []).append(
                        {"via": "co_used", "from": s, "w": round(n / total, 3)}
                    )
            for b in sib.get(s, ()):
                score[b] += p.w_sib * base[s]
        if p.w_rej:
            cand = [a for a, _ in score.most_common(k * 3)]
            for a, (u, r) in self.store.outcomes(cand).items():
                if r:
                    score[a] *= 1 - p.w_rej * r / (u + r + 1)
        return self._finish(score, k, tasks, paths)

    def _finish(self, score, k, tasks, paths) -> Route:
        top = [a for a, _ in score.most_common(k)]
        return Route(top, {a: score[a] for a in top}, tasks, {a: paths.get(a, []) for a in top})

    def feedback(self, runs: Sequence[Run]) -> None:
        self.store.add_runs(runs)
        for r in runs:
            self.remember(r.task_id, r.text)
