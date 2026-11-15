"""Restarts the engine on an existing store and checks that writes still succeed.

Two regressions, both of which left the live app read-only after an engine restart:

* the engine numbers its own HTTP query ids from 1 on every start and uses them as mutation
  idempotency keys, so after a restart id-less writes failed with "idempotency identity was
  reused for a different request" (HydraDB.execute now sends a unique query_id);
* after a hard kill the previous process leaves an unreleased writer lease that the engine cannot
  take over on a local-filesystem store (infra/hydradb/entrypoint.sh clears it at boot).

Needs docker compose and a running hydradb service:
  docker compose up -d --build --wait hydradb && pytest -m integration
"""

import shutil
import subprocess
import time

import pytest

from hydrahack.db import HydraDB

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available"),
]

BASE = 830_000_000
EDGE = "MERGE (a:RestartT {id: $a})-[:R]->(b:RestartT {id: $b})"


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


def _wait_healthy() -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            with HydraDB(timeout=5) as probe:
                if probe.health()["ok"]:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError("engine did not become healthy after restart")


def _check_writes_survive(stop_engine) -> None:
    with HydraDB() as db:
        db.reset(labels=["RestartT"], ids=range(BASE, BASE + 20))
        # several distinct writes before the restart, so any id reuse afterwards is a collision
        for i in range(4):
            db.write(EDGE, {"a": BASE + i, "b": BASE + 10 + i})

    stop_engine()
    _wait_healthy()

    with HydraDB() as db:
        for i in range(4):
            db.write(EDGE, {"a": BASE + 4 + i, "b": BASE + 14 + i})
        db.write(
            "MATCH (a {id: $a})-[r:R]->(b {id: $b}) SET r.w = $w",
            {"a": BASE, "b": BASE + 10, "w": 0.5},
        )
        rows = db.query("MATCH (a {id: $a})-[r:R]->(b) RETURN r.w AS w", {"a": BASE})
        assert rows == [{"w": 0.5}]  # the pre-restart edge survived and took the new write
        assert db.health()["roundtrip"] is True
        db.reset(labels=["RestartT"], ids=range(BASE, BASE + 20))


def test_writes_succeed_after_graceful_restart():
    _check_writes_survive(lambda: _compose("restart", "hydradb"))


def test_writes_succeed_after_hard_kill():
    def kill_and_start():
        _compose("kill", "hydradb")
        _compose("start", "hydradb")

    _check_writes_survive(kill_and_start)
