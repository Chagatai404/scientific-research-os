/* Research OS portal: one page, six views, one lesson player. Everything comes from the record through /api. */
"use strict";
(() => {
  const $main = document.getElementById("main");
  const $status = document.getElementById("status");
  const $pace = document.getElementById("pace");
  const $rec = document.getElementById("rec");
  const $q = document.getElementById("q");
  const state = { seq: 0, view: "", lesson: null, step: null, segment: 0, asking: false, result: null, record: null, name: "" };
  try { state.name = localStorage.getItem("ros.name") || ""; } catch (e) {}

  // ---- data ----------------------------------------------------------------------------------------------------
  async function api(name, args = {}, write = false) {
    const session = write ? await fetch('/services/session').then(r => r.json()).then(b => b.result) : null;
    args = { ...(state.record ? { record: state.record } : {}), ...args };
    const opts = write
      ? { method: "POST", headers: { "Content-Type": "application/json", "X-ROS": "1", "X-ROS-CSRF": session.csrf }, body: JSON.stringify(args) }
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

  // ---- shared pieces ---------------------------------------------------------------------------------------------
  const enc = encodeURIComponent;
  const link = (view, arg, rec) => `#${view}${arg ? "/" + enc(arg) : ""}${(rec || state.record) ? "?r=" + enc(rec || state.record) : ""}`;
  const chip = (text, cls) => `<span class="chip ${esc(cls || "")}">${esc(text)}</span>`;
  const vcls = (v) => "v-" + String(v || "pending").toLowerCase();
  const LABEL = { approve: "Approve the plan", decide: "Decide", defend: "Defend before deciding", commitment: "Open commitment",
    proposal: "Proposed change", "human-decision-required": "Decide", "approval-required": "Approve the plan" };
  const vaultLink = (rel, text) => rel ? `<a href="/vault/${rel.split("/").map(enc).join("/")}" target="_blank" rel="noreferrer">${esc(text)}</a>` : "";
  const kv = (o) => Object.entries(o || {}).filter(([, v]) => v != null && v !== "" && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${inline(typeof v === "object" ? JSON.stringify(v) : String(v))}</td></tr>`).join("");
  function decisionForm(x, rec) {
    const name = `<label>Your name<input type="text" name="by" value="${esc(state.name)}" required></label>`;
    if (x.kind === "approve" || x.kind === "approval-required") return `<form class="row" data-human="approve" data-subject="${esc(x.subject)}" data-record="${esc(rec || "")}">
      ${name}<select name="decision" aria-label="Decision"><option value="approved">Approve</option><option value="changes-requested">Ask for changes</option><option value="rejected">Reject</option></select>
      <button type="submit" class="primary">Record</button></form>`;
    if (x.kind === "commitment") return "";
    if (x.kind === "defend") return `<button class="primary" data-start-scope="${esc(x.subject)}">Practise the defence</button>`;
    const outcomes = x.subject.startsWith("claim:") ? ["accepted", "revise", "rejected", "retracted"] : ["accepted", "rejected"];
    return `<form data-human="decide" data-subject="${esc(x.subject)}" data-record="${esc(rec || "")}">
      <label>Rationale<textarea name="rationale" required></textarea></label>
      <div class="row">${name}<select name="outcome" aria-label="Outcome">${outcomes.map((o) => `<option>${o}</option>`).join("")}</select>
      <button type="submit" class="primary">Decide</button></div></form>`;
  }
  function evidenceHtml(e) {
    const out = [];
    if (e.kind === "claim") {
      out.push(`<p>${chip(e.verdict, vcls(e.verdict))} ${chip("ownership: " + e.ownership)} ${chip(e.assurance)} ${e.can_accept ? chip("can be accepted", "v-pass") : chip("not yet acceptable", "v-warn")}</p>`);
      out.push(`<div class="table-wrap"><table><thead><tr><th>Step</th><th>Verdict</th><th>By</th><th>Notes</th></tr></thead><tbody>${e.required.map((s) => {
        const v = e.steps[s]; return `<tr><td>${esc(s)}</td><td>${v ? chip(v.verdict, vcls(v.verdict)) : chip("waiting", "v-pending")}</td><td>${esc(v ? v.by : "")}</td><td>${v ? inline(v.notes || "") : ""}</td></tr>`; }).join("")}</tbody></table></div>`);
      if ((e.numbers.cited || []).length) out.push(`<p>Numbers cited: ${e.numbers.cited.map((n) => `<code>${esc(n.value)}</code> in ${esc(n.file)}`).join(", ")}${e.numbers.precheck ? " — pre-check " + chip(e.numbers.precheck.verdict, vcls(e.numbers.precheck.verdict)) : ""}</p>`);
      if (e.artifacts.length) out.push(`<p>Files audited: ${e.artifacts.map((a) => `<code>${esc(a)}</code>`).join(", ")}</p>`);
      if (e.citations.length) out.push(`<p>Cites: ${e.citations.map((c) => esc(c.citation)).join("; ")}</p>`);
      if (e.adversary_memo) out.push(`<h3>The strongest case against it</h3><blockquote>${inline(e.adversary_memo)}</blockquote>`);
      if (e.defence_items.length) out.push(`<p>You will be asked to defend: ${e.defence_items.map((d) => esc(d.kind)).join(", ")}.</p>`);
      if (e.decided.length) out.push(`<p>Decided: ${e.decided.map((d) => `${esc(d.outcome)} by ${esc(d.by)}`).join("; ")}.</p>`);
      out.push(`<p><a class="button" href="${link("graphs", "chain/" + e.subject)}">See the evidence chain</a></p>`);
    } else if (e.kind === "approve") {
      out.push(`<p class="notice">${esc(e.authorizes)}</p>`);
      out.push(`<div class="table-wrap"><table><tbody>${kv(e.plan)}</tbody></table></div>`);
      if (!e.has_budget) out.push(`<p class="warn">The plan states no compute budget: ask for one before approving.</p>`);
    } else if (e.kind === "proposal") out.push(`<p>${inline(e.text || "")}</p><p class="muted">${inline(e.why || "")}</p>`);
    else if (e.node) out.push(`<div class="table-wrap"><table><tbody>${kv(e.node)}</tbody></table></div>`);
    const l = e.links || {};
    const links = [];
    if (l.vault) links.push(`<a href="${esc(l.vault.obsidian)}">Open the note in Obsidian</a>`);
    (l.handouts || []).forEach((hd) => links.push(`<a href="${link("node", hd.id)}">${esc(hd.title)}</a> ${chip(hd.status || "draft")}${hd.pdf ? " " + vaultLink(hd.pdf, "PDF") : ""}`));
    if (links.length) out.push(`<ul>${links.map((x) => `<li>${x}</li>`).join("")}</ul>`);
    return out.join("");
  }
  function needCard(x) {
    const ev = x.evidence || {};
    const chips = ev.steps ? Object.entries(ev.steps).map(([k, v]) => chip(`${k}: ${v}`, vcls(v))).join(" ") + (ev.missing && ev.missing.length ? " " + chip("missing " + ev.missing.join(", "), "v-pending") : "") : "";
    return `<div class="card need"><p><strong>${esc(LABEL[x.kind] || x.kind)}</strong> <span class="muted">· ${esc(x.record || "")}</span></p>
      <p>${inline(x.text || x.subject)}</p>${chips ? `<p>${chips}</p>` : ""}
      <p><button data-evidence="${esc(x.subject)}" data-record="${esc(x.record || "")}">Show the evidence</button></p>
      <div class="evidence" hidden></div>${decisionForm(x, x.record)}</div>`;
  }
  const sections = {
    ask: () => `<section class="card"><h2>What do you want to learn or find out?</h2>
      <form data-engage><label>In your own words<textarea name="intent" placeholder="Teach me STAT303. / Is it true that ...?" required></textarea></label>
      <p class="row"><button type="submit" class="primary">Start</button></p></form><div id="engaged" aria-live="polite"></div></section>`,
    happening(b) {
      const hp = b.happening, kinds = Object.entries(hp.tasks).map(([k, v]) => `${v.open + v.claimed} ${esc(k)}`).join(", ");
      return `<section class="card"><h2>What is happening</h2>
        <p><span class="big">${hp.waiting_for_agent}</span> task(s) wait for an agent${hp.oldest_waiting_hours != null ? `, the oldest ${hp.oldest_waiting_hours < 0.1 ? "just now" : hp.oldest_waiting_hours + " h"}` : ""}.</p>
        ${kinds ? `<p class="muted">${kinds}</p>` : ""}
        ${hp.jobs.open + hp.jobs.claimed ? `<p>${hp.jobs.open + hp.jobs.claimed} local job(s) running or queued.</p>` : ""}
        ${hp.problems.map((x) => `<p class="warn">${esc(x)}</p>`).join("")}
        ${hp.recent.length ? `<ul class="muted">${hp.recent.map((r) => `<li>${esc(r.at.slice(5, 16).replace("T", " "))} ${esc(r.record)}: ${esc(Object.keys(r.ran || {}).join(", "))}</li>`).join("")}</ul>` : ""}
        ${hp.waiting_for_agent ? `<p class="muted">Open your agent and say “continue”.</p>` : ""}</section>`;
    },
    learned(b) {
      const l = b.learned;
      return `<section class="card"><h2>What you learned, and next</h2>
        <p><span class="big">${l.due}</span> due for review${l.next_due ? ` <span class="muted">· next ${esc(l.next_due)}</span>` : ""} · ${l.lessons_this_week} lesson(s) this week</p>
        ${l.due ? `<p><button class="primary" data-review>Review now</button></p>` : ""}
        ${l.lessons_ready.length ? `<h3>Next lesson</h3><ul>${l.lessons_ready.map((x) => `<li>${esc(x.title)} <button class="primary" data-start-bundle="${esc(x.bundle)}">Start lesson</button></li>`).join("")}</ul>` : ""}
        ${l.frontier.length ? `<h3>Ready to learn</h3><ul>${l.frontier.map((c) => `<li>${esc(c.title || c.id)} <button data-start-scope="${esc(c.id)}">Learn this</button></li>`).join("")}</ul>` : ""}
        ${l.unreviewed_handouts.length ? `<h3>Handouts to read</h3><ul>${l.unreviewed_handouts.map((x) => `<li><a href="${link("node", x.id, x.record)}">${esc(x.title)}</a> ${chip(x.status)} ${vaultLink(x.pdf, "PDF")} <button data-reviewed="${esc(x.id)}" data-record="${esc(x.record)}">Mark read</button></li>`).join("")}</ul>` : ""}</section>`;
    },
  };

  // ---- views ---------------------------------------------------------------------------------------------------
  const views = {
    async director(_, h) {
      const b = await api("brief", {}, true);  // it also lets what followed from changes happen, so it writes
      const context = await api("context").catch(() => null);
      h(`<h1>Director</h1><p class="next"><strong>Next:</strong> ${esc(b.next_action)}</p>${sections.ask()}
        <section class="card"><h2>Needs your judgement</h2>${b.needs_you.length ? b.needs_you.map(needCard).join("") : `<p class="muted">Nothing is waiting for you.</p>`}</section>
        ${sections.happening(b)}${sections.learned(b)}
        ${b.new.inbox || b.new.my_notes_flowed_back ? `<section class="card"><h2>New in your vault</h2><p>${b.new.inbox} new file(s) read in and ${b.new.my_notes_flowed_back} of your notes flowed back this week. <a href="${link("vault")}">Open the vault view</a></p></section>` : ""}
        ${ctx(context)}`);
    },
    async learn(_, h) {
      if (state.lesson) return renderStep();
      const bs = await api("bundles");
      const rm = await api("roadmap", { limit: 5 }).catch(() => null);  // none when there is nothing to plan for yet
      h(`<h1>Learn</h1>${roadmapCard(rm)}
        <section class="card"><h2>Lessons</h2>${bs.length ? `<ul>${bs.map((b) => `<li>${esc(b.title)} — ${b.ready ? `<button class="primary" data-start-bundle="${esc(b.id)}">Start lesson</button>` : `<span class="muted">being prepared</span>`}</li>`).join("")}</ul>` : `<p class="muted">No prepared lessons yet. Tell your agent what you want to learn.</p>`}</section>
        <section class="card"><h2>What you know</h2><p><a class="button" href="${link("graphs", "knowledge")}">Open the knowledge graph</a></p></section>`);
    },
    async research(_, h) {
      const q = await api("queue");
      const claims = await api("claims").catch(() => []);
      const rec = state.record || "";
      h(`<h1>Research</h1>
        <section class="card"><h2>Decision queue</h2>${q.length ? q.map((x) => needCard({ ...x, record: rec })).join("") : `<p class="muted">Nothing is waiting for you.</p>`}</section>
        <section class="card"><h2>Claims</h2>${claims.length ? `<div class="table-wrap"><table><thead><tr><th>Claim</th><th>Verdict</th><th>Ownership</th></tr></thead><tbody>${claims.map((c) => `<tr><td><a href="${link("node", c.id)}">${inline(c.text || c.id)}</a></td><td>${chip(c.verdict, vcls(c.verdict))}${c.missing.length ? ` <span class="muted">(missing ${esc(c.missing.join(", "))})</span>` : ""}</td><td>${esc(c.ownership)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No claims recorded.</p>`}
        <p><a class="button" href="${link("graphs", "research")}">Open the research graph</a></p></section>`);
    },
    async graphs(arg, h) {
      const i = (arg || "").indexOf("/");
      const mode = (i < 0 ? arg : arg.slice(0, i)) || "knowledge", focus = i < 0 ? "" : arg.slice(i + 1);
      const tabs = [["knowledge", "Knowledge"], ["research", "Research"], ["progress", "Progress"]];
      const nav = `<nav class="tabs" aria-label="Graphs">${tabs.map(([m, t]) => `<a class="button" href="${link("graphs", m)}" ${m === mode ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav>`;
      if (mode === "progress") {
        const p = await api("progress", { weeks: 12 });
        return h(`<h1>Graphs</h1>${nav}<section class="card"><h2>Your last 12 weeks</h2>${drawProgress(p)}</section>`);
      }
      const g = mode === "chain" ? await api("chain", { claim: focus })
        : await api("atlas", { mode: mode === "research" ? "research" : "knowledge", ...(focus ? { focus } : {}) });
      const sum = Object.entries(g.summary || {}).map(([k, v]) => `${v} ${esc(k)}`).join(", ");
      h(`<h1>Graphs</h1>${nav}<section class="card"><h2>${esc(g.title || "")}</h2>
        <p class="muted">${sum}${g.truncated ? ` · ${g.truncated} more not drawn` : ""}</p>
        ${focus && mode !== "chain" ? `<p><a class="button" href="${link("graphs", mode)}">Back to the overview</a></p>` : ""}
        ${drawGraph(g)}<div id="gdetail" aria-live="polite"></div></section>`);
    },
    async vault(_, h) {
      if (!(await api("vault_root"))) return h(`<h1>Vault</h1><section class="card"><p>No Obsidian vault is set yet, so notes, handouts and PDFs have nowhere to go.</p>
        <p>Choose it once: <code>ros vault_set --path &lt;your vault&gt;</code> (with no path it uses the only vault Obsidian knows about).</p></section>`);
      const st = await api("vault_status");
      const hs = await api("handouts").catch(() => []);
      const lib = await api("library").catch(() => []);
      const list = (title, arr, extra) => arr && arr.length ? `<h3>${title} (${arr.length})</h3><ul>${arr.map((p) => `<li><code>${esc(p)}</code>${extra ? " " + extra(p) : ""}</li>`).join("")}</ul>` : "";
      const pend = st.pending;
      h(`<h1>Vault</h1>
        <section class="card"><h2>Find a note</h2><form data-vsearch class="row"><label>Title<input type="text" name="q" autocomplete="off"></label><button type="submit" class="primary">Search</button></form><div id="vresults"></div></section>
        <section class="card"><h2>Is it in step?</h2><p>${st.in_sync ? chip("in step", "v-pass") : chip("needs a look", "v-warn")} ${Object.entries(st.notes).map(([k, v]) => `${v} ${esc(k)}`).join(", ")}</p>
          ${list("You edited (pinned)", st.pinned, (p) => `<button data-resolve="update" data-target="${esc(p)}">Let the record update it</button>`)}
          ${list("You deleted", st.dismissed, (p) => `<button data-resolve="restore" data-target="${esc(p)}">Bring it back</button>`)}
          ${list("Added by you", pend.added)}${list("Links that do not resolve", (st.broken_links || []).map((b) => b.link))}${list("Attachments nothing links to", st.orphan_attachments)}</section>
        <section class="card"><h2>Handouts</h2>${hs.length ? `<ul>${hs.map((x) => `<li><a href="${link("node", x.id)}">${esc(x.title)}</a> ${chip(x.kind)} ${chip(x.status || "draft")} ${vaultLink(x.pdf, "PDF")}</li>`).join("")}</ul>` : `<p class="muted">No handouts yet: they are written for you as you learn.</p>`}</section>
        <section class="card"><h2>Lesson logs</h2>${lib.length ? `<ul>${lib.map((r) => `<li>${esc(r.title || r.id)} ${r.log ? `<a href="#vault" data-log="${esc(r.id)}">Read</a>` : ""}</li>`).join("")}</ul>` : `<p class="muted">No lessons yet.</p>`}<div id="log-view"></div></section>`);
    },
    async history(_, h) {
      const rows = await api("history");
      h(`<h1>History</h1>${rows.length ? `<div class="table-wrap"><table><thead><tr><th>When</th><th>Question</th><th>Answer</th><th>Grade</th></tr></thead><tbody>${rows.slice().reverse().map((r) => `<tr><td>${esc(r.ts.slice(0, 16).replace("T", " "))}</td><td>${inline(r.prompt || "")}</td><td>${inline(r.response == null ? "I don't know" : typeof r.response === "string" ? r.response : JSON.stringify(r.response))}</td><td>${esc(r.grade || "waiting")}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No answers yet.</p>`}`);
    },
    async node(id, h) {
      const e = await api("evidence", { subject: id });
      h(`<h1>${esc((e.node && e.node.title) || e.title || e.text || id)}</h1><section class="card">${evidenceHtml(e)}</section>`);
    },
    async search(q, h) {
      const rows = await api("find", { q, limit: 30 });
      h(`<h1>Search</h1><section class="card"><p class="muted">${rows.length} match(es) for “${esc(q)}”.</p>${rows.length ? `<ul>${rows.map((r) => `<li><a href="${link("node", r.id, r.record)}">${esc(r.title)}</a> ${chip(r.type)} <span class="muted">${esc(r.record)}</span>${r.obsidian ? ` <a href="${esc(r.obsidian)}">Obsidian</a>` : ""}</li>`).join("")}</ul>` : ""}</section>`);
    },
  };
  views.today = views.director; views.library = views.vault;

  // ---- graphs: the server places the nodes, the page draws them ---------------------------------------------------
  function drawGraph(g) {
    if (!g.nodes.length) return `<p class="muted">Nothing to draw yet.</p>`;
    const pos = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    const edges = g.edges.map((e) => {
      const a = pos[e.src], b = pos[e.dst];
      if (!a || !b) return "";
      const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, mx = (x1 + x2) / 2;
      return `<path d="M${x1} ${y1}C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}"/>`;
    }).join("");
    const nodes = g.nodes.map((n) => `<g class="n ${esc(n.cls)}" tabindex="0" role="button" data-gnode="${esc(n.id)}" data-kind="${esc(n.kind)}">
      <title>${esc(n.tip || n.label)}</title><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="6"/>
      <text x="${n.x + 10}" y="${n.y + n.h / 2 + 4}">${esc(String(n.label).slice(0, 24))}${n.cls.includes("frontier") ? " ★" : ""}</text></g>`).join("");
    return `<div class="zoom"><button type="button" data-zoom="-1" aria-label="Zoom out">−</button><button type="button" data-zoom="1" aria-label="Zoom in">+</button></div>
      <div class="graph"><svg viewBox="-6 -6 ${g.width + 12} ${g.height + 12}" width="${g.width + 12}" role="img" aria-label="${esc(g.title || "Graph")}">${edges}${nodes}</svg></div>`;
  }
  function drawProgress(p) {
    const max = Math.max(1, ...p.weeks.map((w) => w.answers)), bw = 28, hgt = 120;
    const bars = p.weeks.map((w, i) => {
      const a = (w.answers / max) * hgt, c = (w.correct / max) * hgt, x = i * (bw + 8);
      return `<g><title>${esc(w.week)}: ${w.answers} answers, ${w.correct} correct, ${w.reviews} reviews, ${w.lessons} lesson(s), ${w.new} new</title>
        <rect class="b-all" x="${x}" y="${hgt - a}" width="${bw}" height="${a}"/><rect class="b-ok" x="${x}" y="${hgt - c}" width="${bw}" height="${c}"/>
        <text x="${x}" y="${hgt + 14}">${esc(w.week.slice(5))}</text></g>`;
    }).join("");
    const total = Object.values(p.states).reduce((a, b) => a + b, 0) || 1;
    const stack = Object.entries(p.states).map(([k, v]) => `<span class="seg st-${esc(k)}" style="flex:${v}" title="${esc(k)}: ${v}"></span>`).join("");
    return `<p><span class="big">${p.due}</span> due · ${p.estimated_recall != null ? `estimated recall <strong>${Math.round(p.estimated_recall * 100)}%</strong> · ` : ""}${p.streak_days} day streak · ${p.reviewed_items} item(s) scheduled</p>
      <div class="graph"><svg viewBox="0 0 ${p.weeks.length * (bw + 8)} ${hgt + 20}" width="${p.weeks.length * (bw + 8)}" role="img" aria-label="Answers and correct answers by week">${bars}</svg></div>
      <p class="legend"><span><i class="b-all"></i>answers</span><span><i class="b-ok"></i>correct</span></p>
      <h3>Where your ${p.capabilities} capabilities stand</h3><div class="stack">${stack}</div>
      <p class="legend">${Object.entries(p.states).map(([k, v]) => `<span class="st-${esc(k)}">${esc(k)} ${v}</span>`).join("")}</p>`;
  }
  async function nodeDetail(el) {
    const id = el.dataset.gnode, kind = el.dataset.kind, box = document.getElementById("gdetail");
    if (["course", "subject", "domain", "goal", "project", "block"].includes(kind)) { location.hash = link("graphs", "knowledge/" + id); return; }
    if (kind === "capability") {
      const caps = await api("capabilities", { scope: id });
      const c = caps.find((x) => x.id === id), items = await api("items", { concept: id });
      box.innerHTML = `<h3>${esc(c.title)}</h3><p>State: <strong>${esc(c.state)}</strong>${c.next_review ? `, next review ${esc(c.next_review)}` : ""}. ${c.ready ? "Ready." : c.blocked_by.length ? `Needs ${esc(c.blocked_by.map((b) => b.split(":")[1]).join(", "))} first.` : ""}</p>
        <p>${items.length} prepared question(s). <a href="${link("graphs", "knowledge/" + id)}">Look around it</a></p>${items.length ? `<button class="primary" data-start-scope="${esc(id)}">Start lesson</button>` : ""}`;
    } else if (kind === "claim" || kind === "experiment" || kind === "handout" || kind === "question" || kind === "hypothesis" || kind === "paper") {
      const e = await api("evidence", { subject: id });
      box.innerHTML = `<h3>${esc((e.node && e.node.title) || e.title || e.text || id)}</h3>${evidenceHtml(e)}<p><a href="${link("node", id)}">Open its page</a></p>`;
    } else box.innerHTML = `<h3>${esc(el.querySelector("title").textContent)}</h3>`;
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
    try {
      if (f.dataset.human) {
        const args = Object.fromEntries(new FormData(f));
        state.name = args.by; try { localStorage.setItem("ros.name", args.by); } catch (e) {}
        await api(f.dataset.human, { subject: f.dataset.subject, ...args, ...(f.dataset.record ? { record: f.dataset.record } : {}) }, true);
        await route(); say("Recorded.");
      } else if (f.hasAttribute("data-engage")) {
        const out = await api("engage", { intent: String(new FormData(f).get("intent")) }, true);
        const n = (out.agent_tasks || []).length;
        document.getElementById("engaged").innerHTML = `<p class="notice">Set up: ${esc(out.kind)}${out.hub ? ` (${esc(out.hub)})` : ""}. ${n ? `${n} task(s) now wait for your agent: open it and say “continue”.` : ""} ${(out.for_you || []).map(esc).join(" ")}</p>`;
        f.reset();
      } else if (f.hasAttribute("data-vsearch")) {
        const q = String(new FormData(f).get("q")).trim(), rows = q ? await api("vault_find", { q }) : [];
        document.getElementById("vresults").innerHTML = rows.length ? `<ul>${rows.map((r) => `<li><a href="${esc(r.obsidian)}">${esc(r.title)}</a> ${chip(r.kind)} <a href="${link("node", r.id)}">details</a></li>`).join("")}</ul>` : `<p class="muted">Nothing found.</p>`;
      }
    } catch (e) { say(e.message); }
  });
  document.addEventListener("click", async (ev) => {
    const t = ev.target.closest("button, a, [data-gnode]");
    if (!t) return;
    try {
      if (t.dataset.startBundle) startLesson({ bundle: t.dataset.startBundle });
      else if (t.dataset.startScope) startLesson({ scope: t.dataset.startScope });
      else if (t.hasAttribute("data-review")) startLesson({ scope: "review:due", title: "Review" });
      else if (t.dataset.gnode) nodeDetail(t);
      else if (t.dataset.zoom) {
        const svg = document.querySelector(".graph svg"), w = svg.getBoundingClientRect().width;
        svg.setAttribute("width", Math.max(240, Math.round(w * (t.dataset.zoom > 0 ? 1.25 : 0.8))));
      } else if (t.dataset.evidence) {
        const box = t.closest(".need").querySelector(".evidence");
        if (!box.hidden) { box.hidden = true; return; }
        box.innerHTML = evidenceHtml(await api("evidence", { subject: t.dataset.evidence, ...(t.dataset.record ? { record: t.dataset.record } : {}) }));
        box.hidden = false;
      } else if (t.dataset.reviewed) {
        await api("vault_resolve", { target: t.dataset.reviewed, action: "reviewed", ...(t.dataset.record ? { record: t.dataset.record } : {}) }, true);
        await route(); say("Marked as read.");
      } else if (t.dataset.resolve) {
        await api("vault_resolve", { target: t.dataset.target, action: t.dataset.resolve }, true);
        await route(); say("Done.");
      } else if (t.hasAttribute("data-idk")) {
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
        location.hash = "#director";
      } else if (t.dataset.log) {
        ev.preventDefault();
        document.getElementById("log-view").innerHTML = `<section class="card">${md(await api("log", { lesson: t.dataset.log }))}</section>`;
      }
    } catch (e) { say(e.message); }
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && ev.target.dataset && ev.target.dataset.gnode) nodeDetail(ev.target); });
  $pace.addEventListener("change", () => { try { localStorage.setItem("ros.pace", $pace.value); } catch (e) {} });
  try { const p = localStorage.getItem("ros.pace"); if (p) $pace.value = p; } catch (e) {}
  $q.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && $q.value.trim()) location.hash = link("search", $q.value.trim()); });
  $rec.addEventListener("change", () => { state.record = $rec.value || null; location.hash = location.hash.split("?")[0] + (state.record ? "?r=" + enc(state.record) : ""); route(); });

  async function route() {
    const [path, qs] = location.hash.slice(1).split("?");
    const parts = path.split("/").map((x) => { try { return decodeURIComponent(x); } catch (e) { return x; } });
    const r = new URLSearchParams(qs || "").get("r");
    if (r !== null && r !== state.record) { state.record = r || null; $rec.value = state.record || ""; }
    const view = parts[0] || "director";
    state.view = views[view] ? view : "director";
    const nav = { today: "director", library: "vault", node: "research", search: "director" }[state.view] || state.view;
    document.querySelectorAll(".rail a").forEach((a) => {
      if (a.getAttribute("href").split("?")[0] === "#" + nav) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    $main.classList.toggle("wide", state.view === "graphs");
    // a slow answer for a page the person has already left must not draw over the page they are on now
    const mine = ++state.seq, draw = (html) => { if (mine === state.seq) $main.innerHTML = html; };
    try { await views[state.view](parts.slice(1).join("/"), draw); if (mine === state.seq) say(""); }
    catch (e) { draw(`<h1>Something went wrong</h1><p>${esc(e.message)}</p>`); }
  }
  window.addEventListener("hashchange", route);
  // When the record changes elsewhere (a grade, an answer, a finished task), refresh what is on screen. A person in the
  // middle of a form is never interrupted: the page only redraws when no field has focus or text in it.
  let refresh = null;
  const es = new EventSource("/events");
  es.addEventListener("change", () => {
    clearTimeout(refresh);
    refresh = setTimeout(async () => {
      if (state.lesson && state.step && state.step.action === "wait") advance(await api("next", { lesson: state.lesson }));
      else if (!state.lesson && ["director", "history", "vault", "research", "learn"].includes(state.view)
        && !$main.contains(document.activeElement) && ![...$main.querySelectorAll("textarea, input[type=text]")].some((x) => x.value)) route();
    }, 600);
  });
  api("records").then((rs) => {
    $rec.innerHTML = rs.map((x) => `<option value="${x.current ? "" : esc(x.name)}"${x.current ? " selected" : ""}>${esc(x.name)}${x.role === "user" ? " (you)" : ""}</option>`).join("");
    $rec.hidden = rs.length < 2;
    document.querySelector(".rec-label").hidden = rs.length < 2;
    const cur = rs.find((x) => x.current);
    document.getElementById("brand").textContent = cur ? cur.name : "Research OS";
    if (state.record) $rec.value = state.record;
  }).catch(() => {});
  route();  // a deferred script runs once the document is parsed
})();
