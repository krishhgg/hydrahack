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
