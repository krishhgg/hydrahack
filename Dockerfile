# App image: FastAPI service (API + static UI). HydraDB itself is a separate service, see
# infra/hydradb/Dockerfile and docker-compose.yml.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first so code changes do not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

# The core app lives at hydrahack.api:app; override with APP_MODULE if that moves.
ENV APP_MODULE=hydrahack.api:app \
    PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$PORT\" --proxy-headers"]
