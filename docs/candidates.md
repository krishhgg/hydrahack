# Candidates

Compressed kickoff (under 7 hours to the cutoff): three candidates, one attack round by an independent OpenAI-model reviewer (openai/gpt-6.1-sol) that did not see our ranking, then a pick. The reviewer's full notes are summarised below; every number here was measured on this machine on 2026-11-15 between 21:00 and 21:10 UTC.

## A. Waypoint: a tool router for agents that learns from every run (Track 2)

**Problem.** Agents with many MCP servers either preload every tool schema (Anthropic cites 58 tools taking about 55K tokens before the conversation starts) or run stateless tool search (regex or BM25 over descriptions) that misses the tools a task needs together. Neither gets better with use.

**Mechanism.** HydraDB holds the tool catalog as a graph, `(:Category)-[:HAS_TOOL]->(:Tool)-[:HAS_API]->(:Api)`, plus the router's experience: `(:Task)-[:USED {w}]->(:Api)` for every finished run and `(:Api)-[:CO_USED {w}]->(:Api)` between tools needed together. A new task resolves entry points by text (HydraDB has no text index, so this happens in the app), then a weighted multi-hop traversal in HydraDB, Task to Api to co-used Api and sibling Api, ranks the tools. Only the top k schemas go into the agent's context. After each run, the outcome (which tools the agent needed) is written back: new Task node, USED and CO_USED weights reinforced, tools that were offered but not needed decayed.

**Data and metric.** ToolBench G3 in the COLT split (hf.co/datasets/Tool-COLT/ToolBenchG3): 1,419 real RapidAPI endpoints, 21,361 train tasks and 2,373 test tasks, about 2.7 needed tools per task. Metric: Completeness@5, the share of held-out tasks where every needed tool is among the 5 loaded (a task with a missing tool fails), plus Recall@5 and schema tokens per task.

**Quick PoC (Python only, 600 test tasks; scripts in poc/).** Stateless BM25: C@5 0.123, R@5 0.375. Dense bge-small: C@5 0.123, R@5 0.398. BM25 plus experience from 10k training runs: C@5 0.688, R@5 0.828.

## B. Path learner on MetaQA (Track 1)

Parse the topic entity of a 2/3-hop WikiMovies question, explore relation paths up to 3 hops in HydraDB, learn question-pattern to relation-path weights from answer correctness, and compress winning paths into shortcut edges. Metric Hits@1 on held-out questions over iterations; baseline untrained traversal. No LLM needed.

## C. Gap filler on HotpotQA or MuSiQue (Track 1)

LLM-extracted entity graph; failed answers trigger gap-driven ingestion of missing passages and entity merges. Metric EM/F1. Needs an LLM call per question.

## Attack round (independent reviewer, openai/gpt-6.1-sol)

| | Engineering | GTM | Strongest attack | Fatal? |
|---|---|---|---|---|
| A | 6/10 | 5/10 | A flat "copy the nearest past task's tools" memory may explain most of the gain; 80% of test tool sets appear in train | Fixable: report matched flat-memory, dense and co-occurrence baselines and a novel-toolset slice; claim graph value only where it beats them |
| B | 5/10 | 2/10 | Templated questions make it a template classifier; movie trivia has no buyer | GTM fatal today |
| C | 2/10 | 3/10 | Gap detection leaks answers; more LLM calls explain any gain; not buildable in 6 hours | Fatal for this deadline |

Findings we verified ourselves:

- **The COLT `tune` file is byte-identical to `test`** (reviewer finding, confirmed with `cmp`). Tuning on it would contaminate the test number, so we never read it. Validation comes from a slice carved out of train.
- **Flat memory is a strong baseline** (reviewer's ad-hoc check, not yet a committed script; eval/run_eval.py regenerates a flat-memory baseline): the reviewer's graph-free "copy the nearest training task's tools" lookup reaches C@5 0.496 on all 2,373 test tasks with the full train set, 0.608 on test tasks whose tool set appeared in train and 0.049 on the 474 that did not. The graph has to beat this, not just BM25.
- **The feedback signal is replayed labels**, not an agent discovering tools. We label it as simulated outcome feedback (the tools a successful run used), which is what a production router would log.

## Kill reasons

- **B**: strongest curve, weakest product. A template-to-path dictionary would explain the gain, and nobody buys movie-trivia QA. Kept as a fallback if A's graph signal fails.
- **C**: needs an LLM per question and an answer-leaking oracle to detect gaps; cannot be built and measured honestly by the 23:45 UTC checkpoint.

A survives, with the reviewer's required baselines and slices built into the eval from the start.
