# Loom script (about 4 minutes)

Record at 1080p. Tabs, left to right: the live app (https://8000-cs6js0x7u8nbs6h8biw2kqrl2vyzobbf.capysandbox.net), `docs/results.md` rendered on GitHub, the repo. Say numbers as shown on screen; if a screen number differs from this script, say the screen's number and tell the team.

## Before you press record

- **Teach exactly once, at the end.** Every Teach click writes a new Task into the live graph (5000000, 5000001, and so on), so a second take starts from a graph that already knows the lesson and the "before" ranking looks better. If you must re-record, change the sports or the coin in the Teach task, or ask the team to reset the graph.
- Route one example first to warm the indexes (the first route after a cold start can take a second). Then reload the page.
- The live app runs on a single 4-CPU instance, and Teach writes are lost when it restarts. Open the app a few minutes before recording, route one example first, and do not run other tabs against it while recording. For load, cite docs/load.md (2 CPU: 56.6 req/s at 20 users, p50 150 ms); the Render free tier in docs/deploy.md is the much slower self-host option (0.1 CPU, about 2 req/s).
- Do not quote a fixed latency on camera; the header shows 20 to 45 ms and varies by machine.
- The three held-out examples below were hand-picked: tasks Waypoint completes and both baselines miss. Call them illustrations, never typical. The representative numbers are the table on the results page.
- The example buttons under "Held-out test tasks" appear once the demo-queries PR is deployed. Before that, paste the task text into the box; the "needed" ticks and the COMPLETE badge will not show.

## Shot list

| Time | Shot | Say |
|---|---|---|
| 0:00 to 0:20 | Title card or face, repo name | "Agents with many tools preload every schema or use stateless search. I built Waypoint: a drop-in MCP endpoint that serves five tools instead of fourteen hundred and learns from every run which five. It runs on the open-source HydraDB graph engine. This is Track 2." |
| 0:20 to 0:50 | Results page: top table and token line | "The metric is Completeness@5: every tool a task needs has to be among the five loaded, because one missing tool and the task fails. On 2,373 held-out ToolBench tasks, stateless BM25, which is how tool search works today, gets 26.7%. Waypoint gets 70.3%, 2.6 times better, and loads 714 schema tokens instead of 200,953 for the whole catalog." |
| 0:50 to 1:40 | Live app: click example #2547 (sports scores plus crypto prices). Point at panel 2, the DailyOHLCV row (source line "6 clauses + text", pink vote bar), then at the BM25 column. Hover DailyOHLCV so panel 3 lights its paths | "Here is one illustration, hand-picked, not typical. A task that mixes sports odds and crypto candles. No past run combined those two, so copying past runs cannot produce this set. Waypoint splits the task into sub-requests, matches the crypto part against past sub-requests, and follows their NEEDS edges in HydraDB to the daily OHLCV tool. BM25 never finds it. The graph built the answer from parts of different runs." |
| 1:40 to 2:05 | Live app: click example #9967 (memes plus username checks). Point at the 4/4 COMPLETE badge, BM25's 3/4, and the token panel (637 tokens) | "A second one: four tools from three sub-requests, all four in the top five, against three of four for BM25, with about a third of a percent of the catalog in context. Again, hand-picked to show the mechanism." |
| 2:05 to 2:50 | Results page: curve, slices and data-efficiency tables | "Now the honest part. The curve rises at every checkpoint. But a plain store of past runs with the same scoring and candidate budget, flat k-NN, gets 69.9%, so most of the gain is the learning loop, not the graph. What the graph adds is where a new catalog lives: on tool sets never seen in training, 41.5% against 38.4%, and it needs roughly a third to a half fewer runs to reach the same accuracy. That is the margin, and I would rather show you the real size than hide it." |
| 2:50 to 3:25 | Live app, last interaction: type the Teach task (sports scores for tonight's basketball plus daily OHLCV for crypto), press Enter, tick the two needed tools, click Teach, then route the rephrased task and point at DailyOHLCV now at #2 | "Now the learning loop, live, once. I log a finished run: these two tools were needed. That writes edges into HydraDB, the counter goes from 19,361 to 19,362, and a differently worded task now finds DailyOHLCV through the new Task and its sub-request. The lesson lives as edges, not in a prompt." |
| 3:25 to 3:55 | Repo or `docs/gtm.md` pricing table | "The buyer is the platform lead with a big MCP catalog, paying for schema tokens and wrong-tool failures. Open source under MIT, a hosted Team plan from $99 a month is the proposal. Repo, live link and results are in the description. Thanks." |

Teach task text, copy and paste:

> I'm a sports fan and I want the latest scores. Fetch the live scores for tonight's basketball games. Also, provide me with the daily OHLCV data for the crypto market.

Rephrased task for the after-check:

> I'm into sports and crypto. Fetch live scores for upcoming football games. Also, give me the daily OHLCV data for Bitcoin.

Checklist before recording: live app responds, results page shows no braces, the posts tagging @hydra_db are live, the Loom link goes in the form last.
