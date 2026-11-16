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
  const gist = (s) => {
    let t = String(s ?? "").trim();
    for (let i = 0; i < 3; i++) {
      t = t.replace(/^(also|and|additionally|furthermore|moreover|then|finally|please|hey|hi)[,!.]?\s+/i, "")
        .replace(/^(i'?m|i am|we'?re|we are)\s+(a|an|the)?\s*/i, "")
        .replace(/^(can|could|would|will)\s+(you|u)\s+(please\s+)?/i, "")
        .replace(/^(i|we)\s+(would like|want|need|wish)\s+(you\s+)?to\s+/i, "")
        .replace(/^(help me|help us)\s+(to\s+)?/i, "")
        .replace(/^(provide|give|get|fetch|find|show|tell|send)\s+(me|us)\s+(with\s+)?/i, "$1 ");
    }
    return t.charAt(0).toUpperCase() + t.slice(1);
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
    const wp = frac(hd.waypoint ?? last.waypoint);
    const bm = frac(hd.baseline ?? last.bm25);
    const fm = frac(hd.flat_memory ?? last.flat_memory);
    const kn = frac(hd.flat_knn ?? last.flat_knn);

    $("#dataset").textContent = isNum(r.test_tasks) ? fmt(r.test_tasks) + " held-out ToolBench tasks" : "";
    if (isNum(r.catalog_apis)) $("#h-cat").textContent = fmt(r.catalog_apis);
    $("#h-k").textContent = String(k);

    const catTok = hd.tokens_catalog;
    const wpTok = hd.tokens_per_task_waypoint;
    const funnel = $("#funnel");
    if (isNum(catTok) && isNum(wpTok) && wpTok > 0) {
      const share = Math.max(0.35, (wpTok / catTok) * 100);
      funnel.replaceChildren(
        el("div", { class: "f-row cat" },
          el("span", { class: "f-l" }, el("b", { text: fmt(catTok) }), " tool-schema tokens", isNum(r.catalog_apis) ? " · all " + fmt(r.catalog_apis) + " tools" : " · the whole catalog"),
          el("span", { class: "f-bar" }, el("span", { class: "f-fill", style: "width:100%" }))),
        el("div", { class: "f-row wp" },
          el("span", { class: "f-l" }, el("b", { text: fmt(wpTok) }), " tokens · Waypoint's " + k + " tools per task"),
          el("span", { class: "f-bar" }, el("span", { class: "f-fill", style: "width:" + share.toFixed(2) + "%" })),
          el("span", { class: "f-x", text: Math.round(catTok / wpTok) + "× fewer" })));
    } else {
      funnel.replaceChildren();
    }

    const rows = [
      ["wp", "Waypoint", "experience graph in HydraDB", wp],
      ["kn", "Flat k-NN", "plain store, same budget", kn],
      ["fm", "Flat memory", "copy the nearest past run", fm],
      ["bm", "BM25 tool search", "stateless, today's default", bm],
    ].filter((x) => x[3] != null);
    $("#hero").replaceChildren(...rows.map(([cls, name, sub, v]) => el("div", { class: "rk " + cls },
      el("span", { class: "rk-n" }, el("b", { text: name }), el("small", { text: sub })),
      el("span", { class: "rk-t" }, el("span", { class: "rk-f", style: "width:" + (v * 100).toFixed(1) + "%" })),
      el("span", { class: "rk-v", text: pct(v) }))));

    const nov = r.slices && r.slices.novel_toolset;
    const foot = [];
    if (wp != null && bm != null && bm > 0) foot.push(el("span", { class: "bf ok" }, el("b", { text: (wp / bm).toFixed(1) + "×" }), " stateless search"));
    if (nov && frac(nov.waypoint) != null && frac(nov.flat_knn) != null) {
      foot.push(el("span", { class: "bf", title: "Test tasks whose tool combination never appeared in training" + (isNum(nov.n) ? " (n = " + fmt(nov.n) + ")" : "") },
        "Never-seen tool combinations: ", el("b", { class: "wpc", text: pct(nov.waypoint) }), " vs ", el("b", { text: pct(nov.flat_knn) }), " plain store"));
    }
    if (isNum(hd.recall5_waypoint) && isNum(hd.recall5_baseline)) foot.push(el("span", { class: "bf" }, "Recall@" + k + " ", el("b", { text: pct(hd.recall5_baseline) }), " → ", el("b", { class: "wpc", text: pct(hd.recall5_waypoint) })));
    $("#board-foot").replaceChildren(...foot);

    const slices = r.slices && typeof r.slices === "object" ? Object.entries(r.slices).filter(([, s]) => s && typeof s === "object") : [];
    const sliceName = { seen_toolset: "Tool sets seen in training", novel_toolset: "Never-seen tool sets" };
    $("#slices").replaceChildren(...slices.map(([key, s]) => {
      const name = sliceName[key] || key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
      const bar = (cls, label, v) => frac(v) == null ? null : el("div", { class: "bar " + cls },
        el("span", { class: "bl", text: label }),
        el("span", { class: "tr" }, el("span", { class: "fl", style: "display:block;width:" + (frac(v) * 100).toFixed(1) + "%" })),
        el("span", { class: "bv", text: pct(v) }));
      return el("div", { class: "slice" },
        el("div", { class: "sh" }, el("b", { text: name }), isNum(s.n) && el("span", { text: "n = " + fmt(s.n) })),
        bar("wp", "Waypoint", s.waypoint), bar("kn", "Flat k-NN", s.flat_knn), bar("fm", "Flat memory", s.flat_memory), bar("bm", "BM25", s.bm25));
    }));
    $("#slices").hidden = !slices.length;

    const gen = r.generated_at ? new Date(r.generated_at) : null;
    $("#results-foot").textContent = "From the committed eval run" + (r.dataset ? " · " + r.dataset : "") + (gen && !isNaN(gen) ? " · generated " + gen.toISOString().replace("T", " ").slice(0, 16) + " UTC" : "") + (MOCK ? " · MOCK DATA" : "");
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
      { key: "flat_knn", cls: "kn" },
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
        row("Waypoint   ", best.waypoint), row("Flat k-NN  ", best.flat_knn), row("Flat memory", best.flat_memory), row("BM25       ", best.bm25));
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

  function pickExample(ex, quiet) {
    if (state.busy) return;
    state.example = ex;
    $("#task").value = ex.text;
    renderExamples();
    if (!quiet) reveal();
    route(ex.text);
  }

  function reveal() {
    const w = $("#work");
    const top = w.getBoundingClientRect().top;
    if (Math.abs(top - 56) < 8) return;
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: window.scrollY + top - 56, behavior: smooth ? "smooth" : "auto" });
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
    renderParts();
    renderGraph();
    renderTokens();
    updateTeach();
  }

  function renderParts() {
    const host = $("#parts");
    const parts = state.route && Array.isArray(state.route.parts) ? state.route.parts.filter((p) => typeof p === "string" && p.trim()) : [];
    host.hidden = parts.length < 2;
    host.replaceChildren(...(parts.length < 2 ? [] : [
      el("span", { class: "parts-l", text: "split into" }),
      ...parts.map((p, i) => {
        const pill = el("span", { class: "part", title: p, "data-part": i }, el("b", { text: String(i + 1) }), p);
        pill.addEventListener("mouseenter", () => focusGraph({ part: i }));
        pill.addEventListener("mouseleave", () => focusGraph(null));
        return pill;
      }),
    ]));
  }

  const VOTE_KINDS = ["task", "clause", "text"];

  function voteOf(t) {
    const v = t.vote && typeof t.vote === "object" ? t.vote : null;
    const out = { text: 0, task: 0, clause: 0, rf: v && isNum(v.rejected_factor) ? v.rejected_factor : 1 };
    if (v && VOTE_KINDS.some((k) => isNum(v[k]))) {
      for (const k of VOTE_KINDS) out[k] = isNum(v[k]) ? Math.max(0, v[k]) : 0;
      return out;
    }
    for (const p of Array.isArray(t.paths) ? t.paths : []) {
      if (!p || !VOTE_KINDS.includes(p.via)) continue;
      const c = isNum(p.c) ? p.c : isNum(p.w) ? p.w : 0;
      out[p.via] += Math.max(0, c);
    }
    return out;
  }

  function voteLabel(t) {
    const paths = Array.isArray(t.paths) ? t.paths.filter(Boolean) : [];
    const tasks = new Set(paths.filter((p) => p.via === "task").map((p) => p.task)).size;
    const clauses = new Set(paths.filter((p) => p.via === "clause").map((p) => p.clause)).size;
    const text = paths.some((p) => p.via === "text" && (isNum(p.c) ? p.c : p.w) > 0);
    const bits = [];
    if (tasks) bits.push(el("span", { class: "v-task", text: tasks + " task" + (tasks === 1 ? "" : "s") }));
    if (clauses) bits.push(el("span", { class: "v-clause", text: clauses + " clause" + (clauses === 1 ? "" : "s") }));
    if (text) bits.push(el("span", { class: "v-text", text: "text" }));
    return bits.flatMap((b, i) => (i ? [" + ", b] : [b]));
  }

  function voteBar(t, maxTotal) {
    const v = voteOf(t);
    const pctOf = (x) => (maxTotal > 0 ? ((x / maxTotal) * 100).toFixed(1) + "%" : "0%");
    const title = "past tasks " + v.task.toFixed(2) + " + clauses " + v.clause.toFixed(2) + " + text " + v.text.toFixed(2)
      + (v.rf < 1 ? " × rejected " + v.rf.toFixed(2) : "") + (isNum(t.score) ? " = " + t.score.toFixed(2) : "");
    return el("span", { class: "vote", title, "aria-label": title },
      ...VOTE_KINDS.filter((k) => v[k] > 0).map((k) => el("span", { class: "vs v-" + k, style: "width:" + pctOf(v[k]) })));
  }

  function renderList(listSel, scoreSel, tools, isWp) {
    const host = $(listSel);
    host.replaceChildren();
    tools = Array.isArray(tools) ? tools.filter((t) => t && t.idx != null) : [];
    const gold = goldSet();
    const prevTools = state.prev ? (isWp ? state.prev.tools : state.prev.baseline) || [] : null;
    const prevRanks = prevTools ? new Map(prevTools.map((t, i) => [t.idx, i])) : null;
    if (!tools.length) host.append(el("li", { class: "empty", text: state.route ? "No tools returned." : "Pick an example or type a task." }));

    const maxTotal = isWp ? Math.max(0, ...tools.map((t) => { const v = voteOf(t); return v.text + v.task + v.clause; })) : 0;
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
      const via = isWp ? voteLabel(t) : [];
      const sub = [t.tool, t.category].filter(Boolean).join(" · ");
      const li = el("li", { class: ["tool", needed && "needed", change && "chg-" + change[0]].filter(Boolean).join(" "), "data-idx": t.idx },
        cb,
        el("span", { class: "rank", text: String(i + 1) }),
        el("div", { class: "tbody" },
          el("div", { class: "tname", title: t.name || "", text: t.name || "API " + t.idx }),
          el("div", { class: "tsub", title: sub }, sub, via.length > 0 && (sub ? " · " : ""), via.length > 0 && el("span", { class: "via" }, via))),
        el("div", { class: "tmeta" },
          change && el("span", { class: "chg " + change[0], text: change[1] }),
          isWp && maxTotal > 0 && voteBar(t, maxTotal),
          isWp && isNum(t.score) && el("span", { class: "tscore", text: t.score.toFixed(2) }),
          needed && el("span", { class: "gold", title: "Ground truth: this task needed this tool", text: "✓" })));
      li.addEventListener("mouseenter", () => focusGraph("a" + t.idx));
      li.addEventListener("mouseleave", () => focusGraph(null));
      host.append(li);
    });


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
    if (entered) parts.push(entered + " tool" + (entered === 1 ? "" : "s") + " entered the top " + K + " (" + b.filter((i) => !a.includes(i)).map((i) => (before.tools.find((t) => t.idx === i) || {}).name || "API " + i).join(", ") + " dropped)");
    if (up) parts.push(up + " moved up");
    parts.push(taughtIn + "/" + used.length + " taught tools load");
    return "Re-routed: " + parts.join(", ") + ".";
  }

  /* ---------- frame 3: graph + tokens ---------- */

  let gIndex = null;

  const partOfClause = (r, id) => {
    const c = (r.clauses || []).find((x) => x && String(x.id) === String(id));
    return c && isNum(c.part) ? c.part : null;
  };

  function renderGraph() {
    const host = $("#graph");
    host.replaceChildren();
    host.classList.remove("focus");
    gIndex = null;
    const r = state.route || {};
    const g = r.graph || {};
    const nodes = Array.isArray(g.nodes) ? g.nodes.filter((n) => n && n.id != null) : [];
    const edges = Array.isArray(g.edges) ? g.edges.filter((e) => e && e.source != null && e.target != null) : [];
    if (!nodes.length) {
      host.append(el("div", { class: "empty" },
        el("b", { text: state.route ? "No graph returned for this route." : "Nothing routed yet." }),
        el("span", { text: state.route ? "" : " Pick a held-out task or type one: the subgraph Waypoint walks in HydraDB appears here." })));
      return;
    }
    const W = Math.max(560, host.clientWidth);
    const H = Math.max(360, host.clientHeight);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const parts = Array.isArray(r.parts) ? r.parts.filter((p) => typeof p === "string" && p.trim()) : [];
    const multi = parts.length > 1;
    const clauseInfo = new Map((r.clauses || []).filter(Boolean).map((c) => [String(c.id), c]));
    const taskInfo = new Map((r.similar_tasks || []).filter(Boolean).map((t) => [String(t.id), t]));
    const partOf = (n) => {
      if (isNum(n.part)) return n.part;
      const c = clauseInfo.get(String(n.id).replace(/^c/, ""));
      return c && isNum(c.part) ? c.part : 0;
    };
    const w0 = new Map();
    for (const e of edges) if (e.source === "q" && isNum(e.w)) w0.set(e.target, e.w);

    const TASKS = 4;
    const PER_PART = 3;
    const tasksAll = nodes.filter((n) => n.kind === "task").sort((a, b) => (w0.get(b.id) ?? 0) - (w0.get(a.id) ?? 0));
    const groups = [{ id: "w", label: multi ? "Whole task" : "Your task", sub: "similar past runs", kind: "task", items: tasksAll.slice(0, TASKS), more: Math.max(0, tasksAll.length - TASKS) }];
    const clausesAll = nodes.filter((n) => n.kind === "clause");
    const nGroups = multi ? parts.length : 1;
    for (let i = 0; i < nGroups; i++) {
      const cs = clausesAll.filter((n) => (multi ? partOf(n) === i : true)).sort((a, b) => (w0.get(b.id) ?? 0) - (w0.get(a.id) ?? 0));
      if (!cs.length && multi) {
        groups.push({ id: "p" + i, label: "Part " + (i + 1), text: parts[i], kind: "clause", items: [], more: 0, part: i });
        continue;
      }
      if (!cs.length) continue;
      groups.push({ id: "p" + i, label: multi ? "Part " + (i + 1) : "Sub-requests", text: multi ? parts[i] : "", kind: "clause", items: cs.slice(0, PER_PART), more: Math.max(0, cs.length - PER_PART), part: multi ? i : null });
    }
    const shown = new Set(groups.flatMap((gr) => gr.items.map((n) => n.id)));

    const rankWp = new Map((r.tools || []).map((t, i) => [t.idx, i]));
    const rankBm = new Map((r.baseline || []).map((t, i) => [t.idx, i]));
    const apis = nodes.filter((n) => n.kind === "api");
    const loaded = apis.filter((n) => rankWp.has(apiIdx(n)) && rankWp.get(apiIdx(n)) < K).sort((a, b) => rankWp.get(apiIdx(a)) - rankWp.get(apiIdx(b)));
    const support = (n) => edges.filter((e) => e.target === n.id && shown.has(e.source)).reduce((s, e) => s + (isNum(e.w) ? e.w : 0), 0);
    const others = apis.filter((n) => !loaded.includes(n)).sort((a, b) => support(b) - support(a)).slice(0, 4);
    const apiCol = [...loaded, ...others];

    const pad = { t: 30, b: 10 };
    const rowsEv = groups.reduce((s, gr) => s + Math.max(1, gr.items.length) + (gr.more ? 0.6 : 0), 0);
    const gapG = 14;
    const rowH = Math.max(22, Math.min(34, (H - pad.t - pad.b - gapG * (groups.length - 1)) / rowsEv));
    const cardH = Math.min(26, rowH - 4);
    const colX = { q: 0, p0: 76, p1: Math.round(W * 0.31), e0: Math.round(W * 0.365), e1: Math.round(W * 0.665), a0: Math.round(W * 0.735) };
    colX.a1 = W - 2;
    const pos = new Map();
    let y = pad.t;
    for (const gr of groups) {
      const n = Math.max(1, gr.items.length);
      const top = y;
      gr.items.forEach((it, i) => pos.set(it.id, { y: top + rowH * i + rowH / 2 }));
      gr.y = top + (rowH * n) / 2;
      gr.moreY = top + rowH * n + 6;
      y = top + rowH * n + (gr.more ? rowH * 0.6 : 0) + gapG;
    }
    const used = y - gapG;
    const shift = Math.max(0, (H - pad.b - used) / 2 - 4);
    for (const p of pos.values()) p.y += shift;
    for (const gr of groups) { gr.y += shift; gr.moreY += shift; }
    const apiRow = Math.min(rowH * 1.25, 40);
    const apiGap = others.length ? apiRow * 0.9 : 0;
    const apiTop = pad.t + Math.max(0, (H - pad.t - pad.b - apiRow * apiCol.length - apiGap) / 2);
    apiCol.forEach((n, i) => pos.set(n.id, { y: apiTop + apiRow * i + apiRow / 2 + (i >= loaded.length ? apiGap : 0) }));
    const qY = pad.t + (H - pad.t - pad.b) / 2;

    const prevG = state.prev && state.prev.graph;
    const prevNodes = prevG && Array.isArray(prevG.nodes) ? new Set(prevG.nodes.map((n) => n.id)) : null;
    const prevEdges = prevG && Array.isArray(prevG.edges) ? new Set(prevG.edges.map((e) => e.source + ">" + e.target)) : null;
    const gold = goldSet();

    const root = svg("svg", { width: W, height: H, viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Subgraph the route walked: your task, its sub-requests, matching past Tasks and Clauses, and the tools they point to" });
    const head = (x, text, anchor) => root.append(svg("text", { x, y: 12, "text-anchor": anchor || "start", class: "colh", text }));
    head(colX.p0, multi ? "SUB-REQUESTS" : "TASK");
    head(colX.e0, "MATCHED IN HYDRADB");
    head(colX.a0, "TOOLS · TOP " + K + " LOADED");

    const edgeLayer = svg("g", {});
    const nodeLayer = svg("g", {});
    root.append(edgeLayer, nodeLayer);
    const maxW = {};
    for (const e of edges) { const t = String(e.type).toLowerCase(); maxW[t] = Math.max(maxW[t] || 0, isNum(e.w) ? Math.abs(e.w) : 0); }
    const link = (s, t, x1, y1, x2, y2, cls, sw, title) => {
      const mx = (x1 + x2) / 2;
      edgeLayer.append(svg("path", { d: "M" + x1 + "," + y1 + " C" + mx + "," + y1 + " " + mx + "," + y2 + " " + x2 + "," + y2, class: "edge " + cls, "stroke-width": sw.toFixed(2), "data-s": s, "data-t": t }, title ? svg("title", { text: title }) : null));
    };

    const grpOf = new Map();
    for (const gr of groups) for (const it of gr.items) grpOf.set(it.id, gr.id);
    for (const gr of groups) link("q", gr.id, colX.q + 64, qY, colX.p0, gr.y, "struct", 1.4);
    for (const gr of groups) for (const it of gr.items) {
      const w = w0.get(it.id) ?? 0;
      const ty = it.kind === "task" ? "similar" : "match";
      const isNew = prevEdges && !prevEdges.has("q>" + it.id);
      link(gr.id, it.id, colX.p1, gr.y, colX.e0, pos.get(it.id).y, ty + (isNew ? " new" : ""), 1 + 5 * (maxW[ty] ? w / maxW[ty] : 0.3), (ty === "similar" ? "SIMILAR" : "MATCH") + " · " + w.toFixed(2));
    }
    for (const e of edges) {
      const ty = String(e.type).toLowerCase();
      if (ty !== "used" && ty !== "needs") continue;
      if (!shown.has(e.source) || !pos.has(e.target)) continue;
      const t = byId.get(e.target);
      const sel = rankWp.has(apiIdx(t)) && rankWp.get(apiIdx(t)) < K;
      const isNew = prevEdges && !prevEdges.has(e.source + ">" + e.target);
      const w = isNum(e.w) ? Math.abs(e.w) : 0;
      link(e.source, e.target, colX.e1, pos.get(e.source).y, colX.a0, pos.get(e.target).y, ty + (sel ? " sel" : "") + (isNew ? " new" : ""), 1 + 3.5 * (maxW[ty] ? w / maxW[ty] : 0.3), e.type + (isNum(e.w) ? " · w " + e.w.toFixed(2) : ""));
    }

    const card = (id, x1, x2, cy, cls, kids, tipFn) => {
      const gEl = svg("g", { class: "node " + cls, "data-id": id, tabindex: "0" });
      gEl.append(svg("rect", { x: x1, y: cy - cardH / 2, width: x2 - x1, height: cardH, rx: 6, class: "card" }));
      for (const k of kids) gEl.append(k);
      if (tipFn) {
        const on = (ev) => { focusGraph(id); showTip(ev, ...tipFn()); };
        gEl.addEventListener("mouseenter", on);
        gEl.addEventListener("mousemove", (ev) => moveTip(ev));
        gEl.addEventListener("mouseleave", () => { focusGraph(null); hideTip(); });
        gEl.addEventListener("focus", () => { focusGraph(id); const b = gEl.getBoundingClientRect(); showTip({ clientX: b.right, clientY: b.top }, ...tipFn()); });
        gEl.addEventListener("blur", () => { focusGraph(null); hideTip(); });
      }
      nodeLayer.append(gEl);
      return gEl;
    };
    const chars = (px) => Math.max(6, Math.floor(px / 6.4));

    const qg = svg("g", { class: "node query", "data-id": "q" });
    qg.append(svg("rect", { x: colX.q, y: qY - 14, width: 64, height: 28, rx: 14, class: "q" }));
    qg.append(svg("text", { x: colX.q + 32, y: qY + 4, "text-anchor": "middle", class: "qt", text: "your task" }));
    qg.addEventListener("mouseenter", (ev) => showTip(ev, el("div", { class: "th", text: "Your task" }), el("div", { class: "tt", text: trunc(state.routedTask, 320) })));
    qg.addEventListener("mouseleave", hideTip);
    nodeLayer.append(qg);

    for (const gr of groups) {
      const isPart = gr.part != null;
      const label = isPart ? trunc(gist(gr.text), chars(colX.p1 - colX.p0 - 30)) : gr.label;
      card(gr.id, colX.p0, colX.p1, gr.y, "grp " + (isPart ? "part" : "whole"), [
        isPart ? svg("text", { x: colX.p0 + 8, y: gr.y + 4, class: "pn", text: String(gr.part + 1) }) : svg("circle", { cx: colX.p0 + 11, cy: gr.y, r: 4, class: "t" }),
        svg("text", { x: colX.p0 + 22, y: gr.y + 4, class: "lbl", text: isPart ? label : gr.label }),
      ], () => isPart
        ? [el("div", { class: "th", text: "Part " + (gr.part + 1) + " of your task" }), el("div", { class: "tt", text: "“" + trunc(gr.text, 300) + "”" }), el("div", { class: "ts", text: "matched against past Clauses → NEEDS edges" })]
        : [el("div", { class: "th", text: "Your whole task" }), el("div", { class: "ts", text: "matched against past Tasks → USED edges" })]);
      if (gr.more) nodeLayer.append(svg("text", { x: colX.e0 + 6, y: gr.moreY + 4, class: "more", text: "+" + gr.more + " more " + (gr.kind === "task" ? "past tasks" : "clauses") + " also vote" }));
      if (!gr.items.length) nodeLayer.append(svg("text", { x: colX.e0 + 6, y: gr.y + 4, class: "more", text: "no matching clause" }));
    }

    for (const gr of groups) for (const it of gr.items) {
      const p = pos.get(it.id);
      const w = w0.get(it.id);
      const isNew = prevNodes && !prevNodes.has(it.id);
      if (it.kind === "task") {
        const id = taskId(it);
        const t = taskInfo.get(String(id)) || {};
        card(it.id, colX.e0, colX.e1, p.y, "ev task" + (isNew ? " new" : ""), [
          svg("circle", { cx: colX.e0 + 11, cy: p.y, r: 4, class: "t" }),
          svg("text", { x: colX.e0 + 22, y: p.y + 4, class: "lbl", text: trunc(gist(t.text || it.text || "Task " + id), chars(colX.e1 - colX.e0 - 64)) }),
          isNum(w) ? svg("text", { x: colX.e1 - 8, y: p.y + 4, "text-anchor": "end", class: "wv", text: w.toFixed(2) }) : null,
        ].filter(Boolean), () => nodeTip(it, ctx));
      } else {
        const cl = clauseInfo.get(String(it.id).replace(/^c/, "")) || {};
        card(it.id, colX.e0, colX.e1, p.y, "ev clause" + (isNew ? " new" : ""), [
          svg("rect", { x: colX.e0 + 7.5, y: p.y - 3.5, width: 7, height: 7, rx: 1, transform: "rotate(45 " + (colX.e0 + 11) + " " + p.y + ")", class: "c" }),
          svg("text", { x: colX.e0 + 22, y: p.y + 4, class: "lbl", text: "“" + trunc(gist(cl.text || it.text || "Clause"), chars(colX.e1 - colX.e0 - 70)) + "”" }),
          isNum(w) ? svg("text", { x: colX.e1 - 8, y: p.y + 4, "text-anchor": "end", class: "wv", text: w.toFixed(2) }) : null,
        ].filter(Boolean), () => nodeTip(it, ctx));
      }
    }

    const apiInfo = new Map();
    for (const t of [...(r.baseline || []), ...(r.tools || [])]) if (t) apiInfo.set(t.idx, t);
    const apiName = (i) => (apiInfo.get(i) && apiInfo.get(i).name) || (byId.get("a" + i) && byId.get("a" + i).label) || "API " + i;
    const ctx = { tasks: taskInfo, clauses: clauseInfo, clausePart: new Map(clausesAll.map((n) => [n.id, partOf(n)])), apiInfo, apiName, rankWp, rankBm, gold, simW: w0 };
    const apiCardH = Math.min(30, apiRow - 6);
    for (const n of apiCol) {
      const idx = apiIdx(n);
      const p = pos.get(n.id);
      const rk = rankWp.get(idx);
      const sel = rk != null && rk < K;
      const needed = gold && gold.has(idx);
      const isNew = prevNodes && !prevNodes.has(n.id);
      const gEl = card(n.id, colX.a0, colX.a1, p.y, "api" + (sel ? " sel" : "") + (needed ? " needed" : "") + (isNew ? " new" : ""), [
        svg("text", { x: colX.a0 + 10, y: p.y + 4, class: "rk", text: sel ? String(rk + 1) : "–" }),
        svg("text", { x: colX.a0 + 26, y: p.y + 4, class: "lbl", text: trunc(apiName(idx), chars(colX.a1 - colX.a0 - 60)) }),
        needed ? svg("text", { x: colX.a1 - 10, y: p.y + 4, "text-anchor": "end", class: "ck", text: "✓" }) : null,
      ].filter(Boolean), () => nodeTip(n, ctx));
      const rect = gEl.querySelector("rect");
      rect.setAttribute("y", p.y - apiCardH / 2);
      rect.setAttribute("height", apiCardH);
    }
    if (others.length) nodeLayer.append(svg("text", { x: colX.a0 + 2, y: pos.get(others[0].id).y - apiRow / 2 - 4, class: "more", text: "reached, not loaded" }));
    host.append(root);

    const colOf = { q: 0 };
    for (const gr of groups) colOf[gr.id] = 0.5;
    for (const n of nodes) if (n.kind !== "query") colOf[n.id] = n.kind === "api" ? 2 : 1;
    const partNodes = {};
    for (const gr of groups) if (gr.part != null) partNodes[gr.part] = [gr.id];
    gIndex = { colOf, partNodes };
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
    if (n.kind === "clause") {
      const cl = ctx.clauses.get(String(n.id).replace(/^c/, "")) || {};
      const part = ctx.clausePart.get(n.id);
      const parts = (state.route && state.route.parts) || [];
      const w = isNum(cl.w) ? cl.w : ctx.simW.get(n.id);
      const needs = Array.isArray(cl.tools) ? cl.tools.map(ctx.apiName) : [];
      return [
        el("div", { class: "th", text: cl.task != null ? "Clause of Task " + cl.task : n.label || "Clause" }),
        el("div", { class: "ts", text: "MATCH" + (isNum(w) ? " · w " + w.toFixed(2) : "") + (isNum(part) ? " · part " + (part + 1) + " of your task" : "") }),
        (cl.text || n.text) && el("div", { class: "tt", text: "“" + trunc(cl.text || n.text, 300) + "”" }),
        isNum(part) && parts[part] && el("div", { class: "ts", text: "matched: “" + trunc(parts[part], 120) + "”" }),
        needs.length && el("div", { class: "ts", text: "NEEDS → " + needs.join(", ") }),
      ];
    }
    const idx = apiIdx(n);
    const a = ctx.apiInfo.get(idx) || {};
    const rw = ctx.rankWp.get(idx);
    const rb = ctx.rankBm.get(idx);
    const v = rw != null ? voteOf(a) : null;
    return [
      el("div", { class: "th", text: a.name || n.label || "API " + idx }),
      el("div", { class: "ts", text: [a.tool || n.tool, a.category || n.category].filter(Boolean).join(" · ") }),
      el("div", { class: "tt", text: (rw != null ? "Waypoint #" + (rw + 1) : "Not loaded by Waypoint") + " · " + (rb != null ? "BM25 #" + (rb + 1) : "not in BM25 top " + K) + (isNum(a.score) ? " · score " + a.score.toFixed(2) : "") }),
      v && el("div", { class: "ts", text: "votes: tasks " + v.task.toFixed(2) + " · clauses " + v.clause.toFixed(2) + " · text " + v.text.toFixed(2) + (v.rf < 1 ? " · ×" + v.rf.toFixed(2) + " rejected" : "") }),
      ctx.gold && ctx.gold.has(idx) && el("div", { class: "tt", style: "color: var(--ok)", text: "✓ This task truly needed this tool" }),
    ];
  }

  function focusGraph(target) {
    const host = $("#graph");
    host.querySelectorAll(".hl").forEach((x) => x.classList.remove("hl"));
    document.querySelectorAll(".tool.hl, .part.hl").forEach((x) => x.classList.remove("hl"));
    const gi = gIndex;
    const seeds = target == null || !gi ? [] : typeof target === "object" ? gi.partNodes[target.part] || [] : [target];
    const live = seeds.filter((id) => id in gi.colOf);
    if (!live.length) {
      host.classList.remove("focus");
      return;
    }
    const edges = [...host.querySelectorAll(".edge")];
    const keepE = new Set();
    const keepN = new Set(live);
    const walk = (from, to) => {
      const queue = [...live];
      const seen = new Set(live);
      while (queue.length) {
        const id = queue.shift();
        for (const e of edges) {
          if (e.dataset[from] !== id) continue;
          keepE.add(e);
          const other = e.dataset[to];
          keepN.add(other);
          if (!seen.has(other)) { seen.add(other); queue.push(other); }
        }
      }
    };
    walk("t", "s");
    if (!live.some((id) => gi.colOf[id] === 0)) walk("s", "t");
    host.classList.add("focus");
    keepE.forEach((e) => e.classList.add("hl"));
    host.querySelectorAll(".node").forEach((n) => keepN.has(n.dataset.id) && n.classList.add("hl"));
    for (const id of keepN) {
      if (gi.colOf[id] === 2) document.querySelectorAll('.tool[data-idx="' + String(id).slice(1) + '"]').forEach((x) => x.classList.add("hl"));
    }
    if (typeof target === "object") document.querySelectorAll('.part[data-part="' + target.part + '"]').forEach((x) => x.classList.add("hl"));
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
    const ncl = Array.isArray(r.clauses) ? r.clauses.length : 0;
    host.replaceChildren(
      el("div", { class: "tok-head" },
        el("span", { class: "tok-big" }, fmt(loaded), el("small", { text: "tool-schema tokens in context" })),
        isNum(loaded) && isNum(cat) && loaded > 0 && el("span", { class: "tok-ratio", text: Math.round(cat / loaded) + "× fewer than the whole catalog" }),
        el("span", { class: "tok-note", text: (sim || ncl ? [sim && sim + " past tasks", ncl && ncl + " clauses"].filter(Boolean).join(" + ") + " traversed · " : "") + (isNum(loaded) && isNum(cat) && cat > 0 ? ((loaded / cat) * 100).toFixed(2) + "% of " + fmt(cat) : "") })),
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

  const MOCK_CLAUSES = [
    [35401, 3540, "Check the forecast so rain doesn't ruin it.", [6]],
    [11871, 1187, "Pull a few cocktail recipes with the ingredients.", [0, 1]],
    [11872, 1187, "Queue up some songs to play.", [4]],
    [22901, 2290, "Find some songs we can play at the party.", [4, 5]],
    [88201, 8820, "How many euros will I get for my dollars?", [10]],
    [89071, 8907, "Book a flight out of SFO.", [9]],
    [44101, 4410, "Somewhere to stay near the beach.", [8]],
    [51201, 5120, "Translate the greeting into her language.", [16]],
    [51202, 5120, "Send it to her phone as a text.", [22]],
    [60311, 6031, "Build a leg day gym routine.", [23]],
    [60441, 6044, "Count the calories in a smoothie.", [3]],
    [70121, 7012, "Latest crypto headlines.", [13]],
    [93101, 9310, "What's showing at the cinema tonight?", [15]],
    [93102, 9310, "A good restaurant near my address.", [20, 19]],
    [14501, 1450, "Some jokes to break the ice.", [17]],
    [14502, 1450, "A snack recipe for the team.", [2]],
    [33051, 3305, "Check that the email addresses are real.", [21]],
  ];

  const mockMem = {
    past: MOCK_PAST.map(([id, text, tools]) => ({ id, text, tools, w: Object.fromEntries(tools.map((t, i) => [t, 1 + ((id + i) % 4)])) })),
    clauses: MOCK_CLAUSES.map(([id, task, text, tools]) => ({ id, task, text, tools })),
    learned: 19361,
    nextId: 99000001,
  };
  const STOP = new Set("a an the and or for to of in on with my me i im is it be some few this that from at by as are what how get find tell give show can you your need want will its her his their them each one now good if so".split(" "));
  const stem = (w) => (w.length > 4 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);
  const toks = (s) => (String(s).toLowerCase().replace(/'/g, "").match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1 && !STOP.has(w)).map(stem);
  const schemaTokens = (idx) => 120 + ((idx * 53) % 130);
  const splitParts = (s) => String(s).split(/(?<=[.?!])\s+|;\s*|,\s+and\s+/i).map((x) => x.trim()).filter((x) => toks(x).length);
  const cosine = (a, b) => {
    let inter = 0;
    for (const w of a) if (b.has(w)) inter += 1;
    return inter / Math.sqrt(Math.max(1, a.size) * Math.max(1, b.size));
  };
  const MOCK_REJECTED = { 17: 0.9 };

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
    const parts = splitParts(task);
    if (!parts.length) parts.push(task);
    const text = MOCK_APIS.map((a) => {
      const words = new Set(toks(a.name + " " + a.tool + " " + a.category + " " + a.kw));
      let s = 0;
      for (const w of words) if (q.has(w)) s += 1;
      return s;
    });
    const maxText = Math.max(1, ...text);
    const sims = mockMem.past.map((p) => ({ p, sim: cosine(q, new Set(toks(p.text))) }))
      .filter((s) => s.sim > 0.12).sort((a, b) => b.sim - a.sim).slice(0, 3);

    const best = new Map();
    parts.forEach((part, i) => {
      const pt = new Set(toks(part));
      mockMem.clauses.map((cl) => ({ cl, s: cosine(pt, new Set(toks(cl.text))), part: i }))
        .filter((m) => m.s >= 0.3).sort((a, b) => b.s - a.s).slice(0, 2)
        .forEach((m) => { if (!best.has(m.cl.id) || best.get(m.cl.id).s < m.s) best.set(m.cl.id, m); });
    });
    const matches = [...best.values()].sort((a, b) => a.part - b.part || b.s - a.s).slice(0, 6);

    const acc = MOCK_APIS.map((a) => {
      const t = +(0.5 * (text[a.idx] / maxText)).toFixed(3);
      return { idx: a.idx, vote: { text: t, task: 0, clause: 0 }, paths: t ? [{ via: "text", w: +(text[a.idx] / maxText).toFixed(2), c: t }] : [] };
    });
    for (const { p, sim } of sims) {
      for (const ti of p.tools) {
        const c = +(sim * Math.min(1, 0.55 + 0.15 * (p.w[ti] || 1))).toFixed(3);
        acc[ti].vote.task += c;
        acc[ti].paths.push({ via: "task", task: p.id, w: +sim.toFixed(2), c });
      }
    }
    for (const { cl, s, part } of matches) {
      for (const ti of cl.tools) {
        const c = +(0.9 * s).toFixed(3);
        acc[ti].vote.clause += c;
        acc[ti].paths.push({ via: "clause", clause: cl.id, part, w: +s.toFixed(2), c });
      }
    }
    for (const a of acc) {
      a.vote.rejected_factor = MOCK_REJECTED[a.idx] || 1;
      for (const key of ["text", "task", "clause"]) a.vote[key] = +a.vote[key].toFixed(3);
      a.score = (a.vote.text + a.vote.task + a.vote.clause) * a.vote.rejected_factor;
    }
    const base = (i) => ({ idx: i, name: MOCK_APIS[i].name, tool: MOCK_APIS[i].tool, category: MOCK_APIS[i].category });
    const tools = [...acc].sort((a, b) => b.score - a.score || a.idx - b.idx).slice(0, k)
      .map((x) => ({ ...base(x.idx), score: +x.score.toFixed(2), paths: x.paths, vote: x.vote }));
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
    for (const { cl, s } of matches) {
      nodes.push({ id: "c" + cl.id, label: "Clause of Task " + cl.task, kind: "clause", text: cl.text });
      edges.push({ source: "q", target: "c" + cl.id, type: "MATCH", w: +s.toFixed(2) });
      for (const ti of cl.tools) {
        apiIds.add(ti);
        edges.push({ source: "c" + cl.id, target: "a" + ti, type: "NEEDS", w: 1 });
      }
    }
    for (const i of apiIds) nodes.push({ id: "a" + i, label: MOCK_APIS[i].name, kind: "api", selected: selected.has(i) });

    return {
      tools,
      baseline,
      parts,
      similar_tasks: sims.map(({ p, sim }) => ({ id: p.id, text: p.text, sim: +sim.toFixed(2), tools: p.tools })),
      clauses: matches.map(({ cl, s, part }) => ({ id: cl.id, task: cl.task, text: cl.text, part, w: +s.toFixed(2), tools: cl.tools })),
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
      const text = String(body.task || "");
      const used = (body.used || []).map(Number).filter((i) => MOCK_APIS[i]);
      let p = mockMem.past.find((x) => x.text === text);
      if (p) {
        for (const i of used) {
          if (!p.tools.includes(i)) p.tools.push(i);
          p.w[i] = (p.w[i] || 0) + 1;
        }
      } else {
        p = { id: mockMem.nextId++, text, tools: used, w: Object.fromEntries(used.map((i) => [i, 1])) };
        mockMem.past.push(p);
        mockMem.learned += 1;
        const parts = splitParts(text);
        parts.forEach((part, n) => {
          const pt = new Set(toks(part));
          const needs = parts.length === 1 ? used : used.filter((i) => toks(MOCK_APIS[i].name + " " + MOCK_APIS[i].kw).some((w) => pt.has(w)));
          if (needs.length) mockMem.clauses.push({ id: p.id * 10 + n + 1, task: p.id, text: part, tools: needs });
        });
      }
      return { task_id: p.id, edges_written: used.length, learned_tasks: mockMem.learned };
    }
    throw new Error("mock: no fixture for " + path);
  }

  /* ---------- boot ---------- */

  function bind() {
    $("#route-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      reveal();
      route($("#task").value);
    });
    $("#task").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        reveal();
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
    $(".cta").addEventListener("click", (ev) => {
      ev.preventDefault();
      reveal();
      const lead = state.examples.find((e) => String(e.id) === "2547") || state.examples[0];
      if (lead && !state.busy && state.example !== lead) pickExample(lead, true);
    });

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
    if (initial && !state.route) pickExample(initial, true);
  }

  boot();
})();
