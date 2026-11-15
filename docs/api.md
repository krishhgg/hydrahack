# Waypoint API

One FastAPI service (`hydrahack.api:app`) serves the API and the UI. It reads `HYDRADB_URL`, `HYDRADB_ADMIN_URL` and `HYDRADB_TOKEN`, listens on `$PORT`, and on start loads the ToolBench G3 catalog and the training runs into HydraDB if the graph is empty. Until that finishes, `/api/*` answers 503 and `/health` reports `"ready": false`.

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Readiness, HydraDB liveness and the number of learned tasks |
| POST | `/api/route` | Route a task: Waypoint's top-k tools, the BM25 baseline's top-k, the similar past tasks, the subgraph used, tokens and latency. Read-only |
| POST | `/api/feedback` | Write a finished run back into the graph: a new Task node, USED edges to the tools needed and REJECTED edges to tools offered but not needed |
| GET | `/api/examples` | Eight held-out test tasks with their needed tools, for the demo |
| GET | `/api/results` | The committed eval result (`eval/results/waypoint-test.json`) in the UI's shape |
| GET | `/` | The single-page UI |

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
