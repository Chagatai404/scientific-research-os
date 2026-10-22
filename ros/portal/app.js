/* Research OS portal: one page, five views, one lesson player. Everything comes from the record through /api. */
"use strict";
(() => {
  const $main = document.getElementById("main");
  const $status = document.getElementById("status");
  const $pace = document.getElementById("pace");
  const state = { view: "", lesson: null, step: null, segment: 0, asking: false, result: null, mapScope: "" };

  // ---- data ----------------------------------------------------------------------------------------------------
  async function api(name, args = {}, write = false) {
    const opts = write
      ? { method: "POST", headers: { "Content-Type": "application/json", "X-ROS": "1" }, body: JSON.stringify(args) }
      : {};
    const q = write ? "" : "?" + new URLSearchParams(Object.entries(args).filter(([, v]) => v != null)
      .map(([k, v]) => [k, JSON.stringify(v)]));
    const r = await fetch(`/api/${name}${write ? "" : q}`, opts);
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || r.statusText);
    return body.result;
  }
  const say = (t) => { $status.textContent = t || ""; };

  // ---- text: a small Markdown subset with math -------------------------------------------------------------------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function tex(src, display) {
    try { return window.katex.renderToString(src, { displayMode: display, throwOnError: false }); }
    catch (e) { return `<code>${esc(src)}</code>`; }
  }
  function inline(s) {
    const parts = [];
    s = String(s ?? "").replace(/\\\$/g, "\u0000").replace(/\$\$([^$]+)\$\$|\$([^$\n]+)\$/g, (m, d, i) => {
      parts.push(d != null ? tex(d, true) : tex(i, false));
      return `\u0001${parts.length - 1}\u0001`;
    });
    s = esc(s).replace(/\u0000/g, "$")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" rel="noreferrer" target="_blank">$1</a>');
    return s.replace(/\u0001(\d+)\u0001/g, (m, n) => parts[+n]);
  }
  function md(src) {
    const out = [];
    let list = null, quote = [];
    const flushQuote = () => { if (quote.length) { out.push(`<blockquote>${md(quote.join("\n"))}</blockquote>`); quote = []; } };
    const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`); list = null; } };
    for (const block of String(src ?? "").split(/\n{2,}/)) {
      for (const line of block.split("\n")) {
        let m;
        if ((m = line.match(/^>\s?(.*)$/))) { flushList(); quote.push(m[1]); continue; }
        flushQuote();
        if ((m = line.match(/^(#{1,3})\s+(.*)$/))) { flushList(); out.push(`<h${m[1].length + 1}>${inline(m[2])}</h${m[1].length + 1}>`); }
        else if ((m = line.match(/^\s*(?:[-*]|(\d+)\.)\s+(.*)$/))) {
          const tag = m[1] ? "ol" : "ul";
          if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
          list.items.push(m[2]);
        } else if (/^---+$/.test(line)) { flushList(); out.push("<hr>"); }
        else if (line.trim()) { flushList(); out.push(`<p>${inline(line)}</p>`); }
      }
      flushQuote(); flushList();
    }
    return out.join("");
  }
  const h = (html) => { $main.innerHTML = html; };
  // A small, closed-by-default window: where this record stands, and how it joins the user-wide knowledge graph.
  const pairs = (o) => Object.entries(o || {}).map(([k, v]) => `${v} ${esc(k)}`).join(", ") || "none";
  const ctx = (c) => {
    if (!c) return "";
    const steps = Object.fromEntries(Object.entries((c.research || {}).next_steps || {}).map(([k, v]) => [k, v.length]));
    const body = c.role === "user"
      ? `<p>${c.knowledge.capabilities} capabilities (${pairs(c.knowledge.states)}).</p>${c.projects.length ? `<ul>${c.projects.map((p) => `<li>${esc(p.record)}: ${p.waiting_for_you} waiting for you; ${pairs(p.next_steps)}</li>`).join("")}</ul>` : `<p class="muted">No project record is linked yet.</p>`}`
      : c.role === "project"
        ? `<p>${esc(c.project)}: ${pairs(c.research.nodes)}. Next: ${pairs(steps)}.</p><p>What you know of what it needs: ${pairs(c.needs.summary)}.</p>`
        : `<p class="muted">${esc(c.note || "Not linked to a user-wide record.")}</p>`;
    return `<details class="card compact"><summary>Context · ${esc(c.role)}</summary>${body}</details>`;
  };
  const roadmapCard = (r) => !r || !r.steps.length ? "" : `<section class="card"><h2>Roadmap</h2>
    <p class="muted">${r.summary.steps} to learn, about ${Math.round(r.summary.effort_minutes / 60)} h${r.schedule.finish ? `; done by ${esc(r.schedule.finish)}` : ""}.</p>
    <ul>${r.steps.map((s) => `<li>${esc(s.title || s.capability)} <span class="muted">${esc(s.kind)}</span>: ${esc(s.reason)} ${s.available && r.role !== "project" ? `<button data-start-scope="${esc(s.start.scope)}">Start</button>` : ""}</li>`).join("")}</ul>
    ${r.role === "project" ? `<p class="muted">These capabilities live in your user-wide record: open that portal to study them.</p>` : ""}</section>`;

  // ---- views ---------------------------------------------------------------------------------------------------
  const views = {
    async today() {
      const t = await api("today");
      const context = await api("context").catch(() => null);
      const nl = t.next_lesson;
      let lesson = `<p class="muted">No prepared lesson yet. An agent prepares one with <code>bundle_create</code>.</p>`;
      if (nl && nl.ready) lesson = `<p>${esc(nl.title)} is ready.</p><button class="primary" data-start-bundle="${esc(nl.bundle)}">Start lesson</button>`;
      else if (nl) lesson = `<p>${esc(nl.title)} is being prepared. Still missing (${nl.missing_count}):</p><ul>${nl.missing.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>`;
      h(`<h1>Today</h1>
        <section class="card"><h2>Reviews</h2><p><span class="big">${t.due}</span> due</p>
          ${t.due ? `<button class="primary" data-review>Review now</button>` : `<p class="muted">Nothing is due.</p>`}</section>
        <section class="card"><h2>Next lesson</h2>${lesson}</section>
        <section class="card"><h2>Waiting for your tutor</h2>
          <p>${t.waiting_answers} written answer(s) and ${t.waiting_questions} question(s).
          ${t.waiting_answers + t.waiting_questions ? "Your tutor reads them when you next start a session with it." : ""}</p></section>
        ${t.frontier.length ? `<section class="card"><h2>Ready to learn</h2><ul>${t.frontier.map((c) => `<li><a href="#learn" data-scope="${esc(c)}">${esc(c.split(":")[1])}</a></li>`).join("")}</ul></section>` : ""}
        ${ctx(context)}`);
    },
    async learn() {
      if (state.lesson) return renderStep();
      const m = await api("map", state.mapScope ? { scope: state.mapScope } : {});
      const bs = await api("bundles");
      const rm = await api("roadmap", { limit: 5 }).catch(() => null);  // none when there is nothing to plan for yet
      h(`<h1>Learn</h1>${roadmapCard(rm)}
        <section class="card"><h2>Lessons</h2>${bs.length ? `<ul>${bs.map((b) => `<li>${esc(b.title)} — ${b.ready ? `<button class="primary" data-start-bundle="${esc(b.id)}">Start lesson</button>` : `<span class="muted">being prepared</span>`}</li>`).join("")}</ul>` : `<p class="muted">No prepared lessons yet.</p>`}</section>
        <section class="card map"><h2>Map${state.mapScope ? `: ${esc(state.mapScope)}` : ""}</h2>${drawMap(m)}
          <p class="legend"><span>unknown</span><span>learning</span><span>demonstrated</span><span>retained</span><span>fragile</span><span>stale</span></p>
          <div id="node-detail" aria-live="polite"></div></section>`);
    },
    async research() {
      const q = await api("queue");
      const claims = await api("claims").catch(() => []);
      const form = (x) => {
        if (x.kind === "approve" || x.kind === "approval-required") return `<form class="row" data-human="approve" data-subject="${esc(x.subject)}">
          <label>Your name<input type="text" name="by" required></label>
          <select name="decision" aria-label="Decision"><option value="approved">Approve</option><option value="changes-requested">Ask for changes</option><option value="rejected">Reject</option></select>
          <button type="submit" class="primary">Record</button></form>`;
        if (x.kind === "commitment" || x.kind === "defend") return "";
        const outcomes = x.subject.startsWith("claim:") ? ["accepted", "revise", "rejected", "retracted"] : ["accepted", "rejected"];
        return `<form data-human="decide" data-subject="${esc(x.subject)}">
          <label>Rationale<textarea name="rationale" required></textarea></label>
          <div class="row"><label>Your name<input type="text" name="by" required></label>
          <select name="outcome" aria-label="Outcome">${outcomes.map((o) => `<option>${o}</option>`).join("")}</select>
          <button type="submit" class="primary">Decide</button></div></form>`;
      };
      const label = { approve: "Approve the plan", decide: "Decide", defend: "Defend before deciding", commitment: "Open commitment",
        proposal: "Proposed change", "human-decision-required": "Decide", "approval-required": "Approve the plan" };
      h(`<h1>Research</h1>
        <section class="card"><h2>Decision queue</h2>${q.length ? q.map((x) => `<div class="card"><p><strong>${esc(label[x.kind] || x.kind)}</strong> · ${esc(x.subject)}</p><p>${inline(x.text || "")}</p>
          ${x.kind === "defend" ? `<button class="primary" data-start-scope="${esc(x.subject)}">Practise the defence</button>` : form(x)}</div>`).join("") : `<p class="muted">Nothing is waiting for you.</p>`}</section>
        <section class="card"><h2>Claims</h2>${claims.length ? `<div class="table-wrap"><table><thead><tr><th>Claim</th><th>Verdict</th><th>Ownership</th></tr></thead><tbody>${claims.map((c) => `<tr><td>${inline(c.text || c.id)}</td><td>${esc(c.verdict)}${c.missing.length ? ` <span class="muted">(missing ${esc(c.missing.join(", "))})</span>` : ""}</td><td>${esc(c.ownership)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No claims recorded.</p>`}</section>`);
    },
    async library() {
      const rows = await api("library");
      h(`<h1>Library</h1>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Lesson</th><th>Started</th><th>Log</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.title || r.id)}${r.legacy ? ' <span class="muted">(imported)</span>' : ""}</td><td>${esc((r.started || "").slice(0, 10))}</td><td>${r.log ? `<a href="#log" data-log="${esc(r.id)}">Read</a>` : "—"}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No lessons yet.</p>`}<div id="log-view"></div>`);
    },
    async history() {
      const rows = await api("history");
      h(`<h1>History</h1>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>When</th><th>Question</th><th>Answer</th><th>Grade</th></tr></thead><tbody>${rows.slice().reverse().map((r) => `<tr><td>${esc(r.ts.slice(0, 16).replace("T", " "))}</td><td>${inline(r.prompt || "")}</td><td>${inline(r.response == null ? "I don't know" : typeof r.response === "string" ? r.response : JSON.stringify(r.response))}</td><td>${esc(r.grade || "waiting")}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No answers yet.</p>`}`);
    },
    async log() { return views.library(); },
  };

  // ---- the map ---------------------------------------------------------------------------------------------------
  function drawMap(m) {
    if (!m.nodes.length) return `<p class="muted">No capabilities in this record yet.</p>`;
    const req = {}; m.edges.forEach((e) => (req[e.src] = req[e.src] || []).push(e.dst));
    const depth = {};
    const d = (id, seen = new Set()) => {
      if (depth[id] != null) return depth[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      return (depth[id] = Math.max(0, ...(req[id] || []).map((p) => d(p, seen) + 1)));
    };
    m.nodes.forEach((n) => d(n.id));
    const cols = {}; m.nodes.forEach((n) => (cols[depth[n.id]] = cols[depth[n.id]] || []).push(n));
    const W = 180, H = 44, GX = 40, GY = 16, pos = {};
    Object.entries(cols).forEach(([c, ns]) => ns.forEach((n, i) => (pos[n.id] = { x: +c * (W + GX), y: i * (H + GY) })));
    const width = (Object.keys(cols).length) * (W + GX) - GX, height = Math.max(...Object.values(cols).map((ns) => ns.length)) * (H + GY) - GY;
    const lines = m.edges.map((e) => pos[e.src] && pos[e.dst] ? `<line x1="${pos[e.dst].x + W}" y1="${pos[e.dst].y + H / 2}" x2="${pos[e.src].x}" y2="${pos[e.src].y + H / 2}"/>` : "").join("");
    const boxes = m.nodes.map((n) => {
      const p = pos[n.id], label = (n.title || n.id).slice(0, 24);
      return `<g class="n st-${esc(n.state)}" tabindex="0" role="button" data-node="${esc(n.id)}" aria-label="${esc(n.title)}: ${esc(n.state)}${n.frontier ? ", ready to learn" : ""}"><rect x="${p.x}" y="${p.y}" width="${W}" height="${H}"/><text x="${p.x + 10}" y="${p.y + 27}">${esc(label)}${n.frontier ? " ★" : ""}</text></g>`;
    }).join("");
    return `<svg viewBox="-4 -4 ${width + 8} ${height + 8}" role="img" aria-label="Capability map">${lines}${boxes}</svg>`;
  }
  async function nodeDetail(id) {
    const caps = await api("capabilities", { scope: id });
    const c = caps.find((x) => x.id === id);
    const items = await api("items", { concept: id });
    document.getElementById("node-detail").innerHTML = `<h3>${esc(c.title)}</h3>
      <p>State: <strong>${esc(c.state)}</strong>${c.next_review ? `, next review ${esc(c.next_review)}` : ""}. ${c.ready ? "Ready." : c.blocked_by.length ? `Needs ${esc(c.blocked_by.map((b) => b.split(":")[1]).join(", "))} first.` : ""}</p>
      <p>${items.length} prepared question(s).</p>${items.length ? `<button class="primary" data-start-scope="${esc(id)}">Start lesson</button>` : ""}`;
  }

  // ---- the lesson player: answer field, I don't know, Ask, Continue, Replay ---------------------------------------
  async function startLesson(args) {
    try {
      const s = await api("start", args, true);
      Object.assign(state, { lesson: s.lesson, step: s.next, segment: 0, result: null, asking: false });
      location.hash = "#learn";
      if (state.view === "learn") renderStep();
    } catch (e) { say(e.message); }
  }
  function media(seg, content) {
    const base = "/media/" + (content.base || "");
    let html = "";
    const a = content.animation;
    if (a && a.video && state.segment === 0) html += `<video src="${esc(base + a.video)}" ${a.poster ? `poster="${esc(base + a.poster)}"` : ""} playsinline preload="metadata"></video>`;
    const v = seg.visual || (content.visuals && content.visuals[0] && state.segment === 0 && !a ? content.visuals[0].path : null);
    if (v) html += `<img src="${esc(base + v)}" alt="${esc(seg.alt || content.title || "")}">`;
    if (content.clip && state.segment === (content.segments.length - 1)) {
      const c = content.clip, id = (c.url.match(/(?:v=|youtu\.be\/)([\w-]{6,})/) || [])[1];
      if (id) html += `<p><a href="https://www.youtube.com/watch?v=${esc(id)}&t=${c.start | 0}s" target="_blank" rel="noreferrer">Watch: ${esc(c.why || "a short clip")} (${Math.round((c.end - c.start) / 60)} min)</a></p>`;
    }
    return html ? `<figure class="media">${html}</figure>` : "";
  }
  function renderStep() {
    const s = state.step;
    if (!s) return;
    const controls = (opts) => `<div class="controls">
      ${opts.answer ? `<button type="button" data-idk>I don't know</button>` : ""}
      <button type="button" data-ask aria-pressed="${state.asking}">Ask</button>
      ${opts.replay ? `<button type="button" data-replay>Replay</button>` : ""}
      <button type="submit" class="primary">Continue</button></div>`;
    const askField = `<label>Your question<textarea name="ask" required></textarea></label>`;
    let body = "";
    if (s.action === "close") {
      body = `<h1>Lesson complete</h1><p>${esc(s.reason)}</p><button class="primary" data-close>Continue</button>`;
      return h(`<section class="player">${body}</section>`);
    }
    if (s.action === "wait") {
      body = `<h1>Waiting for your tutor</h1><p>Your written answer is saved. Your tutor reads it when you next work together; nothing is lost.</p>`;
      return h(`<form class="player card" data-step>${body}${state.asking ? askField : ""}${controls({})}</form>`);
    }
    if (s.action === "teach") {
      const c = s.content || {};
      if (c.live || !(c.segments || []).length) {
        body = `<h1>${esc(s.title)}</h1><p class="live-note">No prepared explanation: your tutor explains this part live.</p>`;
        return h(`<form class="player card" data-step>${body}${state.asking ? askField : ""}${controls({})}</form>`);
      }
      const seg = c.segments[state.segment];
      body = `<h1>${esc(s.title)}</h1>${media(seg, c)}<div class="segment">${md(seg.text)}</div>
        ${seg.audio ? `<audio data-voice src="${esc("/media/" + c.base + seg.audio)}" preload="auto"></audio>` : ""}
        <p class="muted">${state.segment + 1} of ${c.segments.length}</p>`;
      h(`<form class="player card" data-step>${body}${state.asking ? askField : ""}${controls({ replay: !!(seg.audio || c.animation) })}</form>`);
      playVoice();
      return;
    }
    const q = s.question || {};
    let field = "";
    if (state.result) {
      const r = state.result;
      const word = { correct: "Correct.", incorrect: "Not yet.", "partially-correct": "Partly right.", pending: "Saved. Your tutor will read it." }[r.verdict] || r.verdict;
      field = `<div class="feedback ${esc(r.verdict)}"><p><strong>${word}</strong></p>${r.feedback ? md(r.feedback) : ""}${r.verdict !== "correct" && r.explanation ? md(r.explanation) : ""}</div>${state.asking ? askField : ""}`;
    } else if (state.asking) field = askField;
    else if (q.kind === "choice") field = `<fieldset class="choices"><legend class="muted">Choose one</legend>${(q.options || []).map((o, i) => `<label><input type="radio" name="answer" value="${i}" required> <span>${inline(o)}</span></label>`).join("")}</fieldset>`;
    else if (q.kind === "numeric") field = `<label>Your answer<input type="text" name="answer" inputmode="decimal" autocomplete="off" required></label>`;
    else field = `<label>Your answer<textarea name="answer" required></textarea></label>`;
    h(`<form class="player card" data-step><p class="muted">${esc({ probe: "Where are you now?", practice: "Practice", review: "Review", retry: "Try again", recall: "In your own words" }[s.action] || "")}</p>
      <div class="prompt">${md(q.prompt)}</div>${field}${controls({ answer: !state.result && !state.asking })}</form>`);
    const first = $main.querySelector("input, textarea");
    if (first) first.focus();
  }
  function playVoice() {
    const a = $main.querySelector("audio[data-voice]");
    if (a) { a.playbackRate = +$pace.value || 1; a.play().catch(() => {}); }
  }
  async function submitStep(form) {
    const s = state.step, data = new FormData(form);
    try {
      if (state.asking) {
        await api("ask", { lesson: state.lesson, text: String(data.get("ask")) }, true);
        state.asking = false; say("Asked. Your tutor will answer."); return renderStep();
      }
      if (s.action === "teach") {
        const c = s.content || {};
        if (!c.live && state.segment < (c.segments || []).length - 1) { state.segment++; return renderStep(); }
        await api("teach", { lesson: state.lesson, capability: s.capability, mode: s.mode || "explain" }, true);
        return advance(await api("next", { lesson: state.lesson }));
      }
      if (s.action === "wait") return advance(await api("next", { lesson: state.lesson }));
      if (state.result) return advance(state.result.next);
      let response = data.get("answer");
      if (s.question.kind === "choice") response = +response;
      state.result = await api("answer", { lesson: state.lesson, item: s.item, response }, true);
      renderStep();
    } catch (e) { say(e.message); }
  }
  function advance(next) { Object.assign(state, { step: next, segment: 0, result: null }); renderStep(); }

  // ---- events --------------------------------------------------------------------------------------------------
  document.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    if (f.matches("[data-step]")) return submitStep(f);
    if (f.dataset.human) {
      const args = Object.fromEntries(new FormData(f));
      try { await api(f.dataset.human, { subject: f.dataset.subject, ...args }, true); await route(); say("Recorded."); }
      catch (e) { say(e.message); }
    }
  });
  document.addEventListener("click", async (ev) => {
    const t = ev.target.closest("button, a, [data-node]");
    if (!t) return;
    if (t.dataset.startBundle) startLesson({ bundle: t.dataset.startBundle });
    else if (t.dataset.startScope) startLesson({ scope: t.dataset.startScope });
    else if (t.hasAttribute("data-review")) startLesson({ scope: "review:due", title: "Review" });
    else if (t.dataset.scope) { state.mapScope = t.dataset.scope; }
    else if (t.dataset.node) nodeDetail(t.dataset.node);
    else if (t.hasAttribute("data-idk")) {
      state.result = await api("answer", { lesson: state.lesson, item: state.step.item, dont_know: true }, true);
      renderStep();
    } else if (t.hasAttribute("data-ask")) { state.asking = !state.asking; renderStep(); }
    else if (t.hasAttribute("data-replay")) {
      const v = $main.querySelector("video"), a = $main.querySelector("audio[data-voice]");
      if (v) { v.currentTime = 0; v.play().catch(() => {}); }
      if (a) { a.currentTime = 0; playVoice(); }
    } else if (t.hasAttribute("data-close")) {
      await api("close", { lesson: state.lesson, summary: state.step.reason || "" }, true).catch(() => {});
      Object.assign(state, { lesson: null, step: null });
      location.hash = "#library";
    } else if (t.dataset.log) {
      ev.preventDefault();
      document.getElementById("log-view").innerHTML = `<section class="card">${md(await api("log", { lesson: t.dataset.log }))}</section>`;
    }
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && ev.target.dataset && ev.target.dataset.node) nodeDetail(ev.target.dataset.node); });
  $pace.addEventListener("change", () => { try { localStorage.setItem("ros.pace", $pace.value); } catch (e) {} });
  try { const p = localStorage.getItem("ros.pace"); if (p) $pace.value = p; } catch (e) {}

  async function route() {
    const view = (location.hash.slice(1) || "today");
    state.view = views[view] ? view : "today";
    document.querySelectorAll(".rail a").forEach((a) => {
      if (a.getAttribute("href") === "#" + state.view) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    try { await views[state.view](); say(""); } catch (e) { h(`<h1>Something went wrong</h1><p>${esc(e.message)}</p>`); }
  }
  window.addEventListener("hashchange", route);
  // When the record changes elsewhere (a grade, an answer, a finished task), refresh what is on screen.
  let refresh = null;
  const es = new EventSource("/events");
  es.addEventListener("change", () => {
    clearTimeout(refresh);
    refresh = setTimeout(async () => {
      if (state.lesson && state.step && state.step.action === "wait") advance(await api("next", { lesson: state.lesson }));
      else if (!state.lesson && ["today", "history", "library", "research"].includes(state.view)) route();
    }, 300);
  });
  api("status").then((s) => { document.getElementById("brand").textContent = s.record.split(/[\\/]/).filter(Boolean).slice(-1)[0]; }).catch(() => {});
  route();  // a deferred script runs once the document is parsed
})();
