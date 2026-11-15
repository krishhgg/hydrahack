# Go-to-market: Waypoint

Status: draft with {{placeholders}}. Every number below is filled from `docs/results.md` and the `eval/` result files; nothing here is a measured claim until its placeholder is replaced.

## One line

Waypoint is a tool router for agents that learns from every run: it loads the few tool schemas a task needs instead of the whole catalog, and gets more complete with each run.

## First adopter

A platform or AI-infra team that has already connected 5 or more MCP servers to its coding or ops agents and is paying for it twice: in tokens (Anthropic's own example is 58 tools using about 55K tokens before the conversation starts, with 134K seen before optimisation) and in wrong-tool calls. They are easy to find because they are the people filing issues like github-mcp-server #1286 ("over 66 tools") and posting "MCP tools eat 30 to 50% of context". Second adopter: tool-integration and MCP-gateway vendors (Composio and similar) that sell a large catalog and want routing that improves with customer usage.

## Buyer

- Budget holder: head of AI platform or developer productivity, in the AI infra or dev-tools line, not the individual developer.
- User: the engineers building the agent. They install it, the platform lead pays for it.
- Trigger to buy: a token bill or a failure rate they can point at. Waypoint reports both per task ({{TOKENS_ALL}} schema tokens for the full catalog versus {{TOKENS_WAYPOINT}} with Waypoint).

## Problem

Agents with large tool catalogs have two bad options. Preload every schema and pay for it on every request, or use stateless tool search (BM25 or regex over descriptions, which is how Anthropic's and OpenAI's tool search work today) and miss the tools a task needs together. A task with one missing tool fails, so the number that matters is Completeness@5, not a ranking score. Stateless BM25 reaches {{C5_BM25}} on our held-out tasks. Neither option learns from the thousands of runs the agent already did.

## Why now

- MCP made it cheap to connect dozens of servers, so catalogs grew faster than context windows.
- Vendors shipped tool search in 2025 and 2026, which confirms the pain and leaves a gap: it is stateless and per-vendor.
- Teams now log successful runs, so the experience needed to improve routing already exists in their traces.

## Wedge

Start where the pain is measurable: one team, one large MCP catalog, one number (Completeness@5 and schema tokens per task). Drop-in HTTP API (`/route` before a run, `/feedback` after) so it works with any model or agent framework. The router starts at the BM25 baseline on day one and the curve rises as runs are logged: {{C5_BM25}} to {{C5_GRAPH_FINAL}} after {{RUNS}} feedback runs on ToolBench G3.

## Pricing (proposal, to validate with first customers)

| Plan | Price | For |
|---|---|---|
| Open source | Free, self-hosted, MIT | Individual developers, evaluation |
| Team | $99/month flat for up to {{TEAM_AGENTS}} agents | Teams with one catalog, hosted graph and dashboard |
| Scale | $499/month flat plus usage above {{SCALE_ROUTES}} routes | Platform teams, multiple catalogs |
| Enterprise | Custom | VPC or BYOC, audit, SSO |

Anchors from the market: Composio Standard is $18 per seat per month, Zep Flex is $125 and Flex Plus $375 per month, Cognee charges $1 per 1M tokens processed. The Team price is justified when savings exceed it: tokens saved per task ({{TOKENS_ALL}} minus {{TOKENS_WAYPOINT}}) times tasks per month times the model's input price. Fill that line with the customer's own volume in a sales conversation; we do not claim a dollar saving in public copy until it is computed from measured tokens.

## Competition

| Alternative | What it does | Where Waypoint differs |
|---|---|---|
| Preload everything | All schemas in every request | Token cost and wrong-tool errors grow with catalog size; Waypoint loads 5. |
| Anthropic and OpenAI tool search | BM25 or regex over tool descriptions, deferred loading | Stateless, per vendor, no relations between tools, no memory of what worked. This is our measured baseline ({{C5_BM25}}). |
| Composio, Docker MCP gateway | Catalog, auth and dynamic discovery | Complementary: they host tools, Waypoint decides which ones to load. |
| Flat "copy the nearest past task" memory | Remembers past runs, no graph | Our matched control: {{C5_FLAT}} overall and {{C5_NOVEL_FLAT}} on novel toolsets versus {{C5_NOVEL_GRAPH}} for the graph. |
| Zep, Cognee, Mem0 | Agent memory (facts, user history) | Memory of what was said; Waypoint stores which tools worked for which tasks and routes on it. |

We state the graph's advantage only where the eval shows it (see `docs/results.md`), including where flat memory is close.

## Why it needs HydraDB

The learned state is edges: `(:Task)-[:USED {w}]->(:Api)` weights that the feedback loop rewrites after every run. Routing is a weighted multi-hop traversal from similar past tasks to the tools they used, aggregated over several runs, which a key-value or vector store cannot do without rebuilding the aggregation in application code. HydraDB gives us the traversal, the weighted shortest paths used for the "why this tool" view, and durable edge state on object storage at low cost, so experience from millions of runs stays cheap to keep. We run the open-source engine self-hosted, as the event requires, and keep the catalog and the experience in one graph.
