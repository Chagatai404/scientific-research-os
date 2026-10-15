/* Research OS runtime: scientific inline grammar. Mirrors scripts/rich_text.py; tests/fixtures/richtext-cases.json holds both to identical HTML. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSRich = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const ESCAPABLE = new Set('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'.split(''));
  const MAX_DEPTH = 24;
  const MAX_EMPHASIS = 32;
  const SPACE = /^\s$/u;
  const PUNCT = /^[\p{P}\p{S}]$/u;
  const isSpace = c => c === '' || SPACE.test(c);
  const isPunct = c => c !== '' && PUNCT.test(c);
  const normalizeLabel = v => { v = v.trim(); return v.startsWith('eq:') ? v.slice(3) : v; };
  const text = v => ({t: 'text', v});
  const group = (t, c) => ({t, c});
  // The Unicode character before/after a UTF-16 index, so astral symbols flank the same way as in Python.
  function before(s, i) {
    if (i <= 0) return '';
    const low = s.charCodeAt(i - 1);
    if (low >= 0xDC00 && low <= 0xDFFF && i >= 2) { const high = s.charCodeAt(i - 2); if (high >= 0xD800 && high <= 0xDBFF) return s.slice(i - 2, i); }
    return s[i - 1];
  }
  function after(s, i) { return i >= s.length ? '' : String.fromCodePoint(s.codePointAt(i)); }
  function escaped(s, index) {
    let count = 0;
    while (index - 1 - count >= 0 && s[index - 1 - count] === '\\') count++;
    return count % 2 === 1;
  }
  function closingDollar(s, start) {
    let j = start;
    while (j < s.length) {
      const c = s[j];
      if (c === '\\') { j += 2; continue; }
      if (c === '$' && j > start && !/\s/u.test(s[j - 1]) && !(j + 1 < s.length && /[0-9]/.test(s[j + 1]))) return j;
      j++;
    }
    return -1;
  }
  function find(s, needle, start) {
    let j = s.indexOf(needle, start);
    while (j !== -1 && escaped(s, j)) j = s.indexOf(needle, j + 1);
    return j;
  }
  function matchingBracket(s, start) {
    let depth = 0, j = start;
    while (j < s.length) {
      const c = s[j];
      if (c === '\\') { j += 2; continue; }
      if (c === '`') {
        let run = 0; while (s[j + run] === '`') run++;
        const end = s.indexOf('`'.repeat(run), j + run);
        j = end !== -1 ? end + run : j + run;
        continue;
      }
      if (c === '[') depth++;
      else if (c === ']') { depth--; if (depth === 0) return j; }
      j++;
    }
    return -1;
  }
  function linkTarget(s, close) {
    if (close + 1 >= s.length || s[close + 1] !== '(') return null;
    const re = /\(([^()\s]+)(?:\s+"([^"\n]*)")?\)/y; re.lastIndex = close + 1;
    const m = re.exec(s);
    return m ? [m[1], m[2] === undefined ? null : m[2], re.lastIndex] : null;
  }
  function flags(prev, ch, following) {
    const left = !isSpace(following) && (!isPunct(following) || isSpace(prev) || isPunct(prev));
    const right = !isSpace(prev) && (!isPunct(prev) || isSpace(following) || isPunct(following));
    if (ch === '*') return [left, right];
    return [left && (!right || isPunct(prev)), right && (!left || isPunct(following))];
  }
  function sticky(re, s, i) { const r = new RegExp(re.source, re.flags.replace('y', '') + 'y'); r.lastIndex = i; const m = r.exec(s); return m ? {m, end: r.lastIndex} : null; }

  function scan(s, depth) {
    const tokens = []; let buf = []; let i = 0; const n = s.length;
    const flush = () => { if (buf.length) { tokens.push(text(buf.join(''))); buf = []; } };
    const emit = t => { flush(); tokens.push(t); };
    while (i < n) {
      const c = s[i];
      if (c === '\n') {
        const raw = buf.join(''); const stripped = raw.replace(/ +$/, '');
        const hard = raw.length - stripped.length >= 2;
        buf = stripped ? [stripped] : [];
        emit(hard ? {t: 'br'} : text(' '));
        i++; while (i < n && s[i] === ' ') i++;
        continue;
      }
      if (c === '\\') {
        const following = i + 1 < n ? s[i + 1] : '';
        if (following === '\n') { emit({t: 'br'}); i += 2; while (i < n && s[i] === ' ') i++; continue; }
        if (following === '(' || following === '[') {
          const closer = following === '(' ? '\\)' : '\\]';
          const end = find(s, closer, i + 2);
          if (end > i + 2) { emit({t: 'math', v: s.slice(i + 2, end).trim(), display: following === '[', src: s.slice(i, end + 2)}); i = end + 2; }
          else { emit({t: 'diag', code: 'unclosed-math', v: '\\' + following}); i += 2; }
          continue;
        }
        const ref = sticky(/\\eqref\{([^{}\s]+)\}/, s, i);
        if (ref) { emit({t: 'ref', label: normalizeLabel(ref.m[1]), src: ref.m[0]}); i = ref.end; continue; }
        if (following && ESCAPABLE.has(following)) { buf.push(following); i += 2; } else { buf.push('\\'); i++; }
        continue;
      }
      if (c === '`') {
        let run = 0; while (s[i + run] === '`') run++;
        let end = -1;
        const re = /`+/g; re.lastIndex = i + run; let f;
        while ((f = re.exec(s)) !== null) { if (f[0].length === run) { end = f.index; break; } }
        if (end === -1) { buf.push('`'.repeat(run)); i += run; continue; }
        let content = s.slice(i + run, end).replace(/\n/g, ' ');
        if (content.length > 2 && content[0] === ' ' && content[content.length - 1] === ' ' && content.trim()) content = content.slice(1, -1);
        emit({t: 'code', v: content}); i = end + run; continue;
      }
      if (c === '$') {
        if (s.startsWith('$$', i)) {
          const end = find(s, '$$', i + 2);
          if (end > i + 2) { emit({t: 'math', v: s.slice(i + 2, end).trim(), display: true, src: s.slice(i, end + 2)}); i = end + 2; continue; }
        } else if (i + 1 < n && !/\s/u.test(s[i + 1])) {
          const end = closingDollar(s, i + 1);
          if (end !== -1) { emit({t: 'math', v: s.slice(i + 1, end), display: false, src: s.slice(i, end + 1)}); i = end + 1; continue; }
        }
        buf.push('$'); i++; continue;
      }
      if (c === '<') {
        const tag = sticky(/<(sub|sup|mark)>/i, s, i);
        if (tag && depth < MAX_DEPTH) {
          const name = tag.m[1].toLowerCase(); let nesting = 1, end = -1;
          const re = new RegExp('<(/?)' + name + '>', 'gi'); re.lastIndex = tag.end; let part;
          while ((part = re.exec(s)) !== null) { nesting += part[1] ? -1 : 1; if (nesting === 0) { end = part.index; break; } }
          if (end !== -1) { emit(group(name, parseInline(s.slice(tag.end, end), depth + 1))); i = end + name.length + 3; continue; }
        }
        const lone = sticky(/<br\s*\/?>/i, s, i);
        if (lone) { emit({t: 'br'}); i = lone.end; continue; }
        buf.push('<'); i++; continue;
      }
      if (c === '[') {
        if (s.startsWith('[[', i)) {
          const end = s.indexOf(']]', i + 2);
          const inner = end !== -1 ? s.slice(i + 2, end) : '';
          if (end !== -1 && inner && !/[\[\]\n]/.test(inner)) {
            const bar = inner.indexOf('|');
            const target = bar === -1 ? inner : inner.slice(0, bar); const alias = bar === -1 ? '' : inner.slice(bar + 1);
            const label = alias || target.split('#')[0];
            emit({t: 'wikilink', target: target.trim(), c: depth < MAX_DEPTH ? parseInline(label, depth + 1) : [text(label)]});
            i = end + 2; continue;
          }
        }
        const ref = sticky(/\[@([A-Za-z0-9][A-Za-z0-9_.:-]*)\]/, s, i);
        if (ref) { emit({t: 'ref', label: normalizeLabel(ref.m[1]), src: ref.m[0]}); i = ref.end; continue; }
        const close = matchingBracket(s, i);
        const target = close !== -1 ? linkTarget(s, close) : null;
        if (target && depth < MAX_DEPTH) { emit({t: 'link', href: target[0], title: target[1], c: parseInline(s.slice(i + 1, close), depth + 1)}); i = target[2]; continue; }
        buf.push('['); i++; continue;
      }
      if ((c === '~' || c === '=') && s.startsWith(c + c, i) && !s.startsWith(c + c + c, i) && depth < MAX_DEPTH) {
        const next = i + 2 < n ? s[i + 2] : ''; const end = s.indexOf(c + c, i + 2);
        if (next && !/\s/u.test(next) && end > i + 2 && !/\s/u.test(s[end - 1]) && !escaped(s, end)) {
          emit(group(c === '~' ? 'del' : 'mark', parseInline(s.slice(i + 2, end), depth + 1))); i = end + 2; continue;
        }
      }
      if (c === '*' || c === '_') {
        let j = i; while (j < n && s[j] === c) j++;
        const [open, close] = flags(before(s, i), c, after(s, j));
        emit({t: 'delim', ch: c, n: j - i, orig: j - i, open, close});
        i = j; continue;
      }
      buf.push(c); i++;
    }
    flush();
    return tokens;
  }

  function resolveEmphasis(tokens) {
    let i = 0;
    while (i < tokens.length) {
      const closer = tokens[i];
      if (closer.t !== 'delim' || !closer.close || closer.n === 0) { i++; continue; }
      let found = -1;
      for (let j = i - 1; j >= 0; j--) {
        const opener = tokens[j];
        if (opener.t !== 'delim' || opener.ch !== closer.ch || !opener.open || opener.n === 0) continue;
        const odd = (opener.close || closer.open) && (opener.orig + closer.orig) % 3 === 0 && !(opener.orig % 3 === 0 && closer.orig % 3 === 0);
        if (!odd) { found = j; break; }
      }
      if (found < 0) { if (!closer.open) closer.close = false; i++; continue; }
      const opener = tokens[found];
      const use = opener.n >= 2 && closer.n >= 2 ? 2 : 1;
      const inner = tokens.slice(found + 1, i);
      const depth = 1 + inner.reduce((m, t) => Math.max(m, t.d || 0), 0);
      if (depth > MAX_EMPHASIS) { closer.close = false; i++; continue; } // pathological nesting stays literal, as in rich_text.py
      const g = group(use === 2 ? 'strong' : 'em', inner);
      g.d = depth;
      opener.n -= use; closer.n -= use;
      tokens.splice(found + 1, i - found - 1, g);
      i = found + 2;
      if (opener.n === 0) { tokens.splice(found, 1); i--; }
      if (closer.n === 0) tokens.splice(i, 1);
    }
    return tokens;
  }

  function build(tokens) {
    const out = [];
    for (const token of tokens) {
      let node;
      if (token.t === 'delim') node = token.n ? text(token.ch.repeat(token.n)) : null;
      else if (token.t === 'em' || token.t === 'strong') node = group(token.t, build(token.c));
      else node = token;
      if (!node) continue;
      if (node.t === 'text' && out.length && out[out.length - 1].t === 'text') out[out.length - 1] = text(out[out.length - 1].v + node.v);
      else out.push(node);
    }
    return out;
  }

  function parseInline(s, depth = 0) {
    if (!s) return [];
    return build(resolveEmphasis(scan(String(s), depth)));
  }

  const ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'};
  const esc = v => String(v).replace(/[&<>"']/g, ch => ESC[ch]);
  // Syntax of a vault note reference; mirrors scripts/rich_text.py and the host's own check (tests/fixtures/note-targets.json).
  function validNoteTarget(target) {
    if (typeof target !== 'string' || target.length < 1 || target.length > 256 || /^\s|\s$/.test(target)) return false;
    const hash = target.indexOf('#');
    const path = hash < 0 ? target : target.slice(0, hash), sub = hash < 0 ? '' : target.slice(hash + 1);
    if (!path || sub.length > 200 || /[\x00-\x1f\x7f-\x9f\ufeff\u2028\u2029\\:*?"<>|]/.test(path) || /[\x00-\x1f\x7f-\x9f\ufeff\u2028\u2029]/.test(sub)) return false;
    if (path.startsWith('/') || path.endsWith('/')) return false;
    return path.split('/').every(part => part !== '' && part !== '.' && part !== '..' && !part.startsWith('.'));
  }
  const GROUPS = new Set(['em', 'strong', 'del', 'mark', 'sub', 'sup']);

  function toHTML(nodes, labels = {}) {
    let out = '';
    for (const node of nodes) {
      switch (node.t) {
        case 'text': out += esc(node.v); break;
        case 'code': out += '<code>' + esc(node.v) + '</code>'; break;
        case 'math': out += '<span data-ros="equation"' + (node.display ? ' data-display="true"' : '') + ' data-tex="' + esc(node.v) + '" class="ros-math">' + esc(node.src) + '</span>'; break;
        case 'br': out += '<br>'; break;
        case 'link': {
          const label = toHTML(node.c, labels);
          out += /^#[A-Za-z0-9_-]+$/.test(node.href) ? '<a href="' + node.href + '">' + label + '</a>'
            : '<span class="ros-link">' + label + ' <span class="ros-link-target">(' + esc(node.href) + ')</span></span>';
          break;
        }
        case 'wikilink':
          out += validNoteTarget(node.target)
            ? '<a class="ros-note-link" href="#ros-note-link" role="link" data-ros-target="' + esc(node.target) + '" title="' + esc(node.target) + '">' + toHTML(node.c, labels) + '</a>'
            : '<span class="ros-note-link ros-note-link-invalid" data-ros-target="' + esc(node.target) + '" title="' + esc(node.target) + ' (not a navigable note)">' + toHTML(node.c, labels) + '</span>';
          break;
        case 'ref': {
          const number = labels[node.label];
          out += number === undefined
            ? '<span class="ros-diagnostic" data-ros="diagnostic" data-code="unresolved-reference" title="No equation has this label">' + esc(node.src) + '</span>'
            : '<a class="ros-eqref" href="#eq-' + esc(node.label) + '" data-ros-ref="' + esc(node.label) + '">(' + number + ')</a>';
          break;
        }
        case 'diag': out += '<span class="ros-diagnostic" data-ros="diagnostic" data-code="' + esc(node.code) + '" title="Unterminated syntax; shown as written">' + esc(node.v) + '</span>'; break;
        default: if (GROUPS.has(node.t)) out += '<' + node.t + '>' + toHTML(node.c, labels) + '</' + node.t + '>';
      }
    }
    return out;
  }

  function plainText(nodes) {
    let out = '';
    for (const node of nodes) {
      if (node.t === 'text' || node.t === 'code' || node.t === 'math' || node.t === 'diag') out += node.v;
      else if (node.t === 'br') out += ' ';
      else if (node.t === 'ref') out += node.src;
      else if (node.c) out += plainText(node.c);
    }
    return out;
  }

  // DOM construction only (createElement/createTextNode/setAttribute): authored text can never become markup.
  function renderInto(parent, nodes, doc, options = {}) {
    const make = (tag, attrs = {}) => { const el = doc.createElement(tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); return el; };
    for (const node of nodes) {
      let el = null;
      switch (node.t) {
        case 'text': parent.appendChild(doc.createTextNode(node.v)); continue;
        case 'code': el = make('code'); el.textContent = node.v; break;
        case 'math': {
          el = make('span', Object.assign({'data-ros': 'equation'}, node.display ? {'data-display': 'true'} : {}, {'data-tex': node.v, class: 'ros-math'}));
          el.textContent = node.src;
          parent.appendChild(el);
          if (options.onMath) options.onMath(el);
          continue;
        }
        case 'br': el = make('br'); break;
        case 'link':
          if (/^#[A-Za-z0-9_-]+$/.test(node.href)) { el = make('a', {href: node.href}); renderInto(el, node.c, doc, options); }
          else {
            el = make('span', {class: 'ros-link'}); renderInto(el, node.c, doc, options);
            const target = make('span', {class: 'ros-link-target'}); target.textContent = '(' + node.href + ')';
            el.appendChild(doc.createTextNode(' ')); el.appendChild(target);
          }
          break;
        case 'wikilink':
          el = validNoteTarget(node.target)
            ? make('a', {class: 'ros-note-link', href: '#ros-note-link', role: 'link', 'data-ros-target': node.target, title: node.target})
            : make('span', {class: 'ros-note-link ros-note-link-invalid', 'data-ros-target': node.target, title: node.target + ' (not a navigable note)'});
          renderInto(el, node.c, doc, options);
          break;
        case 'ref': {
          const number = options.resolveReference ? options.resolveReference(node.label) : undefined;
          if (number === undefined || number === null) { el = make('span', {class: 'ros-diagnostic', 'data-ros': 'diagnostic', 'data-code': 'unresolved-reference', title: 'No equation has this label'}); el.textContent = node.src; }
          else { el = make('a', {class: 'ros-eqref', href: '#eq-' + node.label, 'data-ros-ref': node.label}); el.textContent = '(' + number + ')'; }
          break;
        }
        case 'diag': el = make('span', {class: 'ros-diagnostic', 'data-ros': 'diagnostic', 'data-code': node.code, title: 'Unterminated syntax; shown as written'}); el.textContent = node.v; break;
        default:
          if (GROUPS.has(node.t)) { el = make(node.t); renderInto(el, node.c, doc, options); }
      }
      if (el) parent.appendChild(el);
    }
    return parent;
  }

  return {parseInline, toHTML, plainText, renderInto, esc, validNoteTarget};
});
