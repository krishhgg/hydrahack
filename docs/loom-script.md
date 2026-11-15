# Loom script (3 to 4 minutes)

Record at 1080p, browser at the live app ({{LIVE_URL}}), a second tab on `docs/results.md` rendered on GitHub, a third on the repo. Total target 3:40. Say numbers as shown on screen; if a number on screen differs from this script, say the screen's number and tell the team.

| Time | Shot | Say |
|---|---|---|
| 0:00 to 0:20 | Face or title card "Waypoint", repo name | "Agents with many tools preload every schema or use stateless search. I built Waypoint: a drop-in MCP endpoint that serves five tools instead of fourteen hundred and learns from every run which five. Built on the open-source HydraDB graph engine, Track 2." |
| 0:20 to 0:50 | Results page: tokens and headline | "The whole catalog is 200,953 schema tokens per task. Waypoint loads 714, 281 times fewer, and every needed tool still has to be among the five. That is the metric: Completeness@5." |
| 0:50 to 1:30 | Live app: type a task, press route; or an MCP client call to find_tools | "Here is a real task from the held-out set. Waypoint splits it into sub-requests, finds similar past ones, follows the NEEDS edges to the tools they needed, and returns five schemas. The path view shows why each tool was picked." |
| 1:30 to 2:15 | Results page: the curve | "Baseline is stateless BM25, the mechanism behind Anthropic and OpenAI tool search: 26.7%. After 19,361 feedback runs it is 70.3% on 2,373 test tasks that are never fed back, 2.6 times better. The curve rises at every checkpoint." |
| 2:15 to 2:55 | Live app: submit feedback, route again | "Now I log a finished run. This writes new edges into HydraDB. Route a similar task again and the ranking changes. The learned state is the graph, shared by every agent that routes through it." |
| 2:55 to 3:25 | Results page: slices table | "The honest check. A plain store of past runs, with the same scoring and candidate budget, gets 69.9%, so most of the gain is the learning loop. The graph adds its margin where a new catalog lives: tool sets never seen in training, 41.5% against 38.4%, and it gets there with roughly a third to a half fewer runs, which is what a new customer's catalog needs. I would rather show you that than hide it." |
| 3:25 to 3:45 | gtm.md pricing table, repo | "Buyer: the platform lead with a big MCP catalog. Free open source, a Team plan from $99 a month. Repo, live link and results are in the description. Thanks." |

Checklist before recording: live app responds, results page shows no braces, the posts tagging @hydra_db are live, the Loom link goes in the form last.
