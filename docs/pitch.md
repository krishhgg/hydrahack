# Pitch: Waypoint

## One-line problem

Large tool catalogs force a tradeoff: preload every schema and pay for it on each request, or retrieve a shortlist with stateless search that may omit tools a task needs together.

## One-line product

Waypoint uses feedback from past runs, stored as weighted relationships in HydraDB, to pick the 5 tool schemas each new task loads.

The feedback signal is the set of tools a finished run actually needed, which a production agent already logs. The eval replays it from the training split and never from the test split.

## Three demo frames

Numbers come from `docs/results.md` and the committed `eval/` result files, never typed by hand. Dataset: ToolBench G3 (COLT split), 1,419 real APIs, 2,373 held-out test tasks that are never fed back. Completeness@5 means every tool the task needs is among the 5 schemas loaded; it measures shortlist coverage, not end-to-end task success.

1. **Frame 1, the cost of preloading.** Loading the whole catalog costs {{TOKENS_ALL}} schema tokens per task; Waypoint loads 5 schemas, {{TOKENS_WAYPOINT}} tokens ({{TOKEN_REDUCTION}} fewer). Routing latency p50 {{P50_MS}} ms.
2. **Frame 2, the curve.** Completeness@5 starts at the stateless BM25 baseline of {{C5_BM25}} and rises to {{C5_GRAPH_FINAL}} after {{RUNS}} feedback runs, with the BM25 line flat underneath. Dense retrieval sits at {{C5_DENSE}}.
3. **Frame 3, why the graph.** On tasks whose tool set never appeared in training, flat "copy the nearest past task" memory scores {{C5_NOVEL_FLAT}} and the graph scores {{C5_NOVEL_GRAPH}}. Waypoint combines tool-use evidence across several similar past tasks instead of copying one task's tool set, and this slice tests whether that improves coverage on unseen tool combinations. A live feedback write then changes the ranking, and the "why this tool" path shows the edges that moved.

## For the judges

- Technical: metric Completeness@5, baseline stateless BM25 ({{C5_BM25}}), result {{C5_GRAPH_FINAL}}; every baseline gets the same feedback budget and candidate count; graph traversal and learned edge weights run in self-hosted HydraDB.
- Go-to-market: platform teams with large MCP catalogs pay to cut schema tokens and wrong-tool failures; see `docs/gtm.md`.

Live app: {{LIVE_URL}}. Repo: github.com/krishhgg/hydrahack.
