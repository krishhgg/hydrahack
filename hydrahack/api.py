"""Waypoint's HTTP API and the static UI, one FastAPI service (deploy contract: hydrahack.api:app).

HydraDB is reached through HYDRADB_URL, HYDRADB_ADMIN_URL and HYDRADB_TOKEN. On start the app loads
the ToolBench G3 catalog into HydraDB if it is missing, rebuilds its text index of past Tasks from
the Task nodes already in the graph, and, on an empty graph, warm-starts the experience graph with
the training split's runs. Held-out test tasks are only ever routed, never written, unless a user
explicitly teaches one through /api/feedback.
"""

from __future__ import annotations

import itertools
import json
import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from hydrahack import mcp
from hydrahack.data import load
from hydrahack.db import HydraDBError
from hydrahack.router import MAX_PARTS, Router
from hydrahack.router import clauses as router_clauses
from hydrahack.store import GraphStore, Run

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RESULTS = ROOT / "eval" / "results" / "waypoint-test.json"
EXAMPLES = ROOT / "eval" / "results" / "examples.json"
LIVE_TASK_BASE = 5_000_000
MCP_MAX_BYTES = 64_000
MCP_MAX_BATCH = 8
log = logging.getLogger("waypoint")


class TimedStore:
    """Wraps the graph store to report how long a route spent in HydraDB traversals."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.local = threading.local()

    def __getattr__(self, name):
        fn = getattr(self.store, name)
        if not callable(fn):
            return fn

        def timed(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                self.local.ms = (
                    getattr(self.local, "ms", 0.0) + (time.perf_counter() - start) * 1000
                )

        return timed

    def take_ms(self) -> float:
        ms = getattr(self.local, "ms", 0.0)
        self.local.ms = 0.0
        return ms


class State:
    def __init__(self) -> None:
        self.ready = False
        self.error: str | None = None
        self.lock = threading.Lock()

    def start(self) -> None:
        try:
            self.ds = load()
            self.apis = {a.idx: a for a in self.ds.apis}
            self.graph = GraphStore()
            self.store = TimedStore(self.graph)
            self.router = Router(self.ds.apis, self.store)
            self.baseline = Router(self.ds.apis, self.store, learn=False)
            import tiktoken

            enc = tiktoken.get_encoding("o200k_base")
            self.tokens = {a.idx: len(enc.encode(a.text)) for a in self.ds.apis}
            self.catalog_tokens = sum(self.tokens.values())
            if self.graph.catalog_size() != len(self.ds.apis):
                self.graph.load_catalog(self.ds.apis)
            seed = [
                Run(int(q), self.ds.queries[q], self.ds.train[q], set())
                for q in self.ds.stream_order
            ]
            past = self.graph.runs()
            if not past:
                self.graph.add_runs(seed)
                past = [(r.task_id, r.text) for r in seed]
            for task_id, text in past:
                self.router.remember(task_id, text)
            parts = self.graph.clause_texts()
            if not parts:
                split = [c for r in seed for c in self.router.split(r)]
                self.graph.add_clauses(split)
                parts = [(c.clause_id, c.text) for c in split]
            for clause_id, text in parts:
                self.router.remember_clause(clause_id, text)
            self.clause_text = dict(parts)
            self.ids = itertools.count(max([LIVE_TASK_BASE, *(t + 1 for t, _ in past)]))
            self.held_out = {_norm(self.ds.queries[q]) for q in self.ds.test}
            self.texts = dict(past)
            self.ready = True
            log.info("waypoint ready: %d apis, %d learned tasks", len(self.apis), len(past))
        except Exception as exc:  # surfaced on /health
            self.error = f"{type(exc).__name__}: {exc}"
            log.exception("startup failed")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


state = State()
app = FastAPI(title="Waypoint", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=state.start, daemon=True).start()


def _ready() -> State:
    if not state.ready:
        raise HTTPException(503, state.error or "warming up: loading the graph")
    return state


def _api(idx: int) -> dict:
    a = state.apis[idx]
    return {"idx": idx, "name": a.name, "tool": a.tool, "category": a.category}


class RouteIn(BaseModel):
    task: str = Field(min_length=3, max_length=4000)
    k: int = Field(default=5, ge=1, le=20)


class FeedbackIn(BaseModel):
    task: str = Field(min_length=3, max_length=4000)
    used: list[int] = Field(min_length=1, max_length=20)
    offered: list[int] = Field(default_factory=list, max_length=40)


@app.get("/health")
def health() -> dict:
    db = state.graph.db.health(roundtrip=False) if state.ready else None
    return {
        "ok": state.ready and bool(db and db["ok"]),
        "ready": state.ready,
        "error": state.error,
        "hydradb": db,
        "learned_tasks": len(state.router.task_index) if state.ready else 0,
    }


@app.post("/api/route")
def route(body: RouteIn) -> dict:
    s = _ready()
    start = time.perf_counter()
    s.store.take_ms()
    r = s.router.route(body.task, body.k)
    base = s.baseline.route(body.task, body.k)
    total = (time.perf_counter() - start) * 1000
    graph_ms = s.store.take_ms()
    used = s.graph.task_tools([t for t, _ in r.tasks])
    needs = s.graph.clause_needs([m["clause"] for m in r.clauses])
    selected = set(r.tools)

    tools = []
    for a in r.tools:
        vote = {"text": 0.0, "task": 0.0, "clause": 0.0}
        for p in r.paths[a]:
            vote[p["via"]] += p["c"]
        tools.append(
            {
                **_api(a),
                "score": round(r.scores[a], 3),
                "paths": [{**p, "c": round(p["c"], 3)} for p in r.paths[a]],
                "vote": {k: round(v, 3) for k, v in vote.items()}
                | {"rejected_factor": round(r.factors.get(a, 1.0), 3)},
            }
        )

    nodes = [{"id": "q", "label": "your task", "kind": "query"}]
    edges = []
    api_nodes: dict[int, dict] = {}

    def api_node(idx: int) -> None:
        api_nodes.setdefault(idx, {"id": f"a{idx}", **_api(idx), "kind": "api"})

    for t, sim in r.tasks:
        hit = used.get(t, set())
        if not hit & selected:
            continue
        nodes.append(
            {"id": f"t{t}", "label": f"Task {t}", "kind": "task", "text": s.texts.get(t, "")}
        )
        edges.append({"source": "q", "target": f"t{t}", "type": "SIMILAR", "w": round(sim, 3)})
        for a in hit:
            api_node(a)
            edges.append({"source": f"t{t}", "target": f"a{a}", "type": "USED", "w": 1})
    clauses = []
    for m in sorted(r.clauses, key=lambda m: -m["w"]):
        hit = needs.get(m["clause"], set())
        if not hit & selected or any(c["id"] == m["clause"] for c in clauses):
            continue
        cid, task = m["clause"], m["clause"] // MAX_PARTS
        text = s.clause_text.get(cid, "")
        clauses.append(
            {
                "id": cid,
                "task": task,
                "text": text,
                "part": m["part"],
                "w": round(m["w"], 3),
                "tools": sorted(hit),
            }
        )
        nodes.append(
            {
                "id": f"c{cid}",
                "label": f"Clause of Task {task}",
                "kind": "clause",
                "text": text,
                "part": m["part"],
            }
        )
        edges.append(
            {
                "source": "q",
                "target": f"c{cid}",
                "type": "MATCH",
                "w": round(m["w"], 3),
                "part": m["part"],
            }
        )
        for a in hit:
            api_node(a)
            edges.append({"source": f"c{cid}", "target": f"a{a}", "type": "NEEDS", "w": 1})
    for a in r.tools:
        api_node(a)
        text_paths = [p for p in r.paths[a] if p["via"] == "text"]
        if text_paths:
            edges.append(
                {"source": "q", "target": f"a{a}", "type": "TEXT", "w": text_paths[0]["w"]}
            )
    for a, n in api_nodes.items():
        nodes.append({**n, "label": n["name"], "selected": a in selected})
    return {
        "tools": tools,
        "baseline": [_api(a) for a in base.tools],
        "parts": router_clauses(body.task),
        "similar_tasks": [
            {
                "id": t,
                "text": s.texts.get(t, ""),
                "sim": round(sim, 3),
                "tools": sorted(used.get(t, ())),
            }
            for t, sim in r.tasks
        ],
        "clauses": clauses,
        "tokens": {
            "loaded": sum(s.tokens[a] for a in r.tools),
            "baseline_loaded": sum(s.tokens[a] for a in base.tools),
            "catalog": s.catalog_tokens,
        },
        "latency_ms": {"total": round(total, 1), "graph": round(graph_ms, 1)},
        "graph": {"nodes": nodes, "edges": edges},
        "learned_tasks": len(s.router.task_index),
    }


def _learn(task: str, used_ids: list[int], offered: list[int]) -> dict:
    s = _ready()
    if _norm(task) in s.held_out:
        raise HTTPException(409, "held-out test task: teaching it would leak eval labels")
    used = {a for a in used_ids if a in s.apis}
    if not used:
        raise HTTPException(422, "used must name at least one known api idx")
    rejected = {a for a in offered if a in s.apis} - used
    with s.lock:
        task_id = next(s.ids)
    try:
        parts = s.router.feedback([Run(task_id, task, used, rejected)])
    except HydraDBError as exc:
        raise HTTPException(503, f"HydraDB refused the write: {exc}") from exc
    for c in parts:
        s.clause_text[c.clause_id] = c.text
    s.texts[task_id] = task
    return {
        "task_id": task_id,
        "edges_written": len(used) + len(rejected),
        "learned_tasks": len(s.router.task_index),
    }


@app.post("/api/feedback")
def feedback(body: FeedbackIn) -> dict:
    return _learn(body.task, body.used, body.offered)


def _find_tools(task: str, k: int) -> dict:
    s = _ready()
    r = s.router.route(task[:4000], k)
    return {
        "tools": [{**mcp.tool_schema(s.apis[a]), "score": round(r.scores[a], 3)} for a in r.tools],
        "tokens_loaded": sum(s.tokens[a] for a in r.tools),
        "tokens_catalog": s.catalog_tokens,
        "learned_tasks": len(s.router.task_index),
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> Response:
    """MCP over Streamable HTTP with plain JSON responses (no SSE stream). Bodies and batches are
    capped, and the blocking routing work runs in the thread pool so /health stays responsive."""
    raw = await request.body()
    if len(raw) > MCP_MAX_BYTES:
        return JSONResponse(mcp._error(None, -32600, "request too large"), status_code=413)
    try:
        body = json.loads(raw)
    except ValueError:
        return JSONResponse(mcp._error(None, -32700, "parse error"), status_code=400)
    messages = body if isinstance(body, list) else [body]
    if not messages or len(messages) > MCP_MAX_BATCH:
        msg = f"batch must hold 1 to {MCP_MAX_BATCH} messages"
        return JSONResponse(mcp._error(None, -32600, msg), status_code=400)

    def learn(task: str, used: list[int], offered: list[int]) -> dict:
        return _learn(task[:4000], used, offered)

    def run() -> list[dict]:
        return [r for r in (mcp.handle(m, _find_tools, learn) for m in messages) if r is not None]

    try:
        replies = await run_in_threadpool(run)
    except HTTPException as exc:
        msg_id = messages[0].get("id") if isinstance(messages[0], dict) else None
        return JSONResponse(mcp._error(msg_id, -32603, str(exc.detail)))
    if not replies:
        return Response(status_code=202)
    return JSONResponse(replies if isinstance(body, list) else replies[0])


@app.get("/mcp")
def mcp_get() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})


@app.get("/api/examples")
def examples() -> list[dict]:
    """Held-out tasks for the demo. eval/run_eval.py picks the shortest ones Waypoint completes
    and BM25 does not; they are showcase picks, the headline numbers cover every test task."""
    s = _ready()
    if EXAMPLES.exists():
        return json.loads(EXAMPLES.read_text())
    picks = [q for q in sorted(s.ds.test, key=int) if len(s.ds.test[q]) >= 2][:8]
    return [{"id": q, "text": s.ds.queries[q], "gold": sorted(s.ds.test[q])} for q in picks]


@app.get("/api/results")
def results() -> dict:
    if not RESULTS.exists():
        raise HTTPException(404, "no eval results yet: run python -m eval.run_eval")
    raw = json.loads(RESULTS.read_text())
    curve = [
        {
            "runs": p["runs"],
            "waypoint": p["waypoint"]["completeness"],
            "bm25": p["bm25"]["completeness"],
            "flat_memory": p["flat_memory"]["completeness"],
        }
        for p in raw["curve"]
    ]
    return {
        "dataset": raw["dataset"],
        "k": raw["k"],
        "test_tasks": raw["eval_tasks"],
        "curve": curve,
        "headline": {"metric": "Completeness@5", **raw["headline"]},
        "slices": raw["slices"],
        "generated_at": raw["generated_at"],
    }


if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    page = WEB / "index.html"
    if not page.exists():
        return {"service": "waypoint", "docs": "/docs"}
    return FileResponse(page)
