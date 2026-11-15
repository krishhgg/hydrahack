# Brief: HydraDB Hackathon

Observed 2026-11-15 between 20:50 and 21:10 UTC. Sources are the event text Krish pasted (Discord announcement and FAQ), the submission form, the Luma page, hydradb.com, the engine repository and a live run of the engine image. Statements are labelled **[rule]** (stated by the event), **[vendor]** (sponsor claim), **[verified]** (we ran it) or **[inference]** (our reading).

## Deadline

**2026-11-16 03:30 UTC** = 9:00 AM IST Nov 16 = **7:30 PM PST Nov 15** [rule, FAQ: "9 AM IST on Nov 16. That's the hard deadline"]. Nothing after it counts.

## The one rule and disqualifiers

- Build on the open-source engine, github.com/hydra-db/hydradb, self-hosted, as the graph DB. Not the hosted platform [rule, FAQ].
- The Luma page adds: "One rule: it has to earn its place over a vector store" (https://luma.com/bqwllms4) [rule].
- Disqualifier risks [inference]: using the hosted HydraDB platform, using Neo4j or a vector store as the real store, missing any of the three submission parts, missing the social post the form requires.
- HydraDB is ELv2: pull it as an image (`ghcr.io/hydra-db/hydradb:0.4.0`), never vendor its source into this MIT repo.

## Tracks [rule]

1. **The self-improving graph**: graph search that learns from its own answers to improve what it ingests and how it queries. Fair game: path compression, edge reweighting, gap-driven ingestion, entity split/merge. The bar: an accuracy curve rising over iterations.
2. **The agent context layer**: HydraDB as the live context store for an agent (skills, tool and MCP definitions, already-resolved entities). Instead of preloading every tool into the window and fanning out into round-trip chains, the agent traverses the graph and pulls only what the task needs.

## Judging [rule]

Two equal halves, both tracks.

- **Technical implementation**: right metrics (not a vanity number); real continual-learning improvement over a clearly defined baseline, "not a one-off result"; impact of HydraDB and the graph ("is the graph doing real work? Would this fall apart on a plain store?"); holds up under load.
- **Go-to-market**: post about the build on Twitter, LinkedIn and other socials tagging the HydraDB account; show who wants it and pitch it as a product people would pay for.
- Judges: none named on hydradb.com, Luma or the form. Company: Nishkarsh Srivastava (founder/CEO), Thomas Foley (CPO), Aadil Garg (founding ML) per LinkedIn search results, not opened pages [unverified].
- What they would reward [inference]: the sponsor's thesis is "context and memory that continuously improve" for agents, on object storage (hydradb.com), and it launched SelfGraph (versioned self-maintaining graphs, "no vector store") on Nov 14. Composio, a tool-integration company, is listed as a customer, so tool context for agents is a live sponsor use case.

## Prizes [rule]

$1,000 total. Each track: winner $300, runner-up $150.

## Submission checklist [rule]

Form: https://docs.google.com/forms/d/e/1FAIpQLSfOQZcJxQLkMwp1Lk76i76bnoRMVwLUhfPYtKhMYreKZG0_jQ/viewform (Google sign-in required). All fields required:

1. Email (auto-recorded)
2. Team or builder name
3. Contact email
4. Project name
5. Which track? ("Track 1 - the self-improving graph" / "Track 2 - the agent context layer")
6. One-line pitch
7. Live app link (hosted)
8. GitHub repo (public)
9. Loom walkthrough link
10. Technical: metric, baseline, and improvement. Help text: "What you measured, your baseline, and the improvement over it. Also where HydraDB and the graph are doing the real work." This must match docs/results.md exactly.
11. Go-to-market: who wants it, and a link to your social post tagging the HydraDB account. **A public post tagging @hydra_db must exist before submitting.** Krish posts it.

## Sponsor technology (engine v0.4.0, commit 9166374)

Facts from source and a live container; the engine thread's docs/hydradb-notes.md is the authoritative list.

| Capability | Status |
|---|---|
| Image `ghcr.io/hydra-db/hydradb:0.4.0`; Bolt 7687, HTTP 8443 (`POST /v1/graphs/{graph}/query`), admin 9090 | [verified] |
| Auth: bearer token from a file; over Bolt it is the password | [verified] |
| neo4j Python driver 6.x over Bolt (5.x rejected, issue #308) | [verified] |
| CREATE, MATCH, WHERE (incl. IN, STARTS WITH), MERGE on id, OPTIONAL MATCH, ORDER BY/SKIP/LIMIT/DISTINCT, count/collect, parameters | [verified] |
| Variable-length paths with an explicit max (`*1..3`) | [verified] |
| SET on node and relationship properties, literals or params only (no `r.w = r.w + 1`) | [verified] |
| UNWIND from a parameter, at most 1024 rows per call | [verified] |
| `algo.SPpaths` / `algo.MSpaths` with `weightProp`, `costProp`, `maxCost`: learned weights change the returned path | [verified] |
| `gds.pageRank` (unweighted) and betweenness, need the `graph-indexer` process | [verified] |
| shortestPath(), index DDL, constraints, list comprehension, MERGE ON CREATE/ON MATCH, labels()/type(), float sum/avg/min/max on the default engine | absent |
| Vector and full-text indexes | absent: text matching has to happen outside the engine |
| Perf: ~22-34k nodes/s and ~5-6k edges/s batch ingest; 3-hop reads ~5 ms p50, ~1400 req/s with 8 clients; ~8 ms per relationship SET | [verified] |
| Restart on a local-disk store breaks writes after the container is recreated; wipe or use S3/MinIO | [verified] |

## Recent tech (last ~90 days, from search results; not all read in full)

| Date | Item | Why it matters |
|---|---|---|
| 2026-11-14 | HydraDB SelfGraph (github.com/hydra-db/selfgraph, Apache-2.0) | Sponsor thesis: versioned, self-maintaining graphs with no vector store |
| 2026 (current) | Tool search default in Claude Code / Agent SDK; OpenAI `tool_search` with `defer_loading` | Incumbent Track 2 baseline: stateless regex/BM25 tool search |
| 2026-07-28 | MCP spec 2026-07-28 final | More servers, more tools per agent: the context-bloat problem grows |
| 2026-10-27 | Mem0 pricing reset to Free + Custom | Memory-layer pricing pressure |
| 2026-09-11 | ToolRet added to MTEB (mteb/ToolRetrieval) | Public tool-retrieval benchmarks are standard |
| 2026 Q3-Q4 | arXiv: STRATA self-maintaining experience graphs (2610.19386), Memory-Centric Continual Learning (2610.29357), Harness Continual Learning (2608.19013) | Experience graphs as a continual-learning mechanism |

## Competition

- **Public entries for this event** (GitHub search, created since Nov 13): Track 2 has at least 8 "tool graph" routers (Sketchify-Dev/toolpath, Pizzylee001/toolpath, safwaankira/loadout, AymanKhan9/deja-hydradb, VasuBansal7576/hydra-toolgraph, ivarunchaudhary/toolgraph, RatnamOjha/contextgraph-hydradb, Revaaa28/skillgraph). The most polished one runs 30 mock tools and labels its numbers estimates. Track 1 has about 5 (TrailMend, rewire, taintline, baton, decisiongraph), with hand-written evals of around 50 questions. None we saw uses a public gold-labelled benchmark with a held-out split [observed 20:55 UTC; an unsuccessful search does not prove absence].
- **Products**: Anthropic and OpenAI tool search (stateless lexical search, no learning); MCP gateways (Obot, Docker MCP Gateway, IBM ContextForge, MetaMCP, Kong, Composio: aggregation and governance, no outcome learning); Zep/Graphiti (temporal KG memory, $125-$375/mo); Cognee (feedback weights on graph nodes and edges, the closest Track 1 prior art, not a tool router); Mem0 (memory with graph mode); Microsoft GraphRAG/LazyGraphRAG (no feedback learning).
- **Research**: COLT (completeness-oriented tool retrieval, the source of the ToolBench G2/G3 splits we use) learns tool co-occurrence offline; Tool2Vec learns usage embeddings offline; RAG-MCP reports tool selection rising from 13% to 43% with retrieval.

## Datasets checked (HF API, 20:52-21:10 UTC)

- **ToolBench G3, Tool-COLT split** (hf.co/datasets/Tool-COLT/ToolBenchG3, 11 MB): 1,419 APIs, 21,361 train / 2,373 test / tune split, about 2.7 gold APIs per task. Downloaded and checked. G2: 11,474 APIs, 82,507 tasks.
- **MetaQA** (hf.co/datasets/camazlucas/MetaQA, 68 MB): 135k triples, 2/3-hop questions with gold answers.
- Also verified: mteb/ToolBench, mangopy/ToolRet-*, Tool-COLT/ToolLens, rmanluo/RoG-webqsp, rmanluo/RoG-cwq.

## Open questions

- Judges' identities.
- Whether a submission may target both tracks (the form takes one).
- Hosting: Railway, with HydraDB as a separate service (Captain, 21:10 UTC).
