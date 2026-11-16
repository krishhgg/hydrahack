"""Live agent check: does Waypoint cut an agent's tokens and round trips without hurting success?

A small real-agent run on 40 held-out ToolBench G3 tasks (COLT test split, each needing at least
two tools). The same OpenAI model, system prompt and mocked call_api are used in four
conditions that differ only in how the agent finds tools:

  catalog   all 1,419 tool schemas are preloaded in the system prompt; the agent only has call_api
  search    search_tools(query): stateless BM25, top 5 schemas (Router(..., learn=False))
  flat_knn  find_tools(task): the budget-matched learned control, eval.run_eval.flat_knn over a
            key-value memory of all 19,361 training runs, Waypoint's weights and candidate counts,
            no graph and no network call, top 5 schemas
  waypoint  find_tools(task): the real POST /mcp endpoint of a running Waypoint app, k = 5

Stateless search has no feedback at all, so it shows what a tool-search feature gives without
learning. flat_knn is the budget-matched learned control: it gets the same training runs, the same
scoring weights and the same k as Waypoint, so Waypoint vs flat_knn isolates what the graph adds.

Execution is mocked: call_api returns a canned success. Test labels are used only for scoring;
nothing is written to the graph (no /api/feedback, no report_run).

    docker compose down -v && docker compose --profile app up -d --build   # wait for /health
    uv run python -m eval.agent_check                    # needs OPENAI_API_KEY in the environment

Every LLM call and every /mcp reply is cached under data/llm_cache/agent_check/, keyed by the exact
request, so a rerun costs nothing and reproduces the committed numbers (latencies are replayed from
the cache). Use --refresh to ignore the cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

from eval.run_eval import flat_knn
from hydrahack.data import DATA_DIR, load
from hydrahack.mcp import tool_schema
from hydrahack.router import Params, Router
from hydrahack.text import BM25

RESULTS = Path(__file__).resolve().parent / "results"
CACHE = DATA_DIR / "llm_cache" / "agent_check"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
WAYPOINT_URL = os.environ.get("WAYPOINT_URL", "http://127.0.0.1:8000")
MODEL = "gpt-5.4-mini"
EXPECTED_LEARNED_TASKS = 19361
SAMPLE_SEED = 7
SAMPLE_SIZE = 40
K = 5
MAX_MODEL_CALLS = 12
MAX_OUTPUT_TOKENS = 2000
CONDITIONS = ["catalog", "search", "flat_knn", "waypoint"]
# USD per 1M tokens, from https://developers.openai.com/api/docs/pricing (standard tier)
PRICES = {"input": 0.75, "cached_input": 0.075, "output": 4.50}
CALL_API_RESULT = {"status": "success", "message": "API call executed", "data": {"ok": True}}

SYSTEM = (
    "You are an agent that completes the user's task by calling APIs. Execution is simulated: "
    "every call_api call succeeds and returns a short confirmation. Complete the task by calling "
    "every API the task needs with call_api(api_id, arguments), choosing plausible argument "
    "values from the task text. Do not ask the user questions. When every needed API has been "
    "called, reply with the single word DONE."
)
ACCESS = {
    "catalog": (
        "The complete API catalog is listed below, one API per line as "
        "'[api_id] name | tool | category | description | params'. Pick the APIs the task needs "
        "from it.\n\n"
    ),
    "search": (
        "You do not know which APIs exist. Call search_tools(query) to find candidate APIs: it "
        "returns the 5 best matching API schemas. You may search as often as you like, then call "
        "the APIs you found with call_api."
    ),
    "waypoint": (
        "You do not know which APIs exist. Call find_tools(task) to find candidate APIs: it "
        "returns the 5 API schemas a task most likely needs. You may call it as often as you "
        "like, then call the APIs you found with call_api."
    ),
}
ACCESS["flat_knn"] = ACCESS["waypoint"]
CALL_API = {
    "type": "function",
    "function": {
        "name": "call_api",
        "description": "Call one API from the catalog by its numeric id and get its result.",
        "parameters": {
            "type": "object",
            "properties": {
                "api_id": {"type": "integer", "description": "The id of the API to call"},
                "arguments": {"type": "object", "description": "Arguments for the API call"},
            },
            "required": ["api_id", "arguments"],
        },
    },
}
SEARCH_TOOLS = {
    "type": "function",
    "function": {
        "name": "search_tools",
        "description": "Search the API catalog. Returns the 5 best matching API schemas.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What you need to do"}},
            "required": ["query"],
        },
    },
}
FIND_TOOLS = {
    "type": "function",
    "function": {
        "name": "find_tools",
        "description": (
            "Find the few APIs a task needs out of a catalog of 1,419 APIs. Returns their names, "
            "descriptions and input schemas."
        ),
        "parameters": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "The task in plain language"}},
            "required": ["task"],
        },
    },
}
FINDERS = {"search": SEARCH_TOOLS, "flat_knn": FIND_TOOLS, "waypoint": FIND_TOOLS}


def cached(key: dict, refresh: bool, produce):
    """Return (value, seconds) for a request, from disk when present, else produce() and store."""
    path = CACHE / (hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest() + ".json")
    if path.exists() and not refresh:
        hit = json.loads(path.read_text())
        return hit["value"], hit["seconds"]
    t0 = time.perf_counter()
    value = produce()
    seconds = time.perf_counter() - t0
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"value": value, "seconds": seconds}))
    return value, seconds


def catalog_text(apis) -> str:
    """Every schema as compact text, byte-identical across tasks so prompt caching applies."""
    lines = []
    for a in apis:
        s = tool_schema(a)
        props, req = s["inputSchema"]["properties"], set(s["inputSchema"]["required"])
        params = "; ".join(
            f"{n}({p['type']}{', required' if n in req else ''}): {p['description']}"
            for n, p in props.items()
        )
        lines.append(
            f"[{s['id']}] {s['name']} | {s['server']} | {s['category']} | "
            f"{' '.join(s['description'].split())} | {params}"
        )
    return "\n".join(lines)


class Agent:
    def __init__(self, ds, refresh: bool):
        self.ds, self.refresh = ds, refresh
        self.apis = {a.idx: a for a in ds.apis}
        self.stateless = Router(ds.apis, None, learn=False)
        self.params = Params()
        self.memory = {int(q): ds.train[q] for q in ds.stream_order}
        self.memory_index = BM25()
        for q in ds.stream_order:
            self.memory_index.add(int(q), ds.queries[q])
        self.catalog = catalog_text(ds.apis)
        self.http = httpx.Client(timeout=180)
        self.api_key = os.environ["OPENAI_API_KEY"]
        self.mcp_ready = False

    def chat(self, body: dict):
        def produce():
            headers = {"Authorization": f"Bearer {self.api_key}"}
            for attempt in range(8):
                r = self.http.post(OPENAI_URL, json=body, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(min(2**attempt, 30))
                    continue
                r.raise_for_status()
                return r.json()
            r.raise_for_status()

        return cached({"openai": body}, self.refresh, produce)

    def mcp(self, method: str, params: dict | None = None) -> dict:
        r = self.http.post(
            f"{WAYPOINT_URL}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )
        r.raise_for_status()
        reply = r.json()
        if "error" in reply:
            raise RuntimeError(f"mcp {method}: {reply['error']}")
        return reply["result"]

    def find(self, condition: str, text: str):
        """A finder's reply as compact JSON, plus the ids it returned and the seconds it took."""
        if condition == "search":
            found, seconds = cached(
                {"search": text, "k": K},
                self.refresh,
                lambda: [tool_schema(self.apis[a]) for a in self.stateless.route(text, K).tools],
            )
        elif condition == "flat_knn":
            found, seconds = cached(
                {"flat_knn": text, "k": K},
                self.refresh,
                lambda: [
                    tool_schema(self.apis[a])
                    for a in flat_knn(
                        self.memory,
                        self.memory_index,
                        self.stateless.api_index,
                        self.params,
                        text,
                    )
                ],
            )
        else:

            def produce():
                if not self.mcp_ready:
                    self.mcp("initialize", {"protocolVersion": "2025-06-18"})
                    self.mcp_ready = True
                args = {"task": text, "k": K}
                reply = self.mcp("tools/call", {"name": "find_tools", "arguments": args})
                return reply["structuredContent"]["tools"]

            found, seconds = cached({"waypoint": text, "k": K}, self.refresh, produce)
        found = [{k: v for k, v in t.items() if k != "score"} for t in found]
        reply = json.dumps({"tools": found}, separators=(",", ":"))
        return reply, [t["id"] for t in found], seconds

    def episode(self, condition: str, qid: str) -> dict:
        task, gold = self.ds.queries[qid], self.ds.test[qid]
        system = SYSTEM + "\n\n" + ACCESS[condition]
        if condition == "catalog":
            system += self.catalog
        tool_defs = [CALL_API] + ([FINDERS[condition]] if condition in FINDERS else [])
        messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
        rec = {
            "qid": qid,
            "task": task,
            "gold": sorted(gold),
            "calls": [],
            "finder_calls": [],
            "offered": [],
            "transcript": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "round_trips": 0,
            "seconds": 0.0,
            "final": None,
        }
        for _ in range(MAX_MODEL_CALLS):
            body = {
                "model": MODEL,
                "messages": messages,
                "tools": tool_defs,
                "temperature": 0,
                "reasoning_effort": "none",
                "max_completion_tokens": MAX_OUTPUT_TOKENS,
            }
            resp, seconds = self.chat(body)
            usage = resp["usage"]
            rec["round_trips"] += 1
            rec["seconds"] += seconds
            rec["input_tokens"] += usage["prompt_tokens"]
            rec["output_tokens"] += usage["completion_tokens"]
            details = usage.get("prompt_tokens_details") or {}
            rec["cached_tokens"] += details.get("cached_tokens", 0)
            msg = resp["choices"][0]["message"]
            messages.append({k: v for k, v in msg.items() if v is not None and k != "refusal"})
            rec["transcript"].append({"assistant": msg.get("content"), "tool_calls": []})
            if not msg.get("tool_calls"):
                rec["final"] = msg.get("content") or ""
                break
            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name == "call_api":
                    api_id = args.get("api_id")
                    ok = isinstance(api_id, int) and api_id in self.apis
                    rec["calls"].append(api_id)
                    out = json.dumps(
                        CALL_API_RESULT if ok else {"status": "error", "message": "unknown api_id"}
                    )
                elif name in ("search_tools", "find_tools") and condition in FINDERS:
                    text = str(args.get("query" if name == "search_tools" else "task") or "")
                    out, ids, seconds = self.find(condition, text)
                    rec["seconds"] += seconds
                    rec["finder_calls"].append(text)
                    rec["offered"] += [i for i in ids if i not in rec["offered"]]
                else:
                    out = json.dumps({"status": "error", "message": f"unknown function {name}"})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
                rec["transcript"][-1]["tool_calls"].append(
                    {"name": name, "arguments": args, "result": out[:300]}
                )
        called = {c for c in rec["calls"] if isinstance(c, int)}
        rec["hit_cap"] = rec["final"] is None
        rec["success"] = gold <= called
        rec["gold_called"] = len(gold & called)
        rec["precision"] = len(gold & called) / len(rec["calls"]) if rec["calls"] else 0.0
        rec["gold_offered"] = (
            len(gold & set(rec["offered"])) / len(gold) if condition in FINDERS else None
        )
        rec["tool_calls"] = len(rec["finder_calls"]) + len(rec["calls"])
        rec["cost_usd"] = cost(rec)
        return rec


def cost(r: dict) -> float:
    fresh = r["input_tokens"] - r["cached_tokens"]
    return (
        fresh * PRICES["input"]
        + r["cached_tokens"] * PRICES["cached_input"]
        + r["output_tokens"] * PRICES["output"]
    ) / 1e6


def summarize(recs: list[dict]) -> dict:
    n = len(recs)

    def total(key):
        return sum(r[key] for r in recs)

    def stat(value, digits=2):
        return {"mean": round(value / n, digits), "total": round(value, digits)}

    offered = [r["gold_offered"] for r in recs if r["gold_offered"] is not None]
    return {
        "tasks": n,
        "success_rate": round(sum(r["success"] for r in recs) / n, 4),
        "successes": sum(r["success"] for r in recs),
        "mean_precision": round(total("precision") / n, 4),
        "mean_gold_offered": round(sum(offered) / len(offered), 4) if offered else None,
        "input_tokens": stat(total("input_tokens"), 1),
        "cached_tokens": stat(total("cached_tokens"), 1),
        "uncached_input_tokens": stat(total("input_tokens") - total("cached_tokens"), 1),
        "output_tokens": stat(total("output_tokens"), 1),
        "round_trips": stat(total("round_trips")),
        "tool_calls": stat(total("tool_calls")),
        "finder_calls": stat(sum(len(r["finder_calls"]) for r in recs)),
        "api_calls": stat(sum(len(r["calls"]) for r in recs)),
        "wall_seconds": stat(total("seconds"), 1),
        "hit_cap": sum(r["hit_cap"] for r in recs),
        "spend_usd": round(total("cost_usd"), 4),
        "spend_usd_per_task": round(total("cost_usd") / n, 5),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="run only the first N sampled tasks")
    ap.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=CONDITIONS)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--budget", type=float, default=7.0, help="abort when spend passes this, USD")
    ap.add_argument("--refresh", action="store_true", help="ignore the on-disk cache")
    ap.add_argument("--out", default=str(RESULTS / "agent-check.json"))
    args = ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set")

    ds = load()
    eligible = [q for q in sorted(ds.test, key=int) if len(ds.test[q]) >= 2]
    sample = random.Random(SAMPLE_SEED).sample(eligible, SAMPLE_SIZE)[: args.limit]
    agent = Agent(ds, args.refresh)

    health = None
    if "waypoint" in args.conditions:
        try:
            health = agent.http.get(f"{WAYPOINT_URL}/health").json()
        except httpx.HTTPError:
            print("waypoint app unreachable: only cached /mcp replies can be used", file=sys.stderr)
        if health is not None and (
            not health.get("ready") or health.get("learned_tasks") != EXPECTED_LEARNED_TASKS
        ):
            sys.exit(f"waypoint is not a warm start from training runs only: {health}")

    spent = 0.0
    out: dict = {}
    pool = ThreadPoolExecutor(args.threads)
    for condition in args.conditions:
        t0 = time.time()
        # the first task runs alone so the shared prompt prefix is cached before the others start
        first = agent.episode(condition, sample[0])
        rest = list(pool.map(lambda q, c=condition: agent.episode(c, q), sample[1:]))
        recs = [first, *rest]
        spent += sum(r["cost_usd"] for r in recs)
        summary = summarize(recs)
        out[condition] = {"summary": summary, "tasks": recs}
        print(
            f"{condition:9s} success {summary['successes']}/{summary['tasks']}  "
            f"in {summary['input_tokens']['mean']:.0f}  "
            f"trips {summary['round_trips']['mean']:.2f}  "
            f"calls {summary['tool_calls']['mean']:.2f}  {summary['spend_usd']:.3f} USD  "
            f"({time.time() - t0:.0f}s real)",
            flush=True,
        )
        if spent > args.budget:
            sys.exit(f"budget exceeded: {spent:.2f} USD > {args.budget:.2f} USD")

    paired = {}
    for other in ("search", "flat_knn", "catalog"):
        if "waypoint" not in out or other not in out:
            continue
        w = {r["qid"]: r["success"] for r in out["waypoint"]["tasks"]}
        o = {r["qid"]: r["success"] for r in out[other]["tasks"]}
        paired[f"waypoint_vs_{other}_success"] = {
            "both": sum(w[q] and o[q] for q in w),
            "waypoint_only": sum(w[q] and not o[q] for q in w),
            f"{other}_only": sum(o[q] and not w[q] for q in w),
            "neither": sum(not w[q] and not o[q] for q in w),
        }
    result = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": "uv run python -m eval.agent_check",
        "model": MODEL,
        "reasoning_effort": "none",
        "temperature": 0,
        "max_model_calls_per_episode": MAX_MODEL_CALLS,
        "k": K,
        "sample": {
            "split": "COLT test (ToolBench G3)",
            "rule": f"random.Random({SAMPLE_SEED}).sample(tasks needing >= 2 tools, {SAMPLE_SIZE})",
            "tasks": len(sample),
            "qids": sample,
        },
        "prices_usd_per_1m_tokens": PRICES,
        "prices_source": "https://developers.openai.com/api/docs/pricing (standard tier)",
        "metric_definitions": {
            "success": "every gold api_id was passed to call_api",
            "precision": "distinct gold api_ids called / all call_api calls (0 when none)",
            "gold_offered": "share of gold ids the finder ever returned (finder conditions only)",
            "tool_calls": "finder calls + call_api calls",
            "wall_seconds": "sum of model and finder call latencies as first measured",
            "tokens": "OpenAI usage fields summed over the episode's model calls",
        },
        "waypoint_health": health,
        "total_spend_usd": round(spent, 4),
        "paired": paired,
        "conditions": {c: out[c]["summary"] for c in out},
        "records": {c: out[c]["tasks"] for c in out},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n")
    print(f"wrote {args.out}; total spend {spent:.3f} USD")


if __name__ == "__main__":
    main()
