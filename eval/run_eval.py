"""Waypoint's learning-curve eval on ToolBench G3 (COLT split), against a running HydraDB.

The router serves training tasks in order. After each task it reports which tools it offered; the
run's outcome (tools needed, tools offered but not needed) is written back into HydraDB as a Task
node with USED and REJECTED edges. At each checkpoint every held-out task is routed and scored.
Held-out tasks are only ever routed, never written back.

    uv run python -m eval.run_eval              # test split, writes eval/results/
    uv run python -m eval.run_eval --split val  # validation slice of train, for tuning
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from hydrahack.data import load
from hydrahack.router import Params, Router, clauses
from hydrahack.store import GraphStore, Run
from hydrahack.text import BM25

RESULTS = Path(__file__).resolve().parent / "results"
CHECKPOINTS = [0, 250, 500, 1000, 2000, 4000, 8000, 12000, 16000, 19361]
K = 5


def tokens_of(texts: list[str]) -> list[int]:
    import tiktoken

    enc = tiktoken.get_encoding("o200k_base")
    return [len(enc.encode(t)) for t in texts]


def score(tops: dict[str, list[int]], gold: dict[str, set[int]], ids: list[str]) -> dict:
    comp = rec = 0.0
    for q in ids:
        hit = len(gold[q] & set(tops[q][:K]))
        rec += hit / len(gold[q])
        comp += hit == len(gold[q])
    n = len(ids) or 1
    return {"completeness": round(comp / n, 4), "recall": round(rec / n, 4), "n": len(ids)}


def flat_memory(memory: dict[int, set[int]], index: BM25, baseline: list[int], text: str):
    """The plain-store baseline: copy the nearest past task's tools, pad with BM25."""
    hits = index.search(text, 1)
    out = list(memory[hits[0][0]]) if hits else []
    return (out + [a for a in baseline if a not in out])[:K]


def flat_knn(memory: dict[int, set[int]], index: BM25, api_index: BM25, p: Params, text: str):
    """Budget-matched plain-store baseline: Waypoint's scoring, weights and candidate counts
    (lex_top tools, task_top past runs for the task, clause_top past runs per sub-request) over a
    key-value store of whole runs. It has no Clause-NEEDS links and no rejection counters."""
    score: Counter[int] = Counter()
    lex = api_index.search(text, p.lex_top)
    top = lex[0][1] if lex else 1.0
    for a, s in lex:
        score[a] += p.w_lex * s / top
    hits, ceiling = index.search_scaled(text, p.task_top)
    for t, s in hits:
        for a in memory[t]:
            score[a] += p.w_exp * (s / ceiling) ** p.sim_power
    for part in clauses(text):
        hits, ceiling = index.search_scaled(part, p.clause_top)
        for t, s in hits:
            for a in memory[t]:
                score[a] += p.w_needs * s / ceiling
    return [a for a, _ in score.most_common(K)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["test", "val"], default="test")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N tasks")
    ap.add_argument("--w-rej", type=float, default=Params().w_rej)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ds = load()
    gold = ds.test if args.split == "test" else ds.val
    eval_ids = sorted(gold, key=int)[: args.limit]
    stream = ds.stream_order

    store = GraphStore()
    store.reset()
    if store.catalog_size() != len(ds.apis):
        store.load_catalog(ds.apis)
    params = Params(w_rej=args.w_rej)
    router = Router(ds.apis, store, params)
    stateless = Router(ds.apis, store, params, learn=False)

    pool = ThreadPoolExecutor(args.threads)
    baseline = dict(
        zip(
            eval_ids,
            pool.map(lambda q: stateless.route(ds.queries[q], K).tools, eval_ids),
            strict=True,
        )
    )
    train_sets = {frozenset(ds.train[q]) for q in stream}
    seen = [q for q in eval_ids if frozenset(gold[q]) in train_sets]
    novel = [q for q in eval_ids if frozenset(gold[q]) not in train_sets]

    memory: dict[int, set[int]] = {}
    mem_index = BM25()
    curve = []
    served = 0
    t0 = time.time()
    for cp in CHECKPOINTS:
        batch = stream[served:cp]
        if batch:
            offered = pool.map(lambda q: router.route(ds.queries[q], K).tools, batch)
            runs = [
                Run(int(q), ds.queries[q], ds.train[q], set(off) - ds.train[q])
                for q, off in zip(batch, offered, strict=True)
            ]
            router.feedback(runs)
            for r in runs:
                memory[r.task_id] = r.used
                mem_index.add(r.task_id, r.text)
            served = cp

        def timed(q):
            s = time.perf_counter()
            tools = router.route(ds.queries[q], K).tools
            return tools, (time.perf_counter() - s) * 1000

        out = list(pool.map(timed, eval_ids))
        tops = {q: o[0] for q, o in zip(eval_ids, out, strict=True)}
        lat = sorted(o[1] for o in out)
        flat = {q: flat_memory(memory, mem_index, baseline[q], ds.queries[q]) for q in eval_ids}
        knn = {
            q: flat_knn(memory, mem_index, router.api_index, params, ds.queries[q])
            for q in eval_ids
        }
        point = {
            "runs": served,
            "waypoint": score(tops, gold, eval_ids),
            "bm25": score(baseline, gold, eval_ids),
            "flat_memory": score(flat, gold, eval_ids),
            "flat_knn": score(knn, gold, eval_ids),
            "slices": {
                name: {
                    "waypoint": score(tops, gold, ids),
                    "bm25": score(baseline, gold, ids),
                    "flat_memory": score(flat, gold, ids),
                    "flat_knn": score(knn, gold, ids),
                }
                for name, ids in (("seen_toolset", seen), ("novel_toolset", novel))
            },
            "latency_ms": {
                "p50": round(statistics.median(lat), 1),
                "p95": round(lat[int(0.95 * (len(lat) - 1))], 1),
            },
        }
        curve.append(point)
        print(
            f"runs={served:>6} waypoint C@5={point['waypoint']['completeness']:.3f} "
            f"bm25={point['bm25']['completeness']:.3f} "
            f"flat={point['flat_memory']['completeness']:.3f} "
            f"knn={point['flat_knn']['completeness']:.3f} "
            f"p50={point['latency_ms']['p50']}ms t={time.time() - t0:.0f}s",
            flush=True,
        )
        last_tops = tops

    by_idx = {a.idx: a.text for a in ds.apis}
    catalog_tokens = tokens_of(list(by_idx.values()))
    tok = dict(zip(by_idx, catalog_tokens, strict=True))
    loaded = [sum(tok[a] for a in last_tops[q][:K]) for q in eval_ids]
    final = curve[-1]
    result = {
        "dataset": "ToolBench G3, COLT split (hf.co/datasets/Tool-COLT/ToolBenchG3)",
        "split": args.split,
        "eval_tasks": len(eval_ids),
        "train_stream": len(stream),
        "k": K,
        "params": params.__dict__,
        "metric": "Completeness@5: share of held-out tasks whose every needed tool is in the top 5",
        "baseline": "stateless BM25 over tool descriptions (Waypoint's entry-point index)",
        "curve": curve,
        "headline": {
            "baseline": final["bm25"]["completeness"],
            "waypoint": final["waypoint"]["completeness"],
            "flat_memory": final["flat_memory"]["completeness"],
            "flat_knn": final["flat_knn"]["completeness"],
            "recall5_baseline": final["bm25"]["recall"],
            "recall5_waypoint": final["waypoint"]["recall"],
            "tokens_per_task_waypoint": round(statistics.mean(loaded)),
            "tokens_catalog": sum(catalog_tokens),
            "latency_p50_ms": final["latency_ms"]["p50"],
            "latency_p95_ms": final["latency_ms"]["p95"],
        },
        "slices": {
            name: {"n": v["waypoint"]["n"], **{m: v[m]["completeness"] for m in v}}
            for name, v in final["slices"].items()
        },
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    RESULTS.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else RESULTS / f"waypoint-{args.split}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["headline"], indent=2))
    print(json.dumps(result["slices"], indent=2))


if __name__ == "__main__":
    main()
