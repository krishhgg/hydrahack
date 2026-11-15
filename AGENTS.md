# AGENTS.md

Hackathon entry built on the open-source HydraDB engine (self-hosted) as the graph database. Python 3.12 + uv, FastAPI.

## Review guidelines

Review for what matters at this stage of a time-boxed hackathon build. Flag P0/P1 issues only when they are real; skip style nits.

- The graph must do real work: multi-hop traversal and edge/path state that the learning loop changes. Flag code that quietly falls back to a plain key-value or vector lookup, or that stores the learned state outside the graph.
- Eval integrity: no test answers or held-out labels leaking into ingestion, training or tuning. Baseline and learned numbers must come from a committed eval script, never hard-coded in docs, UI or pitch.
- Waypoint eval (ToolBench G3, COLT split): the test split's tool labels must never reach the graph, the learning loop or any tuning. COLT's `query_tool_tune.txt` is byte-identical to the test file, so any read of it is a leak; validation must be a slice of train. Flag any comparison where baselines get a different feedback budget or candidate count than the graph.
- No secrets: no API keys, tokens or .env contents in code, tests, workflows, logs or docs. Secrets come from environment variables only.
- The demo path must not break: the live app, the query endpoint, docker compose and CI should keep working. Flag changes that break startup, health or readiness checks.
- Cypher: parameterize queries, never string-interpolate user input.
- Do not vendor HydraDB source (it is ELv2); pull it as a Docker image or pinned git ref.
- Infra: workflows must pin images/refs and stay under ~5 minutes; never rebuild the Rust engine in PR CI.
