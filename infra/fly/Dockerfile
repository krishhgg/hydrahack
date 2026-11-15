# Combined image for Fly.io: the HydraDB engine and the FastAPI app in one container, so HydraDB
# listens on loopback only and is never public. Build with the repo root as context:
#   docker build -f infra/fly/Dockerfile -t hydrahack-fly .
# The base is the published wrapper image (pinned upstream engine plus env defaults), see
# infra/hydradb/Dockerfile and .github/workflows/hydradb-image.yml.
ARG HYDRADB_BASE=ghcr.io/krishhgg/hydrahack-hydradb@sha256:081ac63cfda4d8e1d8e52ee6769c22ef9c734cb8bceb3e0d28ae70a23886fe24
FROM ${HYDRADB_BASE}

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

# Take the healthcheck from this checkout, not the pinned base, so fixes to it ship with the app.
COPY infra/hydradb/healthcheck.sh /usr/local/bin/hydradb-healthcheck
COPY infra/fly/entrypoint.sh /usr/local/bin/fly-entrypoint
RUN chmod 0755 /usr/local/bin/fly-entrypoint /usr/local/bin/hydradb-healthcheck

# Both processes share the container, so the engine is reached over loopback.
ENV APP_MODULE=hydrahack.api:app \
    PORT=8080 \
    HYDRADB_URL=http://127.0.0.1:8443 \
    HYDRADB_ADMIN_URL=http://127.0.0.1:9090 \
    GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687 \
    GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687

EXPOSE 8080
HEALTHCHECK NONE
# Starts as root so it can chown the Fly volume at /data, then drops both processes to uid 10001.
USER root
ENTRYPOINT ["/usr/local/bin/fly-entrypoint"]
