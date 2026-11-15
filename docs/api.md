# Waypoint API

One FastAPI service (`hydrahack.api:app`) serves the API and the UI. It reads `HYDRADB_URL`, `HYDRADB_ADMIN_URL` and `HYDRADB_TOKEN`, listens on `$PORT`, and on start loads the ToolBench G3 catalog and the training runs into HydraDB if the graph is empty. Until that finishes, `/api/*` answers 503 and `/health` reports `"ready": false`.

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Readiness, HydraDB liveness and the number of learned tasks |
| POST | `/api/route` | Route a task: Waypoint's top-k tools, the BM25 baseline's top-k, the similar past tasks, the subgraph used, tokens and latency. Read-only |
| POST | `/api/feedback` | Write a finished run back into the graph: a new Task node, USED edges to the tools needed and REJECTED edges to tools offered but not needed |
| GET | `/api/examples` | Eight held-out test tasks with their needed tools, for the demo (picked by `eval/examples.py`) |
| GET | `/api/results` | The committed eval result (`eval/results/waypoint-test.json`) in the UI's shape |
| GET | `/` | The single-page UI |
| POST | `/mcp` | MCP server (Streamable HTTP, JSON responses) with two tools: `find_tools(task, k)` returns the schemas of the k tools a task needs, and `report_run(task, used, offered)` writes the outcome back |

## /api/route

Request: `{"task": "<text>", "k": 5}` (`k` 1-20, default 5). Each route makes three HydraDB traversals: the similar Tasks' USED tools, then the USED and REJECTED counts of the candidate tools.

Sample bodies for load tests (the first three are held-out test tasks):

```json
{"task": "I'm planning a surprise birthday party for my best friend. Can you help me find a list of popular cocktails to serve at the party? Also, I need some suggestions for cocktail recipes that are easy to make.", "k": 5}
```

```json
{"task": "I'm planning a trip to Istanbul and I need to know the postal code of the hotel area, the current exchange rate from USD to TRY and the weather forecast for next week.", "k": 5}
```

```json
{"task": "My company wants to track a shipment with ID 6045e2f44e1b233199a5e77a and check the health of our carbon-accounting API.", "k": 5}
```

```json
{"task": "Find me trending songs this week, the lyrics of the top one and a related YouTube video.", "k": 5}
```

```json
{"task": "get me a random joke and a fun fact about cats", "k": 3}
```

## /api/feedback

Request: `{"task": "<text>", "used": [4, 0, 1], "offered": [4, 0, 1, 7, 9]}`. `used` holds the api `idx` values the run actually needed; `offered` holds what the router offered, and anything offered but not used becomes a REJECTED edge. Each call writes one Task node and `len(used) + len(offered - used)` edges, so keep it out of read-only load tests.

## /mcp

Point any MCP client at `https://<host>/mcp`. The agent sees two tools, not 1,419:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "find_tools", "arguments": {"task": "Find popular cocktails and the weather forecast for tonight", "k": 5}}}
```

The result's `structuredContent.tools` holds each tool's `id`, `name`, `server` (the RapidAPI tool), `description` and `inputSchema`, plus `tokens_loaded` and `tokens_catalog`. `report_run` takes `{"task", "used": [ids], "offered": [ids]}` and refuses held-out test tasks.

Tested with the official MCP Python client (`mcp` package, `streamable_http_client`): initialize, `list_tools` and `call_tool("find_tools")` all work. A request body is capped at 64 KB and a JSON-RPC batch at 8 messages; larger ones get 413 or 400. Routing runs in the server's thread pool, so a slow request doesn't block `/health`.
