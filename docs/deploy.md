# Deploy (Railway)

Two services in one Railway project, talking over the private network. HydraDB needs a long-running process and a persistent disk, which is why this is not a serverless host.

| Service | Source | Notes |
|---|---|---|
| `hydradb` | `ghcr.io/krishhgg/hydrahack-hydradb:latest` (pinned upstream engine v0.4.0 plus env defaults, published by `.github/workflows/hydradb-image.yml`) | Volume at `/data` holds the store and cache. No public domain: only the app reaches it. Variables: `HYDRADB_TOKEN` (random, generated once), `RAILWAY_RUN_UID=0` (volume is root-owned). |
| `app` | root `Dockerfile` (FastAPI via uvicorn on `$PORT`) | Public domain. `HYDRADB_URL`, `HYDRADB_ADMIN_URL` and `HYDRADB_TOKEN` are Railway references to the `hydradb` service; `OPENAI_API_KEY` set from the deployer's environment. |

```bash
export RAILWAY_API_TOKEN=...            # account token, never committed
infra/railway/deploy.sh setup           # first deploy
infra/railway/deploy.sh app             # redeploy the app after each merge to main
infra/railway/deploy.sh status          # services, domain, live /health
```

Sizing: the engine used about 150 MB resident with 20k nodes and 40k edges loaded (about 17 MB idle), so it fits the 1 GB trial limit for the demo graph, but a sustained load test pushed a long-lived container to about 930 MB, so Hobby is the safer plan for the load test.
