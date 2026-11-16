# Deploy

## Current host: Render free web service

The live link runs on Render's free tier, which needs no card: **512 MB RAM, 0.1 CPU, no persistent disk**, and it spins down after 15 idle minutes (a keep-alive workflow pings /health every 5 minutes). One container runs both HydraDB (loopback only) and the FastAPI app, from `infra/render/Dockerfile`.

- **No disk means no persistence.** The graph is baked into the image at build time: the `seed` stage starts the engine, lets the app ingest the ToolBench catalog and training runs (never test labels), and stops the engine cleanly. A cold start only opens that store. Anything written at runtime (the Teach button, live feedback) is lost when the instance restarts or redeploys, and the demo returns to the baked state.
- **Cold start is about 200 s at 0.1 CPU** (about 11 minutes before the store was baked), which is why the keep-alive ping matters. The remaining time is the app rebuilding its in-memory BM25 index from the 19,361 stored tasks and a 30 s scan of them. The container sets `HYDRADB_TIMEOUT=150` and `GRAPH_MAX_QUERY_RUNTIME_MS=120000` because single queries take 25 to 30 s on 0.1 CPU.
- **Performance is the free tier's, not the app's**: see docs/load.md for the 0.1 CPU numbers next to the 2-CPU ones.
- Image: `.github/workflows/render-image.yml` builds and pushes `ghcr.io/krishhgg/hydrahack-render` on every push to main. `infra/render/deploy.sh setup|deploy|status` (needs `RENDER_API_KEY`) creates the service and redeploys it.

## Fly.io and Railway (kept, unused)

Fly.io needs a card and Railway restricted the workspace, so neither is the host. The Fly variant is below and its files stay in the repo (`fly.toml`, `infra/fly/`).

### Fly.io

One Fly app, one machine, two processes in one container: HydraDB (the engine, on loopback) and the FastAPI app (public). HydraDB needs a long-running process and a persistent disk, which is why this is not a serverless host.

**Why a single machine.** The engine is single-node and keeps its store on local disk, so there is nothing to scale out. Putting the API in the same container means HydraDB listens on `127.0.0.1` only: it is never public, and there is no private-network, DNS or IPv6 wiring to get wrong. `infra/fly/entrypoint.sh` starts the engine, waits for the write/read/delete round-trip healthcheck, then runs uvicorn; if either process exits the container exits and Fly restarts it.

| Piece | Where |
|---|---|
| Image | `infra/fly/Dockerfile`, built on `ghcr.io/krishhgg/hydrahack-hydradb` pinned by digest (the wrapper built from #3, 31ecb99) (pinned upstream engine v0.4.0, see `infra/hydradb/Dockerfile`) plus python and the app, installed with `uv sync --locked --no-dev` |
| Config | `fly.toml`: region `sjc`, `shared-cpu-2x` with 2 GB, volume `hydradb_data` at `/data`, `/health` check every 15 s, `auto_stop_machines = "off"` and `min_machines_running = 1` so it stays warm |
| Secrets | `HYDRADB_TOKEN` (random, generated once by `deploy.sh`), `OPENAI_API_KEY` (from the deployer's environment, if set). Never committed or printed |
| App module | `APP_MODULE` defaults to `hydrahack.api:app`. While that module does not exist the entrypoint serves `infra/app_stub.py` (`/health` only), so the deploy still goes green |

```bash
export FLY_API_TOKEN=...                # never committed; flyctl is installed into ~/.fly if missing
infra/fly/deploy.sh setup               # first deploy: app, 3 GB volume, secrets, remote build (idempotent)
infra/fly/deploy.sh app                 # redeploy after each merge to main
infra/fly/deploy.sh status              # machine state and live /health
```

`FLY_APP_NAME` (default `hydrahack-live`), `FLY_REGION` (default `sjc`) and `FLY_ORG` override the defaults. The live URL is `https://<app>.fly.dev`, and `/health` returns `{"healthz": true, "readyz": true, "roundtrip": true, "ok": true}` when the engine accepts writes.

**Redeploy on merge.** `.github/workflows/deploy.yml` runs `flyctl deploy --remote-only` on every push to `main` when the `FLY_API_TOKEN` repository secret exists, and skips cleanly otherwise. Optionally set the `FLY_APP_NAME` repository variable if the app name differs.

**Volume.** Fly mounts volumes root-owned. The entrypoint runs as root, `chown`s `/data` to uid 10001, and starts both processes as that user with `setpriv`. Data survives restarts and redeploys; `fly volumes` snapshots are the backup.

**Sizing.** The engine used about 150 MB resident with 20k nodes and 40k edges loaded, but a sustained load test pushed a long-lived process to about 930 MB, so the machine has 2 GB and 2 shared CPUs, leaving room for the API and the load test.

## Alternative: Railway (unused)

Railway was the first plan but the workspace is restricted, so Fly is primary. The Railway variant runs two services (the engine from the GHCR image with a volume and `RAILWAY_RUN_UID=0`, and the app from the root `Dockerfile`) over Railway's private network, with `infra/railway/deploy.sh`. It needs private-network variable references and a second public-facing service, which is the complexity the single-machine design avoids.
