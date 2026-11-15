"""Placeholder app used until hydrahack.api exists: proves the Railway wiring (app -> hydradb
over the private network). Select it with APP_MODULE=infra.app_stub:app on the app service."""

from fastapi import FastAPI

from hydrahack.db import HydraDB

app = FastAPI()


@app.get("/health")
def health():
    with HydraDB() as db:
        return db.health()
