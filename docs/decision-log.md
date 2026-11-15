# Decision log

Newest last. Times are UTC.

## 2026-11-15 20:50 Kickoff (compressed mode)

- Lead: claude-code/claude-opus-5-5, high reasoning. Research subagents use the lead's model. Independent worker for attack rounds: openai/gpt-6.1-sol (the codex CLI is not configured; CREW.md).
- Repo: krishhgg/hydrahack, public, MIT, empty at kickoff. No prior work.
- Scope: MVP build, not just a recommendation (Captain, on Krish's behalf). Under 7 hours remain, so the kickoff runs compressed: three candidates, one attack round, the PoC as the first slice of the MVP.
- Merge policy: pending at kickoff; granted by Krish at 21:10 (CREW.md).
- OPENAI_API_KEY was absent at kickoff and arrived later. The eval is designed not to need an LLM so every number is cheap and deterministic.

## 2026-11-15 21:05 Research inputs

- Engine: `ghcr.io/hydra-db/hydradb:0.4.0` runs; Bolt with neo4j driver 6.x; no text or vector index; SET takes params only; weighted `algo.SPpaths` works. Consequence: text matching happens in the app, traversal and learned weights live in HydraDB, updates are read-compute-write in batches.
- Market: Track 2 has 8+ public look-alike tool routers, all on mock tools or estimated numbers; no public entry uses a gold-labelled benchmark with a held-out split. The GTM thread finds Track 2 has the easier "who pays" story.

## 2026-11-15 21:10 PoC numbers before the pick

ToolBench G3 (COLT split), 600 test tasks, Python only: BM25 C@5 0.123; dense bge-small C@5 0.123; BM25 plus experience from 10k training runs C@5 0.688.

## 2026-11-15 21:15 Attack round and pick

- Independent reviewer (openai/gpt-6.1-sol) scored A 6/5, B 5/2, C 2/3 (engineering/GTM) and would build A.
- Verified: COLT's `query_tool_tune.txt` is byte-identical to `query_tool_test.txt`. Decision: never read it; validation is a slice of train.
- Accepted the reviewer's demand for matched baselines (BM25, dense, flat episodic memory) and seen/novel toolset slices; graph value is claimed only where it beats flat memory.
- **Pick: A, Waypoint, Track 2.** B kept as the fallback if A's graph signal fails. C killed for the deadline and answer leakage.

## 2026-11-15 21:25 Router design from validation

- Co-use expansion (Api <-USED- Task -USED-> Api) and same-Tool sibling expansion both lowered validation Completeness@5 (0.684 with both off vs 0.626-0.680 with them on, 800 validation tasks, in-memory store). Both weights set to 0. The code paths stay for the ablation, and the co-use query is skipped when its weight is 0, because counting Task paths gets slow as the graph grows (600 ms at 19k Tasks).
- Past-task similarity is BM25 divided by the query's score ceiling (an absolute 0..1 similarity), not divided by the top hit. Dividing by the top hit made the first few hundred runs hurt (0.276 to 0.221 at 250 runs); the absolute version rises monotonically. w_exp = 4 chosen on validation.
- Outcome counters (used, rejected) live as properties on Api nodes, folded in per feedback batch, because counting REJECTED edges per query grew with the number of Tasks. The edges stay as the record.
- The text index (BM25) is in the app because HydraDB has no text index; it is rebuilt from Task nodes in the graph at startup.

## 2026-11-15 21:40 First test-split run

Completeness@5 on 2,373 held-out tasks after 19,361 runs: BM25 0.267, flat memory 0.603, Waypoint 0.673 (eval/results/waypoint-test.json). Rejection weight 0.3 chosen on validation (0.682 / 0.688 / 0.689 for 0 / 0.3 / 0.6: within noise, kept and reported as no measurable gain). Waypoint ties flat memory on novel tool sets (0.329 vs 0.327).

## 2026-11-15 22:00 Codex review of #9, and what "graph doing work" means here

- Codex flagged that the default router path had no multi-hop traversal and that flat memory had a smaller retrieval budget. Recorded answer: the same algorithm on dicts returns identical rankings (parity test), so the accuracy comes from how Waypoint learns from its experience graph, not from the engine. Every multi-hop expansion we tried lowered validation accuracy: co-use, query-weighted co-use (0.717 vs 0.722, 1,000 validation tasks), and same-Tool siblings. The unused code paths were removed.

## 2026-11-15 22:05 Sub-request Clause nodes

- Each run is split into sentence-level Clause nodes. Every needed tool is assigned to the clause whose text best matches the tool (BM25 over the tool description), giving `(:Task)-[:HAS_CLAUSE]->(:Clause)-[:NEEDS]->(:Api)`. Each part of a new task matches past clauses and follows NEEDS.
- Validation, 1,000 tasks, in-memory reference, full stream:

  | Router | All | Novel tool sets |
  |---|---|---|
  | Before | 0.691 | 0.367 |
  | Clause entry into the task index only | 0.722 | 0.419 |
  | NEEDS edges, w_needs = 1, clause_top = 6 | 0.735 | 0.465 |

  Earlier checkpoints: 0.301 vs 0.312 at 250 runs (a small early dip), then ahead from 1,000 runs on. w_needs = 2 scored 0.735 overall and 0.484 novel, but did worse early, so we kept 1.0.
- Test split (HydraDB): Completeness@5 0.703, against 0.673 before. Novel tool sets 0.415, against 0.329 before and 0.327 for flat memory.

## 2026-11-15 22:40 Budget-matched baseline and MCP limits (Codex P1s on #11)

- Codex flagged that the nearest-run cache gets a smaller retrieval budget than the clause-enhanced router. Added `flat_knn` to `eval/run_eval.py`: Waypoint's scoring, weights and candidate counts over whole past runs, with no NEEDS links and no rejection counters, using Waypoint's weights unchanged (not tuned for it). Test split: 0.699 against Waypoint's 0.703 overall, 0.785 vs 0.782 on seen tool sets, 0.384 vs 0.415 on novel tool sets. So most of the margin over the nearest-run cache is retrieval budget; the graph structure's own contribution is the novel-set and early-stream gap. The docs and pitch now say that.
- Codex security review flagged unbounded `/mcp` batches on the event loop. `/mcp` now caps the body at 64 KB and a batch at 8 messages, and routes in the thread pool. No rate limiter in the app; that belongs at the edge with the other public endpoints.

## 2026-11-15 22:45 Data efficiency, and three structure ideas that did not hold

- Added a data-efficiency table to `eval/report.py`: runs each router needs to first reach a Completeness@5 level, interpolated from the committed curve. Waypoint needs 43%, 48% and 28% fewer runs than flat k-NN to reach 25%, 30% and 35% on novel tool sets (levels above the 22.8% both start at with zero runs; Codex caught that a 20% level would count the post-dip recovery), and 38% / 20% / 10% fewer at 40% / 50% / 60% overall. No new eval run; it reads `eval/results/waypoint-test.json`.
- Tried on validation only (in-memory reference, first 1,000 validation tasks, 215 of them with novel tool sets, checkpoints 250 / 1,000 / 4,000 / 19,361 runs). Baseline router: all 0.299 / 0.393 / 0.541 / 0.736, novel 0.167 / 0.181 / 0.298 / 0.460.
  - Part coverage: reserve a top-5 slot for each sub-request's strongest `NEEDS` tool (optionally adding that part's text match), then fill by score. Every setting was lower at the end of the stream (0.672 to 0.724 overall). Dropped.
  - Api experience profiles: index each Api by the texts of the Clauses that `NEED` it (`Api <-NEEDS- Clause`) and match each sub-request against them. The best setting (weight 0.5, top 5) scored 0.739 / 0.498 at the end of the stream, but 0.286 / 0.135 at 250 runs and 0.394 / 0.177 at 1,000, so it hurts the early curve, and +0.038 on 215 novel tasks is about 8 tasks. Not shipped.
  - Per-part normalization of clause votes, so each sub-request's best match counts 1: lower at every checkpoint. Dropped.
- None reached test, so the test numbers are unchanged.
