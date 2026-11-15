"use strict";
(() => {
  const params = new URLSearchParams(location.search);
  const MOCK = params.has("mock") && params.get("mock") !== "0";
  const K = 5;
  const SVGNS = "http://www.w3.org/2000/svg";
  const $ = (sel, root = document) => root.querySelector(sel);

  const state = {
    results: null,
    examples: [],
    example: null,
    routedExample: null,
    route: null,
    routedTask: "",
    prev: null,
    checked: new Set(),
    busy: false,
  };

  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid);
    return e;
  }

  function svg(tag, attrs, ...kids) {
    const e = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") e.textContent = v;
      else e.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid);
    return e;
  }

  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  const frac = (v) => (isNum(v) ? (v > 1 ? v / 100 : v) : null);
  const pct = (v) => {
    const f = frac(v);
    if (f == null) return "–";
    const p = f * 100;
    return (Math.abs(p - Math.round(p)) < 0.05 ? String(Math.round(p)) : p.toFixed(1)) + "%";
  };
  const fmt = (n) => (isNum(n) ? Math.round(n).toLocaleString("en-US") : "–");
  const short = (n) => {
    if (!isNum(n)) return "–";
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + "k";
    return String(Math.round(n));
  };
  const trunc = (s, n) => {
    s = String(s ?? "");
    return s.length > n ? s.slice(0, Math.max(1, n - 1)) + "…" : s;
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const niceStep = (r) => {
    const e = 10 ** Math.floor(Math.log10(r || 1));
    const f = r / e;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * e;
  };
  const apiIdx = (node) => (isNum(node.idx) ? node.idx : parseInt(String(node.id).replace(/^\D+/, ""), 10));
  const taskId = (node) => (node.task_id ?? String(node.id).replace(/^t/, ""));

  async function api(path, body) {
    if (MOCK) {
      await sleep(80 + Math.random() * 140);
      return JSON.parse(JSON.stringify(mockApi(path, body)));
    }
    const init = body === undefined
      ? { headers: { Accept: "application/json" } }
      : { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, init);
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      try {
        const j = await res.json();
        if (j && j.detail) msg += ": " + (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      } catch (_) { /* non-JSON error body */ }
      throw new Error(msg);
    }
    return res.json();
  }

  /* ---------- header ---------- */

  async function loadHealth() {
    const h = $("#health");
    const label = $("span", h);
    try {
      const j = await api("/health");
      const ok = !!(j && j.ok);
      h.className = "health " + (ok ? "ok" : "bad");
      h.title = JSON.stringify(j);
      label.textContent = MOCK ? "mock data (?mock=1)" : ok ? "HydraDB live" : "degraded";
    } catch (e) {
      h.className = "health bad";
      label.textContent = "API offline";
      h.title = e.message;
    }
  }

  function setLearned(n, flash) {
    if (!isNum(n)) return;
    const p = $("#learned");
    p.textContent = fmt(n) + " tasks learned";
    if (flash) {
      p.classList.remove("flash");
      void p.offsetWidth;
      p.classList.add("flash");
    }
  }

  /* ---------- frame 1: results ---------- */

  async function loadResults() {
    try {
      state.results = await api("/api/results");
    } catch (e) {
      state.results = null;
      $("#hero").replaceChildren(el("div", { class: "empty", text: "Results unavailable (" + e.message + "). Run the eval to generate them." }));
      return;
    }
    renderResults();
    renderCurve();
  }

  function sortedCurve() {
    const r = state.results || {};
    return (Array.isArray(r.curve) ? r.curve : []).filter((p) => p && isNum(p.runs)).sort((a, b) => a.runs - b.runs);
  }

  function renderResults() {
    const r = state.results || {};
    const hd = r.headline || {};
    const last = sortedCurve().at(-1) || {};
    const k = isNum(r.k) ? r.k : K;
    const metric = hd.metric || "Completeness@" + k;
    const wp = frac(hd.waypoint ?? last.waypoint);
    const bm = frac(hd.baseline ?? last.bm25);
    const fm = frac(hd.flat_memory ?? last.flat_memory);

    $("#dataset").textContent = [r.dataset, isNum(r.test_tasks) && fmt(r.test_tasks) + " held-out tasks"].filter(Boolean).join(" · ");

    const hero = $("#hero");
    hero.replaceChildren(
      el("div", { class: "big wp" }, el("div", { class: "v", text: pct(wp) }), el("div", { class: "l", text: "Waypoint" })),
      el("div", { class: "big bm" }, el("div", { class: "v", text: pct(bm) }), el("div", { class: "l", text: "BM25 tool search" })),
      wp != null && bm != null && el("div", { class: "big delta" },
        el("div", { class: "v" }, (wp >= bm ? "+" : "") + ((wp - bm) * 100).toFixed(1), el("small", { text: "pts" })),
        el("div", { class: "l", text: bm > 0 ? (wp / bm).toFixed(1) + "× the baseline" : "over baseline" })),
    );

    const sub = el("div", { class: "hero-sub", text: metric + " = share of " + (isNum(r.test_tasks) ? fmt(r.test_tasks) + " " : "") + "held-out tasks where every tool the task needed is among the " + k + " loaded into context." });
    const kpis = [];
    if (fm != null) kpis.push(el("div", { class: "kpi" }, el("div", { class: "k", text: "Flat memory" }), el("div", { class: "v" }, el("span", { class: "fm", text: pct(fm) }))));
    if (isNum(hd.recall5_baseline) || isNum(hd.recall5_waypoint)) {
      kpis.push(el("div", { class: "kpi" }, el("div", { class: "k", text: "Recall@" + k }),
        el("div", { class: "v" }, el("span", { class: "from", text: pct(hd.recall5_baseline) }), " → ", el("span", { class: "to", text: pct(hd.recall5_waypoint) }))));
    }
    if (isNum(hd.tokens_per_task_waypoint)) {
      kpis.push(el("div", { class: "kpi", title: "Tool-schema tokens loaded per task vs loading the whole catalog" }, el("div", { class: "k", text: "Tokens / task" }),
        el("div", { class: "v" }, el("span", { class: "to", text: short(hd.tokens_per_task_waypoint) }), isNum(hd.tokens_catalog) && el("small", { text: " of " + short(hd.tokens_catalog) }))));
    }
    hero.after(sub);
    document.querySelectorAll("#p-results .hero-sub").forEach((n) => n !== sub && n.remove());
    document.querySelectorAll("#p-results .kpis").forEach((n) => n.remove());
    if (kpis.length) sub.after(el("div", { class: "kpis", style: "grid-template-columns: repeat(" + kpis.length + ", minmax(0, 1fr))" }, kpis));

    const slices = r.slices && typeof r.slices === "object" ? Object.entries(r.slices).filter(([, s]) => s && typeof s === "object") : [];
    const sliceHint = {
      seen_toolset: "Test tasks whose tool combination appeared in the experience graph",
      novel_toolset: "Test tasks whose tool combination never appeared in the experience graph",
    };
    $("#slices").replaceChildren(...slices.map(([key, s]) => {
      const name = key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
      const bar = (cls, label, v) => frac(v) == null ? null : el("div", { class: "bar " + cls },
        el("span", { class: "bl", text: label }),
        el("span", { class: "tr" }, el("span", { class: "fl", style: "display:block;width:" + (frac(v) * 100).toFixed(1) + "%" })),
        el("span", { class: "bv", text: pct(v) }));
      return el("div", { class: "slice", title: sliceHint[key] || "" },
        el("div", { class: "sh" }, el("b", { text: name }), isNum(s.n) && el("span", { text: "n = " + fmt(s.n) })),
        bar("wp", "Waypoint", s.waypoint), bar("fm", "Flat memory", s.flat_memory), bar("bm", "BM25", s.bm25));
    }));
    $("#slices").hidden = !slices.length;

    const gen = r.generated_at ? new Date(r.generated_at) : null;
    $("#results-foot").textContent = "From the committed eval run" + (gen && !isNaN(gen) ? " · generated " + gen.toISOString().replace("T", " ").slice(0, 16) + " UTC" : "") + (MOCK ? " · MOCK DATA" : "");
  }

  function renderCurve() {
    const host = $("#curve");
    host.replaceChildren();
    const r = state.results || {};
    const pts = sortedCurve();
    if (!pts.length) {
      host.append(el("div", { class: "empty", text: "No learning curve in the results yet." }));
      return;
    }
    const W = Math.max(260, host.clientWidth);
    const H = Math.max(150, host.clientHeight);
    const m = { l: 38, r: 52, t: 12, b: 32 };
    const x0 = pts[0].runs;
    const x1 = pts.at(-1).runs;
    const span = x1 - x0 || 1;
    const X = (v) => m.l + ((v - x0) / span) * (W - m.l - m.r);
    const Y = (v) => m.t + (1 - Math.max(0, Math.min(1, v))) * (H - m.t - m.b);
    const root = svg("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Completeness over feedback runs" });
    root.append(svg("defs", {}, svg("linearGradient", { id: "wpGrad", x1: 0, y1: 0, x2: 0, y2: 1 },
      svg("stop", { offset: "0", "stop-color": "#5aa9ff", "stop-opacity": 0.28 }),
      svg("stop", { offset: "1", "stop-color": "#5aa9ff", "stop-opacity": 0 }))));

    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      root.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grid-l" }));
      root.append(svg("text", { x: m.l - 6, y: Y(t) + 3.5, "text-anchor": "end", class: "axis", text: Math.round(t * 100) + "%" }));
    }
    const step = niceStep(span / 4);
    for (let t = Math.ceil(x0 / step) * step; t <= x1 + 1e-9; t += step) {
      root.append(svg("text", { x: X(t), y: H - m.b + 15, "text-anchor": "middle", class: "axis", text: short(t) }));
    }
    root.append(svg("text", { x: m.l + (W - m.l - m.r) / 2, y: H - 3, "text-anchor": "middle", class: "axis-title", text: "feedback runs (tasks the router has learned from)" }));

    const hdBase = frac(r.headline && r.headline.baseline);
    const series = [
      { key: "bm25", cls: "bm" },
      { key: "flat_memory", cls: "fm" },
      { key: "waypoint", cls: "wp" },
    ];
    const ends = [];
    for (const s of series) {
      let sp = pts.filter((p) => isNum(p[s.key])).map((p) => [p.runs, frac(p[s.key])]);
      if (!sp.length && s.key === "bm25" && hdBase != null) sp = [[x0, hdBase], [x1, hdBase]];
      if (!sp.length) continue;
      const d = sp.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join("");
      if (s.key === "waypoint" && sp.length > 1) {
        root.append(svg("path", { d: d + "L" + X(sp.at(-1)[0]).toFixed(1) + "," + Y(0) + "L" + X(sp[0][0]).toFixed(1) + "," + Y(0) + "Z", class: "area" }));
      }
      root.append(svg("path", { d, class: "line " + s.cls }));
      if (s.key === "waypoint") for (const p of sp.slice(0, -1)) root.append(svg("circle", { cx: X(p[0]), cy: Y(p[1]), r: 2.6, class: "dot wp" }));
      const lp = sp.at(-1);
      ends.push({ cls: s.cls, x: X(lp[0]), y: Y(lp[1]), ly: Y(lp[1]), v: lp[1] });
    }
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].ly - ends[i - 1].ly < 15) ends[i].ly = ends[i - 1].ly + 15;
    for (const e of ends) {
      root.append(svg("circle", { cx: e.x, cy: e.y, r: 4, class: "end " + e.cls }));
      root.append(svg("text", { x: e.x + 8, y: e.ly + 4.5, class: "endlabel " + e.cls, text: pct(e.v) }));
    }

    const cursor = svg("line", { y1: m.t, y2: H - m.b, class: "cursor", visibility: "hidden" });
    root.append(cursor);
    const hit = svg("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
    hit.addEventListener("mousemove", (ev) => {
      const box = root.getBoundingClientRect();
      const mx = ev.clientX - box.left;
      let best = pts[0];
      for (const p of pts) if (Math.abs(X(p.runs) - mx) < Math.abs(X(best.runs) - mx)) best = p;
      cursor.setAttribute("x1", X(best.runs));
      cursor.setAttribute("x2", X(best.runs));
      cursor.setAttribute("visibility", "visible");
      const row = (label, v) => isNum(v) ? el("div", { class: "ts", text: label + "  " + pct(v) }) : null;
      showTip(ev, el("div", { class: "th", text: fmt(best.runs) + " feedback runs" }),
        row("Waypoint   ", best.waypoint), row("Flat memory", best.flat_memory), row("BM25       ", best.bm25));
    });
    hit.addEventListener("mouseleave", () => { cursor.setAttribute("visibility", "hidden"); hideTip(); });
    root.append(hit);
    host.append(root);
  }

  /* ---------- frame 2: route ---------- */

  async function loadExamples() {
    try {
      const ex = await api("/api/examples");
      state.examples = Array.isArray(ex) ? ex.filter((e) => e && e.text) : [];
    } catch (e) {
      state.examples = [];
      $("#examples").replaceChildren(el("span", { class: "status err", style: "grid-column: 1 / -1", text: "Examples unavailable: " + e.message }));
      return;
    }
    renderExamples();
  }

  function renderExamples() {
    $("#examples").replaceChildren(...state.examples.map((ex) => el("button", {
      type: "button",
      class: "chip" + (state.example === ex ? " on" : ""),
      title: ex.text,
      onclick: () => pickExample(ex),
    }, el("b", { text: "#" + ex.id }), " ", ex.text)));
  }

  function pickExample(ex) {
    if (state.busy) return;
    state.example = ex;
    $("#task").value = ex.text;
    renderExamples();
    route(ex.text);
  }

  const goldSet = () => {
    const ex = state.routedExample;
    return ex && Array.isArray(ex.gold) ? new Set(ex.gold.map(Number)) : null;
  };

  function setBusy(b) {
    state.busy = b;
    $("#route-btn").disabled = b;
    document.querySelectorAll(".chip").forEach((c) => (c.disabled = b));
    updateTeach();
  }

  async function route(task) {
    task = String(task || "").trim();
    if (!task || state.busy) return;
    setBusy(true);
    try {
      await doRoute(task, null);
    } finally {
      setBusy(false);
    }
  }

  async function doRoute(task, prev) {
    const st = $("#route-status");
    st.className = "status";
    st.textContent = prev ? "Re-routing with the new edges…" : "Routing…";
    try {
      const res = await api("/api/route", { task, k: K });
      state.prev = prev;
      state.route = res || {};
      state.routedTask = task;
      if (!prev) {
        state.routedExample = state.example && String(state.example.text).trim() === task ? state.example : null;
        state.checked = new Set();
        const gold = goldSet();
        if (gold) for (const t of [...(state.route.tools || []), ...(state.route.baseline || [])]) if (gold.has(t.idx)) state.checked.add(t.idx);
        $("#teach-status").textContent = "";
        $("#teach-status").className = "status";
      }
      setLearned(state.route.learned_tasks);
      st.textContent = "";
      renderRoute();
      return true;
    } catch (e) {
      st.className = "status err";
      st.textContent = "Route failed: " + e.message;
      return false;
    }
  }

  function renderRoute() {
    const r = state.route || {};
    const lat = r.latency_ms || {};
    $("#latency").textContent = isNum(lat.total)
      ? lat.total.toFixed(1) + " ms" + (isNum(lat.graph) ? " · graph " + lat.graph.toFixed(1) + " ms" : "")
      : "";
    renderList("#wp-list", "#wp-score", r.tools, true);
    renderList("#bm-list", "#bm-score", r.baseline, false);
    renderGraph();
    renderTokens();
    updateTeach();
  }

  function viaText(paths) {
    if (!Array.isArray(paths) || !paths.length) return "";
    const tasks = new Set(paths.filter((p) => p && p.via === "task").map((p) => p.task)).size;
    const text = paths.some((p) => p && p.via === "text");
    const parts = [];
    if (tasks) parts.push(tasks + " past task" + (tasks === 1 ? "" : "s"));
    if (text) parts.push("text");
    return parts.length ? "via " + parts.join(" + ") : "";
  }

  function renderList(listSel, scoreSel, tools, isWp) {
    const host = $(listSel);
    host.replaceChildren();
    tools = Array.isArray(tools) ? tools.filter((t) => t && t.idx != null) : [];
    const gold = goldSet();
    const prevTools = state.prev ? (isWp ? state.prev.tools : state.prev.baseline) || [] : null;
    const prevRanks = prevTools ? new Map(prevTools.map((t, i) => [t.idx, i])) : null;
    if (!tools.length) host.append(el("li", { class: "empty", text: state.route ? "No tools returned." : "Pick an example or type a task." }));

    tools.forEach((t, i) => {
      const needed = !!(gold && gold.has(t.idx));
      let change = null;
      if (prevRanks && isWp) {
        if (!prevRanks.has(t.idx)) change = ["new", "NEW"];
        else {
          const d = prevRanks.get(t.idx) - i;
          if (d > 0) change = ["up", "▲" + d];
          else if (d < 0) change = ["down", "▼" + -d];
        }
      }
      const cb = el("input", { type: "checkbox", class: "tg", title: "I needed this tool", "aria-label": "I needed " + (t.name || "this tool"), "data-idx": t.idx });
      cb.checked = state.checked.has(t.idx);
      cb.addEventListener("change", () => {
        if (cb.checked) state.checked.add(t.idx);
        else state.checked.delete(t.idx);
        document.querySelectorAll('.tg[data-idx="' + t.idx + '"]').forEach((c) => (c.checked = cb.checked));
        updateTeach();
      });
      const via = isWp ? viaText(t.paths) : "";
      const sub = [t.tool, t.category].filter(Boolean).join(" · ");
      const li = el("li", { class: ["tool", needed && "needed", change && "chg-" + change[0]].filter(Boolean).join(" "), "data-idx": t.idx },
        cb,
        el("span", { class: "rank", text: String(i + 1) }),
        el("div", { class: "tbody" },
          el("div", { class: "tname", title: t.name || "", text: t.name || "API " + t.idx }),
          el("div", { class: "tsub", title: sub }, sub, via && (sub ? " · " : ""), via && el("span", { class: "via", text: via }))),
        el("div", { class: "tmeta" },
          change && el("span", { class: "chg " + change[0], text: change[1] }),
          isWp && isNum(t.score) && el("span", { class: "tscore", text: t.score.toFixed(2) }),
          needed && el("span", { class: "gold", title: "Ground truth: this task needed this tool", text: "✓" })));
      li.addEventListener("mouseenter", () => focusGraph("a" + t.idx));
      li.addEventListener("mouseleave", () => focusGraph(null));
      host.append(li);
    });

    if (prevTools && isWp) {
      const now = new Set(tools.map((t) => t.idx));
      const dropped = prevTools.filter((t) => !now.has(t.idx));
      if (dropped.length) host.append(el("li", { class: "dropped", text: "dropped out: " + dropped.map((t) => t.name || "API " + t.idx).join(", ") }));
    }

    const score = $(scoreSel);
    if (gold && gold.size && tools.length) {
      const hit = tools.slice(0, K).filter((t) => gold.has(t.idx)).length;
      const complete = hit === gold.size;
      score.replaceChildren(
        el("span", { class: "hits", text: hit + "/" + gold.size + " needed" }),
        el("span", { class: "pill " + (complete ? "ok" : "miss"), text: complete ? "complete" : "incomplete" }));
    } else {
      score.replaceChildren();
    }
  }

  function updateTeach() {
    const btn = $("#teach-btn");
    const n = state.checked.size;
    const heldOut = !!(state.routedExample && state.routedTask === String(state.routedExample.text).trim());
    btn.disabled = state.busy || !state.route || !n || heldOut;
    btn.textContent = heldOut
      ? "Held-out test task: edit the text to teach (keeps the eval clean)"
      : "Teach Waypoint: these were the tools I needed" + (n ? " (" + n + ")" : "");
  }

  async function teach() {
    if (state.busy || !state.route || !state.checked.size) return;
    const task = state.routedTask;
    const used = [...state.checked];
    const st = $("#teach-status");
    st.className = "status";
    st.textContent = "Writing (:Task)-[:USED]->(:Api) edges to HydraDB…";
    setBusy(true);
    try {
      const fb = (await api("/api/feedback", { task, used })) || {};
      setLearned(fb.learned_tasks, true);
      const edges = isNum(fb.edges_written) ? fb.edges_written : used.length;
      const head = "Wrote " + edges + " USED edge" + (edges === 1 ? "" : "s") + (fb.task_id != null ? " from Task " + fb.task_id : "") + " to HydraDB.";
      st.textContent = head + " Re-routing…";
      const before = state.route;
      if (!(await doRoute(task, before))) {
        st.className = "status err";
        st.textContent = head + " Re-route failed.";
        return;
      }
      st.className = "status ok";
      st.textContent = head + " " + diffSummary(before, state.route, used);
    } catch (e) {
      st.className = "status err";
      st.textContent = "Feedback failed: " + e.message;
    } finally {
      setBusy(false);
    }
  }

  function diffSummary(before, after, used) {
    const b = (before.tools || []).map((t) => t.idx);
    const a = (after.tools || []).map((t) => t.idx);
    const entered = a.filter((i) => !b.includes(i)).length;
    const up = a.filter((i, r) => b.includes(i) && b.indexOf(i) > r).length;
    const taughtIn = used.filter((i) => a.slice(0, K).includes(i)).length;
    const parts = [];
    if (entered) parts.push(entered + " tool" + (entered === 1 ? "" : "s") + " entered the top " + K);
    if (up) parts.push(up + " moved up");
    parts.push(taughtIn + "/" + used.length + " taught tools load");
    return "Re-routed: " + parts.join(", ") + ".";
  }

  /* ---------- frame 3: graph + tokens ---------- */

  function renderGraph() {
    const host = $("#graph");
    host.replaceChildren();
    host.classList.remove("focus");
    const r = state.route || {};
    const g = r.graph || {};
    const nodes = Array.isArray(g.nodes) ? g.nodes.filter((n) => n && n.id != null) : [];
    const edges = Array.isArray(g.edges) ? g.edges.filter((e) => e && e.source != null && e.target != null) : [];
    if (!nodes.length) {
      host.append(el("div", { class: "empty", text: state.route ? "No graph returned for this route." : "Route a task to see the subgraph it traversed." }));
      return;
    }
    const W = Math.max(320, host.clientWidth);
    const H = Math.max(240, host.clientHeight);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const col = (n) => (n.kind === "query" ? 0 : n.kind === "task" ? 1 : 2);
    const cols = [[], [], []];
    for (const n of nodes) cols[col(n)].push(n);

    const prevG = state.prev && state.prev.graph;
    const prevNodes = prevG && Array.isArray(prevG.nodes) ? new Set(prevG.nodes.map((n) => n.id)) : null;
    const prevEdges = prevG && Array.isArray(prevG.edges) ? new Set(prevG.edges.map((e) => e.source + ">" + e.target)) : null;

    const simW = new Map();
    for (const e of edges) {
      const s = byId.get(e.source);
      const t = byId.get(e.target);
      if (s && t && col(s) === 0 && col(t) === 1) simW.set(t.id, isNum(e.w) ? e.w : 0);
    }
    cols[1].sort((a, b) => (simW.get(b.id) ?? 0) - (simW.get(a.id) ?? 0));

    const top = 30;
    const bot = 12;
    const pos = new Map();
    const xs = [42, Math.round(W * 0.33), Math.round(W * 0.585)];
    const place = (arr, x, maxGap) => {
      const avail = H - top - bot;
      const gap = arr.length > 1 ? Math.min(maxGap, avail / (arr.length - 1)) : 0;
      const start = top + (avail - gap * (arr.length - 1)) / 2;
      arr.forEach((n, i) => pos.set(n.id, { x, y: start + gap * i }));
    };
    place(cols[0], xs[0], 60);
    place(cols[1], xs[1], 92);

    const rankWp = new Map((r.tools || []).map((t, i) => [t.idx, i]));
    const rankBm = new Map((r.baseline || []).map((t, i) => [t.idx, i]));
    const bary = new Map();
    for (const n of cols[2]) {
      const ys = [];
      for (const e of edges) {
        const other = e.target === n.id ? e.source : e.source === n.id ? e.target : null;
        const p = other != null && pos.get(other);
        if (p && byId.get(other) && col(byId.get(other)) === 1) ys.push(p.y);
      }
      bary.set(n.id, ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : H + (rankWp.get(apiIdx(n)) ?? 99));
    }
    cols[2].sort((a, b) => bary.get(a.id) - bary.get(b.id));
    place(cols[2], xs[2], 46);

    const root = svg("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Subgraph used by the route" });
    root.append(svg("text", { x: 10, y: 12, class: "colh", text: "QUERY" }));
    root.append(svg("text", { x: xs[1], y: 12, "text-anchor": "middle", class: "colh", text: "SIMILAR PAST TASKS" }));
    root.append(svg("text", { x: xs[2] - 8, y: 12, class: "colh", text: "APIS (top " + K + " loaded)" }));

    const maxByType = {};
    for (const e of edges) {
      const ty = String(e.type || "edge").toLowerCase();
      maxByType[ty] = Math.max(maxByType[ty] || 0, isNum(e.w) ? Math.abs(e.w) : 0);
    }
    const radius = (n) => (col(n) === 0 ? 36 : col(n) === 1 ? 7 : 7);
    const edgeLayer = svg("g", {});
    for (const e of edges) {
      let s = byId.get(e.source);
      let t = byId.get(e.target);
      if (!s || !t) continue;
      let a = pos.get(s.id);
      let b = pos.get(t.id);
      if (a.x > b.x) { [s, t] = [t, s]; [a, b] = [b, a]; }
      const ty = String(e.type || "edge").toLowerCase();
      const w = isNum(e.w) ? Math.abs(e.w) : 0;
      const sw = 0.8 + 5.2 * (maxByType[ty] ? w / maxByType[ty] : 0.3);
      const sx = a.x + radius(s);
      const tx = b.x - radius(t);
      const mx = (sx + tx) / 2;
      const isNew = prevEdges && !prevEdges.has(e.source + ">" + e.target);
      const cls = ["edge", ty, t.selected && "sel", isNew && "new"].filter(Boolean).join(" ");
      edgeLayer.append(svg("path", {
        d: "M" + sx + "," + a.y + " C" + mx + "," + a.y + " " + mx + "," + b.y + " " + tx + "," + b.y,
        class: cls, "stroke-width": sw.toFixed(2), "data-s": s.id, "data-t": t.id,
      }, svg("title", { text: (e.type || "edge") + (isNum(e.w) ? " · w " + e.w.toFixed(2) : "") })));
    }
    root.append(edgeLayer);

    const gold = goldSet();
    const tasks = new Map((r.similar_tasks || []).map((t) => [String(t.id), t]));
    const apiInfo = new Map();
    for (const t of [...(r.baseline || []), ...(r.tools || [])]) if (t) apiInfo.set(t.idx, t);
    const apiName = (i) => (apiInfo.get(i) && apiInfo.get(i).name) || (byId.get("a" + i) && byId.get("a" + i).label) || "API " + i;
    const labelChars = Math.max(8, Math.floor((W - xs[2] - 16) / 6.3));

    for (const n of nodes) {
      const p = pos.get(n.id);
      const c = col(n);
      const isNew = prevNodes && !prevNodes.has(n.id);
      const gEl = svg("g", { class: ["node", n.selected && "sel", isNew && "new"].filter(Boolean).join(" "), "data-id": n.id, transform: "translate(" + p.x + "," + p.y + ")" });
      if (c === 0) {
        gEl.append(svg("rect", { x: -36, y: -12, width: 72, height: 24, rx: 12, class: "q" }));
        gEl.append(svg("text", { x: 0, y: 4, "text-anchor": "middle", class: "qt", text: trunc(n.label || "your task", 11) }));
      } else if (c === 1) {
        if (isNew) gEl.append(svg("circle", { r: 7, class: "ring2" }));
        gEl.append(svg("circle", { r: 7, class: "t" }));
        const w = simW.get(n.id);
        gEl.append(svg("text", { x: 0, y: -11, "text-anchor": "middle", class: "lbl" },
          trunc(n.label || "Task " + taskId(n), 16), isNum(w) ? svg("tspan", { class: "w", text: "  " + w.toFixed(2) }) : null));
      } else {
        const idx = apiIdx(n);
        if (n.selected) gEl.append(svg("circle", { r: 10, class: "ring" }));
        if (isNew) gEl.append(svg("circle", { r: 7, class: "ring2" }));
        gEl.append(svg("circle", { r: n.selected ? 6.5 : 5, class: "a" }));
        const needed = gold && gold.has(idx);
        gEl.append(svg("text", { x: 13, y: 4, class: "lbl" },
          trunc(n.label || apiName(idx), labelChars - (needed ? 2 : 0)),
          needed ? svg("tspan", { class: "ck", text: " ✓" }) : null));
      }
      gEl.addEventListener("mouseenter", (ev) => { focusGraph(n.id); showTip(ev, ...nodeTip(n, { tasks, apiInfo, apiName, rankWp, rankBm, gold, simW })); });
      gEl.addEventListener("mousemove", (ev) => moveTip(ev));
      gEl.addEventListener("mouseleave", () => { focusGraph(null); hideTip(); });
      root.append(gEl);
    }
    host.append(root);
  }

  function nodeTip(n, ctx) {
    if (n.kind === "query") {
      return [el("div", { class: "th", text: "Your task" }), el("div", { class: "tt", text: trunc(state.routedTask, 320) })];
    }
    if (n.kind === "task") {
      const id = taskId(n);
      const t = ctx.tasks.get(String(id)) || {};
      const sim = isNum(t.sim) ? t.sim : ctx.simW.get(n.id);
      const used = Array.isArray(t.tools) ? t.tools.map(ctx.apiName) : [];
      return [
        el("div", { class: "th", text: "Task " + id }),
        el("div", { class: "ts", text: "SIMILAR" + (isNum(sim) ? " · sim " + sim.toFixed(2) : "") }),
        (t.text || n.text) && el("div", { class: "tt", text: trunc(t.text || n.text, 320) }),
        used.length && el("div", { class: "ts", text: "USED → " + used.join(", ") }),
      ];
    }
    const idx = apiIdx(n);
    const a = ctx.apiInfo.get(idx) || {};
    const rw = ctx.rankWp.get(idx);
    const rb = ctx.rankBm.get(idx);
    return [
      el("div", { class: "th", text: a.name || n.label || "API " + idx }),
      el("div", { class: "ts", text: [a.tool || n.tool, a.category || n.category].filter(Boolean).join(" · ") }),
      el("div", { class: "tt", text: (rw != null ? "Waypoint #" + (rw + 1) : "Not loaded by Waypoint") + " · " + (rb != null ? "BM25 #" + (rb + 1) : "not in BM25 top " + K) + (isNum(a.score) ? " · score " + a.score.toFixed(2) : "") }),
      ctx.gold && ctx.gold.has(idx) && el("div", { class: "tt", style: "color: var(--ok)", text: "✓ This task truly needed this tool" }),
    ];
  }

  function focusGraph(id) {
    const host = $("#graph");
    host.querySelectorAll(".hl").forEach((x) => x.classList.remove("hl"));
    document.querySelectorAll(".tool.hl").forEach((x) => x.classList.remove("hl"));
    if (id == null || !host.querySelector('[data-id="' + id + '"]')) {
      host.classList.remove("focus");
      return;
    }
    host.classList.add("focus");
    const keep = new Set([id]);
    host.querySelectorAll(".edge").forEach((e) => {
      if (e.dataset.s === id || e.dataset.t === id) {
        e.classList.add("hl");
        keep.add(e.dataset.s);
        keep.add(e.dataset.t);
      }
    });
    host.querySelectorAll(".node").forEach((n) => keep.has(n.dataset.id) && n.classList.add("hl"));
    if (String(id).startsWith("a")) document.querySelectorAll('.tool[data-idx="' + String(id).slice(1) + '"]').forEach((x) => x.classList.add("hl"));
  }

  function renderTokens() {
    const host = $("#tokens");
    const r = state.route;
    if (!r) {
      host.replaceChildren();
      return;
    }
    const t = r.tokens || {};
    const hd = (state.results && state.results.headline) || {};
    const cat = isNum(t.catalog) ? t.catalog : hd.tokens_catalog;
    const loaded = t.loaded;
    const rows = [
      ["wp", "Waypoint top " + K, loaded],
      ["bm", "BM25 top " + K, t.baseline_loaded],
      ["cat", "Whole catalog", cat],
    ].filter((x) => isNum(x[2]));
    const max = Math.max(1, ...rows.map((x) => x[2]));
    const sim = Array.isArray(r.similar_tasks) ? r.similar_tasks.length : 0;
    host.replaceChildren(
      el("div", { class: "tok-head" },
        el("span", { class: "tok-big" }, fmt(loaded), el("small", { text: "tool-schema tokens in context" })),
        isNum(loaded) && isNum(cat) && loaded > 0 && el("span", { class: "tok-ratio", text: Math.round(cat / loaded) + "× fewer than the whole catalog" }),
        el("span", { class: "tok-note", text: (sim ? sim + " similar past tasks traversed · " : "") + (isNum(loaded) && isNum(cat) && cat > 0 ? ((loaded / cat) * 100).toFixed(2) + "% of " + fmt(cat) : "") })),
      el("div", { class: "tok-rows" }, rows.map(([cls, label, v]) => el("div", { class: "tok-row " + cls },
        el("span", { text: label }),
        el("span", { class: "tr" }, el("span", { class: "fl", style: "display:block;width:" + ((v / max) * 100).toFixed(3) + "%" })),
        el("span", { class: "tv", text: fmt(v) })))));
  }

  /* ---------- tooltip ---------- */

  function showTip(ev, ...kids) {
    const tip = $("#tip");
    tip.replaceChildren(...kids.filter(Boolean));
    tip.hidden = false;
    moveTip(ev);
  }
  function moveTip(ev) {
    const tip = $("#tip");
    if (tip.hidden) return;
    const pad = 14;
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width > innerWidth - 6) x = ev.clientX - r.width - pad;
    if (y + r.height > innerHeight - 6) y = ev.clientY - r.height - pad;
    tip.style.left = Math.max(6, x) + "px";
    tip.style.top = Math.max(6, y) + "px";
  }
  function hideTip() {
    $("#tip").hidden = true;
  }

  /* ---------- mock fixtures (?mock=1) ---------- */

  const MOCK_APIS = [
    ["List of Cocktails", "The Cocktail DB", "Food", "cocktail drinks list"],
    ["Detailed Cocktail Recipe by ID", "The Cocktail DB", "Food", "cocktail recipe ingredients"],
    ["Search Recipes", "Tasty", "Food", "recipe meal dinner cook snack"],
    ["Nutrition Analysis", "Edamam", "Food", "nutrition calories diet"],
    ["Search Track", "Deezer", "Music", "music track artist"],
    ["Get Playlist", "Deezer", "Music", "playlist party music"],
    ["5 Day Forecast", "Weatherbit", "Weather", "weather forecast temperature"],
    ["Current Air Quality", "Weatherbit", "Weather", "air quality pollution"],
    ["Search Hotels", "Booking.com", "Travel", "hotel stay room"],
    ["Search Flights", "Skyscanner", "Travel", "flight airport airline"],
    ["Currency Exchange", "Currency Converter", "Finance", "currency exchange rate convert"],
    ["Stock Time Series", "Alpha Vantage", "Finance", "stock price quote market"],
    ["Coin Price", "CoinGecko", "Cryptocurrency", "bitcoin crypto price"],
    ["Top Headlines", "Google News", "News", "news headlines article"],
    ["Search Titles", "IMDb", "Movies", "movie film title rating"],
    ["Theater Showtimes", "Fandango", "Movies", "showtimes cinema theater tickets"],
    ["Translate", "Google Translate", "Translation", "translate language"],
    ["Random Joke", "Jokes by API-Ninjas", "Entertainment", "joke funny party friend"],
    ["Trivia Questions", "Open Trivia DB", "Entertainment", "trivia quiz question game"],
    ["Forward Geocoding", "Geoapify", "Mapping", "address location coordinates"],
    ["Business Search", "Yelp", "Food", "restaurant nearby food"],
    ["Validate Email", "MailboxLayer", "Email", "email validate verify"],
    ["Send SMS", "Twilio", "SMS", "sms text message phone"],
    ["List Exercises by Muscle", "ExerciseDB", "Health and Fitness", "exercise workout muscle"],
    ["Song Lyrics", "Genius", "Music", "lyrics song"],
    ["Event Search", "Ticketmaster", "Events", "concert event tickets party"],
  ].map(([name, tool, category, kw], idx) => ({ idx, name, tool, category, kw }));

  const MOCK_PAST = [
    [3540, "Throw a surprise birthday party with cocktail recipes, songs to play and the Saturday forecast", [0, 1, 4, 6]],
    [1187, "Plan a cocktail night with recipes and music for friends", [0, 1, 4]],
    [2290, "Pick songs and a playlist for a house party", [4, 5]],
    [8820, "Trip to Paris: book flights and a hotel and convert dollars to euros", [9, 8, 10]],
    [8907, "Business travel to London: flights, a hotel near the office and the exchange rate for dollars", [9, 8, 10]],
    [4410, "Weekend getaway: a hotel and the weather forecast for the beach", [8, 6]],
    [5120, "Translate a greeting into Spanish and send it as a text message to my mom's phone", [16, 22]],
    [6031, "Make me a gym routine for legs and count the calories of my protein shake", [23, 3]],
    [6044, "Workout plan for the week with healthy meal recipes", [23, 2, 3]],
    [7012, "Bitcoin price today and the latest crypto news headlines", [12, 13]],
    [7120, "Stock price for Apple and the latest market news", [11, 13]],
    [9310, "Movie night out: showtimes near my address, film ratings and dinner nearby", [15, 14, 20, 19]],
    [9330, "Find a good restaurant near this address", [19, 20]],
    [1450, "Team quiz night with trivia questions and jokes", [18, 17]],
    [3305, "Verify customer email addresses and text them a sign up code", [21, 22]],
  ];

  const MOCK_EXAMPLES = [
    { id: "23081", text: "I'm planning a surprise party for my best friend this Saturday. Suggest some cocktails with full recipes, a few songs to play, and tell me if it will rain.", gold: [0, 1, 4, 6] },
    { id: "41207", text: "Heading to Tokyo next month for a conference. Find me flights from SFO, a place to stay in Shinjuku, and how many yen I get for 2,000 dollars.", gold: [9, 8, 10] },
    { id: "51833", text: "My grandmother only speaks Portuguese. Help me write her a birthday greeting in her language and send it to her phone.", gold: [16, 22] },
    { id: "60412", text: "I want to get in shape: build me a leg day gym routine and estimate the calories in my post-workout smoothie.", gold: [23, 3] },
    { id: "70259", text: "Is now a good time to buy bitcoin? Show me its price and the latest crypto headlines.", gold: [12, 13] },
    { id: "77320", text: "Date night tomorrow: what's showing at the cinema near my address, how are those films rated, and a good restaurant nearby?", gold: [15, 14, 20, 19] },
    { id: "82946", text: "Organize a trivia night for my team with some jokes to break the ice and a snack recipe.", gold: [18, 17, 2] },
    { id: "90115", text: "Before I sign up new users, check that their email addresses are real and send each one a welcome text.", gold: [21, 22] },
  ];

  const mockMem = {
    past: MOCK_PAST.map(([id, text, tools]) => ({ id, text, tools, w: Object.fromEntries(tools.map((t, i) => [t, 1 + ((id + i) % 4)])) })),
    learned: 19361,
    nextId: 99000001,
  };
  const STOP = new Set("a an the and or for to of in on with my me i im is it be some few this that from at by as are what how get find tell give show can you your need want will its her his their them each one now good".split(" "));
  const stem = (w) => (w.length > 4 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);
  const toks = (s) => (String(s).toLowerCase().replace(/'/g, "").match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1 && !STOP.has(w)).map(stem);
  const schemaTokens = (idx) => 120 + ((idx * 53) % 130);

  function mockResults() {
    const runs = [0, 250, 500, 1000, 1500, 2000, 3000, 4000, 5000];
    const sat = (x, tau) => (1 - Math.exp(-x / tau)) / (1 - Math.exp(-5000 / tau));
    return {
      dataset: "ToolBench G3 (COLT split)",
      k: 5,
      test_tasks: 2373,
      curve: runs.map((r) => ({
        runs: r,
        waypoint: +(0.123 + (0.68 - 0.123) * sat(r, 1400)).toFixed(3),
        bm25: 0.123,
        flat_memory: +(0.49 * sat(r, 1900)).toFixed(3),
      })),
      headline: { metric: "Completeness@5", baseline: 0.123, waypoint: 0.68, flat_memory: 0.49, recall5_baseline: 0.37, recall5_waypoint: 0.82, tokens_per_task_waypoint: 900, tokens_catalog: 250000 },
      slices: {
        seen_toolset: { n: 1899, bm25: 0.13, waypoint: 0.76, flat_memory: 0.61 },
        novel_toolset: { n: 474, bm25: 0.1, waypoint: 0.38, flat_memory: 0.05 },
      },
      generated_at: "2026-11-15T22:40:00Z",
    };
  }

  function mockRoute(task, k) {
    const q = new Set(toks(task));
    const text = MOCK_APIS.map((a) => {
      const words = new Set(toks(a.name + " " + a.tool + " " + a.category + " " + a.kw));
      let s = 0;
      for (const w of words) if (q.has(w)) s += 1;
      return s;
    });
    const maxText = Math.max(1, ...text);
    const sims = mockMem.past.map((p) => {
      const pt = new Set(toks(p.text));
      let inter = 0;
      for (const w of q) if (pt.has(w)) inter += 1;
      return { p, sim: inter / Math.sqrt(Math.max(1, q.size) * Math.max(1, pt.size)) };
    }).filter((s) => s.sim > 0.12).sort((a, b) => b.sim - a.sim).slice(0, 4);

    const score = MOCK_APIS.map((a) => ({
      idx: a.idx,
      s: 0.5 * (text[a.idx] / maxText),
      paths: text[a.idx] ? [{ via: "text", w: +(text[a.idx] / maxText).toFixed(2) }] : [],
    }));
    for (const { p, sim } of sims) {
      for (const ti of p.tools) {
        const w = Math.min(1, 0.55 + 0.15 * (p.w[ti] || 1));
        score[ti].s += sim * w;
        score[ti].paths.push({ via: "task", task: p.id, w: +(sim * w).toFixed(2) });
      }
    }
    const base = (i) => ({ idx: i, name: MOCK_APIS[i].name, tool: MOCK_APIS[i].tool, category: MOCK_APIS[i].category });
    const ranked = [...score].sort((a, b) => b.s - a.s || a.idx - b.idx).slice(0, k);
    const tools = ranked.map((x) => ({ ...base(x.idx), score: +x.s.toFixed(2), paths: x.paths }));
    const baseline = MOCK_APIS.map((a) => a.idx).sort((a, b) => text[b] - text[a] || a - b).slice(0, k).map(base);
    const selected = new Set(tools.map((t) => t.idx));

    const nodes = [{ id: "q", label: "your task", kind: "query" }];
    const edges = [];
    const apiIds = new Set(selected);
    for (const { p, sim } of sims) {
      nodes.push({ id: "t" + p.id, label: "Task " + p.id, kind: "task" });
      edges.push({ source: "q", target: "t" + p.id, type: "SIMILAR", w: +sim.toFixed(2) });
      for (const ti of p.tools) {
        apiIds.add(ti);
        edges.push({ source: "t" + p.id, target: "a" + ti, type: "USED", w: p.w[ti] || 1 });
      }
    }
    for (const i of apiIds) nodes.push({ id: "a" + i, label: MOCK_APIS[i].name, kind: "api", selected: selected.has(i) });

    return {
      tools,
      baseline,
      similar_tasks: sims.map(({ p, sim }) => ({ id: p.id, text: p.text, sim: +sim.toFixed(2), tools: p.tools })),
      tokens: {
        loaded: tools.reduce((a, t) => a + schemaTokens(t.idx), 0),
        baseline_loaded: baseline.reduce((a, t) => a + schemaTokens(t.idx), 0),
        catalog: 251000,
      },
      latency_ms: { total: +(11 + Math.random() * 9).toFixed(1), graph: +(3.5 + Math.random() * 4).toFixed(1) },
      graph: { nodes, edges },
      learned_tasks: mockMem.learned,
    };
  }

  function mockApi(path, body) {
    body = body || {};
    if (path === "/health") return { ok: true, hydradb: "mock" };
    if (path === "/api/results") return mockResults();
    if (path === "/api/examples") return MOCK_EXAMPLES;
    if (path === "/api/route") return mockRoute(String(body.task || ""), body.k || K);
    if (path === "/api/feedback") {
      const used = (body.used || []).map(Number).filter((i) => MOCK_APIS[i]);
      let p = mockMem.past.find((x) => x.text === body.task);
      if (p) {
        for (const i of used) {
          if (!p.tools.includes(i)) p.tools.push(i);
          p.w[i] = (p.w[i] || 0) + 1;
        }
      } else {
        p = { id: mockMem.nextId++, text: String(body.task || ""), tools: used, w: Object.fromEntries(used.map((i) => [i, 1])) };
        mockMem.past.push(p);
        mockMem.learned += 1;
      }
      return { task_id: p.id, edges_written: used.length, learned_tasks: mockMem.learned };
    }
    throw new Error("mock: no fixture for " + path);
  }

  /* ---------- boot ---------- */

  function bind() {
    $("#route-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      route($("#task").value);
    });
    $("#task").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        route($("#task").value);
      }
    });
    $("#task").addEventListener("input", () => {
      if (state.example && $("#task").value.trim() !== String(state.example.text).trim()) {
        state.example = null;
        renderExamples();
      }
    });
    $("#teach-btn").addEventListener("click", teach);

    let raf = 0;
    const rerender = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (state.results) renderCurve();
        if (state.route) renderGraph();
      });
    };
    if ("ResizeObserver" in window) {
      const ro = new ResizeObserver(rerender);
      ro.observe($("#curve"));
      ro.observe($("#graph"));
    } else {
      addEventListener("resize", rerender);
    }
  }

  async function boot() {
    bind();
    updateTeach();
    renderList("#wp-list", "#wp-score", [], true);
    renderList("#bm-list", "#bm-score", [], false);
    renderGraph();
    loadHealth();
    await Promise.all([loadResults(), loadExamples()]);
    const initial = state.examples[0];
    if (initial && !state.route) pickExample(initial);
  }

  boot();
})();
