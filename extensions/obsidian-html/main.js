'use strict';
const {Plugin, FileView, Component, normalizePath} = require('obsidian');
const crypto = require('crypto');
const fs = require('fs');
const nodePath = require('path');
const VIEW = 'research-os-html';
const MAX_STATE = 4 * 1024 * 1024;
const MAX_HTML = 4 * 1024 * 1024;
const MAX_EVENTS = 10000;
const RUNTIME = '.research-os/runtime/';
// Spoken questions. The host records (the sandboxed page never gets the microphone), a local worker (scripts/voice.py worker) transcribes, and the
// transcript goes back to the page as text for the learner to read and edit before sending it as an ordinary open question.
const VOICE_DIR = '.research-os/voice/';
const VOICE_MAX_MS = 60000, VOICE_MAX_BYTES = 3 * 1024 * 1024, VOICE_WAIT_MS = 45000, VOICE_POLL_MS = 400, VOICE_BEAT_MAX = 10, VOICE_WARM_MAX = 60;
// The tutor's live voice: the page asks for one sentence at a time, a local Kokoro worker (scripts/voice.py tts-worker) speaks it, and the audio comes back
// for the page to play as it arrives. Not recordings made in advance.
const TTS_WAIT_MS = 25000, TTS_POLL_MS = 40, TTS_MAX_BYTES = 3 * 1024 * 1024, TTS_MAX_CHARS = 600, TTS_MAX_PENDING = 4;
const TRUST_REGISTRY = RUNTIME + 'extensions/trusted-modules.json';
const TAGS = new Set(('a abbr article aside b blockquote br button caption code col colgroup dd del details div dl dt em fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr i img input label legend li main mark nav ol option p pre section select small span strong sub summary sup table tbody td textarea th thead tr ul svg g path circle rect line polyline polygon ellipse text tspan canvas').split(' '));
const ATTRS = new Set(('id class title alt role aria-label aria-labelledby aria-describedby aria-expanded aria-live aria-hidden tabindex type name value start min max step placeholder checked disabled selected for open rows cols scope colspan rowspan width height viewbox d x y x1 x2 y1 y2 cx cy r rx ry points fill stroke stroke-width transform xmlns').split(' '));

function sibling(path) { return path.replace(/\.html$/i, '.state.json'); }
// Navigation is a validated host operation: the page asks, the host decides. Same syntax rule as scripts/rich_text.py and
// the runtime (tests/fixtures/note-targets.json); the host never trusts the page's judgement of it.
const NOTE_PATH_BAD = new RegExp('[\\u0000-\\u001f\\u007f-\\u009f\\ufeff\\u2028\\u2029\\\\\\\\:*?"<>|]');
const NOTE_SUB_BAD = new RegExp('[\\u0000-\\u001f\\u007f-\\u009f\\ufeff\\u2028\\u2029]');
const OPENABLE_NOTES = new Set(['md', 'html']);
const ADAPT_MODES = ['simpler', 'more-rigorous', 'derivation', 'visual', 'analogy', 'worked-example', 'physical-interpretation', 'implementation', 'prerequisites'];
function validNoteTarget(target) {
  if (typeof target !== 'string' || target.length < 1 || target.length > 256 || /^\s|\s$/.test(target)) return false;
  const hash = target.indexOf('#');
  const path = hash < 0 ? target : target.slice(0, hash), sub = hash < 0 ? '' : target.slice(hash + 1);
  if (!path || sub.length > 200 || NOTE_PATH_BAD.test(path) || NOTE_SUB_BAD.test(sub) || path.startsWith('/') || path.endsWith('/')) return false;
  return path.split('/').every(part => part !== '' && part !== '.' && part !== '..' && !part.startsWith('.'));
}
// Only places the session itself names can be opened from it: wikilinks in its text and questions, and its navigation list.
function declaredTargets(state) {
  const found = new Set();
  for (const item of Array.isArray(state && state.navigation) ? state.navigation : []) if (item && typeof item.target === 'string') found.add(item.target);
  for (const match of JSON.stringify(state || {}).matchAll(/\[\[([^\[\]|\\]+?)(?:\|[^\[\]\\]*)?\]\]/g)) found.add(match[1].trim());
  return found;
}
function resolveNote(app, target, sourcePath, state) {
  if (!validNoteTarget(target)) throw new Error('That is not a note reference.');
  if (!declaredTargets(state).has(target)) throw new Error('This session does not link to that note.');
  const hash = target.indexOf('#');
  const linkpath = hash < 0 ? target : target.slice(0, hash), subpath = hash < 0 ? '' : target.slice(hash);
  const file = app.metadataCache && typeof app.metadataCache.getFirstLinkpathDest === 'function' ? app.metadataCache.getFirstLinkpathDest(linkpath, sourcePath) : null;
  if (!file || file.children) throw new Error('No note named "' + linkpath + '" exists in this vault.');
  if (!OPENABLE_NOTES.has(String(file.extension || '').toLowerCase()) || String(file.path).split('/').some(part => part.startsWith('.'))) throw new Error('That file cannot be opened from a session.');
  return {file, subpath};
}
function validateResources(resources, sessionPath) {
  if (resources === undefined) return [];
  if (!Array.isArray(resources) || resources.length > 32) throw new Error('At most 32 approved resources are allowed.');
  const own = sessionPath.replace(/\.html$/i, '.assets/'); const folder = sessionPath.includes('/') ? sessionPath.slice(0, sessionPath.lastIndexOf('/') + 1) : ''; const relativeOwn = own.slice(folder.length); const ids = new Set();
  return resources.map(resource => {
    if (!resource || typeof resource !== 'object' || Object.keys(resource).some(k => !['id', 'path', 'kind', 'alt', 'title', 'sha256', 'visual_id', 'visual_class', 'verification_outcome'].includes(k))) throw new Error('Invalid resource declaration.');
    const p = resource.path; const id = resource.id || p;
    if (typeof p !== 'string' || !p.length || p.length > 1024 || /[\\:%?#\x00-\x1f]/.test(p) || p.startsWith('/') || p.split('/').some((s, index) => !s || s === '.' || s === '..' || (s.startsWith('.') && !(index === 0 && s === '.research-os' && p.startsWith(RUNTIME + 'extensions/'))))) throw new Error('Unsafe resource path.');
    const resolved = p.startsWith(relativeOwn) ? folder + p : p;
    if (!resolved.startsWith(own) && !resolved.startsWith(RUNTIME + 'extensions/')) throw new Error('Resource is outside approved session/runtime extension directories.');
    if (!['image', 'module'].includes(resource.kind) || (resource.kind === 'module' && !p.endsWith('.js')) || (resource.kind === 'image' && !/\.(png|jpe?g|webp|svg)$/i.test(p))) throw new Error('Unsupported approved resource type.');
    if (resource.visual_id !== undefined && !(typeof resource.visual_id === 'string' && /^VIS-[A-Za-z0-9][A-Za-z0-9._-]*$/.test(resource.visual_id))) throw new Error('Invalid visual identity.');
    if (resource.visual_class !== undefined && !['schematic', 'analytic', 'empirical', 'source'].includes(resource.visual_class)) throw new Error('Unsupported visual class.');
    if (resource.verification_outcome !== undefined && !(typeof resource.verification_outcome === 'string' && /^[a-z-]{1,40}$/.test(resource.verification_outcome))) throw new Error('Invalid verification outcome.');
    if (resource.kind === 'module' && (typeof resource.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(resource.sha256))) throw new Error('Local modules require an explicit SHA-256 declaration.');
    if (typeof id !== 'string' || !id.length || id.length > 1024 || ids.has(id)) throw new Error('Invalid or duplicate resource ID.');
    for (const key of ['alt', 'title']) if (resource[key] !== undefined && (typeof resource[key] !== 'string' || resource[key].length > 2048)) throw new Error('Invalid resource description.');
    ids.add(id); return {id, path: resolved, kind: resource.kind, alt: resource.alt || resource.title || id, sha256: resource.sha256};
  });
}
function approveModule(resource, code, trustedModules) {
  const digest = crypto.createHash('sha256').update(code, 'utf8').digest('hex');
  if (digest !== resource.sha256 || !trustedModules || !Object.prototype.hasOwnProperty.call(trustedModules, resource.path) || trustedModules[resource.path] !== digest) throw new Error('Local module is not approved or changed: ' + resource.path + '. Review its code and explicitly approve its SHA-256 in plugin settings.');
  return code;
}
// Static drawing only, mirroring scripts/visual_assets.py: no scripting, embedding, animation or outside references.
const SVG_ELEMENTS = new Set('svg g defs title desc rect circle ellipse line polyline polygon path text tspan marker lineargradient radialgradient stop clippath use style'.split(' '));
function svgProblems(text) {
  if (/<!\s*(doctype|entity)/i.test(text)) return ['DOCTYPE and ENTITY declarations are not allowed'];
  if (text.replace(/^\s*<\?xml\s[^>]*\?>/, '').includes('<?')) return ['processing instructions (such as xml-stylesheet) are not allowed'];
  const problems = [];
  const tags = text.replace(/<!--[\s\S]*?-->/g, '').match(/<\s*[A-Za-z][^>]*>/g) || [];
  if (!tags.length || !/^<\s*svg[\s>]/i.test(tags[0]) || !/xmlns\s*=\s*["']http:\/\/www\.w3\.org\/2000\/svg["']/.test(tags[0])) problems.push('the root element is not an SVG svg element');
  for (const tag of tags) {
    const name = tag.match(/^<\s*([A-Za-z][\w:.-]*)/)[1].toLowerCase();
    if (!SVG_ELEMENTS.has(name)) problems.push('element not allowed: ' + name);
    for (const attribute of tag.matchAll(/([A-Za-z_:][\w:.-]*)\s*=\s*("([^"]*)"|'([^']*)')/g)) {
      const key = attribute[1].toLowerCase().replace(/^.*:/, ''); const value = attribute[3] !== undefined ? attribute[3] : attribute[4];
      if (key.startsWith('on')) problems.push('event handler attribute: ' + key);
      else if (key === 'href' && !value.startsWith('#')) problems.push('link to something outside the figure');
      else if (/javascript:|expression\s*\(|@import|behavior\s*:|-moz-binding|url\(\s*(?!['"]?#)/i.test(value)) problems.push('attribute ' + key + ' reaches outside the figure');
    }
  }
  const sheets = text.match(/<style[\s\S]*?<\/style>/gi) || [];
  if (sheets.some(s => /javascript:|expression\s*\(|@import|behavior\s*:|-moz-binding|url\(\s*(?!['"]?#)/i.test(s))) problems.push('style sheet reaches outside the figure');
  return Array.from(new Set(problems)).sort();
}
function imageData(bytes, path) {
  const b = Buffer.from(bytes);
  if (b.length > 2 * 1024 * 1024) throw new Error('Image exceeds 2 MiB limit.');
  let mime;
  if (/\.svg$/i.test(path)) {
    const problems = svgProblems(b.toString('utf8'));
    if (problems.length) throw new Error('SVG is not safe to show inline: ' + problems.join('; '));
    return 'data:image/svg+xml;base64,' + b.toString('base64');
  }
  if (/\.png$/i.test(path) && b.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) mime = 'image/png';
  else if (/\.jpe?g$/i.test(path) && b[0] === 255 && b[1] === 216 && b[2] === 255) mime = 'image/jpeg';
  else if (/\.webp$/i.test(path) && b.subarray(0,4).toString() === 'RIFF' && b.subarray(8,12).toString() === 'WEBP') mime = 'image/webp';
  else throw new Error('Image file signature does not match approved type.');
  return 'data:' + mime + ';base64,' + b.toString('base64');
}
function acquireLock(vault, sessionPath, token) {
  if (!vault.adapter || typeof vault.adapter.getBasePath !== 'function') throw new Error('Session persistence requires a desktop filesystem vault.');
  const base = fs.realpathSync(vault.adapter.getBasePath());
  const lockPath = nodePath.resolve(base, sessionPath.replace(/\.html$/i, '.session.lock'));
  const parent = fs.realpathSync(nodePath.dirname(lockPath));
  const compare = p => process.platform === 'win32' ? p.toLowerCase() : p;
  if (!compare(lockPath).startsWith(compare(base + nodePath.sep)) || compare(parent) !== compare(nodePath.dirname(lockPath))) throw new Error('Unsafe session lock location.');
  let fd;
  try { fd = fs.openSync(lockPath, 'wx'); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Session is locked by another writer. Retry after its operation completes.'); throw error; }
  try { fs.writeFileSync(fd, JSON.stringify({owner: 'obsidian-html', token})); }
  catch (error) { fs.closeSync(fd); fs.unlinkSync(lockPath); throw error; }
  fs.closeSync(fd);
  return () => {
    const owner = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
    if (owner.token !== token) throw new Error('Session lock ownership changed; refusing to remove it.');
    fs.unlinkSync(lockPath);
  };
}
// The agent's Python writer holds the same lock for milliseconds; wait briefly instead of failing a submission.
async function acquireLockWithRetry(vault, sessionPath, token, timeout = 3000) {
  const start = Date.now();
  for (;;) {
    try { return acquireLock(vault, sessionPath, token); }
    catch (error) { if (!/locked by another writer/.test(error.message) || Date.now() - start > timeout) throw error; }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}
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
  const allowed = new Set(['event_id', 'type', 'question_id', 'response', 'created_at', 'origin']);
  if (Object.keys(event).some(k => !allowed.has(k))) throw new Error('Unknown event field.');
  if (event.origin !== undefined) {
    // Where in the lesson an open question was asked, so the learner can return there.
    const o = event.origin;
    if (!['open-question', 'explanation-request'].includes(event.type) || !o || typeof o !== 'object' || Array.isArray(o) || Object.keys(o).some(k => !['section', 'title'].includes(k))
      || typeof o.section !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(o.section) || typeof o.title !== 'string' || o.title.length > 200) throw new Error('Invalid question origin.');
  }
  if (typeof event.event_id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(event.event_id)) throw new Error('Invalid event ID.');
  if (!['response', 'hint', 'solution', 'confidence', 'checkpoint', 'reset', 'open-question', 'explanation-request', 'plan-answer'].includes(event.type)) throw new Error('Unsupported event type.');
    if (event.type === 'plan-answer') {
      // An answer to a question in the session plan, judged on the page against the plan's own key: a pacing decision, never evidence of learning.
      const plan = state && state.plan, r = event.response;
      const planIds = plan ? ['probe', 'check'].flatMap(tree => ((plan[tree] || {}).questions || []).map(q => q.id)) : [];
      if (!planIds.includes(event.question_id) || !r || typeof r !== 'object' || Array.isArray(r) || Object.keys(r).some(k => !['answer', 'verdict', 'tree'].includes(k))
        || !['correct', 'wrong', 'pending'].includes(r.verdict) || !['probe', 'check'].includes(r.tree) || !['string', 'number'].includes(typeof r.answer)) throw new Error('Unknown plan question.');
    }
    // A request for another explanation names one known mode and no question; it is never evidence of anything.
    if (event.type === 'explanation-request' && (!ADAPT_MODES.includes(event.response) || (event.question_id !== undefined && event.question_id !== null))) throw new Error('Unknown explanation mode.');
    if (event.type !== 'open-question' && event.type !== 'explanation-request' && event.type !== 'plan-answer' && !(event.type === 'checkpoint' && event.question_id == null) && !state.questions.some(q => q.id === event.question_id)) throw new Error('Unknown question.');
    if (event.type === 'open-question' && (typeof event.response !== 'string' || !event.response.trim())) throw new Error('Open question must have a prompt.');
    if (event.type === 'checkpoint' && (typeof event.response !== 'string' || !event.response.trim())) throw new Error('Checkpoint must include a raw explanation.');
  if (event.question_id !== undefined && !(['checkpoint', 'open-question', 'explanation-request'].includes(event.type) && event.question_id === null) && (typeof event.question_id !== 'string' || event.question_id.length > 128)) throw new Error('Invalid question ID.');
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
// appendUnplaced keeps the historical behaviour (an image with no place follows the content); a session with
// explicit placement shows a visible diagnostic from its own page instead and never appends.
function sanitizeHtml(html, doc, images = new Map(), descriptions = new Map(), appendUnplaced = true) {
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
      const anchor = tag === 'a' && /^#[A-Za-z0-9_-]+$/.test(node.getAttribute('href') || '') ? node.getAttribute('href') : null;
      for (const attr of Array.from(node.attributes)) {
        const key = attr.name.toLowerCase();
        if (!(ATTRS.has(key) || /^data-[a-z0-9_-]+$/.test(key)) || /url\s*\(/i.test(attr.value)) node.removeAttribute(attr.name);
      }
      // All navigation is deliberately inert until mediated navigation is implemented.
      if (tag === 'a') { node.removeAttribute('href'); if (anchor) node.setAttribute('href', anchor); }
      if (tag === 'input' && !['text', 'number', 'range', 'radio', 'checkbox', 'button', 'submit', 'reset', 'hidden'].includes((node.getAttribute('type') || 'text').toLowerCase())) node.setAttribute('type', 'text');
      if (tag === 'img') {
        const id = node.getAttribute('data-resource-id');
        if (!id || !images.has(id)) { const warning = doc.createElement('span'); warning.textContent = '[Image unavailable: declare an approved local image resource.]'; node.replaceWith(warning); continue; }
        node.setAttribute('src', images.get(id)); node.setAttribute('alt', node.getAttribute('alt') || node.getAttribute('title') || 'Session image');
      }
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
  const used = new Set(Array.from(root.querySelectorAll('img[data-resource-id]')).map(n => n.getAttribute('data-resource-id')));
  for (const [id, data] of images) {
    if (used.has(id) || !appendUnplaced) continue;
    const figure = doc.createElement('figure'); const image = doc.createElement('img'); const caption = doc.createElement('figcaption');
    image.setAttribute('src', data); image.setAttribute('alt', descriptions.get(id) || 'Approved session image: ' + id); image.setAttribute('data-resource-id', id);
    caption.textContent = descriptions.get(id) || id; figure.appendChild(image); figure.appendChild(caption); root.appendChild(figure);
  }
  const wrapper = doc.createElement('div'); wrapper.appendChild(root); return wrapper.innerHTML;
}
// Teaching resources a lesson declares on its Teaching Cards (snapshots of vetted registry records). Looked up by id in host-held state.
function declaredResource(state, id) {
  if (typeof id !== 'string' || !/^RES-[A-Za-z0-9][A-Za-z0-9._-]{0,59}$/.test(id) || !state || !Array.isArray(state.teaching)) return null;
  for (const block of state.teaching) {
    const list = block && block.card && Array.isArray(block.card.resources) ? block.card.resources : [];
    for (const item of list) if (item && item.id === id && typeof item.url === 'string') return item;
  }
  return null;
}
// The context binding is for agents (it holds local paths); the sandboxed page never needs it.
// The agent's liveness lease (scripts/supervision.py): same shape and bounds as the writer. Anything else reads as "no live agent".
function parseLease(text) {
  if (typeof text !== 'string' || text.length > 8192) return null;
  let lease; try { lease = JSON.parse(text); } catch (_) { return null; }
  const keys = ['supervision_schema', 'holder', 'provider', 'mode', 'reviewing', 'started_at', 'last_seen_at', 'expires_at', 'ttl'];
  if (!lease || typeof lease !== 'object' || Array.isArray(lease) || Object.keys(lease).length !== keys.length || keys.some(k => !(k in lease)) || lease.supervision_schema !== 1) return null;
  if (typeof lease.holder !== 'string' || !/^[A-Za-z0-9_.:@-]{1,64}$/.test(lease.holder) || typeof lease.provider !== 'string' || !/^[a-z0-9][a-z0-9._-]{0,31}$/.test(lease.provider)) return null;
  if (!['waiting', 'reviewing', 'working'].includes(lease.mode) || !Number.isInteger(lease.ttl) || lease.ttl < 15 || lease.ttl > 3600) return null;
  if (!Array.isArray(lease.reviewing) || lease.reviewing.length > 50 || lease.reviewing.some(x => typeof x !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(x))) return null;
  const [started, seen, expires] = ['started_at', 'last_seen_at', 'expires_at'].map(k => Date.parse(lease[k]));
  if (![started, seen, expires].every(Number.isFinite) || !(started <= seen && seen <= expires) || expires - seen > 3600000) return null;
  return lease;
}
// What the page is shown. The lease and the host's clock ride along so the page can tell "waiting" from "disconnected" without trusting its own.
function pageState(state, live = null) {
  const visible = Object.assign({}, state); delete visible.context;
  visible.supervision_live = live; visible.host_now = Date.now();
  // Always present, so a decision that was withdrawn clears on the page instead of lingering through a merge.
  if (!('supervision' in visible)) visible.supervision = null;
  return visible;
}
// What the page may say about the voice worker, from its lease file (the same rule as voice.py lease_state): never "listening" unless it beat recently.
function voiceWorkerState(text, nowSeconds) {
  let lease; try { lease = JSON.parse(text); } catch (_) { return {state: 'off', reason: 'no worker has run here'}; }
  if (!lease || typeof lease !== 'object' || Array.isArray(lease) || typeof lease.heartbeat !== 'number') return {state: 'off', reason: 'the worker record is unreadable'};
  const model = typeof lease.model === 'string' ? lease.model.slice(0, 40) : null, device = typeof lease.device === 'string' ? lease.device.slice(0, 16) : null;
  if (lease.state === 'stopped' || lease.state === 'error') return {state: lease.state, model, device, reason: typeof lease.last_error === 'string' ? lease.last_error.slice(0, 200) : null};
  const age = nowSeconds - lease.heartbeat;
  if (age > (lease.state === 'warming' ? VOICE_WARM_MAX : VOICE_BEAT_MAX)) return {state: 'off', reason: 'the worker has not reported for ' + Math.floor(age) + ' s'};
  return {state: ['ready', 'busy', 'warming'].includes(lease.state) ? lease.state : 'off', model, device};
}
// A transcript file from the worker, for one recording. Anything else is refused; the text is only ever text.
function parseVoiceResult(text, id) {
  if (typeof text !== 'string' || text.length > 20000) throw new Error('The transcript could not be read.');
  let result; try { result = JSON.parse(text); } catch (_) { throw new Error('The transcript could not be read.'); }
  if (!result || typeof result !== 'object' || Array.isArray(result) || result.id !== id) throw new Error('The transcript does not match the recording.');
  if (typeof result.error === 'string') throw new Error(result.error.slice(0, 300));
  if (typeof result.text !== 'string' || result.text.length > 4000) throw new Error('The transcript is missing or too long.');
  return {text: result.text.replace(/\s+/g, ' ').trim(), language: typeof result.language === 'string' ? result.language.slice(0, 8) : null};
}
function microphoneMessage(error) {
  const name = error && error.name;
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'Microphone access was refused. Allow it for Obsidian in your system settings (on Windows: Privacy & security, Microphone, let desktop apps use it).';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone was found.';
  if (name === 'NotReadableError') return 'The microphone is in use by another program.';
  return 'The microphone could not start: ' + String(error && error.message || error).slice(0, 160);
}
// The recorder is the host's own (Electron renderer); a plugin can supply another (tests do). Returns null where recording is impossible.
function browserRecorder() {
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  if (!nav || !nav.mediaDevices || typeof nav.mediaDevices.getUserMedia !== 'function' || typeof MediaRecorder === 'undefined') return null;
  return {
    async start(maxMs, onLimit) {
      const stream = await nav.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}});
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mime ? {mimeType: mime} : undefined);
      const chunks = []; recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
      const stopped = new Promise(resolve => { recorder.onstop = resolve; });
      const release = () => stream.getTracks().forEach(track => track.stop());
      recorder.start(250);
      const limit = setTimeout(() => { if (onLimit) onLimit(); }, maxMs);
      return {
        async stop() {
          clearTimeout(limit); if (recorder.state !== 'inactive') recorder.stop();
          await stopped; release();
          const blob = new Blob(chunks, {type: recorder.mimeType});
          return {bytes: new Uint8Array(await blob.arrayBuffer()), mime: recorder.mimeType};
        },
        cancel() { clearTimeout(limit); recorder.ondataavailable = null; try { if (recorder.state !== 'inactive') recorder.stop(); } catch (_) { /* already stopped */ } release(); }
      };
    }
  };
}
function buildDocument(body, state, token, runtime, css, theme, modules = [], position = null, live = null, voice = false) {
  const nonce = crypto.randomBytes(24).toString('hex');
  // `voice` is what this host can do: true (record spoken questions) or {capable, speak}. A capability the host lacks is not offered to the page.
  const abilities = voice === true ? {capable: true} : voice && typeof voice === 'object' ? Object.fromEntries(['capable', 'speak'].filter(k => voice[k] === true).map(k => [k, true])) : {};
  const safeJSON = JSON.stringify({token, session_id: state.session_id, state: pageState(state, live), position, voice: Object.keys(abilities).length ? abilities : undefined}).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const safeScript = runtime.replace(/<\/script/gi, '<\\/script');
  const safeCSS = css.replace(/<\/style/gi, '<\\/style');
  const moduleScripts = modules.map(code => '<script nonce="' + nonce + '">document.addEventListener("DOMContentLoaded",function(){"use strict";\n' + code.replace(/<\/script/gi, '<\\/script') + '\n},{once:true});</script>').join('');
  return '<!doctype html><html data-theme="' + (theme === 'dark' ? 'dark' : 'light') + '"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'nonce-' + nonce + '\'; style-src \'nonce-' + nonce + '\'; style-src-attr \'unsafe-inline\'; img-src data:; connect-src \'none\'; font-src data:; frame-src \'none\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'"><style nonce="' + nonce + '">' + safeCSS + '</style></head><body class="' + (theme === 'dark' ? 'theme-dark' : 'theme-light') + '">' + body + '<script nonce="' + nonce + '">window.ROS_HOST=' + safeJSON + ';</script><script nonce="' + nonce + '">' + safeScript + '</script>' + moduleScripts + '</body></html>';
}

class SessionHost extends Component {
  constructor(plugin, container, path) { super(); this.plugin = plugin; this.container = container; this.path = path; this.queue = Promise.resolve(); this.generation = 0; this.pending = 0; }
  onload() {
    if (this.plugin.hosts) this.plugin.hosts.add(this);
    this.container.classList.add('ros-html-host');
    this.status = this.container.ownerDocument.createElement('div'); this.status.className = 'ros-html-status'; this.container.appendChild(this.status);
    this.registerDomEvent(window, 'message', event => this.receive(event));
    this.registerEvent(this.plugin.app.vault.on('modify', file => { if (file.path === TRUST_REGISTRY) this.plugin.loadTrust().then(() => this.reload()).catch(error => this.fail(error.message)); }));
    this.registerEvent(this.plugin.app.vault.on('create', file => { if (file.path === TRUST_REGISTRY) this.plugin.loadTrust().then(() => this.reload()).catch(error => this.fail(error.message)); }));
    this.registerEvent(this.plugin.app.vault.on('delete', file => { if (file.path === TRUST_REGISTRY) { this.plugin.trustedModules = {}; this.reload(); } }));
    this.registerEvent(this.plugin.app.vault.on('rename', (file, old) => { if (old === TRUST_REGISTRY || file.path === TRUST_REGISTRY) this.plugin.loadTrust().then(() => this.reload()).catch(error => this.fail(error.message)); }));
    this.registerEvent(this.plugin.app.vault.on('modify', async file => {
      if (this.writing) return;
      if ([this.path, sibling(this.path)].includes(file.path)) {
        try {
          const current = await this.read(file.path);
          const prior = this.loaded && (file.path === this.path ? this.loaded.html : this.loaded.raw);
          if (current !== prior) this.scheduleRefresh();
        } catch (error) { this.fail(error.message); }
      } else if ([RUNTIME + 'session.js', RUNTIME + 'session.css', ...(this.resources || []).map(r => r.path)].includes(file.path)) this.reload();
    }));
    this.registerEvent(this.plugin.app.vault.on('rename', (file, old) => { if ([this.path, sibling(this.path), ...(this.resources || []).map(r => r.path)].includes(old)) { this.invalidated = true; this.fail('Session/resource renamed. Repair all artifact and resource references together, then reopen.'); } }));
    this.registerEvent(this.plugin.app.vault.on('delete', file => { if ([this.path, sibling(this.path), ...(this.resources || []).map(r => r.path)].includes(file.path)) { this.invalidated = true; this.fail('Session/resource artifact deleted. Reopen after repair.'); } }));
    this.registerEvent(this.plugin.app.workspace.on('css-change', () => { const theme = this.container.ownerDocument.body.classList.contains('theme-dark') ? 'dark' : 'light'; if (!this.loaded || theme !== this.loaded.theme) this.reload(); }));
    this.reload();
    // The lease is a plain file the agent renews; Obsidian does not announce changes to it, so look at it now and then.
    this.leaseTimer = setInterval(() => this.pollLease(), 5000);
  }
  leasePath() { return this.path.replace(/\.html$/i, '.supervision.json'); }
  async readLease() {
    try {
      const adapter = this.plugin.app.vault.adapter;
      if (typeof adapter.exists === 'function' && !(await adapter.exists(this.leasePath()))) return null;
      return parseLease(await adapter.read(this.leasePath()));
    } catch (_) { return null; }
  }
  async pollLease() {
    if (this.invalidated || !this.token) return;
    const lease = await this.readLease();
    if (JSON.stringify(lease) === JSON.stringify(this.lease || null)) return;
    this.lease = lease;
    this.reply(this.token, {type: 'supervision', live: lease, host_now: Date.now()});
  }
  fail(message) { this.generation++; this.token = null; if (this.frame) { this.frame.remove(); this.frame = null; } this.status.textContent = message; this.status.classList.add('ros-error'); }
  async read(path, required = true) {
    if ([RUNTIME + 'session.js', RUNTIME + 'session.css', TRUST_REGISTRY].includes(path)) {
      // Obsidian excludes dot directories from its indexed TFile inventory.
      // Adapter reads are limited to these fixed, canonical host-owned paths.
      try {
        const adapter = this.plugin.app.vault.adapter;
        const base = fs.realpathSync(adapter.getBasePath());
        const expected = nodePath.resolve(base, path);
        const actual = fs.realpathSync(expected);
        const canonical = value => process.platform === 'win32' ? value.toLowerCase() : value;
        if (canonical(expected) !== canonical(actual)) throw new Error('Symlinked runtime resource rejected.');
        return await adapter.read(path);
      } catch (error) { if (required) throw error; return ''; }
    }
    const file = this.plugin.app.vault.getAbstractFileByPath(path);
    if (!file || file.children) { if (required) throw new Error('Missing session resource: ' + path); return ''; }
    return this.plugin.app.vault.read(file);
  }
  // Agent writes touch state, HTML and bridge in quick succession; coalesce them into one live update.
  scheduleRefresh() { clearTimeout(this.refreshTimer); this.refreshTimer = setTimeout(() => this.refresh(), 120); }
  async refresh() {
    if (this.invalidated) return;
    if (!this.frame || !this.ready || !this.loaded) { this.reload(); return; }
    const generation = this.generation; const token = this.token;
    try {
      const [html, raw] = await Promise.all([this.read(this.path), this.read(sibling(this.path))]);
      if (generation !== this.generation || token !== this.token) return;
      if (html === this.loaded.html && raw === this.loaded.raw) return;
      const state = parseState(raw);
      // New resources need fresh approval and inlining; only content/state changes are patched live.
      if (JSON.stringify(state.resources || []) !== JSON.stringify(this.state.resources || []) || state.session_id !== this.state.session_id) { this.reload(); return; }
      const message = {type: 'update', state: pageState(state, this.lease || null)};
      if (html !== this.loaded.html) message.body = sanitizeHtml(html, this.container.ownerDocument, this.images || new Map(), new Map((this.resources || []).map(r => [r.id, r.alt])));
      this.loaded.html = html; this.loaded.raw = raw; this.state = state;
      this.reply(token, message);
    } catch (error) { if (generation === this.generation) this.fail(error.message); }
  }
  async reload() {
    if (this.invalidated) return;
    this.ready = false; clearTimeout(this.refreshTimer);
    const generation = ++this.generation; this.token = null;
    try {
      const [html, raw, runtime, css] = await Promise.all([this.read(this.path), this.read(sibling(this.path)), this.read(RUNTIME + 'session.js', false), this.read(RUNTIME + 'session.css', false)]);
      if (generation !== this.generation) return;
      const state = parseState(raw);
      this.lease = await this.readLease();
      const resources = validateResources(state.resources, this.path); const images = new Map(); const modules = []; let total = 0;
      for (const resource of resources) {
        const adapter = this.plugin.app.vault.adapter;
        if (!adapter || typeof adapter.getBasePath !== 'function') throw new Error('Approved resources require a desktop filesystem vault.');
        const base = fs.realpathSync(adapter.getBasePath());
        const expected = nodePath.resolve(base, resource.path);
        const actual = fs.realpathSync(expected);
        const canonical = value => process.platform === 'win32' ? value.toLowerCase() : value;
        if (canonical(actual) !== canonical(expected)) throw new Error('Symlinked resources are not approved: ' + resource.path);
        const file = this.plugin.app.vault.getAbstractFileByPath(resource.path);
        if ((!file || file.children) && !resource.path.startsWith(RUNTIME + 'extensions/')) throw new Error('Missing approved resource: ' + resource.path);
        if (resource.kind === 'module') {
          if (!runtime) throw new Error('Approved modules require the installed session runtime.');
          const code = file ? await this.plugin.app.vault.read(file) : await adapter.read(resource.path);
          if (code.length > 256 * 1024) throw new Error('Local module exceeds 256 KiB limit.');
          total += code.length; modules.push(approveModule(resource, code, this.plugin.trustedModules));
        } else {
          const bytes = file ? await this.plugin.app.vault.readBinary(file) : await adapter.readBinary(resource.path); total += bytes.byteLength;
          images.set(resource.id, imageData(bytes, resource.path));
        }
        if (total > 8 * 1024 * 1024) throw new Error('Approved resources exceed 8 MiB total limit.');
      }
      if (generation !== this.generation) return;
      this.loaded = {html, raw, theme: this.container.ownerDocument.body.classList.contains('theme-dark') ? 'dark' : 'light'};
      this.state = state; this.resources = resources; this.images = images; this.token = crypto.randomBytes(32).toString('hex');
      const doc = this.container.ownerDocument;
      const body = sanitizeHtml(html, doc, images, new Map(resources.map(r => [r.id, r.alt])), state.placement !== 'explicit');
      if (this.frame) this.frame.remove();
      this.frame = doc.createElement('iframe'); this.frame.className = 'ros-html-frame'; this.frame.title = this.state.title || 'Research OS session'; this.frame.setAttribute('sandbox', 'allow-scripts'); this.frame.setAttribute('referrerpolicy', 'no-referrer');
      this.frame.srcdoc = buildDocument(body, this.state, this.token, runtime, css, doc.body.classList.contains('theme-dark') ? 'dark' : 'light', modules, this.position || null, this.lease || null, this.abilities());
      this.container.appendChild(this.frame); this.status.classList.remove('ros-error'); this.status.textContent = runtime ? '' : 'Interactive runtime is not installed; showing isolated session content.';
    } catch (error) { if (generation === this.generation) this.fail(error.message); }
  }
  receive(message) {
    const data = message.data;
    if (!this.frame || message.source !== this.frame.contentWindow || !data || data.channel !== 'research-os' || data.token !== this.token || data.session_id !== this.state.session_id) return;
    if (data.type === 'ready') { this.ready = true; return; }
    if (data.type === 'position') {
      // Remembered in memory only, so a reload (theme change, plugin refresh) returns the learner to where they were.
      if (typeof data.section === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(data.section) && Number.isFinite(data.offset) && Math.abs(data.offset) < 1e6) this.position = {section: data.section, offset: data.offset};
      return;
    }
    if (data.type === 'voice') { this.voice(data.action, this.token); return; }
    if (data.type === 'speak') { this.speak(data.action, data.id, data.text, this.token); return; }
    if (data.type === 'board-position') { this.boardPosition(data); return; }
    if (data.type === 'navigate') { this.navigate(data.target, this.token); return; }
    if (data.type === 'open-resource') { this.openResource(data.id, this.token); return; }
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
        const releaseLock = await acquireLockWithRetry(this.plugin.app.vault, this.path, token);
        try {
        await this.plugin.app.vault.process(file, raw => {
          const state = parseState(raw);
          if (token !== this.token || generation !== this.generation || this.invalidated) throw new Error('Session view changed before persistence.');
          if (state.session_id !== data.session_id) throw new Error('Session identity changed.');
          validateEvent(data.event, state);
          if (!state.events.some(e => e.event_id === event.event_id)) {
            if (state.events.length >= MAX_EVENTS) throw new Error('Session event limit reached.');
            state.events.push(event); state.updated_at = event.created_at;
            if (event.type === 'explanation-request') {
              if (!Array.isArray(state.explanation_requests)) state.explanation_requests = [];
              if (state.explanation_requests.length >= 200) throw new Error('Too many explanation requests.');
              const asked = {id: event.event_id, mode: event.response, status: 'open', created_at: event.created_at};
              if (event.origin) asked.origin = event.origin;
              state.explanation_requests.push(asked);
            }
            if (event.type === 'open-question') {
              if (!Array.isArray(state.open_questions)) state.open_questions = [];
              const record = {id: event.event_id, prompt: event.response, status: 'open', created_at: event.created_at, session_id: state.session_id, concept: state.metadata && state.metadata.concept || null, explanation_refs: []};
              if (event.origin) record.origin = event.origin;
              state.open_questions.push(record);
            }
          }
          const output = JSON.stringify(state, null, 2) + '\n'; if (output.length > MAX_STATE) throw new Error('Session state exceeds size limit.');
          if (this.loaded) this.loaded.raw = output;
          this.state = state; return output;
        });
        } finally { releaseLock(); }
        this.reply(token, {type: 'state', state: pageState(this.state, this.lease || null)});
      } catch (error) { this.reply(token, {type: 'error', message: error.message}); }
      finally { this.writing = false; this.pending--; }
    });
  }
  // ---- where the learner is in a lecture. The page reports it (validated here); the lecturer reads <session>.board-position.json to pace itself and to know where an
  // answer belongs. It is a hint, kept out of the session state, and never evidence of anything.
  boardPosition(data) {
    const id = /^[A-Za-z0-9_-]{1,64}$/;
    if (typeof data.widget !== 'string' || !id.test(data.widget) || typeof data.step !== 'string' || !id.test(data.step) || !Number.isInteger(data.index) || data.index < 0 || data.index > 1000
      || !Number.isInteger(data.count) || data.count < 0 || data.count > 1000 || !['idle', 'playing', 'paused', 'waiting', 'done', 'revised'].includes(data.status)) return;
    this.positions = this.positions || {};
    const was = this.positions[data.widget];
    const next = {step: data.step, index: data.index, count: data.count, status: data.status, at: Date.now() / 1000};
    if (Object.keys(this.positions).length >= 16 && !was) return;
    this.positions[data.widget] = next;
    const changed = !was || was.status !== next.status;
    clearTimeout(this.positionTimer);
    const write = async () => {
      try {
        const adapter = this.plugin.app.vault.adapter;
        if (typeof adapter.write !== 'function' || this.invalidated) return;
        await adapter.write(this.path.replace(/\.html$/i, '.board-position.json'), JSON.stringify({schema: 1, boards: this.positions}));
      } catch (_) { /* a position is a hint; losing one changes nothing */ }
    };
    if (changed) write(); else this.positionTimer = setTimeout(write, this.positionDelayMs === undefined ? 400 : this.positionDelayMs);
  }
  // ---- spoken questions: the page asks by action only ("status", "start", "stop", "cancel"); everything else is decided here.
  voiceCapable() { return !!(this.plugin.recorder || browserRecorder()); }
  // The live voice needs only the vault's own files, so any desktop vault can offer it; whether a worker is running is checked when it is asked.
  speakCapable() { const adapter = this.plugin.app && this.plugin.app.vault && this.plugin.app.vault.adapter; return !!(adapter && typeof adapter.writeBinary === 'function' && typeof adapter.readBinary === 'function' && typeof adapter.exists === 'function'); }
  abilities() { return {capable: this.voiceCapable(), speak: this.speakCapable()}; }
  async ttsWorker() {
    try {
      const adapter = this.plugin.app.vault.adapter, path = VOICE_DIR + 'tts-worker.json';
      if (!(await adapter.exists(path))) return {state: 'off', reason: 'no live voice worker has run here'};
      return voiceWorkerState(await adapter.read(path), Date.now() / 1000);
    } catch (_) { return {state: 'off', reason: 'the live voice worker could not be checked'}; }
  }
  async speak(action, id, text, token) {
    const say = (payload, transfer) => this.reply(token, Object.assign({type: 'speech'}, payload), transfer);
    const label = typeof id === 'string' && /^[A-Za-z0-9_-]{1,32}$/.test(id) ? id : null;
    try {
      if (action === 'status') { say(Object.assign({status: 'worker'}, await this.ttsWorker())); return; }
      if (action === 'cancel') {
        if (label) (this.ttsCancelled = this.ttsCancelled || new Set()).add(label); else if (id === undefined || id === null) this.ttsAbort = (this.ttsAbort || 0) + 1;
        return;
      }
      if (action !== 'synth') throw new Error('Unknown speech action.');
      if (!label) throw new Error('A speech request needs an id.');
      if (typeof text !== 'string' || !text.trim() || text.length > TTS_MAX_CHARS || /[\u0000-\u0008\u000b-\u001f\u007f]/.test(text)) throw new Error('A speech request is one sentence of text, 1 to ' + TTS_MAX_CHARS + ' characters.');
      this.ttsPending = this.ttsPending || new Set();
      if (this.ttsPending.size >= TTS_MAX_PENDING) throw new Error('Too many sentences are waiting to be spoken.');
      const worker = await this.ttsWorker();
      if (worker.state !== 'ready' && worker.state !== 'busy') throw new Error('The live voice is not running' + (worker.reason ? ' (' + worker.reason + ')' : '') + '. Start it with: python scripts/voice.py tts-worker --dir .research-os/voice --voice model_dir=<Kokoro folder>');
      const adapter = this.plugin.app.vault.adapter, request = crypto.randomBytes(8).toString('hex'), base = VOICE_DIR + 'tts/', aborted = this.ttsAbort || 0;
      this.ttsPending.add(label);
      try {
        for (const directory of [VOICE_DIR.slice(0, -1), base.slice(0, -1), base + 'inbox']) if (!(await adapter.exists(directory))) await adapter.mkdir(directory);
        await adapter.write(base + 'inbox/' + request + '.json', JSON.stringify({text: text.trim()}));
        const answer = base + 'out/' + request + '.json', wav = base + 'out/' + request + '.wav', deadline = Date.now() + (this.ttsWaitMs || TTS_WAIT_MS);
        const tidy = async () => { for (const path of [answer, wav, base + 'inbox/' + request + '.json']) { try { if (await adapter.exists(path)) await adapter.remove(path); } catch (_) { /* the worker tidies old files itself */ } } };
        let result = null;
        while (Date.now() < deadline) {
          if (this.invalidated || token !== this.token || (this.ttsAbort || 0) !== aborted || (this.ttsCancelled && this.ttsCancelled.has(label))) { await tidy(); return; }
          if (await adapter.exists(answer)) { result = JSON.parse(await adapter.read(answer)); break; }
          await new Promise(resolve => setTimeout(resolve, this.ttsPollMs || TTS_POLL_MS));
        }
        if (!result) { await tidy(); throw new Error('The live voice did not answer in time.'); }
        if (!result || typeof result !== 'object' || result.id !== request) { await tidy(); throw new Error('The live voice answered with something unreadable.'); }
        if (typeof result.error === 'string') { await tidy(); throw new Error(result.error.slice(0, 300)); }
        const bytes = await adapter.readBinary(wav);
        await tidy();
        if (!bytes || !bytes.byteLength || bytes.byteLength > TTS_MAX_BYTES) throw new Error('The spoken sentence is missing or too large.');
        if (this.ttsCancelled && this.ttsCancelled.has(label)) return;
        const seconds = Number.isFinite(result.audio_seconds) ? Math.round(result.audio_seconds * 1000) / 1000 : null;
        say({status: 'audio', id: label, seconds, sample_rate: Number.isFinite(result.sample_rate) ? result.sample_rate : 24000, wav: bytes}, [bytes]);
      } finally { this.ttsPending.delete(label); if (this.ttsCancelled) this.ttsCancelled.delete(label); }
    } catch (error) { say({status: 'error', id: label, message: String(error && error.message || error).slice(0, 400)}); }
  }
  async voiceWorker() {
    try {
      const adapter = this.plugin.app.vault.adapter, path = VOICE_DIR + 'worker.json';
      if (typeof adapter.exists === 'function' && !(await adapter.exists(path))) return {state: 'off', reason: 'no worker has run here'};
      return voiceWorkerState(await adapter.read(path), Date.now() / 1000);
    } catch (_) { return {state: 'off', reason: 'the worker could not be checked'}; }
  }
  voiceCancel() {
    const session = this.voiceSession; this.voiceSession = null; this.voiceAborted = (this.voiceAborted || 0) + 1;
    if (session) { session.cancelled = true; if (session.handle) { try { session.handle.cancel(); } catch (_) { /* nothing to cancel */ } } }
  }
  async voiceWrite(name, bytes) {
    const adapter = this.plugin.app.vault.adapter;
    for (const directory of [VOICE_DIR.slice(0, -1), VOICE_DIR + 'inbox']) if (!(await adapter.exists(directory))) await adapter.mkdir(directory);
    await adapter.writeBinary(VOICE_DIR + 'inbox/' + name, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  }
  async voiceWait(id, token) {
    const adapter = this.plugin.app.vault.adapter, path = VOICE_DIR + 'out/' + id + '.json', aborted = this.voiceAborted || 0;
    const deadline = Date.now() + (this.voiceWaitMs || VOICE_WAIT_MS);
    while (Date.now() < deadline) {
      if (this.invalidated || token !== this.token || (this.voiceAborted || 0) !== aborted) return null;
      if (await adapter.exists(path)) {
        const text = await adapter.read(path);
        try { await adapter.remove(path); } catch (_) { /* the worker tidies old results itself */ }
        return parseVoiceResult(text, id);
      }
      await new Promise(resolve => setTimeout(resolve, this.voicePollMs || VOICE_POLL_MS));
    }
    throw new Error('The voice worker did not answer in time. Check that it is running: python scripts/voice.py worker-status --dir .research-os/voice');
  }
  async voice(action, token) {
    const say = payload => this.reply(token, Object.assign({type: 'voice'}, payload));
    try {
      if (action === 'status') { say(Object.assign({status: 'worker'}, await this.voiceWorker())); return; }
      if (action === 'cancel') { this.voiceCancel(); say({status: 'cancelled'}); return; }
      const recorder = this.plugin.recorder || browserRecorder();
      if (!recorder) throw new Error('This Obsidian cannot record audio.');
      if (action === 'start') {
        if (this.voiceSession || this.voiceBusy) throw new Error('Already listening.');
        const now = Date.now();
        if (this.voiceAt && now - this.voiceAt < 400) throw new Error('Please wait a moment.');
        this.voiceAt = now;
        const worker = await this.voiceWorker();
        if (worker.state === 'warming') throw new Error('The voice worker is still warming up. Try again in a moment.');
        if (worker.state !== 'ready' && worker.state !== 'busy') throw new Error('No voice worker is running' + (worker.reason ? ' (' + worker.reason + ')' : '') + '. Start it with: python scripts/voice.py worker --dir .research-os/voice');
        const session = {id: crypto.randomBytes(12).toString('hex'), cancelled: false, handle: null};
        this.voiceSession = session;
        try { session.handle = await recorder.start(this.voiceMaxMs || VOICE_MAX_MS, () => this.voice('stop', token)); }
        catch (error) { if (this.voiceSession === session) this.voiceSession = null; throw new Error(microphoneMessage(error)); }
        if (session.cancelled || this.voiceSession !== session) { try { session.handle.cancel(); } catch (_) { /* nothing to cancel */ } return; }
        say({status: 'recording', max_seconds: (this.voiceMaxMs || VOICE_MAX_MS) / 1000});
        return;
      }
      if (action === 'stop') {
        const session = this.voiceSession;
        if (!session) return;
        this.voiceSession = null;
        if (!session.handle) { session.cancelled = true; say({status: 'cancelled'}); return; }   // let go before the microphone had opened
        this.voiceBusy = session.id;
        try {
          say({status: 'transcribing', id: session.id});
          const {bytes, mime} = await session.handle.stop();
          if (session.cancelled) return;
          if (!bytes || !bytes.byteLength) throw new Error('Nothing was recorded.');
          if (bytes.byteLength > VOICE_MAX_BYTES) throw new Error('The recording is too long to send. Keep a question under a minute.');
          await this.voiceWrite(session.id + (/ogg/.test(String(mime)) ? '.ogg' : '.webm'), bytes);
          const heard = await this.voiceWait(session.id, token);
          if (heard) say({status: 'transcript', id: session.id, text: heard.text, language: heard.language});
        } finally { this.voiceBusy = null; }
        return;
      }
      throw new Error('Unknown voice action.');
    } catch (error) { say({status: 'error', message: String(error && error.message || error).slice(0, 400)}); }
  }
  // Open a note the session links to, in a new tab so the lesson stays exactly where the learner left it.
  async navigate(target, token) {
    const now = Date.now();
    try {
      if (this.navigatedAt && now - this.navigatedAt < 400) throw new Error('Please wait a moment before opening another note.');
      this.navigatedAt = now;
      const workspace = this.plugin.app.workspace;
      if (!workspace || typeof workspace.openLinkText !== 'function') throw new Error('Opening notes is not available in this Obsidian.');
      const {file, subpath} = resolveNote(this.plugin.app, target, this.path, this.state);
      await workspace.openLinkText(file.path + subpath, this.path, 'tab');
      this.reply(token, {type: 'navigated', target, title: file.basename || file.path});
    } catch (error) { this.reply(token, {type: 'navigation-error', target: typeof target === 'string' ? target.slice(0, 256) : '', message: error.message}); }
  }
  // A teaching resource opens in the system browser. The page asks by id only; the URL comes from the state this host holds, is checked
  // here, and is never taken from the sandboxed page. This host's page policy forbids frames, so nothing is ever embedded.
  openResource(id, token) {
    try {
      const now = Date.now();
      if (this.openedAt && now - this.openedAt < 400) throw new Error('Please wait a moment before opening another link.');
      this.openedAt = now;
      const spec = declaredResource(this.state, id);
      if (!spec) throw new Error('This lesson does not declare that resource.');
      let url; try { url = new URL(spec.url); } catch (_) { throw new Error('The resource link is not a valid URL.'); }
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Only HTTPS links without credentials open.');
      const open = this.plugin.openExternal || (href => (typeof activeWindow !== 'undefined' ? activeWindow : window).open(href, '_blank', 'noopener,noreferrer'));
      open(url.href);
      this.reply(token, {type: 'resource-opened', id, title: String(spec.title || id).slice(0, 200)});
    } catch (error) { this.reply(token, {type: 'resource-error', id: typeof id === 'string' ? id.slice(0, 80) : '', message: error.message}); }
  }
  reply(token, payload, transfer) { if (this.frame && token === this.token) this.frame.contentWindow.postMessage(Object.assign({channel: 'research-os', token, session_id: this.state.session_id}, payload), '*', transfer || []); }
  onunload() { this.voiceCancel(); clearTimeout(this.positionTimer); clearTimeout(this.refreshTimer); clearInterval(this.leaseTimer); if (this.plugin.hosts) this.plugin.hosts.delete(this); this.invalidated = true; this.generation++; this.token = null; if (this.frame) this.frame.remove(); this.container.replaceChildren(); }
}
class SessionView extends FileView {
  constructor(leaf, plugin) { super(leaf); this.plugin = plugin; }
  getViewType() { return VIEW; }
  getDisplayText() { return this.file ? this.file.basename : 'Research OS HTML'; }
  async onLoadFile(file) { if (this.host) this.removeChild(this.host); this.contentEl.replaceChildren(); this.host = new SessionHost(this.plugin, this.contentEl, file.path); this.addChild(this.host); }
  async onUnloadFile() { if (this.host) { this.removeChild(this.host); this.host = null; } }
}
class ResearchOSHTML extends Plugin {
  async loadTrust() {
    this.trustedModules = {};
    const adapter = this.app.vault.adapter;
    if (!await adapter.exists(TRUST_REGISTRY)) return;
    const base = fs.realpathSync(adapter.getBasePath());
    const expected = nodePath.resolve(base, TRUST_REGISTRY);
    if (fs.realpathSync(expected).toLowerCase() !== expected.toLowerCase()) throw new Error('Symlinked trust registry rejected.');
    const raw = await adapter.read(TRUST_REGISTRY);
    if (raw.length > 65536) throw new Error('Module trust registry exceeds size limit.');
    const registry = JSON.parse(raw);
    if (!registry || typeof registry !== 'object' || Array.isArray(registry) || Object.keys(registry).length > 256 || Object.entries(registry).some(([path, hash]) => !path || typeof hash !== 'string' || !/^[a-f0-9]{64}$/.test(hash))) throw new Error('Invalid module trust registry.');
    this.trustedModules = registry;
  }
  async onload() {
    this.hosts = new Set();
    await this.loadTrust();
    const reload = async () => {
      try { await this.loadTrust(); for (const host of this.hosts) host.reload(); }
      catch (error) { for (const host of this.hosts) host.fail(error.message); }
    };
    this.addCommand({id:'reload-html-sessions', name:'Reload HTML sessions and trusted resources', callback:reload});
    const runtimeDirectory = nodePath.resolve(this.app.vault.adapter.getBasePath(), RUNTIME);
    try {
      const hashes = new Map();
      const digest = relative => {
        try { const value = fs.readFileSync(nodePath.resolve(runtimeDirectory, relative)); return crypto.createHash('sha256').update(value).digest('hex'); }
        catch (_) { return 'missing'; }
      };
      for (const relative of ['session.js','session.css','extensions/trusted-modules.json']) hashes.set(relative,digest(relative));
      const watcher = fs.watch(runtimeDirectory, {recursive:true}, (_, filename) => {
        const relative = String(filename || '').replace(/\\/g,'/');
        if (!['session.js','session.css','extensions/trusted-modules.json'].includes(relative) && !/^extensions\/[A-Za-z0-9_/-]+\.js$/.test(relative)) return;
        const current = digest(relative);
        if (hashes.get(relative) === current) return; // Windows access/metadata events are not content updates.
        hashes.set(relative,current); reload();
      });
      this.register(() => watcher.close());
    } catch (_) { /* Missing runtime/watcher: explicit reload command remains available. */ }
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
module.exports._test = {pageState, parseLease, parseState, validateEvent, validateResources, approveModule, imageData, svgProblems, validNoteTarget, declaredTargets, declaredResource, resolveNote, acquireLock, acquireLockWithRetry, sanitizeHtml, buildDocument, SessionHost, sibling, voiceWorkerState, parseVoiceResult, microphoneMessage, browserRecorder};
