# Go-to-market: Waypoint

Status: numbers filled from `docs/results.md` and `eval/results/waypoint-test.json` (ToolBench G3, COLT split, 2,373 held-out test tasks, 19,361 runs fed back). Pricing and customer claims are proposals, not measurements.

## One line

Waypoint is a drop-in MCP endpoint that serves 5 tools instead of 1,400, and learns from every run which 5 to serve.

## First adopter

A platform or AI-infra team that has already connected 5 or more MCP servers to its coding or ops agents and is paying twice: in tokens (Anthropic's own example is 58 tools using about 55K tokens before the conversation starts, with 134K seen before optimisation) and in wrong-tool calls. They are easy to find because they file issues like github-mcp-server #1286 ("over 66 tools") and post "MCP tools eat 30 to 50% of context". Second adopter: tool-integration and MCP-gateway vendors (Composio and similar) that sell a large catalog and want routing that improves with customer usage.

## Buyer

- Budget holder: head of AI platform or developer productivity, in the AI infra or dev-tools line, not the individual developer.
- User: the engineers building the agent. They point their MCP client at one URL; the platform lead pays.
- Trigger to buy: a token bill or a failure rate they can point at. On ToolBench G3 the whole catalog is 200,953 schema tokens per task and Waypoint loads 714 (281x fewer).

## Problem

Agents with large tool catalogs have two bad options. Preload every schema and pay for it on every request, or use stateless tool search (BM25 or regex over descriptions, which is how Anthropic's and OpenAI's tool search work today) and miss tools the task needs together. A task with one missing tool fails, so the number that matters is Completeness@5 (every needed tool is in the 5 loaded). Stateless BM25 reaches 26.7% on our held-out tasks, and it never learns from the thousands of runs the agent already did.

## Why now

- MCP made it cheap to connect dozens of servers, so catalogs grew faster than context windows.
- Vendors shipped tool search in 2025 and 2026, which confirms the pain and leaves a gap: it is stateless and per vendor.
- Teams already log which tools successful runs used, so the experience needed to improve routing exists in their traces.

## Wedge

One team, one large MCP catalog, one number. Waypoint exposes an MCP endpoint (`/mcp`, tool `find_tools` returns the 5 schemas a task needs, `report_run` writes the outcome back), tested with the official MCP Python client, so any MCP-capable agent can use it without code changes. It starts at BM25 quality on day one and improves with logged runs: 26.7% to 70.3% Completeness@5 after 19,361 runs, 2.6x, with the token cut on top.

## Pricing (proposal, to validate with first customers)

| Plan | Price | For |
|---|---|---|
| Open source | Free, self-hosted, MIT | Individual developers, evaluation |
| Team | $99/month flat for up to 10 agents | Teams with one catalog, hosted graph and dashboard |
| Scale | $499/month flat plus usage above 1M routes | Platform teams, multiple catalogs |
| Enterprise | Custom | VPC or BYOC, audit, SSO |

Anchors from the market: Composio Standard is $18 per seat per month, Zep Flex is $125 and Flex Plus $375 per month, Cognee charges $1 per 1M tokens processed. The Team price pays for itself when tokens saved per task (200,953 minus 714 on this benchmark) times tasks per month times the model's input price exceeds it. We do not publish a dollar saving until it is computed from a customer's own volume.

## Competition

| Alternative | What it does | Where Waypoint differs |
|---|---|---|
| Preload everything | All schemas in every request | Token cost and wrong-tool errors grow with catalog size; Waypoint serves 5. |
| Anthropic and OpenAI tool search | BM25 or regex over tool descriptions, deferred loading | Stateless, per vendor, no memory of what worked. This is our measured baseline (26.7%). |
| Composio, Docker MCP gateway | Catalog, auth and dynamic discovery | Complementary: they host tools, Waypoint decides which ones to serve. |
| Plain store of past runs | Remembers past runs without a graph | A strong control. Copying the nearest past run reaches 60.3%; a budget-matched flat k-NN (same scoring and candidate budget as Waypoint, in plain dicts) reaches 69.9% against Waypoint's 70.3%. |
| Zep, Cognee, Mem0 | Agent memory (facts, user history) | Memory of what was said; Waypoint stores which tools worked for which sub-requests and routes on it. |

## What is the learning loop and what is the graph

Most of the gain over BM25 comes from the learning loop: logging which tools finished runs needed and routing on that. A budget-matched plain store gets almost all of it (69.9% against 70.3%, level on tool sets seen in training at 78.5% against 78.2%). We say so because the eval shows it.

What the graph structure adds is concentrated where a new customer lives. On tool sets never seen in training, Waypoint scores 41.5% against 38.4% for the plain store, and it learns new combinations faster: it reaches 30% on those tasks after about 4,600 runs where the plain store needs about 8,800 (roughly 28% to 48% fewer runs across the levels measured; 10% to 38% fewer over all tasks; interpolated between checkpoints, so approximate). A new customer's catalog starts with few runs, so this is the number that matters for adoption. A `Clause -NEEDS-> Api` edge carries only the tools one sub-request needed, so Waypoint can assemble a new tool set from parts of different past runs, where a whole stored run drags in tools the new task does not need. The gain is real but modest.

## Why it needs HydraDB

The learned state lives on graph edges that the feedback loop rewrites after every run, and routing is a multi-hop traversal (task clauses to similar past clauses to the tools they needed) run live inside self-hosted HydraDB. The same traversal on Python dicts returns exactly what HydraDB returns (a parity test asserts it), so we do not claim the engine makes the accuracy higher. HydraDB is where the graph lives in production: persistent, shared by every agent that routes through it, cheap to keep on object storage as runs accumulate, and queryable for the "why this tool" view. We run the open-source engine self-hosted, as the event requires.
