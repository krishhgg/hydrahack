# Render image: HydraDB engine and the FastAPI app in one container (like infra/fly/Dockerfile), with
# the learned graph baked in at build time. Render's free tier has 0.1 CPU and no disk, and loading
# the ToolBench catalog and training runs into HydraDB took about 11 minutes there. The seed stage
# runs that ingestion once on a build machine, so a cold start only opens an existing store.
# Only the catalog and the training runs are ingested (never test labels): see hydrahack.api.State.
#   docker build -f infra/render/Dockerfile -t hydrahack-render .
ARG HYDRADB_BASE=ghcr.io/krishhgg/hydrahack-hydradb@sha256:081ac63cfda4d8e1d8e52ee6769c22ef9c734cb8bceb3e0d28ae70a23886fe24

FROM ${HYDRADB_BASE} AS base
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN uv sync --locked --no-dev
COPY infra/hydradb/healthcheck.sh /usr/local/bin/hydradb-healthcheck
COPY infra/hydradb/entrypoint.sh /usr/local/bin/hydradb-entrypoint
COPY infra/fly/entrypoint.sh /usr/local/bin/fly-entrypoint
COPY infra/render/seed.sh /usr/local/bin/seed-store
RUN chmod 0755 /usr/local/bin/hydradb-healthcheck /usr/local/bin/hydradb-entrypoint \
    /usr/local/bin/fly-entrypoint /usr/local/bin/seed-store
ENV WAYPOINT_DATA=/data/waypoint \
    TIKTOKEN_CACHE_DIR=/data/tiktoken \
    APP_MODULE=hydrahack.api:app \
    PORT=10000 \
    HYDRADB_URL=http://127.0.0.1:8443 \
    HYDRADB_ADMIN_URL=http://127.0.0.1:9090 \
    HYDRADB_TIMEOUT=150 \
    GRAPH_MAX_QUERY_RUNTIME_MS=120000 \
    GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687 \
    GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687

FROM base AS seed
RUN /usr/local/bin/seed-store

FROM base
COPY --from=seed --chown=10001:10001 /data /data
EXPOSE 10000
HEALTHCHECK NONE
USER root
ENTRYPOINT ["/usr/local/bin/fly-entrypoint"]
