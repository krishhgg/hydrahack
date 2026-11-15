"""Load test for the deployed app.

  LOAD_HOST=https://<app domain> load/run.sh [users] [spawn-rate] [duration]

Defaults to POST /api/route with the sample tasks in load/route_bodies.json (read-only: it never
calls /api/feedback, which writes).

Environment:
  LOAD_QUERY_PATH    the query endpoint (default /api/route; GET when LOAD_QUERY_METHOD=GET)
  LOAD_QUERY_BODIES  JSON list of request bodies, picked at random (default load/route_bodies.json)
  LOAD_HEALTH_PATH   cheap readiness endpoint mixed in at 1/10 weight (default /health)
"""

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

QUERY_PATH = os.environ.get("LOAD_QUERY_PATH", "/api/route")
METHOD = os.environ.get("LOAD_QUERY_METHOD", "POST").upper()
BODIES = json.loads(
    os.environ.get("LOAD_QUERY_BODIES") or (Path(__file__).parent / "route_bodies.json").read_text()
)
HEALTH_PATH = os.environ.get("LOAD_HEALTH_PATH", "/health")


class Visitor(HttpUser):
    wait_time = between(0.05, 0.3)

    @task(10)
    def query(self):
        body = random.choice(BODIES)
        if METHOD == "GET":
            self.client.get(QUERY_PATH, params=body, name=f"GET {QUERY_PATH}")
        else:
            self.client.post(QUERY_PATH, json=body, name=f"POST {QUERY_PATH}")

    @task(1)
    def health(self):
        self.client.get(HEALTH_PATH, name=f"GET {HEALTH_PATH}")
