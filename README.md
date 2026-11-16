# Waypoint

**A drop-in MCP endpoint that serves 5 tools instead of 1,400, and learns from every run which 5 to serve.** Built for the HydraDB Hackathon, Track 2 (the agent context layer), on the open-source [HydraDB](https://github.com/hydra-db/hydradb) engine, self-hosted, as the graph database.

**Live app:** {{LIVE_URL}} (free tier: see [the caveats below](#live-app-and-load))
**Loom walkthrough:** {{LOOM_URL}}

![Waypoint UI: a held-out task routed, Waypoint's top 5 against BM25's top 5, and the subgraph the route traversed](docs/img/waypoint-ui.png)

The screenshot is one hand-picked illustration: a held-out task that Waypoint completes and both baselines miss. It is not typical; the representative numbers are the tables below.

## The problem

Agents with large tool catalogs either load every tool schema on every request (Anthropic cites 58 tools using about 55K tokens before the conversation starts) or use stateless tool search (BM25 or regex over descriptions) that misses tools a task needs together. One missing tool and the task fails, and neither approach learns from the runs the agent already did.

## What Waypoint does

HydraDB stores the tool catalog and the router's experience as a graph. A new task is split into sub-requests, matched against past tasks and past sub-requests, and a traversal in HydraDB follows `Task -USED-> Api` and `Clause -NEEDS-> Api` edges to the tools they needed. Only the top 5 schemas go to the agent, through a `/mcp` endpoint that any MCP client can use (`find_tools`, and `report_run` to write the outcome back). Each finished run writes new edges, so the router improves with use.

## Results

Metric: **Completeness@5**, the share of held-out tasks where every needed tool is among the 5 loaded. Data: ToolBench G3, COLT split, 1,419 real APIs; 2,373 test tasks that are never fed back; 19,361 training runs fed back. Every number comes from `eval/` and is listed with its method in [docs/results.md](docs/results.md).

| Router | Completeness@5 | Recall@5 |
|---|---|---|
| Stateless BM25 tool search (baseline) | 26.7% | 56.0% |
| Flat memory: copy the nearest past run's tools | 60.3% | 76.0% |
| Flat k-NN: Waypoint's scoring and candidate budget over whole past runs in plain dicts | 69.9% | 83.5% |
| **Waypoint** (experience graph in HydraDB) | **70.3%** | **83.9%** |

- **2.6x over stateless tool search**, and 714 tool-schema tokens per task against 200,953 for the whole catalog (281x fewer).
- The curve rises at every checkpoint: see [docs/img/waypoint-curve.svg](docs/img/waypoint-curve.svg).
- **Most of the gain is the learning loop.** A budget-matched plain store gets 69.9%. What the graph structure adds is concentrated where a new catalog lives: on tool sets never seen in training, 41.5% against 38.4%, and it reaches the same accuracy with roughly 10% to 48% fewer runs (interpolated between checkpoints, so approximate; see the data-efficiency table in docs/results.md). On tool sets seen in training the two are level (78.2% against 78.5%).
- Both flat baselines run on Python dicts, not in HydraDB, and a parity test shows the same traversal returns identical results either way. We therefore attribute the accuracy to the learning design, not the engine; HydraDB is where the graph lives in production: persistent, shared by every agent that routes through it, and traversed live.
- Feedback is simulated from the training labels (a finished run reports the tools it needed), the test labels never reach the graph, and COLT's tune file is never read because it is byte-identical to the test file.

## Live app and load

- The live app runs on Render's free tier (0.1 CPU, 512 MB), so it is **much slower under concurrent use** than the load test below: about 2 route requests per second, and several seconds per query with a few users. It stays correct (no failed requests in testing). Cold start takes about 3 minutes and a keep-alive ping runs every 5 minutes. Teach and feedback writes are lost when the instance restarts.
- **Load test** ([docs/load.md](docs/load.md)), same image at 2 CPU: 56.6 route requests per second at 20 users, p50 150 ms, p95 280 ms, zero failures. At 0.1 CPU (the free tier): 1.8 requests per second at 5 users, p50 2.3 s, zero failures.
- Routing latency in the eval, 8 concurrent clients against one HydraDB node: p50 68.9 ms, p95 103.2 ms.

## Run it

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
docker compose --profile app up --build     # HydraDB (pinned image) and the app on http://127.0.0.1:8000
# or, to reproduce the eval:
docker compose up -d --wait hydradb
uv sync
uv run python -m eval.run_eval               # about 3 minutes, writes eval/results/waypoint-test.json
uv run python -m eval.plot                   # eval/results/waypoint-test.svg
uv run python -m eval.report                 # refreshes the generated block in docs/results.md
```

The first run downloads the dataset (11 MB) into `data/`. `run_eval` wipes the graph's Task nodes before it starts, so do not point it at a live demo's HydraDB.

## Docs

- [docs/results.md](docs/results.md): results, slices, data efficiency, what we tried that did not help, eval protocol
- [docs/api.md](docs/api.md): HTTP API and the `/mcp` endpoint
- [docs/load.md](docs/load.md): load test profiles
- [docs/deploy.md](docs/deploy.md) and `infra/render/`: deploy (Render free tier; Fly.io and Railway variants kept)
- [docs/gtm.md](docs/gtm.md) and [docs/pitch.md](docs/pitch.md): who buys it and the pitch; [docs/loom-script.md](docs/loom-script.md): the walkthrough script
- [docs/decision-log.md](docs/decision-log.md), [docs/recommendation.md](docs/recommendation.md), [docs/hydradb-notes.md](docs/hydradb-notes.md): how we got here

## License

MIT, see [LICENSE](LICENSE). HydraDB is a separate project under its own license; it is pulled as a pinned Docker image and not vendored here.
