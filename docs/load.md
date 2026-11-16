# Load test

Script: `load/locustfile.py` run by `load/run.sh` (locust, headless). Mix: 10 parts `POST /api/route` (five sample tasks from `load/route_bodies.json`, k 3 to 5) to 1 part `GET /health`. It is read-only: it never calls `/api/feedback`, which writes. Command: `LOAD_HOST=<url> load/run.sh <users> <spawn rate> <duration>`.

Every row below is zero failures. Each `/api/route` request makes three HydraDB traversals plus a BM25 and scoring pass in the app.

## Same image, same code, two CPU budgets (local Docker, 30 s runs)

The image is the one deployed (`ghcr.io/krishhgg/hydrahack-render`, graph baked in). The load generator ran on the same machine, so the 2 CPU numbers are a floor, not a ceiling.

| CPU / RAM limit | users | route req/s | route p50 | route p95 | route p99 | peak memory |
|---|---|---|---|---|---|---|
| 2 CPU / 2 GB | 20 | 56.6 | 150 ms | 280 ms | 380 ms | 466 MiB |
| 2 CPU / 2 GB | 100 | 48.4 | 1.6 s | 2.3 s | 2.6 s | 466 MiB |
| **0.1 CPU / 512 MB** (Render free tier) | 5 | 1.8 | 2.3 s | 3.3 s | 4.6 s | 371 MiB |
| **0.1 CPU / 512 MB** (Render free tier) | 20 | 1.4 | 10 s | 15 s | 16 s | 371 MiB |

## What this means

- The app is CPU-bound: one uvicorn process serves about 50 to 60 route requests per second on 2 CPUs, and latency past that point is queueing, not errors. We did not add workers because the router keeps its index and live task ids in process memory.
- **The live link runs on Render's free tier, which gives the container 0.1 CPU.** At that budget it serves about 2 route requests per second, so expect seconds per query under concurrent use. It stayed correct and inside 512 MB (no OOM, no failed requests) at 20 concurrent users, it is just slow.
- Cold start takes about 3 minutes at 0.1 CPU (12 s at 2 CPUs) and the instance is kept warm by a ping every 5 minutes. Teach/feedback writes are not persisted across restarts (no disk).
- Writes: HydraDB commits are the slow path (about 8 ms each on the tuned image, see docs/hydradb-notes.md), which is why the load test is read-only and why the learning loop batches.

## Live instance

Numbers against the live Render URL are added below once it is up.
