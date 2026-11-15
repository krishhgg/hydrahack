# Pitch: Waypoint

## One-line problem

Large tool catalogs force a tradeoff: preload every schema and pay for it on each request, or retrieve a shortlist with stateless search that may omit tools a task needs together.

## Headline

Waypoint is 2.5x better than today's stateless tool search (67.3% against 26.7% Completeness@5) while loading 281x fewer schema tokens than the whole catalog (714 against 200,953).

## One-line product

Waypoint uses feedback from past runs, stored as weighted relationships in HydraDB, to pick the 5 tool schemas each new task loads.

The feedback signal is the set of tools a finished run actually needed, which a production agent already logs. The eval replays it from the training split and never from the test split.

## Three demo frames

Numbers come from `docs/results.md` and the committed `eval/` result files, never typed by hand. Dataset: ToolBench G3 (COLT split), 1,419 real APIs, 2,373 held-out test tasks that are never fed back. Completeness@5 means every tool the task needs is among the 5 schemas loaded; it measures shortlist coverage, not end-to-end task success.

1. **Frame 1, the cost of preloading.** Loading the whole catalog costs 200,953 schema tokens per task; Waypoint loads 5 schemas, 714 tokens (281x fewer). Routing latency p50 27.5 ms.
2. **Frame 2, the curve.** Completeness@5 starts at the stateless BM25 baseline of 26.7% and rises to 67.3% after 19,361 feedback runs, with the BM25 line flat underneath.
3. **Frame 3, what the graph adds, honestly.** A plain store that copies the nearest past run's tools reaches 60.3%; Waypoint reaches 67.3% by voting over several similar past runs through the graph, and beats flat memory at all ten checkpoints. On tool sets never seen in training the two tie (32.7% flat, 32.9% Waypoint), which is the limit of experience-based routing on this benchmark. A live feedback write then changes the ranking, and the "why this tool" path shows the edges that moved.

## For the judges

- Technical: metric Completeness@5, baseline stateless BM25 (26.7%), result 67.3%; every baseline gets the same feedback budget and candidate count; graph traversal and learned edge weights run in self-hosted HydraDB.
- Go-to-market: platform teams with large MCP catalogs pay to cut schema tokens and wrong-tool failures; see `docs/gtm.md`.

Live app: {{LIVE_URL}}. Repo: github.com/krishhgg/hydrahack.
