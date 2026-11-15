"""Pick the held-out demo tasks shown as buttons in the UI (eval/results/examples.json).

    uv run python -m eval.examples

Picks test tasks whose tool combination never appeared in training, that Waypoint completes and
both stateless BM25 and the budget-matched flat k-NN miss, shortest first. It replays the training
stream into the in-memory store, which returns the same rankings as HydraDB
(tests/test_store_integration.py asserts that parity). Test labels are only read to choose
showcase tasks; nothing is written back. The headline numbers cover every test task.
"""

from __future__ import annotations

import json

from eval.run_eval import RESULTS, K, flat_knn
from hydrahack.data import load
from hydrahack.router import Params, Router
from hydrahack.store import MemoryStore, Run
from hydrahack.text import BM25

PICKS = 8


def main() -> None:
    ds = load()
    store = MemoryStore()
    store.load_catalog(ds.apis)
    params = Params()
    router = Router(ds.apis, store, params)
    stateless = Router(ds.apis, store, params, learn=False)
    memory: dict[int, set[int]] = {}
    index = BM25()
    for q in ds.stream_order:
        offered = router.route(ds.queries[q], K).tools
        run = Run(int(q), ds.queries[q], ds.train[q], set(offered) - ds.train[q])
        router.feedback([run])
        memory[run.task_id] = run.used
        index.add(run.task_id, run.text)
    seen = {frozenset(ds.train[q]) for q in ds.stream_order}
    wins = []
    for q in sorted(ds.test, key=int):
        gold, text = ds.test[q], ds.queries[q]
        if len(gold) < 2 or frozenset(gold) in seen:
            continue
        if not gold <= set(router.route(text, K).tools):
            continue
        if gold <= set(stateless.route(text, K).tools):
            continue
        if gold <= set(flat_knn(memory, index, router.api_index, params, text)):
            continue
        wins.append(q)
    wins.sort(key=lambda q: len(ds.queries[q]))
    demo = [{"id": q, "text": ds.queries[q], "gold": sorted(ds.test[q])} for q in wins[:PICKS]]
    (RESULTS / "examples.json").write_text(json.dumps(demo, indent=2) + "\n")
    print(f"{len(wins)} novel tasks Waypoint completes and both baselines miss; wrote {len(demo)}")


if __name__ == "__main__":
    main()
