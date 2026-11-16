# Pitch: Waypoint

## Headline

Waypoint takes tool routing from 26.7% to 70.7% Completeness@5 (about 2.6x over today's stateless tool search) while loading 713 schema tokens per task instead of 200,953 for the whole catalog (282x fewer). When new tools are added after launch, a plain store of past runs collapses to 1.8% on them and Waypoint holds 24.2%.

## One-line problem

Large tool catalogs force a tradeoff: preload every schema and pay for it on each request, or retrieve a shortlist with stateless search that may omit tools a task needs together.

## One-line product

Waypoint is a drop-in MCP endpoint that serves 5 tools instead of 1,400, and learns from every run which 5 to serve, storing that experience as edges in HydraDB.

The feedback signal is the set of tools a finished run actually needed, which a production agent already logs. The eval replays it from the training split and never from the test split.

## Three demo frames

Numbers come from `docs/results.md` and the committed `eval/` result files, never typed by hand. Dataset: ToolBench G3 (COLT split), 1,419 real APIs, 2,373 held-out test tasks that are never fed back. Completeness@5 means every tool the task needs is among the 5 schemas loaded; it measures shortlist coverage, not end-to-end task success.

1. **Frame 1, drop-in and cheap.** Point an MCP client at `/mcp`: the agent sees two tools, `find_tools` and `report_run`, not 1,419. A task returns 5 schemas, 713 tokens instead of 200,953 (282x fewer). In a live check with a real gpt-5.4-mini agent on 40 held-out tasks, Waypoint scored 50.0% success at 2,905 input tokens per task, against 35.0% for the preloaded catalog at 183,962 tokens and 17.5% for stateless search. A flat k-NN finder ties Waypoint there (52.5%), so that check shows the win over today's options, not a graph advantage.
2. **Frame 2, the curve.** Completeness@5 starts at the stateless BM25 baseline of 26.7% and rises to 70.7% after 19,361 feedback runs, with the BM25 line flat underneath. The curve rises at every checkpoint and Waypoint is ahead of every baseline at every checkpoint after 250 runs.
3. **Frame 3, would it fall apart on a plain store?** On familiar tasks, no: a budget-matched flat k-NN gets 69.9% against Waypoint's 70.7%, and the two are level on tool sets seen in training (78.5% against 78.2%). On tools added after launch, yes: with 10% of the catalog held out of every training run, flat k-NN collapses to 1.8% on the tasks that need a new tool, because its votes bury tools nobody has used, while Waypoint holds 24.2% by reaching the new endpoint through its Tool in the graph, and beats the plain store by about 6 points over all tasks (60.9% against 55.1%). Caveat: on new tools stateless BM25 is close behind (22.8%), so the claim is that the graph keeps the learned gains without losing new tools. A new catalog also learns faster: on tool sets never seen in training Waypoint scores 42.9% against 38.4%, with roughly 40% to 60% fewer runs to reach the same accuracy (approximate, interpolated between checkpoints). A live feedback write then changes the ranking and the "why this tool" view shows the edges that moved.

## For the judges

- Technical: metric Completeness@5, baseline stateless BM25 (26.7%), result 70.7%; baselines get the same runs and candidate budget; the graph's own margin over the strongest plain store is reported at its real size, and the new-tools holdout is where the plain store falls apart; learned state and traversal live in self-hosted HydraDB.
- Go-to-market: platform teams with large MCP catalogs pay to cut schema tokens and wrong-tool failures; see `docs/gtm.md`.

Live app: https://8000-cs6js0x7u8nbs6h8biw2kqrl2vyzobbf.capysandbox.net. Repo: github.com/krishhgg/hydrahack.
