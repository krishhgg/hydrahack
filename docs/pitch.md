# Pitch: Waypoint

## Headline

Waypoint takes tool routing from 26.7% to 70.3% Completeness@5 (2.6x over today's stateless tool search) while loading 714 schema tokens per task instead of 200,953 for the whole catalog (281x fewer).

## One-line problem

Large tool catalogs force a tradeoff: preload every schema and pay for it on each request, or retrieve a shortlist with stateless search that may omit tools a task needs together.

## One-line product

Waypoint is a drop-in MCP endpoint that serves 5 tools instead of 1,400, and learns from every run which 5 to serve, storing that experience as edges in HydraDB.

The feedback signal is the set of tools a finished run actually needed, which a production agent already logs. The eval replays it from the training split and never from the test split.

## Three demo frames

Numbers come from `docs/results.md` and the committed `eval/` result files, never typed by hand. Dataset: ToolBench G3 (COLT split), 1,419 real APIs, 2,373 held-out test tasks that are never fed back. Completeness@5 means every tool the task needs is among the 5 schemas loaded; it measures shortlist coverage, not end-to-end task success.

1. **Frame 1, drop-in and cheap.** Point an MCP client at `/mcp`: the agent sees two tools, `find_tools` and `report_run`, not 1,419. A task returns 5 schemas, 714 tokens instead of 200,953 (281x fewer), p50 68.9 ms and p95 103.2 ms with 8 concurrent clients.
2. **Frame 2, the curve.** Completeness@5 starts at the stateless BM25 baseline of 26.7% and rises to 70.3% after 19,361 feedback runs, with the BM25 line flat underneath. The curve rises at every checkpoint and Waypoint is ahead of every baseline at every checkpoint after 250 runs.
3. **Frame 3, what the graph adds, honestly.** The learning loop does most of the work: a budget-matched flat k-NN over plain stored runs reaches 69.9%, against Waypoint's 70.3%. The graph's own contribution shows up where a new catalog lives: on tool sets never seen in training, 41.5% against 38.4%, and in data efficiency, which is what a new customer's catalog lives on: on never-seen tool sets Waypoint reaches 30% Completeness@5 after about 4,600 runs where the plain store needs about 8,800 (roughly 48% fewer; 28% to 48% across the levels we measured), and over all tasks it saves 10% to 38%. Run counts are interpolated between checkpoints, so read them as approximate. A `Clause -NEEDS-> Api` edge carries only the tools one sub-request needed, so Waypoint can build a new set from parts of different runs. A live feedback write then changes the ranking and the "why this tool" view shows the edges that moved.

## For the judges

- Technical: metric Completeness@5, baseline stateless BM25 (26.7%), result 70.3%; baselines get the same runs and candidate budget; the graph's own margin over the strongest plain store is reported at its real size; learned state and traversal live in self-hosted HydraDB.
- Go-to-market: platform teams with large MCP catalogs pay to cut schema tokens and wrong-tool failures; see `docs/gtm.md`.

Live app: {{LIVE_URL}}. Repo: github.com/krishhgg/hydrahack.
