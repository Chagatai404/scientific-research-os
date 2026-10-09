'use strict';
const {Plugin, FileView, Component, normalizePath} = require('obsidian');
const crypto = require('crypto');
const VIEW = 'research-os-html';
const MAX_STATE = 4 * 1024 * 1024;
const MAX_HTML = 4 * 1024 * 1024;
const MAX_EVENTS = 10000;
const RUNTIME = '.research-os/runtime/';
const TAGS = new Set(('a abbr article aside b blockquote br button caption code col colgroup dd details div dl dt em fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr i input label legend li main mark nav ol option p pre section select small span strong sub summary sup table tbody td textarea th thead tr ul svg g path circle rect line polyline polygon ellipse text tspan canvas').split(' '));
const ATTRS = new Set(('id class title role aria-label aria-labelledby aria-describedby aria-expanded aria-live aria-hidden tabindex type name value min max step placeholder checked disabled selected for open rows cols width height viewbox d x y x1 x2 y1 y2 cx cy r rx ry points fill stroke stroke-width transform xmlns').split(' '));

function sibling(path) { return path.replace(/\.html$/i, '.state.json'); }
function parseState(text) {
  if (typeof text !== 'string' || text.length > MAX_STATE) throw new Error('Session state exceeds size limit.');
  const s = JSON.parse(text);
  if (!s || s.schema_version !== 1 || typeof s.session_id !== 'string' || !s.session_id.length || s.session_id.length > 256 || !Array.isArray(s.questions) || !Array.isArray(s.events) || s.events.length > MAX_EVENTS) throw new Error('Unsupported or invalid session state.');
  const ids = s.questions.map(q => q && q.id);
  if (ids.some(id => typeof id !== 'string' || id.length > 128) || new Set(ids).size !== ids.length) throw new Error('Invalid question IDs.');
  return s;
}
function validateEvent(event, state) {
  if (!event || typeof event !== 'object' || Array.isArray(event)) throw new Error('Invalid event.');
  const allowed = new Set(['event_id', 'type', 'question_id', 'response', 'created_at']);
  if (Object.keys(event).some(k => !allowed.has(k))) throw new Error('Unknown event field.');
  if (typeof event.event_id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(event.event_id)) throw new Error('Invalid event ID.');
  if (!['response', 'hint', 'solution', 'confidence', 'checkpoint', 'reset', 'open-question'].includes(event.type)) throw new Error('Unsupported event type.');
    if (event.type !== 'open-question' && !state.questions.some(q => q.id === event.question_id)) throw new Error('Unknown question.');
    if (event.type === 'open-question' && (typeof event.response !== 'string' || !event.response.trim())) throw new Error('Open question must have a prompt.');
  if (event.question_id !== undefined && (typeof event.question_id !== 'string' || event.question_id.length > 128)) throw new Error('Invalid question ID.');
  function checkValue(value, depth = 0) {
    if (depth > 4) throw new Error('Response nesting limit exceeded.');
    if (value === null || ['string', 'boolean'].includes(typeof value)) return;
    if (typeof value === 'number' && Number.isFinite(value)) return;
    if (Array.isArray(value) && value.length <= 100) { value.forEach(v => checkValue(v, depth + 1)); return; }
    if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype && Object.keys(value).length <= 100) {
      for (const [key, v] of Object.entries(value)) { if (['__proto__', 'constructor', 'prototype'].includes(key)) throw new Error('Invalid response key.'); checkValue(v, depth + 1); } return;
    }
    throw new Error('Invalid response.');
  }
  if (event.response !== undefined) checkValue(event.response);
  if (JSON.stringify(event).length > 16384) throw new Error('Event exceeds size limit.');
  if (event.created_at !== undefined && (typeof event.created_at !== 'string' || !Number.isFinite(Date.parse(event.created_at)))) throw new Error('Invalid event time.');
  return Object.assign({}, event, {created_at: new Date().toISOString(), status: 'pending-review'});
}
function sanitizeHtml(html, doc) {
  if (typeof html !== 'string' || html.length > MAX_HTML) throw new Error('Session HTML exceeds size limit.');
  // Parse in a detached template: scripts cannot run and resources are never attached.
  const template = doc.createElement('template');
  template.innerHTML = html;
  function visit(parent) {
    for (const node of Array.from(parent.childNodes)) {
      if (node.nodeType === 8) { node.remove(); continue; }
      if (node.nodeType !== 1) continue;
      const tag = node.localName.toLowerCase();
      if (!TAGS.has(tag)) { node.remove(); continue; }
      for (const attr of Array.from(node.attributes)) {
        const key = attr.name.toLowerCase();
        if (!(ATTRS.has(key) || /^data-[a-z0-9_-]+$/.test(key)) || /url\s*\(/i.test(attr.value)) node.removeAttribute(attr.name);
      }
      // All navigation is deliberately inert until mediated navigation is implemented.
      if (tag === 'a') node.removeAttribute('href');
      visit(node);
    }
  }
  // Extract body before allowlisting removes the html/head wrappers.
  const body = template.content.querySelector('body');
  let root = template.content;
  if (body) { const fragment = doc.createDocumentFragment(); while (body.firstChild) fragment.appendChild(body.firstChild); root = fragment; }
  else {
    const htmlNode = template.content.querySelector('html');
    if (htmlNode) { const fragment = doc.createDocumentFragment(); while (htmlNode.firstChild) fragment.appendChild(htmlNode.firstChild); root = fragment; }
  }
  visit(root);
  const wrapper = doc.createElement('div'); wrapper.appendChild(root); return wrapper.innerHTML;
}
function buildDocument(body, state, token, runtime, css, theme) {
  const nonce = crypto.randomBytes(24).toString('hex');
  const safeJSON = JSON.stringify({token, session_id: state.session_id, state}).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const safeScript = runtime.replace(/<\/script/gi, '<\\/script');
  const safeCSS = css.replace(/<\/style/gi, '<\\/style');
  return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'nonce-' + nonce + '\'; style-src \'nonce-' + nonce + '\'; style-src-attr \'unsafe-inline\'; img-src \'none\'; connect-src \'none\'; font-src data:; frame-src \'none\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'"><style nonce="' + nonce + '">' + safeCSS + '</style></head><body class="' + (theme === 'dark' ? 'theme-dark' : 'theme-light') + '">' + body + '<script nonce="' + nonce + '">window.ROS_HOST=' + safeJSON + ';</script><script nonce="' + nonce + '">' + safeScript + '</script></body></html>';
}

class SessionHost extends Component {
  constructor(plugin, container, path) { super(); this.plugin = plugin; this.container = container; this.path = path; this.queue = Promise.resolve(); this.generation = 0; this.pending = 0; }
  onload() {
    this.container.classList.add('ros-html-host');
    this.status = this.container.ownerDocument.createElement('div'); this.status.className = 'ros-html-status'; this.container.appendChild(this.status);
    this.registerDomEvent(window, 'message', event => this.receive(event));
    this.registerEvent(this.plugin.app.vault.on('modify', file => { if ([this.path, sibling(this.path), RUNTIME + 'session.js', RUNTIME + 'session.css'].includes(file.path) && !this.writing) this.reload(); }));
    this.registerEvent(this.plugin.app.vault.on('rename', (file, old) => { if ([this.path, sibling(this.path)].includes(old)) { this.invalidated = true; this.fail('Session renamed. Repair HTML/state/Markdown references together, then reopen.'); } }));
    this.registerEvent(this.plugin.app.vault.on('delete', file => { if ([this.path, sibling(this.path)].includes(file.path)) { this.invalidated = true; this.fail('Session artifact deleted. Reopen after repair.'); } }));
    this.registerEvent(this.plugin.app.workspace.on('css-change', () => this.reload()));
    this.reload();
  }
  fail(message) { this.generation++; this.token = null; if (this.frame) { this.frame.remove(); this.frame = null; } this.status.textContent = message; this.status.classList.add('ros-error'); }
  async read(path, required = true) {
    const file = this.plugin.app.vault.getAbstractFileByPath(path);
    if (!file || file.children) { if (required) throw new Error('Missing session resource: ' + path); return ''; }
    return this.plugin.app.vault.read(file);
  }
  async reload() {
    if (this.invalidated) return;
    const generation = ++this.generation; this.token = null;
    try {
      const [html, raw, runtime, css] = await Promise.all([this.read(this.path), this.read(sibling(this.path)), this.read(RUNTIME + 'session.js', false), this.read(RUNTIME + 'session.css', false)]);
      if (generation !== this.generation) return;
      this.state = parseState(raw); this.token = crypto.randomBytes(32).toString('hex');
      const doc = this.container.ownerDocument;
      const body = sanitizeHtml(html, doc);
      if (this.frame) this.frame.remove();
      this.frame = doc.createElement('iframe'); this.frame.className = 'ros-html-frame'; this.frame.title = this.state.title || 'Research OS session'; this.frame.setAttribute('sandbox', 'allow-scripts'); this.frame.setAttribute('referrerpolicy', 'no-referrer');
      this.frame.srcdoc = buildDocument(body, this.state, this.token, runtime, css, doc.body.classList.contains('theme-dark') ? 'dark' : 'light');
      this.container.appendChild(this.frame); this.status.classList.remove('ros-error'); this.status.textContent = runtime ? '' : 'Interactive runtime is not installed; showing isolated session content.';
    } catch (error) { if (generation === this.generation) this.fail(error.message); }
  }
  receive(message) {
    const data = message.data;
    if (!this.frame || message.source !== this.frame.contentWindow || !data || data.channel !== 'research-os' || data.token !== this.token || data.session_id !== this.state.session_id) return;
    if (this.pending >= 32) { this.reply(this.token, {type: 'error', message: 'Too many pending events.'}); return; }
    this.pending++;
    const token = this.token; const generation = this.generation;
    this.queue = this.queue.then(async () => {
      if (token !== this.token || generation !== this.generation || this.invalidated) { this.pending--; return; }
      try {
        const event = validateEvent(data.event, this.state);
        const file = this.plugin.app.vault.getAbstractFileByPath(sibling(this.path));
        if (!file || file.children) throw new Error('Session state is missing.');
        this.writing = true;
        const lockPath = this.path.replace(/\.html$/i, '.session.lock');
        const lockFile = await this.plugin.app.vault.create(lockPath, JSON.stringify({owner: 'obsidian-html', token}));
        try {
        await this.plugin.app.vault.process(file, raw => {
          const state = parseState(raw);
          if (state.session_id !== data.session_id) throw new Error('Session identity changed.');
          validateEvent(data.event, state);
          if (!state.events.some(e => e.event_id === event.event_id)) {
            if (state.events.length >= MAX_EVENTS) throw new Error('Session event limit reached.');
            state.events.push(event); state.updated_at = event.created_at;
            if (event.type === 'open-question') {
              if (!Array.isArray(state.open_questions)) state.open_questions = [];
              state.open_questions.push({id: event.event_id, prompt: event.response, status: 'open', created_at: event.created_at});
            }
          }
          const output = JSON.stringify(state, null, 2) + '\n'; if (output.length > MAX_STATE) throw new Error('Session state exceeds size limit.');
          this.state = state; return output;
        });
        } finally { await this.plugin.app.vault.delete(lockFile); }
        this.reply(token, {type: 'state', state: this.state});
      } catch (error) { this.reply(token, {type: 'error', message: error.message}); }
      finally { this.writing = false; this.pending--; }
    });
  }
  reply(token, payload) { if (this.frame && token === this.token) this.frame.contentWindow.postMessage(Object.assign({channel: 'research-os', token, session_id: this.state.session_id}, payload), '*'); }
  onunload() { this.invalidated = true; this.generation++; this.token = null; if (this.frame) this.frame.remove(); this.container.replaceChildren(); }
}
class SessionView extends FileView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; }
  getViewType() { return VIEW; }
  getDisplayText() { return this.file ? this.file.basename : 'Research OS HTML'; }
  async onLoadFile(file) { if (this.host) this.removeChild(this.host); this.contentEl.replaceChildren(); this.host = new SessionHost(this.plugin, this.contentEl, file.path); this.addChild(this.host); }
  async onUnloadFile() { if (this.host) { this.removeChild(this.host); this.host = null; } }
}
class ResearchOSHTML extends Plugin {
  async onload() {
    this.registerView(VIEW, leaf => new SessionView(leaf, this)); this.registerExtensions(['html'], VIEW);
    this.registerMarkdownCodeBlockProcessor('ros-session', (source, element, context) => {
      const value = source.trim();
      if (!value || /[\\\r\n]|(^|\/)\.\.(\/|$)|:|^\//.test(value) || !value.endsWith('.html')) { element.textContent = 'Invalid Research OS session embed path.'; return; }
      context.addChild(new SessionHost(this, element, normalizePath(value)));
    });
  }
  onunload() { this.app.workspace.detachLeavesOfType(VIEW); }
}
module.exports = ResearchOSHTML;
module.exports._test = {parseState, validateEvent, sanitizeHtml, buildDocument, SessionHost, sibling};
