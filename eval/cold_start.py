"""Cold-start eval: Apis added to the catalog after deployment.

    uv run python -m eval.cold_start                 # test split, against HydraDB
    uv run python -m eval.cold_start --split val     # validation slice of train, for tuning
    uv run python -m eval.cold_start --memory        # same rankings from the in-memory store

A seeded 10% of the catalog's Apis is held out of every training run: any run that used one is
dropped from the stream, as if those endpoints were added after the router went live. They stay in
the catalog (with their Tool and Category edges) but no run has ever used them. Held-out tasks that
need at least one of them are the "new Api" slice; the rest are the "familiar" slice. Waypoint is
compared with and without its Tool-structure transfer (Params.w_new), against stateless BM25, the
nearest-run cache and the budget-matched flat k-NN. Held-out tasks are only routed, never written.
"""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

from eval.run_eval import RESULTS, K, flat_knn, flat_memory
from hydrahack.data import load
from hydrahack.router import Params, Router
from hydrahack.store import GraphStore, MemoryStore, Run
from hydrahack.text import BM25

SEED = 7
BATCH = 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["test", "val"], default="test")
    ap.add_argument("--frac", type=float, default=0.1)
    ap.add_argument("--memory", action="store_true", help="in-memory store instead of HydraDB")
    ap.add_argument("--w-new", type=float, default=Params().w_new)
    ap.add_argument("--new-tau", type=float, default=Params().new_tau)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ds = load()
    ids = sorted(a.idx for a in ds.apis)
    held = set(random.Random(SEED).sample(ids, round(args.frac * len(ids))))
    stream = [q for q in ds.stream_order if not ds.train[q] & held]
    gold = ds.test if args.split == "test" else ds.val
    eval_ids = sorted(gold, key=int)
    new = [q for q in eval_ids if gold[q] & held]
    familiar = [q for q in eval_ids if not gold[q] & held]

    store = MemoryStore() if args.memory else GraphStore()
    if args.memory:
        store.load_catalog(ds.apis)
    else:
        store.reset()
        if store.catalog_size() != len(ds.apis):
            store.load_catalog(ds.apis)
    params = Params(w_new=args.w_new, new_tau=args.new_tau)
    router = Router(ds.apis, store, params)
    stateless = Router(ds.apis, store, params, learn=False)
    pool = ThreadPoolExecutor(args.threads)

    memory: dict[int, set[int]] = {}
    mem_index = BM25()
    for i in range(0, len(stream), BATCH):
        batch = stream[i : i + BATCH]
        offered = pool.map(lambda q: router.route(ds.queries[q], K).tools, batch)
        runs = [
            Run(int(q), ds.queries[q], ds.train[q], set(off) - ds.train[q])
            for q, off in zip(batch, offered, strict=True)
        ]
        router.feedback(runs)
        for r in runs:
            memory[r.task_id] = r.used
            mem_index.add(r.task_id, r.text)

    def route_all(r: Router) -> dict[str, list[int]]:
        tools = pool.map(lambda q: r.route(ds.queries[q], K).tools, eval_ids)
        return dict(zip(eval_ids, tools, strict=True))

    tops = {"waypoint": route_all(router)}
    router.p = replace(params, w_new=0.0)
    tops["waypoint_no_transfer"] = route_all(router)
    router.p = params
    tops["bm25"] = route_all(stateless)
    tops["flat_memory"] = {
        q: flat_memory(memory, mem_index, tops["bm25"][q], ds.queries[q]) for q in eval_ids
    }
    tops["flat_knn"] = {
        q: flat_knn(memory, mem_index, router.api_index, params, ds.queries[q]) for q in eval_ids
    }

    def completeness(top: dict[str, list[int]], qs: list[str]) -> float:
        return round(sum(gold[q] <= set(top[q]) for q in qs) / (len(qs) or 1), 4)

    def new_recall(top: dict[str, list[int]]) -> float:
        need = [(q, a) for q in new for a in gold[q] & held]
        return round(sum(a in top[q] for q, a in need) / (len(need) or 1), 4)

    result = {
        "dataset": "ToolBench G3, COLT split (hf.co/datasets/Tool-COLT/ToolBenchG3)",
        "split": args.split,
        "store": "memory" if args.memory else "hydradb",
        "held_out_apis": len(held),
        "held_out_frac": args.frac,
        "seed": SEED,
        "train_stream": len(stream),
        "train_stream_full": len(ds.stream_order),
        "k": K,
        "params": params.__dict__,
        "tasks": {"new_api": len(new), "familiar": len(familiar), "all": len(eval_ids)},
        "completeness": {
            name: {
                "new_api": completeness(top, new),
                "familiar": completeness(top, familiar),
                "all": completeness(top, eval_ids),
            }
            for name, top in tops.items()
        },
        "new_api_recall": {name: new_recall(top) for name, top in tops.items()},
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    RESULTS.mkdir(exist_ok=True)
    out = args.out or RESULTS / f"cold-start-{args.split}.json"
    with open(out, "w") as f:
        f.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("tasks", "completeness", "new_api_recall")}, indent=2))


if __name__ == "__main__":
    main()
