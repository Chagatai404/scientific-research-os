/* Research OS narration: reads a section aloud with the browser's own speech synthesis. No service, plugin or network is involved;
   tests/narration-unit.js and tests/html-narration-browser.cjs pin it. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSNarration = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  // ---------------------------------------------------------------------------------------------------------------- mathematics
  // Only constructs whose spoken form is unambiguous are read. Anything else makes the whole expression "not read aloud", because
  // a partly spoken equation can mislead more than silence does.
  const NAMES = {
    alpha: 'alpha', beta: 'beta', gamma: 'gamma', delta: 'delta', epsilon: 'epsilon', varepsilon: 'epsilon', zeta: 'zeta', eta: 'eta', theta: 'theta', vartheta: 'theta',
    iota: 'iota', kappa: 'kappa', lambda: 'lambda', mu: 'mu', nu: 'nu', xi: 'xi', pi: 'pi', rho: 'rho', varrho: 'rho', sigma: 'sigma', tau: 'tau', upsilon: 'upsilon',
    phi: 'phi', varphi: 'phi', chi: 'chi', psi: 'psi', omega: 'omega', Gamma: 'capital gamma', Delta: 'capital delta', Theta: 'capital theta', Lambda: 'capital lambda',
    Xi: 'capital xi', Pi: 'capital pi', Sigma: 'capital sigma', Phi: 'capital phi', Psi: 'capital psi', Omega: 'capital omega',
    pm: 'plus or minus', mp: 'minus or plus', times: 'times', cdot: 'dot', div: 'divided by', leq: 'is less than or equal to', le: 'is less than or equal to',
    geq: 'is greater than or equal to', ge: 'is greater than or equal to', neq: 'is not equal to', ne: 'is not equal to', approx: 'is approximately', sim: 'is similar to',
    propto: 'is proportional to', equiv: 'is equivalent to', in: 'in', notin: 'not in', subset: 'is a subset of', cup: 'union', cap: 'intersection', forall: 'for all',
    exists: 'there exists', infty: 'infinity', partial: 'partial', nabla: 'nabla', to: 'goes to', rightarrow: 'goes to', leftarrow: 'comes from', Rightarrow: 'implies',
    Leftrightarrow: 'if and only if', mapsto: 'maps to', ell: 'script l', hbar: 'h bar', circ: 'degrees', prime: 'prime', ldots: 'dot dot dot', cdots: 'dot dot dot',
    dots: 'dot dot dot', langle: 'open angle bracket', rangle: 'close angle bracket', sin: 'sine', cos: 'cosine', tan: 'tangent', log: 'log', ln: 'natural log', exp: 'exp',
    min: 'minimum', max: 'maximum', lim: 'the limit', det: 'determinant', sum: 'the sum', prod: 'the product', int: 'the integral', oint: 'the contour integral',
    sinh: 'hyperbolic sine', cosh: 'hyperbolic cosine', tanh: 'hyperbolic tangent', arg: 'argument', Pr: 'probability', Re: 'real part', Im: 'imaginary part'
  };
  const IGNORED = new Set([',', ';', ':', '!', ' ', 'quad', 'qquad', 'left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'displaystyle', 'textstyle', 'limits', 'nolimits']);
  const LABELLED = new Set(['text', 'mathrm', 'mathbf', 'mathit', 'mathsf', 'mathtt', 'mathcal', 'mathbb', 'mathfrak', 'textbf', 'textit', 'boldsymbol', 'operatorname', 'mbox']);
  const ACCENTS = {vec: ['vector ', ''], hat: ['', ' hat'], bar: ['', ' bar'], overline: ['', ' bar'], dot: ['', ' dot'], ddot: ['', ' double dot'], tilde: ['', ' tilde']};
  const OPERATORS = {'=': 'equals', '+': 'plus', '-': 'minus', '*': 'times', '/': 'divided by', '<': 'is less than', '>': 'is greater than', ',': ',', ';': ';', ':': 'colon',
    '!': 'factorial', "'": 'prime', '(': 'open paren', ')': 'close paren', '[': 'open bracket', ']': 'close bracket', '|': 'bar', '.': ''};
  const LIMIT = 600;

  function tokenize(tex) {
    const tokens = [];
    let space = false;
    for (let i = 0; i < tex.length;) {
      const c = tex[i];
      if (/\s/.test(c)) { space = true; i++; continue; }
      let token;
      if (c === '\\') {
        const m = /^\\([A-Za-z]+)/.exec(tex.slice(i));
        if (m) { token = {t: 'cmd', v: m[1]}; i += m[0].length; } else if (i + 1 < tex.length) { token = {t: 'cmd', v: tex[i + 1]}; i += 2; } else return null;
      } else {
        const number = /^\d+(?:\.\d+)?/.exec(tex.slice(i));
        if (number) { token = {t: 'num', v: number[0]}; i += number[0].length; } else { token = {t: 'ch', v: c}; i++; }
      }
      token.sp = space; space = false;
      tokens.push(token);
      if (tokens.length > LIMIT) return null;
    }
    return tokens;
  }

  function texToWords(tex) {
    const tokens = tokenize(String(tex));
    if (!tokens || tokens.length > LIMIT) return {text: '', complete: false};
    let pos = 0, complete = true;
    const fail = () => { complete = false; };
    const peek = () => tokens[pos];
    const isCh = (token, v) => token && token.t === 'ch' && token.v === v;

    function group() {  // after '{'
      const words = sequence('}');
      if (isCh(peek(), '}')) pos++; else fail();
      return words;
    }
    function atom() {   // one operand: a group or a single token
      const token = peek();
      if (!token) { fail(); return []; }
      if (isCh(token, '{')) { pos++; return group(); }
      return single();
    }
    function rawText() {  // \text{two words}: the letters as written, not spelled out
      if (!isCh(peek(), '{')) return atom();
      pos++;
      let depth = 1, text = '';
      while (pos < tokens.length) {
        const token = tokens[pos++];
        if (isCh(token, '{')) depth++;
        else if (isCh(token, '}') && --depth === 0) return [text.trim()];
        else if (token.t === 'cmd') fail();
        else text += (token.sp && text ? ' ' : '') + token.v;
      }
      fail();
      return [text.trim()];
    }
    function limits(of) {
      const out = [];
      for (let k = 0; k < 2; k++) {
        const t = peek();
        if (isCh(t, '_')) { pos++; out.push('from', ...atom()); } else if (isCh(t, '^')) { pos++; out.push('to', ...atom()); } else break;
      }
      return [of, ...out];
    }
    function single() {
      const token = tokens[pos++];
      if (token.t === 'num') return [token.v];
      if (token.t === 'ch') {
        if (token.v === '{') return group();
        if (token.v === '}' || token.v === '^' || token.v === '_' || token.v === '&' || token.v === '~' || token.v === '#' || token.v === '%') { fail(); return []; }
        if (/[A-Za-z]/.test(token.v)) return [token.v];
        if (Object.prototype.hasOwnProperty.call(OPERATORS, token.v)) return OPERATORS[token.v] ? [OPERATORS[token.v]] : [];
        if (/[\p{L}\p{N}]/u.test(token.v)) return [token.v];
        fail(); return [];
      }
      const name = token.v;
      if (IGNORED.has(name)) return [];
      if (name === '{') return ['open brace'];
      if (name === '}') return ['close brace'];
      if (name === '|') return ['norm bars'];
      if (name === '\\') { fail(); return []; }
      if (name === 'tag' || name === 'label') { atom(); return []; }  // the equation number is spoken from the page, not from the TeX
      if (name === 'nonumber' || name === 'notag') return [];
      if (name === 'frac' || name === 'dfrac' || name === 'tfrac') {
        const top = atom(), bottom = atom();
        return top.length === 1 && bottom.length === 1 ? [...top, 'over', ...bottom] : ['the fraction', ...top, 'over', ...bottom, 'end fraction'];
      }
      if (name === 'sqrt') {
        if (isCh(peek(), '[')) { fail(); return []; }
        const inside = atom();
        return ['the square root of', ...inside, ...(inside.length > 1 ? ['end root'] : [])];
      }
      if (LABELLED.has(name)) return rawText();
      if (Object.prototype.hasOwnProperty.call(ACCENTS, name)) {
        const inside = atom(), [head, tail] = ACCENTS[name];
        return [(head + inside.join(' ') + tail).trim()];
      }
      if (name === 'sum' || name === 'prod' || name === 'int' || name === 'oint') return limits(NAMES[name]);
      if (name === 'lim') return limits(NAMES.lim);
      if (Object.prototype.hasOwnProperty.call(NAMES, name)) return [NAMES[name]];
      fail(); return [];
    }
    function sequence(stop) {
      const words = [];
      while (pos < tokens.length) {
        const token = peek();
        if (stop && isCh(token, stop)) break;
        if (isCh(token, '^')) {
          pos++;
          const operand = atom();
          if (operand.length === 1 && operand[0] === '2') words.push('squared');
          else if (operand.length === 1 && operand[0] === '3') words.push('cubed');
          else if (operand.length === 1 && (operand[0] === 'degrees' || operand[0] === 'prime')) words.push(operand[0]);
          else if (operand.length === 1) words.push('to the', operand[0]);
          else words.push('to the power', ...operand, 'end power');
          continue;
        }
        if (isCh(token, '_')) {
          pos++;
          const operand = atom();
          words.push('sub', ...operand, ...(operand.length > 1 ? ['end sub'] : []));
          continue;
        }
        words.push(...single());
        if (words.length > LIMIT) { fail(); break; }
      }
      return words;
    }
    const words = sequence(null);
    return {text: complete ? words.filter(Boolean).join(' ').replace(/\s+,/g, ',').replace(/\s{2,}/g, ' ').trim() : '', complete: complete && words.length > 0};
  }

  function equationSpeech(tex, display, number) {
    const result = texToWords(tex);
    if (!result.complete) return display ? 'An equation that is not read aloud; see the page.' : 'an equation shown on the page';
    return display ? 'Equation' + (number ? ' ' + number : '') + '. ' + result.text + '.' : result.text;
  }

  // ------------------------------------------------------------------------------------------------------------------------ text
  function splitSpeech(text, max) {
    max = max || 220;
    const clean = String(text).replace(/\s+/g, ' ').trim();
    if (!clean) return [];
    if (clean.length <= max) return [clean];
    const parts = [];
    let current = '';
    for (const sentence of clean.split(/(?<=[.!?;:])\s+/)) {
      for (let piece = sentence; piece.length; ) {
        let head = piece;
        if (head.length > max) {
          const cut = head.lastIndexOf(' ', max);
          head = piece.slice(0, cut > max / 2 ? cut : max);
        }
        piece = piece.slice(head.length).trimStart();
        if (current && (current + ' ' + head).length > max) { parts.push(current); current = head; } else current = current ? current + ' ' + head : head;
      }
    }
    if (current) parts.push(current);
    return parts;
  }

  const BLOCKS = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,dt,dd,td,th,pre,figure,.ros-formula,[data-ros="equation"][data-display="true"]';
  const SKIP = '[data-question-id],.ros-question,.ros-explain,.ros-toc,.ros-nav-extra,.ros-listen,details[data-ros="solution"],[data-ros="widget"],[data-ros="legacy"],'
    + 'form,nav,button,input,textarea,select,script,style,canvas,noscript,[hidden],[aria-hidden="true"],.ros-sr-only,[data-ros-narration="skip"]';
  const isBlock = el => !!(el.matches && el.matches(BLOCKS));

  function inlineText(node, out) {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) { out.push(child.nodeValue); continue; }
      if (child.nodeType !== 1 || child.matches(SKIP) || isBlock(child)) continue;  // a nested block is spoken as its own part
      if (child.matches('.ros-math,[data-ros="equation"]')) {
        out.push(' ' + equationSpeech(child.getAttribute('data-tex') || '', child.getAttribute('data-display') === 'true', child.getAttribute('data-eq-number')) + ' ');
      } else if (child.matches('a.ros-eqref')) out.push(' equation ' + child.textContent.replace(/[()]/g, '') + ' ');
      else if (child.tagName === 'IMG') { const alt = child.getAttribute('alt'); if (alt) out.push(' image: ' + alt + '. '); }
      else if (child.tagName === 'BR') out.push(' ');
      else if (child.tagName === 'SUB') { out.push(' sub '); inlineText(child, out); out.push(' '); }
      else if (child.tagName === 'SUP') { out.push(' to the '); inlineText(child, out); out.push(' '); }
      else if (child.tagName.toLowerCase() === 'svg') { const title = child.querySelector('title'); if (title) out.push(' figure: ' + title.textContent + '. '); }
      else inlineText(child, out);
    }
  }

  function blockText(el) {
    if (el.tagName === 'PRE') return 'A code block follows; see the page.';
    if (el.matches('.ros-formula,[data-ros="equation"]')) return equationSpeech(el.getAttribute('data-tex') || '', true, el.getAttribute('data-eq-number'));
    if (el.tagName === 'FIGURE') {
      const image = el.querySelector('img'), caption = el.querySelector('figcaption'), title = el.querySelector('svg title');
      const alt = (image && image.getAttribute('alt')) || (title && title.textContent) || '';
      const out = [];
      if (caption) inlineText(caption, out);
      const said = out.join('').replace(/\s+/g, ' ').trim();
      return ('Figure' + (alt ? ': ' + alt.trim().replace(/[.]+$/, '') : '') + '.' + (said ? ' ' + said : ''));
    }
    const out = [];
    inlineText(el, out);
    let text = out.join('').replace(/\s+/g, ' ').trim();
    if (/^H[1-6]$/.test(el.tagName) && text && !/[.!?:]$/.test(text)) text += '.';
    return text;
  }

  // The speakable parts of the document between two headings (the end heading may be null for "to the end").
  function chunksFor(mount, start, end) {
    const chunks = [];
    for (const el of mount.querySelectorAll(BLOCKS)) {
      if (el !== start && !(start.compareDocumentPosition(el) & 4)) continue;
      if (end && !(end.compareDocumentPosition(el) & 2)) continue;
      if (el.closest(SKIP) || (el.closest('figure') && el.tagName !== 'FIGURE')) continue;
      if (el.parentElement && el.parentElement.closest('.ros-formula,[data-ros="equation"]')) continue;
      const text = blockText(el);
      if (text) chunks.push({element: el, text});
    }
    return chunks;
  }

  // ----------------------------------------------------------------------------------------------------------------- speaking
  function create(win) {
    const synth = win.speechSynthesis, Utterance = win.SpeechSynthesisUtterance;
    const supported = !!(synth && Utterance && typeof synth.speak === 'function' && typeof synth.cancel === 'function');
    let run = 0, queue = [], index = 0, hooks = {}, settings = {rate: 1, voiceURI: null}, state = 'idle';
    const raw = () => { try { return supported && synth.getVoices ? Array.from(synth.getVoices()) : []; } catch (_) { return []; } };
    const voices = () => raw().map(v => ({voiceURI: v.voiceURI || v.name, name: v.name, lang: v.lang || '', local: v.localService !== false, isDefault: !!v.default}));
    // On-device voices first, matching the page language when known. An online voice is never chosen for the learner.
    function defaultVoice(language) {
      const wanted = String(language || '').toLowerCase().split('-')[0];
      const local = voices().filter(v => v.local);
      return (local.find(v => wanted && v.lang.toLowerCase().startsWith(wanted)) || local.find(v => v.isDefault) || local[0] || {}).voiceURI || null;
    }
    function speakNext(token) {
      if (token !== run || state !== 'speaking') return;
      if (index >= queue.length) { state = 'idle'; hooks.end && hooks.end('finished'); return; }
      const item = queue[index];
      if (hooks.part) hooks.part(item, index, queue.length);
      const utterance = new Utterance(item.part);
      utterance.rate = settings.rate;
      const voice = settings.voiceURI ? raw().find(v => (v.voiceURI || v.name) === settings.voiceURI) : undefined;
      if (voice) { utterance.voice = voice; if (voice.lang) utterance.lang = voice.lang; }
      utterance.onend = () => { if (token === run) { index++; speakNext(token); } };
      utterance.onerror = event => {
        if (token !== run || (event && (event.error === 'canceled' || event.error === 'interrupted'))) return;
        state = 'idle'; hooks.end && hooks.end('error', event && event.error);
      };
      try { synth.speak(utterance); } catch (error) { state = 'idle'; hooks.end && hooks.end('error', String(error && error.message || error)); }
    }
    const api = {
      supported, voices, defaultVoice,
      get state() { return state; },
      start(chunks, options, callbacks) {
        api.stop(true);
        settings = Object.assign({rate: 1, voiceURI: null}, options);
        hooks = callbacks || {};
        queue = [];
        chunks.forEach((chunk, chunkIndex) => splitSpeech(chunk.text).forEach(part => queue.push({chunk, chunkIndex, part})));
        index = 0;
        if (!queue.length) { state = 'idle'; hooks.end && hooks.end('empty'); return false; }
        state = 'speaking'; run++;
        speakNext(run);
        return true;
      },
      // Pausing stops the engine and remembers the place, so it behaves the same on every platform.
      pause() { if (state !== 'speaking') return; run++; state = 'paused'; try { synth.cancel(); } catch (_) { /* nothing to cancel */ } hooks.paused && hooks.paused(); },
      resume() { if (state !== 'paused') return; state = 'speaking'; run++; speakNext(run); },
      stop(silent) {
        const was = state;
        run++; state = 'idle'; queue = []; index = 0;
        if (supported) { try { synth.cancel(); } catch (_) { /* nothing to cancel */ } }
        if (!silent && was !== 'idle' && hooks.end) hooks.end('stopped');
      },
      setRate(rate) { settings.rate = rate; },
      setVoice(uri) { settings.voiceURI = uri; }
    };
    return api;
  }

  return {texToWords, equationSpeech, splitSpeech, chunksFor, create, BLOCKS};
});
