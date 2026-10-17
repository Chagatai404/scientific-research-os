/* Research OS blackboard: performs a board script (see scripts/board_script.py) as chalk writing, formulas and drawings timed to spoken sentences.
   The script is untrusted data: text only becomes text, a path is parsed into numbers and rebuilt, colours and sizes are names from fixed tables.
   tests/board-unit.js pins the grammar and the timing; tests/html-board-browser.cjs pins the drawing in a real browser. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ResearchOSBoard = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  // ----------------------------------------------------------------------------------------------------------------- grammar (mirrors scripts/board_script.py)
  const SCHEMA = 1, WIDTH = 160, HEIGHT = 90, SVG_NS = 'http://www.w3.org/2000/svg';
  const COLORS = {chalk: '#f4f0e6', yellow: '#f6d96b', blue: '#8cc8ff', green: '#9ae6b4', pink: '#ffb4c8', orange: '#ffbd7a'};
  const SIZES = {small: 2.3, medium: 3.2, large: 4.6, huge: 6.8};   // font size as a percentage of the board width
  const HANDS = ['kalam', 'patrick', 'caveat', 'kalam-patrick', 'patrick-kalam'];   // the last two pair a title font with a body font
  const DEFAULT_HAND = 'kalam';   // chosen by the researcher over Patrick Hand (too casual) on 2026-10-17
  const MAX = {steps: 200, perStep: 12, actions: 1500, say: 600, text: 300, tex: 400, path: 1500, numbers: 300, points: 400};
  const ID = /^[A-Za-z0-9_-]{1,64}$/;
  const ARITY = {M: 2, L: 2, H: 1, V: 1, C: 6, S: 4, Q: 4, T: 2, Z: 0};
  const CONTROL = /[\x00-\x08\x0b-\x1f\x7f]/;
  const COMMON = ['op', 'id', 'delay', 'duration'];
  const OPS = {write: ['text', 'at', 'size', 'color'], math: ['tex', 'at', 'size', 'color'], draw: ['path', 'color', 'width'], arrow: ['from', 'to', 'color', 'width'],
    circle: ['at', 'r', 'color', 'width'], rect: ['at', 'w', 'h', 'color', 'width'], axes: ['at', 'w', 'h', 'color', 'width'], plot: ['points', 'color', 'width'],
    dot: ['at', 'r', 'color'], move: ['target', 'path'], highlight: ['target', 'color'], erase: ['target']};
  const REQUIRED = {write: ['text', 'at'], math: ['tex', 'at'], draw: ['path'], arrow: ['from', 'to'], circle: ['at', 'r'], rect: ['at', 'w', 'h'], axes: ['at', 'w', 'h'],
    plot: ['points'], dot: ['at'], move: ['target', 'path'], highlight: ['target'], erase: ['target']};
  const num = (v, low, high) => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
  const point = v => Array.isArray(v) && v.length === 2 && num(v[0], 0, WIDTH) && num(v[1], 0, HEIGHT);
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObject = v => v !== null && typeof v === 'object' && !Array.isArray(v);

  function tokens(d) { return String(d).match(/([MLHVCSQTZ])|(-?\d+(?:\.\d+)?)/g) || []; }

  function pathProblem(d) {
    if (typeof d !== 'string' || d.length < 1 || d.length > MAX.path) return `path must be text of 1 to ${MAX.path} characters`;
    const leftover = d.replace(/([MLHVCSQTZ])|(-?\d+(?:\.\d+)?)/g, '').replace(/[\s,]/g, '');
    if (leftover) return /[A-Za-z]/.test(leftover[0]) ? `path: unsupported command '${leftover[0]}'` : `path has unsupported text '${leftover[0]}'`;
    const list = tokens(d);
    if (!list.length || list[0] !== 'M') return 'path must start with M';
    let numbers = 0, command = null, count = 0;
    const close = () => (command !== null && ARITY[command] && (count === 0 || count % ARITY[command]) ? `path: wrong number of values for ${command}` : null);
    for (const token of list) {
      if (has(ARITY, token)) {
        const problem = close();
        if (problem) return problem;
        command = token; count = 0;
      } else {
        const value = Number(token);
        if (value < -200 || value > 400) return 'path numbers must be between -200 and 400';
        numbers++; count++;
        if (numbers > MAX.numbers) return `path has too many numbers (at most ${MAX.numbers})`;
        if (command === 'Z') return 'path: Z takes no values';
      }
    }
    return close();
  }

  // The string the page actually draws: rebuilt from the validated tokens, never the author's text.
  function normalizePath(d) { return pathProblem(d) ? null : tokens(d).join(' '); }

  function checkAction(action, where, known, problems) {
    if (!isObject(action)) { problems.push(`${where}: an action must be an object`); return; }
    const op = action.op;
    if (typeof op !== 'string' || !has(OPS, op)) { problems.push(`${where}: unknown op '${op}'`); return; }
    for (const key of Object.keys(action)) if (!COMMON.includes(key) && !OPS[op].includes(key)) problems.push(`${where}: unknown key '${key}'`);
    for (const key of REQUIRED[op]) if (!has(action, key)) problems.push(`${where}: ${op} needs '${key}'`);
    let defined = null;
    if (has(action, 'id')) {
      const id = action.id;
      if (typeof id !== 'string' || !ID.test(id)) problems.push(`${where}.id: id must be 1 to 64 letters, digits, - or _`);
      else if (known.has(id) || id === 'all') problems.push(`${where}.id: duplicate id '${id}'`);
      else defined = id;
    }
    if (has(action, 'delay') && !num(action.delay, 0, 60)) problems.push(`${where}.delay: delay must be a number from 0 to 60`);
    if (has(action, 'duration') && !num(action.duration, 0.1, 30)) problems.push(`${where}.duration: duration must be a number from 0.1 to 30`);
    if (has(action, 'color') && !(typeof action.color === 'string' && has(COLORS, action.color))) problems.push(`${where}.color: color must be one of ${Object.keys(COLORS).join(', ')}`);
    if (has(action, 'size') && !(typeof action.size === 'string' && has(SIZES, action.size))) problems.push(`${where}.size: size must be one of ${Object.keys(SIZES).join(', ')}`);
    if (has(action, 'width') && !num(action.width, 0.2, 2.0)) problems.push(`${where}.width: width must be a number from 0.2 to 2`);
    for (const key of ['at', 'from', 'to']) if (has(action, key) && !point(action[key])) problems.push(`${where}.${key}: ${key} must be [x, y] with x 0 to ${WIDTH} and y 0 to ${HEIGHT}`);
    for (const [key, high] of [['r', 80], ['w', WIDTH], ['h', HEIGHT]]) if (has(action, key) && !num(action[key], key === 'r' ? 0.2 : 1, high)) problems.push(`${where}.${key}: ${key} must be a number up to ${high}`);
    for (const [key, limit] of [['text', MAX.text], ['tex', MAX.tex]]) {
      if (has(action, key) && !(typeof action[key] === 'string' && action[key].length >= 1 && action[key].length <= limit && !CONTROL.test(action[key]))) problems.push(`${where}.${key}: ${key} must be 1 to ${limit} characters of text`);
    }
    if (has(action, 'path')) { const problem = pathProblem(action.path); if (problem) problems.push(`${where}.path: ${problem}`); }
    if (has(action, 'points')) {
      const p = action.points;
      if (!(Array.isArray(p) && p.length >= 2 && p.length <= MAX.points && p.every(point))) problems.push(`${where}.points: points must be 2 to ${MAX.points} [x, y] pairs inside the board`);
    }
    if (has(action, 'target')) {
      const t = action.target;
      if (t !== 'all' && !(typeof t === 'string' && known.has(t))) problems.push(`${where}.target: target '${t}' is not defined earlier`);
      else if ((op === 'move' || op === 'highlight') && t === 'all') problems.push(`${where}.target: ${op} needs one element, not 'all'`);
    }
    if (defined) known.add(defined);
  }

  function validate(script) {
    const problems = [];
    if (!isObject(script)) return ['a board script must be an object'];
    if (script.board_schema !== SCHEMA) problems.push(`board_schema must be ${SCHEMA}`);
    for (const key of Object.keys(script)) if (!['board_schema', 'hand', 'open', 'steps'].includes(key)) problems.push(`unknown key '${key}'`);
    if (has(script, 'hand') && !HANDS.includes(script.hand)) problems.push(`hand must be one of ${HANDS.join(', ')}`);
    if (has(script, 'open') && typeof script.open !== 'boolean') problems.push('open must be true or false');
    const steps = script.steps;
    if (!Array.isArray(steps) || steps.length < 1 || steps.length > MAX.steps) { problems.push(`steps must be a list of 1 to ${MAX.steps} steps`); return problems; }
    const known = new Set(), stepIds = new Set();
    let total = 0;
    steps.forEach((step, i) => {
      const where = `steps[${i}]`;
      if (!isObject(step)) { problems.push(`${where}: a step must be an object`); return; }
      for (const key of Object.keys(step)) if (!['id', 'say', 'do'].includes(key)) problems.push(`${where}: unknown key '${key}'`);
      if (typeof step.id !== 'string' || !ID.test(step.id)) problems.push(`${where}.id: id must be 1 to 64 letters, digits, - or _`);
      else if (stepIds.has(step.id)) problems.push(`${where}.id: duplicate id '${step.id}'`);
      else stepIds.add(step.id);
      const say = has(step, 'say') ? step.say : '', actions = has(step, 'do') ? step.do : [];
      if (typeof say !== 'string' || say.length > MAX.say || CONTROL.test(say)) problems.push(`${where}.say: say must be text of at most ${MAX.say} characters`);
      if (!Array.isArray(actions) || actions.length > MAX.perStep) { problems.push(`${where}.do: do must be a list of at most ${MAX.perStep} actions`); return; }
      if (!(typeof say === 'string' && say.trim()) && !actions.length) problems.push(`${where}: a step needs speech or an action`);
      total += actions.length;
      actions.forEach((action, j) => checkAction(action, `${where}.do[${j}]`, known, problems));
    });
    if (total > MAX.actions) problems.push(`a script may have at most ${MAX.actions} actions`);
    return problems;
  }

  // ----------------------------------------------------------------------------------------------------------------- timing
  const words = text => (String(text).match(/\S+/g) || []).length;
  // Seconds a sentence takes at normal pace plus the pause after it; the captions-only voice uses this, and a device voice's watchdog is a multiple of it.
  const estimate = (text, rate) => (Math.max(1.2, words(text) / 2.6) + 0.5) / (rate || 1);

  const realClock = {now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: handle => clearTimeout(handle)};

  // Timers that can be paused (the remaining time is kept), flushed (all fire now) or cleared.
  function createTimers(clock) {
    let paused = false;
    const live = new Set();
    function sleep(ms) {
      return new Promise(resolve => {
        const timer = {remaining: Math.max(0, ms), startedAt: clock.now(), handle: null};
        timer.fire = () => { live.delete(timer); resolve(); };
        live.add(timer);
        if (!paused) timer.handle = clock.setTimeout(timer.fire, timer.remaining);
      });
    }
    return {
      sleep,
      get paused() { return paused; },
      pause() { if (paused) return; paused = true; for (const t of live) { clock.clearTimeout(t.handle); t.remaining = Math.max(0, t.remaining - (clock.now() - t.startedAt)); } },
      resume() { if (!paused) return; paused = false; for (const t of live) { t.startedAt = clock.now(); t.handle = clock.setTimeout(t.fire, t.remaining); } },
      flush() { for (const t of [...live]) { clock.clearTimeout(t.handle); t.fire(); } },
      clear() { for (const t of live) clock.clearTimeout(t.handle); live.clear(); }
    };
  }

  // A speaker says one sentence and returns a promise that settles when it has been said. cancel() settles a pending sentence at once.
  function silentSpeaker(clock) {
    const timers = createTimers(clock || realClock);
    let rate = 1;
    return {
      kind: 'captions', supported: true,
      speak: text => timers.sleep(estimate(text, rate) * 1000),
      pause: () => timers.pause(), resume: () => timers.resume(), cancel: () => { timers.resume(); timers.flush(); },
      setRate(r) { rate = r > 0 ? r : 1; }, setVoice() {}
    };
  }

  // The device's own voice. Pausing stops the engine and re-says the sentence on resume, which behaves the same on every platform.
  function deviceSpeaker(win, clock) {
    clock = clock || realClock;
    const synth = win && win.speechSynthesis, Utterance = win && win.SpeechSynthesisUtterance;
    const supported = !!(synth && Utterance && typeof synth.speak === 'function' && typeof synth.cancel === 'function');
    let current = null, rate = 1, voiceURI = null, serial = 0;
    const voices = () => { try { return supported && synth.getVoices ? Array.from(synth.getVoices()) : []; } catch (_) { return []; } };
    function begin(entry) {
      const id = ++serial;
      entry.id = id; entry.paused = false;
      clock.clearTimeout(entry.watchdog);
      const settle = () => { if (current === entry && entry.id === id) { clock.clearTimeout(entry.watchdog); current = null; entry.resolve(); } };
      // Some engines never report the end of a sentence (for instance before the page has had a user gesture); do not stall the lecture on that.
      entry.watchdog = clock.setTimeout(settle, (estimate(entry.text, rate) * 3 + 5) * 1000);
      const utterance = new Utterance(entry.text);
      utterance.rate = rate;
      const voice = voiceURI ? voices().find(v => (v.voiceURI || v.name) === voiceURI) : null;
      if (voice) { utterance.voice = voice; if (voice.lang) utterance.lang = voice.lang; }
      utterance.onend = settle;
      utterance.onerror = event => { if (entry.paused || (event && (event.error === 'canceled' || event.error === 'interrupted') && current !== entry)) return; settle(); };
      try { synth.speak(utterance); } catch (_) { settle(); }
    }
    return {
      kind: 'device', supported, voices,
      speak(text) { return new Promise(resolve => { current = {text, resolve, id: 0, paused: false, watchdog: null}; begin(current); }); },
      pause() { if (!current || current.paused) return; current.paused = true; clock.clearTimeout(current.watchdog); try { synth.cancel(); } catch (_) { /* nothing to cancel */ } },
      resume() { if (current && current.paused) begin(current); },
      cancel() {
        const entry = current;
        current = null;
        if (entry) { clock.clearTimeout(entry.watchdog); entry.paused = true; }
        try { if (supported) synth.cancel(); } catch (_) { /* nothing to cancel */ }
        if (entry) entry.resolve();
      },
      setRate(r) { rate = r > 0 ? r : 1; }, setVoice(uri) { voiceURI = uri || null; }
    };
  }

  // ----------------------------------------------------------------------------------------------------------------- the player
  // Runs a script step by step: the sentence is spoken while the step's actions fire at their delays; the step ends when both are done.
  // effects: {apply(action, {instant, index}) -> promise, pause(), resume(), finishAll(), reset()}.
  function createPlayer(options) {
    const speaker = options.speaker, effects = options.effects, clock = options.clock || realClock, onEvent = options.onEvent || (() => {});
    const timers = createTimers(clock);
    let script = options.script, steps = script.steps, index = 0, run = 0, status = 'idle', skipping = false, reduced = !!options.reducedMotion;
    function setStatus(next) { if (status !== next) { status = next; onEvent('status', {status}); } }
    async function loop(token) {
      while (token === run) {
        if (index >= steps.length) { setStatus(script.open ? 'waiting' : 'done'); return; }
        setStatus('playing');
        const i = index, step = steps[i];
        skipping = false;
        onEvent('step', {index: i, step});
        const jobs = [];
        if (typeof step.say === 'string' && step.say.trim()) jobs.push(Promise.resolve().then(() => speaker.speak(step.say.trim(), {index: i})).catch(() => {}));
        for (const action of step.do || []) {
          const wait = action.delay > 0 ? timers.sleep(action.delay * 1000) : Promise.resolve();
          jobs.push(wait.then(() => (token === run ? effects.apply(action, {instant: reduced || skipping, index: i}) : null)).catch(() => {}));
        }
        await Promise.all(jobs);
        if (token !== run) return;
        onEvent('step-done', {index: i});
        index = i + 1;
      }
    }
    const api = {
      get status() { return status; },
      get index() { return index; },
      get steps() { return steps; },
      set reducedMotion(value) { reduced = !!value; },
      start() {
        if (status === 'paused') return api.resume();
        if (status === 'playing') return undefined;
        if (status === 'done' || status === 'revised') return api.replay();
        run++; loop(run);
        return undefined;
      },
      pause() { if (status !== 'playing') return; speaker.pause(); timers.pause(); effects.pause(); setStatus('paused'); },
      resume() { if (status !== 'paused') return; speaker.resume(); timers.resume(); effects.resume(); setStatus('playing'); },
      skip() {
        if (status === 'paused') api.resume();
        if (status !== 'playing') return;
        skipping = true;
        speaker.cancel(); timers.flush();
        Promise.resolve().then(() => effects.finishAll());
      },
      replay() { run++; timers.clear(); speaker.cancel(); effects.reset(); index = 0; status = 'idle'; onEvent('reset', {}); api.start(); },
      stop() { run++; timers.clear(); speaker.cancel(); effects.finishAll(); setStatus('idle'); },
      // A live update. Steps already started must be unchanged; new steps after them are played as they arrive.
      update(next) {
        const problems = validate(next);
        if (problems.length) return {ok: false, problems};
        const started = Math.min(index + (status === 'playing' || status === 'paused' ? 1 : 0), steps.length);
        const same = next.steps.length >= started && steps.slice(0, started).every((s, i) => next.steps[i].id === s.id);
        script = next;
        if (!same) {
          run++; timers.clear(); speaker.cancel(); effects.reset(); steps = next.steps; index = 0; status = 'idle'; onEvent('reset', {});
          setStatus('revised');
          return {ok: true, revised: true};
        }
        steps = next.steps;
        onEvent('steps', {count: steps.length, open: !!next.open});
        if (status === 'waiting' && index < steps.length) { run++; loop(run); }
        else if (status === 'waiting' && !next.open) setStatus('done');
        else if (status === 'done' && next.open) setStatus('waiting');
        return {ok: true, revised: false};
      }
    };
    return api;
  }

  // ----------------------------------------------------------------------------------------------------------------- the drawing (needs a DOM)
  function createEffects(ctx) {
    const {doc, surface, ink, layer, pen, renderMath} = ctx;
    const items = new Map();
    const running = new Set();
    const svg = (name, attributes) => { const el = doc.createElementNS(SVG_NS, name); for (const [k, v] of Object.entries(attributes || {})) el.setAttribute(k, String(v)); return el; };
    const scale = () => (surface.clientWidth || 800) / WIDTH;
    const f = n => (Math.round(n * 100) / 100);
    const colour = action => COLORS[action.color] || COLORS.chalk;
    function track(animation) {
      running.add(animation);
      const done = () => running.delete(animation);
      return animation.finished.then(done, done);
    }
    function remember(action, el) { if (action.id) items.set(action.id, el); return el; }
    function penAlong(samples, duration) {
      if (!pen.animate || !samples.length) return;
      pen.hidden = false;
      pen.style.left = '0px'; pen.style.top = '0px';
      const animation = pen.animate(samples.map(([x, y]) => ({transform: `translate(${f(x)}px, ${f(y)}px)`})), {duration: duration * 1000, easing: 'linear', fill: 'forwards'});
      track(animation).then(() => { pen.hidden = true; try { animation.cancel(); } catch (_) { /* already gone */ } });
    }
    function wipe(el, duration, instant) {
      if (instant || !el.animate) return Promise.resolve();
      el.style.clipPath = 'inset(-12% 100% -12% -2%)';
      const animation = el.animate([{clipPath: 'inset(-12% 100% -12% -2%)'}, {clipPath: 'inset(-12% -2% -12% -2%)'}], {duration: duration * 1000, easing: 'linear', fill: 'forwards'});
      penAlong([[el.offsetLeft, el.offsetTop + el.offsetHeight * 0.55], [el.offsetLeft + el.offsetWidth, el.offsetTop + el.offsetHeight * 0.55]], duration);
      return track(animation).then(() => { el.style.clipPath = ''; try { animation.cancel(); } catch (_) { /* already gone */ } });
    }
    function drawPath(d, action, duration, instant) {
      const path = svg('path', {d, fill: 'none', stroke: colour(action), 'stroke-width': action.width || 0.9, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', pathLength: 1});
      path.setAttribute('class', 'ros-board-stroke');
      ink.append(path);
      remember(action, path);
      if (instant || !path.animate) return Promise.resolve();
      path.style.strokeDasharray = '1 1';
      const animation = path.animate([{strokeDashoffset: 1}, {strokeDashoffset: 0}], {duration: duration * 1000, easing: 'ease-in-out', fill: 'forwards'});
      try {
        const total = path.getTotalLength(), k = scale(), samples = [];
        for (let i = 0; i <= 28; i++) { const p = path.getPointAtLength(total * i / 28); samples.push([p.x * k, p.y * k]); }
        penAlong(samples, duration);
      } catch (_) { /* no geometry available: the stroke still draws */ }
      return track(animation).then(() => { path.style.strokeDasharray = ''; try { animation.cancel(); } catch (_) { /* already gone */ } });
    }
    function arrowPath(a, b, head) {
      const angle = Math.atan2(b[1] - a[1], b[0] - a[0]), wing = Math.PI / 7, h = head || 2.6;
      const side = k => `${f(b[0] - h * Math.cos(angle + k))} ${f(b[1] - h * Math.sin(angle + k))}`;
      return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]} M ${side(wing)} L ${b[0]} ${b[1]} L ${side(-wing)}`;
    }
    function textItem(action, className) {
      const el = doc.createElement('div');
      el.className = 'ros-board-item ' + className;
      el.setAttribute('data-size', SIZES[action.size] ? action.size : 'medium');
      el.style.left = f(action.at[0] / WIDTH * 100) + '%';
      el.style.top = f(action.at[1] / HEIGHT * 100) + '%';
      el.style.setProperty('--fs', String(SIZES[action.size] || SIZES.medium));
      el.style.setProperty('--ink', colour(action));
      layer.append(el);
      remember(action, el);
      return el;
    }
    function pulse(el, duration) {
      if (!el.animate) return Promise.resolve();
      const frames = el.namespaceURI === SVG_NS
        ? [0.9, 2.6, 0.9, 2.6, 0.9].map(w => ({strokeWidth: String(w)}))
        : [1, 1.12, 1, 1.12, 1].map(s => ({transform: `scale(${s})`}));
      return track(el.animate(frames, {duration: duration * 1000, easing: 'ease-in-out'}));
    }
    return {
      apply(action, how) {
        const instant = !!(how && how.instant), d = action.duration;
        switch (action.op) {
          case 'write': {
            const el = textItem(action, 'ros-board-write');
            el.textContent = action.text;
            return wipe(el, d || Math.min(6, Math.max(0.5, action.text.length * 0.055)), instant);
          }
          case 'math': {
            const el = textItem(action, 'ros-board-math');
            el.setAttribute('data-tex', action.tex);
            el.textContent = action.tex;
            if (renderMath) renderMath(el);
            return wipe(el, d || Math.min(5, Math.max(0.8, action.tex.length * 0.05)), instant);
          }
          case 'draw': return drawPath(normalizePath(action.path), action, d || 1.4, instant);
          case 'arrow': return drawPath(arrowPath(action.from, action.to), action, d || 0.9, instant);
          case 'circle': { const [x, y] = action.at, r = action.r; return drawPath(`M ${f(x - r)} ${y} A ${r} ${r} 0 1 0 ${f(x + r)} ${y} A ${r} ${r} 0 1 0 ${f(x - r)} ${y}`, action, d || 1.1, instant); }
          case 'rect': { const [x, y] = action.at; return drawPath(`M ${x} ${y} H ${f(x + action.w)} V ${f(y + action.h)} H ${x} Z`, action, d || 1.2, instant); }
          case 'axes': {
            const [x, y] = action.at;
            return drawPath(arrowPath([x, y], [x, f(y - action.h)], 2.2) + ' ' + arrowPath([x, y], [f(x + action.w), y], 2.2), action, d || 1.4, instant);
          }
          case 'plot': return drawPath('M ' + action.points.map(p => `${p[0]} ${p[1]}`).join(' L '), action, d || 1.8, instant);
          case 'dot': {
            const el = svg('circle', {cx: action.at[0], cy: action.at[1], r: action.r || 1.4, fill: colour(action)});
            el.setAttribute('class', 'ros-board-dot');
            ink.append(el); remember(action, el);
            if (instant || !el.animate) return Promise.resolve();
            return track(el.animate([{opacity: 0}, {opacity: 1}], {duration: 250, fill: 'backwards'}));
          }
          case 'move': {
            const el = items.get(action.target), route = normalizePath(action.path);
            if (!el || !route) return Promise.resolve();
            const probe = svg('path', {d: route});
            ink.append(probe);
            let samples = [];
            try { const total = probe.getTotalLength(); for (let i = 0; i <= 40; i++) samples.push(probe.getPointAtLength(total * i / 40)); } catch (_) { samples = []; }
            probe.remove();
            if (!samples.length) return Promise.resolve();
            const x0 = Number(el.getAttribute('cx')), y0 = Number(el.getAttribute('cy'));
            const frames = samples.map(p => ({transform: `translate(${f(p.x - x0)}px, ${f(p.y - y0)}px)`}));
            const last = frames[frames.length - 1].transform;
            if (instant || !el.animate) { el.style.transform = last; return Promise.resolve(); }
            const animation = el.animate(frames, {duration: (d || 2) * 1000, easing: 'ease-in-out', fill: 'forwards'});
            return track(animation).then(() => { el.style.transform = last; try { animation.cancel(); } catch (_) { /* already gone */ } });
          }
          case 'highlight': { const el = items.get(action.target); return el && !instant ? pulse(el, d || 1.2) : Promise.resolve(); }
          case 'erase': {
            const all = action.target === 'all';
            const targets = all ? [...ink.querySelectorAll('.ros-board-stroke,.ros-board-dot'), ...layer.querySelectorAll('.ros-board-item')] : [items.get(action.target)];
            const unique = [...new Set(targets.filter(Boolean))];
            if (all) items.clear(); else items.delete(action.target);
            if (instant || !unique.length || !unique[0].animate) { unique.forEach(el => el.remove()); return Promise.resolve(); }
            return Promise.all(unique.map(el => track(el.animate([{opacity: 1}, {opacity: 0}], {duration: (d || 0.6) * 1000, fill: 'forwards'})).then(() => el.remove())));
          }
          default: return Promise.resolve();
        }
      },
      pause() { for (const a of running) { try { a.pause(); } catch (_) { /* finished */ } } },
      resume() { for (const a of running) { try { a.play(); } catch (_) { /* finished */ } } },
      finishAll() { for (const a of [...running]) { try { a.finish(); } catch (_) { /* finished */ } } },
      reset() {
        for (const a of [...running]) { try { a.cancel(); } catch (_) { /* finished */ } }
        running.clear(); items.clear();
        for (const el of [...ink.querySelectorAll('.ros-board-stroke,.ros-board-dot'), ...layer.children]) el.remove();
        pen.hidden = true;
      }
    };
  }

  // ----------------------------------------------------------------------------------------------------------------- the widget
  const STATUS_TEXT = {idle: 'Ready. Press Start.', playing: 'Lecturing', paused: 'Paused', waiting: 'Waiting for the tutor to continue', done: 'Finished',
    revised: 'The tutor revised the lecture. Press Replay.'};

  let boardCount = 0;
  function mount(container, script, options) {
    options = options || {};
    const doc = options.doc || container.ownerDocument;
    const win = options.win || doc.defaultView || {};
    const problems = validate(script);
    const node = (tag, text, className) => { const el = doc.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
    if (problems.length) {
      container.append(node('p', 'This board script cannot be shown: ' + problems.slice(0, 3).join('; ')));
      return {status: 'invalid', update() { return {ok: false, problems}; }, destroy() {}};
    }
    const figure = node('figure', undefined, 'ros-board');
    figure.setAttribute('data-hand', script.hand || DEFAULT_HAND);
    const frame = node('div', undefined, 'ros-board-frame');
    const surface = node('div', undefined, 'ros-board-surface');
    surface.setAttribute('role', 'img');
    surface.setAttribute('aria-label', 'Blackboard. The text alternative is the transcript below.');
    const ink = doc.createElementNS(SVG_NS, 'svg');
    ink.setAttribute('class', 'ros-board-ink'); ink.setAttribute('viewBox', `0 0 ${WIDTH} ${HEIGHT}`); ink.setAttribute('aria-hidden', 'true');
    // Roughened edges, so strokes look like chalk on slate. The filter is local to this board.
    const filterId = 'ros-chalk-' + (++boardCount);
    const defs = doc.createElementNS(SVG_NS, 'defs'), filter = doc.createElementNS(SVG_NS, 'filter');
    filter.setAttribute('id', filterId);
    const noise = doc.createElementNS(SVG_NS, 'feTurbulence');
    for (const [k, v] of [['type', 'fractalNoise'], ['baseFrequency', '0.9'], ['numOctaves', '2'], ['seed', '4'], ['result', 'noise']]) noise.setAttribute(k, v);
    const displace = doc.createElementNS(SVG_NS, 'feDisplacementMap');
    for (const [k, v] of [['in', 'SourceGraphic'], ['in2', 'noise'], ['scale', '0.4'], ['xChannelSelector', 'R'], ['yChannelSelector', 'G']]) displace.setAttribute(k, v);
    filter.append(noise, displace); defs.append(filter); ink.append(defs);
    ink.style.filter = `url(#${filterId})`;
    const layer = node('div', undefined, 'ros-board-text');
    layer.setAttribute('aria-hidden', 'true');
    const pen = node('div', undefined, 'ros-board-pen');
    pen.hidden = true;
    const hint = node('div', 'Press Start', 'ros-board-hint');
    surface.append(ink, layer, pen, hint);
    frame.append(surface);
    const bar = node('div', undefined, 'ros-board-bar');
    const play = node('button', 'Start', 'ros-board-play'); play.type = 'button';
    const skip = node('button', 'Skip step'); skip.type = 'button';
    const replay = node('button', 'Replay'); replay.type = 'button';
    const voiceLabel = node('label', 'Voice '), voice = node('select'); voiceLabel.append(voice);
    const rateLabel = node('label', 'Speed '), rate = node('select'); rateLabel.append(rate);
    for (const r of [0.8, 0.9, 1, 1.1, 1.25]) { const o = node('option', r === 1 ? 'Normal' : r + '×'); o.value = String(r); if (r === 1) o.selected = true; rate.append(o); }
    const state = node('span', undefined, 'ros-board-state'); state.setAttribute('role', 'status');
    bar.append(play, skip, replay, voiceLabel, rateLabel, state);
    const caption = node('p', '', 'ros-board-caption');
    const transcript = node('details', undefined, 'ros-board-transcript');
    transcript.append(node('summary', 'Transcript and what is written on the board'));
    const list = node('ol');
    transcript.append(list);
    figure.append(frame, bar, caption, transcript);
    container.append(figure);

    const speakers = {};
    const device = deviceSpeaker(win, options.clock);
    if (device.supported) speakers.device = device;
    speakers.captions = silentSpeaker(options.clock);
    for (const [id, extra] of Object.entries(options.speakers || {})) if (extra && typeof extra.speak === 'function') speakers[id] = extra;
    const labels = Object.assign({device: 'Device voice', captions: 'Captions only (timed)'}, options.speakerLabels || {});
    for (const id of Object.keys(speakers)) { const o = node('option', labels[id] || id); o.value = id; voice.append(o); }
    const initial = options.speaker && speakers[options.speaker] ? options.speaker : (speakers.device ? 'device' : 'captions');
    let speaker = speakers[initial];
    voice.value = initial;

    const reduced = options.reducedMotion !== undefined ? !!options.reducedMotion : !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const effects = createEffects({doc, surface, ink, layer, pen, renderMath: options.renderMath});
    const speakerProxy = {speak: (t, o) => speaker.speak(t, o), pause: () => speaker.pause(), resume: () => speaker.resume(), cancel: () => speaker.cancel()};
    // Text is sized from the board's own width in pixels, so it scales with the board without container-query units.
    function fitText() { surface.style.setProperty('--bw', (surface.clientWidth || 800) + 'px'); }
    fitText();
    let observer = null;
    if (win.ResizeObserver) { observer = new win.ResizeObserver(fitText); observer.observe(surface); } else if (win.addEventListener) win.addEventListener('resize', fitText);

    function renderTranscript(s) {
      list.textContent = '';
      for (const step of s.steps) {
        const li = node('li'); li.setAttribute('data-step', step.id);
        li.append(node('span', step.say || '(silent drawing)'));
        const written = (step.do || []).filter(a => a.op === 'write' || a.op === 'math').map(a => (a.op === 'write' ? a.text : a.tex));
        if (written.length) li.append(node('small', ' On the board: ' + written.join(' | '), 'ros-board-written'));
        list.append(li);
      }
    }
    renderTranscript(script);
    function mark(i) { for (const li of list.children) li.removeAttribute('aria-current'); if (list.children[i]) list.children[i].setAttribute('aria-current', 'step'); }

    function refresh() {
      const s = player.status;
      state.textContent = STATUS_TEXT[s] || s;
      play.textContent = s === 'playing' ? 'Pause' : s === 'paused' ? 'Resume' : s === 'done' ? 'Play again' : s === 'waiting' ? 'Waiting…' : s === 'revised' ? 'Replay' : 'Start';
      play.disabled = s === 'waiting';
      skip.disabled = !(s === 'playing' || s === 'paused');
      figure.setAttribute('data-status', s);
    }
    const player = createPlayer({
      script, speaker: speakerProxy, effects, clock: options.clock, reducedMotion: reduced,
      onEvent(type, data) {
        if (type === 'step') { hint.hidden = true; caption.textContent = data.step.say || ''; mark(data.index); }
        if (type === 'reset') { hint.hidden = false; caption.textContent = ''; mark(-1); }
        if (type === 'status' || type === 'reset') refresh();
        if (options.onEvent) options.onEvent(type, data);
      }
    });
    play.addEventListener('click', () => { const s = player.status; if (s === 'playing') player.pause(); else if (s === 'paused') player.resume(); else player.start(); });
    skip.addEventListener('click', () => player.skip());
    replay.addEventListener('click', () => player.replay());
    voice.addEventListener('change', () => {
      if (player.status === 'playing' || player.status === 'paused') speaker.cancel();
      speaker = speakers[voice.value];
      speaker.setRate(Number(rate.value));
    });
    rate.addEventListener('change', () => { for (const s of Object.values(speakers)) s.setRate(Number(rate.value)); });
    refresh();

    return {
      player, figure,
      get status() { return player.status; },
      start: () => player.start(), pause: () => player.pause(), resume: () => player.resume(), skip: () => player.skip(), replay: () => player.replay(),
      update(next) {
        const result = player.update(next);
        if (result.ok) {
          figure.setAttribute('data-hand', next.hand || DEFAULT_HAND);
          renderTranscript(next);
          mark(player.status === 'playing' || player.status === 'paused' ? player.index : -1);
          refresh();
        }
        return result;
      },
      destroy() { player.stop(); effects.reset(); if (observer) observer.disconnect(); figure.remove(); }
    };
  }

  return {SCHEMA, WIDTH, HEIGHT, COLORS, SIZES, HANDS, MAX, validate, pathProblem, normalizePath, estimate, createTimers, silentSpeaker, deviceSpeaker, createPlayer, mount};
});
