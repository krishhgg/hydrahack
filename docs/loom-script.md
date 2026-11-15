# Loom script (3 to 4 minutes)

Record at 1080p, browser at the live app ({{LIVE_URL}}), a second tab on `docs/results.md` rendered on GitHub, a third on the repo. Total target 3:40. Say numbers as shown on screen; if a placeholder is still unfilled, stop and ask the team.

| Time | Shot | Say |
|---|---|---|
| 0:00 to 0:20 | Face or title card "Waypoint", repo name | "Agents with many tools preload every schema or use stateless search. I built Waypoint, a tool router that learns from every run, on the open-source HydraDB graph engine, for Track 2." |
| 0:20 to 0:50 | Slide or results page: token numbers | "Loading the whole catalog costs {{TOKENS_ALL}} schema tokens per task. Waypoint loads 5 schemas, {{TOKENS_WAYPOINT}} tokens, and every needed tool still has to be among them. That is the metric: Completeness@5." |
| 0:50 to 1:30 | Live app: type a task, press route | "Here is a real task from the held-out set. Waypoint finds similar past tasks, follows the USED edges to the tools they needed, and returns five schemas. The path view shows why each tool was picked." |
| 1:30 to 2:15 | Live app or results: the curve | "Baseline is stateless BM25, the mechanism behind Anthropic and OpenAI tool search: {{C5_BM25}}. After {{RUNS}} feedback runs it is {{C5_GRAPH_FINAL}} on {{N_TEST}} test tasks that are never fed back. Dense retrieval is {{C5_DENSE}}." |
| 2:15 to 2:55 | Live app: submit feedback, route again | "Now I log a finished run. This writes new weights onto the edges in HydraDB. Route the same kind of task again and the ranking changes. The learned state is the edges, not a cache in my app." |
| 2:55 to 3:20 | Results page: novel toolsets | "The honest check: flat memory that just copies the nearest past task scores {{C5_NOVEL_FLAT}} on tools it never saw together, the graph scores {{C5_NOVEL_GRAPH}}, because it aggregates weights across several similar runs. A plain store would need that aggregation rebuilt in app code." |
| 3:20 to 3:40 | gtm.md pricing table, repo | "Buyer: the platform lead with a big MCP catalog. Free open source, Team plan from $99 a month. Repo, live link and results are in the description. Thanks." |

Checklist before recording: live app responds, results page shows no braces, the posts tagging @hydra_db are live, the Loom link goes in the form last.
