# Recommendation: Waypoint (Track 2, the agent context layer)

**One line.** Waypoint is a tool router for agents that learns from every run: HydraDB stores the tool catalog and the router's experience as a weighted graph, and each new task traverses it to load only the handful of tools it needs.

**Track.** Track 2, the agent context layer. The judging FAQ asks every track for a continual-learning curve over a baseline, so Waypoint ships one.

## The claim we will measure

- **Metric**: Completeness@5 on held-out tasks, the share of tasks where every tool the task needs is among the 5 tool schemas loaded into the agent's context. A task with a missing tool fails, so this is the number that decides whether the agent can finish, not a ranking vanity score. Secondary: Recall@5, schema tokens per task versus loading the whole catalog, and p50 query latency.
- **Baseline**: stateless BM25 tool search over tool descriptions, the mechanism behind Anthropic's and OpenAI's tool search today. Also reported: dense retrieval (bge-small) and a flat episodic memory that copies the nearest past task's tools, the strongest graph-free baseline the attack round found.
- **Dataset**: ToolBench G3, COLT split (hf.co/datasets/Tool-COLT/ToolBenchG3): 1,419 real RapidAPI endpoints, 21,361 train tasks, 2,373 test tasks. The test split is never fed back into the graph. The COLT tune file is identical to test, so validation is carved from train.
- **Curve**: the router serves training tasks in batches; after each batch the outcomes are written into HydraDB and Completeness@5 is measured on the untouched test set. x = feedback runs, y = Completeness@5, with the BM25 line flat underneath.
- **PoC evidence** (Python only, 600 test tasks): BM25 0.123 to 0.688 after 10k runs of feedback. The eval will report all 2,373 test tasks, seen-toolset and novel-toolset slices, and the flat-memory comparison, and we will publish whatever the graph's margin over flat memory turns out to be.

## Why the graph is doing the work

- Ranking is a weighted multi-hop traversal inside HydraDB: matched past Tasks to the Apis they USED, then CO_USED and same-Tool sibling hops to complete the set. The learned state, USED and CO_USED weights, lives on HydraDB edges and is what the loop changes.
- The CO_USED and sibling hops are what can complete a tool set no past task used exactly (the novel slice, where flat memory scores 0.049).
- Learned weights also drive `algo.SPpaths` with `weightProp` for the demo's "why this tool" path.

## Why this one wins

- **Engineering**: a public, gold-labelled benchmark with a held-out split and a learning curve. None of the eight public Track 2 entries we found has that; the most polished runs 30 mock tools with estimated numbers.
- **Go-to-market**: tokens and wrong-tool calls cost money per request. Buyers are teams running agents over large or private MCP catalogs (agent platforms, MCP gateways, tool-integration companies such as Composio, which HydraDB lists as a customer). Incumbent tool search is stateless; Waypoint gets better with every run.

## Risks

- The flat-memory baseline may come close to the graph on tasks that repeat a known workflow. We report it either way and lean on the novel slice and on the edge-state curve.
- Feedback is replayed from labels (simulated outcomes). The demo shows a live feedback write changing the ranking.
- HydraDB writes cost about 8 ms per relationship SET, so weight updates are batched per iteration through UNWIND.

## Build sequence

1. Ingest G3 into HydraDB (Category, Tool, Api, structural edges).
2. Router: text entry points in the app, weighted traversal in HydraDB, top-k.
3. Learning loop: batched write-back of Task, USED and CO_USED weights.
4. eval/: baselines, iterations, slices, JSON plus SVG curve.
5. FastAPI `hydrahack.api:app` with /health, /route, /feedback and a one-page UI.
6. docs/results.md and docs/api.md.
