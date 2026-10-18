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
  // Text and formulas are placed either at a point (`at`, optionally wrapped to a width `w`) or in a named zone of the board (`zone`), where they stack from the top
  // of the zone, wrap to its width and push the next item down. Drawings always use board coordinates.
  const ZONES = {title: {x: 5, y: 2, w: 150, h: 15}, left: {x: 5, y: 18, w: 60, h: 62}, right: {x: 70, y: 18, w: 85, h: 62}, body: {x: 5, y: 18, w: 150, h: 62}, caption: {x: 5, y: 81, w: 150, h: 8}};
  const OPS = {write: ['text', 'at', 'zone', 'w', 'size', 'color'], math: ['tex', 'at', 'zone', 'w', 'size', 'color'], draw: ['path', 'color', 'width'], arrow: ['from', 'to', 'color', 'width'],
    circle: ['at', 'r', 'color', 'width'], rect: ['at', 'w', 'h', 'color', 'width'], axes: ['at', 'w', 'h', 'color', 'width'], plot: ['points', 'color', 'width'],
    dot: ['at', 'r', 'color'], move: ['target', 'path'], highlight: ['target', 'color'], erase: ['target']};
  const REQUIRED = {write: ['text'], math: ['tex'], draw: ['path'], arrow: ['from', 'to'], circle: ['at', 'r'], rect: ['at', 'w', 'h'], axes: ['at', 'w', 'h'],
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
    if (op === 'write' || op === 'math') {
      if (!has(action, 'at') && !has(action, 'zone')) problems.push(`${where}: ${op} needs 'at' (a point) or 'zone' (${Object.keys(ZONES).join(', ')})`);
      else if (has(action, 'at') && has(action, 'zone')) problems.push(`${where}: ${op} takes 'at' or 'zone', not both`);
      if (has(action, 'zone') && !(typeof action.zone === 'string' && has(ZONES, action.zone))) problems.push(`${where}.zone: zone must be one of ${Object.keys(ZONES).join(', ')}`);
      if (has(action, 'w') && !has(action, 'at')) problems.push(`${where}.w: w sets the width of text placed with 'at'; a zone has its own width`);
    }
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

  // ----------------------------------------------------------------------------------------------------------------- layout (mirrors scripts/board_script.py)
  // Where text and drawings go and whether they fit. One algorithm serves two uses: a script is checked before it is shown, with text extents estimated from the
  // hand's glyph widths (layoutProblems), and the page places each item with the extents it measured, shifting new text to the next free slot (createEffects).
  // All numbers are board units (160 x 90). The estimates describe the default hand (Kalam) only; tests/fixtures/board-cases.json pins them in both languages.
  // Advance widths of Kalam in 1/1000 em, measured in real Chrome by tests/board-metrics-probe.cjs: ascii is U+0020..U+007E, extra is the rest of Latin-1 and Latin Extended-A.
  const FONT = {
    regular: {ascii: [401,371,331,656,534,890,704,145,485,504,357,600,228,459,237,354,500,314,581,571,551,537,556,461,602,488,246,306,539,631,561,518,965,608,637,599,645,585,523,611,670,310,468,591,546,789,677,613,543,641,584,531,535,598,532,782,624,575,620,453,600,450,422,608,213,469,525,445,499,450,376,475,536,238,254,469,245,796,533,453,478,474,331,426,387,481,422,673,427,469,440,421,368,538,594], extra: {' ':401,'¡':354,'¢':482,'£':657,'¤':600,'¥':563,'¦':369,'§':464,'¨':273,'©':708,'ª':474,'«':657,'¬':496,'®':589,'¯':365,'°':339,'±':600,'²':308,'³':311,'´':219,'µ':575,'¶':521,'·':237,'¸':252,'¹':154,'º':452,'»':833,'¼':783,'½':787,'¾':876,'¿':380,'À':608,'Á':608,'Â':608,'Ã':608,'Ä':608,'Å':608,'Æ':831,'Ç':603,'È':585,'É':585,'Ê':585,'Ë':585,'Ì':310,'Í':310,'Î':310,'Ï':310,'Ð':619,'Ñ':677,'Ò':613,'Ó':613,'Ô':613,'Õ':613,'Ö':613,'×':488,'Ø':613,'Ù':592,'Ú':592,'Û':592,'Ü':592,'Ý':575,'Þ':503,'ß':585,'à':472,'á':472,'â':472,'ã':472,'ä':472,'å':472,'æ':743,'ç':447,'è':438,'é':438,'ê':438,'ë':438,'ì':238,'í':238,'î':238,'ï':238,'ð':452,'ñ':532,'ò':452,'ó':452,'ô':452,'õ':452,'ö':452,'÷':600,'ø':457,'ù':479,'ú':479,'û':479,'ü':479,'ý':469,'þ':526,'ÿ':469,'Ā':608,'ā':472,'Ă':608,'ă':472,'Ą':608,'ą':472,'Ć':685,'ć':447,'Ĉ':667,'ĉ':444,'Ċ':667,'ċ':444,'Č':692,'č':447,'Ď':645,'ď':732,'Đ':625,'đ':508,'Ē':585,'ē':438,'Ĕ':611,'ĕ':444,'Ė':585,'ė':438,'Ę':585,'ę':438,'Ě':585,'ě':438,'Ĝ':722,'ĝ':500,'Ğ':611,'ğ':471,'Ġ':722,'ġ':500,'Ģ':611,'ģ':471,'Ĥ':722,'ĥ':500,'Ħ':722,'ħ':500,'Ĩ':333,'ĩ':278,'Ī':310,'ī':238,'Ĭ':333,'ĭ':278,'Į':310,'į':238,'İ':310,'ı':260,'Ĳ':708,'ĳ':552,'Ĵ':389,'ĵ':278,'Ķ':602,'ķ':495,'ĸ':500,'Ĺ':546,'ĺ':234,'Ļ':546,'ļ':234,'Ľ':546,'ľ':448,'Ŀ':611,'ŀ':344,'Ł':514,'ł':362,'Ń':677,'ń':532,'Ņ':677,'ņ':532,'Ň':677,'ň':532,'ŉ':604,'Ŋ':702,'ŋ':495,'Ō':613,'ō':452,'Ŏ':722,'ŏ':500,'Ő':613,'ő':452,'Œ':940,'œ':906,'Ŕ':575,'ŕ':318,'Ŗ':575,'ŗ':326,'Ř':575,'ř':318,'Ś':526,'ś':426,'Ŝ':556,'ŝ':389,'Ş':539,'ş':426,'Š':526,'š':426,'Ţ':521,'ţ':364,'Ť':521,'ť':432,'Ŧ':611,'ŧ':278,'Ũ':722,'ũ':500,'Ū':592,'ū':479,'Ŭ':722,'ŭ':500,'Ů':592,'ů':479,'Ű':592,'ű':479,'Ų':579,'ų':479,'Ŵ':944,'ŵ':722,'Ŷ':722,'ŷ':500,'Ÿ':575,'Ź':620,'ź':432,'Ż':620,'ż':432,'Ž':620,'ž':432,'ſ':278,'‐':333,'‑':333,'‒':500,'–':610,'—':917,'―':1000,'‖':281,'‗':500,'‘':287,'’':286,'‚':291,'‛':333,'“':491,'”':487,'„':485,'‟':444,'†':403,'‡':500,'•':237,'‣':350,'․':333,'‥':666,'…':666,'‧':250}},
    bold: {ascii: [385,478,484,780,592,991,786,220,478,530,375,600,262,531,237,282,513,302,583,547,545,506,542,472,590,506,246,306,475,672,616,608,1078,630,624,617,666,551,542,597,651,309,486,602,546,756,631,619,549,659,601,552,544,595,532,785,585,561,646,463,600,521,422,619,258,510,567,489,539,488,435,481,563,260,260,493,266,819,554,456,538,519,362,467,451,486,422,710,474,520,480,462,456,626,586], extra: {' ':385,'¡':425,'¢':545,'£':732,'¤':600,'¥':615,'¦':455,'§':529,'¨':335,'©':708,'ª':536,'«':426,'¬':496,'®':671,'¯':377,'°':421,'±':600,'²':335,'³':300,'´':266,'µ':439,'¶':592,'·':237,'¸':301,'¹':161,'º':452,'»':833,'¼':823,'½':858,'¾':962,'¿':396,'À':631,'Á':631,'Â':631,'Ã':631,'Ä':631,'Å':631,'Æ':899,'Ç':629,'È':551,'É':551,'Ê':551,'Ë':551,'Ì':309,'Í':309,'Î':309,'Ï':309,'Ð':649,'Ñ':631,'Ò':619,'Ó':619,'Ô':619,'Õ':619,'Ö':619,'×':433,'Ø':619,'Ù':578,'Ú':578,'Û':578,'Ü':578,'Ý':561,'Þ':535,'ß':599,'à':518,'á':518,'â':518,'ã':518,'ä':518,'å':518,'æ':770,'ç':493,'è':454,'é':454,'ê':454,'ë':454,'ì':260,'í':260,'î':260,'ï':260,'ð':452,'ñ':552,'ò':452,'ó':452,'ô':452,'õ':452,'ö':452,'÷':600,'ø':452,'ù':479,'ú':479,'û':479,'ü':479,'ý':520,'þ':526,'ÿ':520,'Ā':631,'ā':518,'Ă':631,'ă':518,'Ą':631,'ą':518,'Ć':629,'ć':493,'Ĉ':722,'ĉ':444,'Ċ':722,'ċ':444,'Č':629,'č':493,'Ď':666,'ď':779,'Đ':666,'đ':508,'Ē':551,'ē':454,'Ĕ':667,'ĕ':444,'Ė':551,'ė':454,'Ę':551,'ę':454,'Ě':551,'ě':454,'Ĝ':778,'ĝ':500,'Ğ':597,'ğ':471,'Ġ':778,'ġ':500,'Ģ':597,'ģ':471,'Ĥ':778,'ĥ':556,'Ħ':778,'ħ':556,'Ĩ':389,'ĩ':278,'Ī':309,'ī':260,'Ĭ':389,'ĭ':278,'Į':309,'į':260,'İ':309,'ı':260,'Ĳ':823,'ĳ':552,'Ĵ':500,'ĵ':333,'Ķ':602,'ķ':495,'ĸ':556,'Ĺ':546,'ĺ':234,'Ļ':546,'ļ':234,'Ľ':546,'ľ':501,'Ŀ':667,'ŀ':396,'Ł':546,'ł':383,'Ń':631,'ń':552,'Ņ':631,'ņ':552,'Ň':631,'ň':552,'ŉ':729,'Ŋ':769,'ŋ':556,'Ō':619,'ō':452,'Ŏ':778,'ŏ':500,'Ő':619,'ő':452,'Œ':950,'œ':906,'Ŕ':575,'ŕ':326,'Ŗ':575,'ŗ':326,'Ř':575,'ř':326,'Ś':539,'ś':467,'Ŝ':556,'ŝ':389,'Ş':539,'ş':467,'Š':539,'š':467,'Ţ':505,'ţ':364,'Ť':505,'ť':522,'Ŧ':667,'ŧ':333,'Ũ':722,'ũ':556,'Ū':578,'ū':479,'Ŭ':722,'ŭ':556,'Ů':578,'ů':479,'Ű':578,'ű':479,'Ų':543,'ų':479,'Ŵ':1000,'ŵ':722,'Ŷ':722,'ŷ':500,'Ÿ':561,'Ź':646,'ź':459,'Ż':646,'ż':459,'Ž':646,'ž':459,'ſ':278,'‐':333,'‑':333,'‒':500,'–':624,'—':968,'―':1000,'‖':324,'‗':500,'‘':352,'’':352,'‚':346,'‛':333,'“':606,'”':595,'„':569,'‟':500,'†':539,'‡':500,'•':237,'‣':350,'․':333,'‥':667,'…':795,'‧':250}}};
  const FALLBACK = 560, TRACKING = 10;          // an unknown character, and the letter-spacing (.01em) the board's text carries
  const LINE = 1.25;                              // line height, as a multiple of the font size (board.css uses the same number)
  const GAP = 1.5, PAD = 0.6, STEP = 1, EDGE = 0.5;   // space between stacked items, clearance when looking for a free slot, search step, margin kept from the board's edge
  const INSET_X = 0.1, INSET_Y = 0.2;             // a line box is taller than the ink in it: the part of the font size trimmed from each side before boxes are compared
  const MIN_SHRINK = 0.6, MATH_EM = 1.05;        // a formula that is too wide shrinks to at least this fraction; the formula's em as a multiple of the item's font size (board.css)
  const fontUnits = size => (SIZES[size] || SIZES.medium) * WIDTH / 100;
  const isBold = size => size === 'large' || size === 'huge';

  function advance(ch, bold) {
    const table = bold ? FONT.bold : FONT.regular, code = ch.codePointAt(0);
    return (code >= 32 && code <= 126 ? table.ascii[code - 32] : has(table.extra, ch) ? table.extra[ch] : FALLBACK) + TRACKING;
  }
  const textWidth = (s, fs, bold) => { let w = 0; for (const ch of s) w += advance(ch, bold); return w / 1000 * fs; };

  // Greedy wrapping at spaces, the way the page wraps; a word wider than the line is not split here (the page may split it), it is reported as too wide.
  function wrapText(text, fs, bold, maxWidth) {
    const space = advance(' ', bold) / 1000 * fs;
    let lines = 0, widest = 0, tooWide = false;
    for (const paragraph of String(text).split('\n')) {
      let current = 0, started = false;
      lines++;
      for (const word of paragraph.split(' ')) {
        const w = textWidth(word, fs, bold);
        if (w > maxWidth + 1e-9) tooWide = true;
        if (!started) { current = w; started = true; }
        else if (current + space + w <= maxWidth + 1e-9) current += space + w;
        else { widest = Math.max(widest, current); lines++; current = w; }
      }
      widest = Math.max(widest, current);
    }
    return {width: widest, height: lines * LINE * fs, lines, tooWide};
  }

  // A formula's size in em, from a small reading of the TeX: good to roughly a tenth for the formulas a lecture writes, never a substitute for the page's own measurement.
  const GREEK = new Set('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega'.split(' '));
  const GREEK_UP = new Set('Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega'.split(' '));
  const RELATION = new Set('le leq ge geq ne neq approx sim simeq equiv to rightarrow leftarrow Rightarrow Leftarrow leftrightarrow Leftrightarrow mapsto in notin subset subseteq supset supseteq propto ll gg perp parallel cong'.split(' '));
  const BINARY = new Set('pm mp times div cup cap setminus oplus otimes wedge vee ast star circ bullet'.split(' '));
  const NAMED = new Set('sin cos tan cot sec csc log ln exp lim min max sup inf det dim arg gcd deg Pr ker'.split(' '));
  const WRAPPERS = new Set('text textbf textit mathrm mathbf mathit mathbb mathcal mathsf mathtt boldsymbol operatorname'.split(' '));
  const ACCENTS = new Set('bar hat vec tilde dot ddot overline underline widehat widetilde'.split(' '));
  const SPACES = {quad: 1, qquad: 2, ',': 0.17, ':': 0.22, ';': 0.28, '!': -0.17, ' ': 0.28};
  const SYMBOLS = {cdot: 0.72, infty: 1, partial: 0.57, nabla: 0.83, ldots: 1.17, cdots: 1.17, dots: 1.17, vdots: 0.3, prime: 0.3, hbar: 0.55, ell: 0.42};
  function glyphEm(ch) {
    if (/^[a-z]$/.test(ch)) return 0.52;
    if (/^[A-Z]$/.test(ch)) return 0.7;
    if (/^[0-9]$/.test(ch)) return 0.5;
    if (ch === '=' || ch === '<' || ch === '>') return 1.33;
    if (ch === '+' || ch === '-' || ch === '−') return 1.22;
    if ('()[]'.includes(ch)) return 0.39;
    if (ch === '|' || ch === '.' || ch === '!') return 0.28;
    if (ch === ',' || ch === ';') return 0.45;
    if (ch === '/' || ch === ':') return 0.52;
    if (ch === '*') return 0.8;
    if (ch === "'") return 0.3;
    return 0.6;
  }
  function mathBox(tex) {
    const t = (String(tex).match(/\\[A-Za-z]+|\\[\s\S]|[{}^_]|\s+|[\s\S]/g) || []).filter(s => !/^\s+$/.test(s));
    let i = 0;
    const box = (w, h) => ({w, h: h === undefined ? 1.2 : h});
    function command(name) {
      if (name === 'frac' || name === 'dfrac' || name === 'tfrac' || name === 'binom') {
        const a = base(), b = base(), s = name === 'dfrac' ? 1 : 0.7;
        return box(s * Math.max(a.w, b.w) + 0.2, s * 0.82 * (a.h + b.h));
      }
      if (name === 'sqrt') {
        if (t[i] === '[') { while (i < t.length && t[i] !== ']') i++; i++; }
        const a = base();
        return box(1 + a.w, Math.max(a.h, 1.2) + 0.15);
      }
      if (name === 'left') { i++; const inner = sequence(false, true); return box(inner.w + 1, inner.h > 1.3 ? inner.h * 1.25 + 0.2 : inner.h + 0.15); }   // sizes the delimiters to what is inside
      if (name === 'right') { i++; return box(0.5); }
      if (WRAPPERS.has(name)) return base();
      if (ACCENTS.has(name)) { const a = base(); return box(a.w, a.h + 0.2); }
      if (name === 'sum' || name === 'prod') return box(1, 1.5);
      if (name === 'int' || name === 'oint') return box(0.56, 1.8);
      if (has(SPACES, name)) return box(SPACES[name], 0);
      if (has(SYMBOLS, name)) return box(SYMBOLS[name]);
      if (GREEK.has(name)) return box(0.6);
      if (GREEK_UP.has(name)) return box(0.72);
      if (RELATION.has(name)) return box(1.33);
      if (BINARY.has(name)) return box(1.22);
      if (NAMED.has(name)) return box(name.length * 0.5 + 0.28);
      return box(0.7);
    }
    function base() {
      const tok = t[i++];
      if (tok === undefined || tok === '}') return box(0, 0);
      if (tok === '{') return sequence(true);
      if (tok[0] === '\\') return command(tok.slice(1));
      return box(glyphEm(tok));
    }
    function withScripts(b) {
      let up = null, down = null;
      while (t[i] === '^' || t[i] === '_') { const which = t[i++], s = base(); if (which === '^') up = s; else down = s; }
      if (!up && !down) return b;
      const w = Math.max(up ? up.w : 0, down ? down.w : 0) * 0.7 + 0.05;
      return box(b.w + w, b.h + (up && down ? 0.3 : 0.1));
    }
    function sequence(braced, untilRight) {
      let w = 0, h = 0;
      while (i < t.length) {
        if (untilRight && t[i] === '\\right') { i += 2; break; }
        if (t[i] === '}') { i++; if (braced) break; continue; }
        const b = withScripts(base());
        w += b.w; h = Math.max(h, b.h);
      }
      return box(w, h || 1.2);
    }
    return sequence(false);
  }

  // Width, height and font size (units) of a write or math action, for a script that has not been drawn: wrapped to its zone or its `w`, a formula shrunk to fit.
  function estimateItem(action) {
    const size = action.size || 'medium', fs = fontUnits(size), zone = has(action, 'zone') ? ZONES[action.zone] : null;
    const limit = zone ? zone.w : (has(action, 'w') ? action.w : Infinity);
    if (action.op === 'write') {
      const t = wrapText(action.text, fs, isBold(size), limit);
      return {w: t.width, h: t.height, fs, wide: t.tooWide};
    }
    const m = mathBox(action.tex), em = fs * MATH_EM;
    let w = m.w * em, h = m.h * em, scale = 1;
    if (w > limit) { scale = Math.max(MIN_SHRINK, limit / w); w *= scale; h *= scale; }
    return {w, h, fs: fs * scale, wide: w > limit + 1e-9};
  }

  // The ink of a drawing as polylines in board units (curves sampled): what a text box must stay clear of.
  function curve(points, steps, out) {
    for (let k = 1; k <= steps; k++) {
      const u = k / steps, v = 1 - u;
      if (points.length === 4) out.push([v * v * v * points[0][0] + 3 * v * v * u * points[1][0] + 3 * v * u * u * points[2][0] + u * u * u * points[3][0],
        v * v * v * points[0][1] + 3 * v * v * u * points[1][1] + 3 * v * u * u * points[2][1] + u * u * u * points[3][1]]);
      else out.push([v * v * points[0][0] + 2 * v * u * points[1][0] + u * u * points[2][0], v * v * points[0][1] + 2 * v * u * points[1][1] + u * u * points[2][1]]);
    }
  }
  function sampledPath(d) {
    const t = tokens(d), polys = [];
    let cur = null, i = 0, cmd = null, x = 0, y = 0, sx = 0, sy = 0, last = null;   // last: {kind: 'c' | 'q', control: [x, y]} of the previous curve, for S and T
    const take = n => { const a = []; for (let k = 0; k < n; k++) a.push(Number(t[i++])); return a; };
    const begin = () => { if (!cur) { cur = [[x, y]]; polys.push(cur); } };
    while (i < t.length) {
      if (has(ARITY, t[i])) { cmd = t[i++]; if (cmd === 'Z') { if (cur) { cur.push([sx, sy]); x = sx; y = sy; cur = null; } last = null; continue; } }
      let next = null;
      if (cmd === 'M') { [x, y] = take(2); sx = x; sy = y; cur = [[x, y]]; polys.push(cur); cmd = 'L'; }
      else if (cmd === 'L') { begin(); [x, y] = take(2); cur.push([x, y]); }
      else if (cmd === 'H') { begin(); [x] = take(1); cur.push([x, y]); }
      else if (cmd === 'V') { begin(); [y] = take(1); cur.push([x, y]); }
      else if (cmd === 'C') { begin(); const [a, b, c, e, f, g] = take(6); curve([[x, y], [a, b], [c, e], [f, g]], 8, cur); next = {kind: 'c', control: [c, e]}; x = f; y = g; }
      else if (cmd === 'S') { begin(); const [c, e, f, g] = take(4), a = last && last.kind === 'c' ? [2 * x - last.control[0], 2 * y - last.control[1]] : [x, y]; curve([[x, y], a, [c, e], [f, g]], 8, cur); next = {kind: 'c', control: [c, e]}; x = f; y = g; }
      else if (cmd === 'Q') { begin(); const [a, b, f, g] = take(4); curve([[x, y], [a, b], [f, g]], 6, cur); next = {kind: 'q', control: [a, b]}; x = f; y = g; }
      else if (cmd === 'T') { begin(); const [f, g] = take(2), a = last && last.kind === 'q' ? [2 * x - last.control[0], 2 * y - last.control[1]] : [x, y]; curve([[x, y], a, [f, g]], 6, cur); next = {kind: 'q', control: a}; x = f; y = g; }
      else break;
      last = next;
    }
    return polys;
  }
  function arrowInk(a, b, head) {
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]), wing = Math.PI / 7, h = head || 2.6;
    const side = k => [b[0] - h * Math.cos(angle + k), b[1] - h * Math.sin(angle + k)];
    return [[a, b], [side(wing), b, side(-wing)]];
  }
  function squareInk(c, r) { return [[[c[0] - r, c[1] - r], [c[0] + r, c[1] - r], [c[0] + r, c[1] + r], [c[0] - r, c[1] + r], [c[0] - r, c[1] - r]]]; }
  function inkOf(action) {
    switch (action.op) {
      case 'draw': return sampledPath(normalizePath(action.path));
      case 'arrow': return arrowInk(action.from, action.to, 2.6);
      case 'circle': { const ring = []; for (let k = 0; k <= 24; k++) ring.push([action.at[0] + action.r * Math.cos(2 * Math.PI * k / 24), action.at[1] + action.r * Math.sin(2 * Math.PI * k / 24)]); return [ring]; }
      case 'rect': { const [x, y] = action.at; return [[[x, y], [x + action.w, y], [x + action.w, y + action.h], [x, y + action.h], [x, y]]]; }
      case 'axes': { const [x, y] = action.at; return [...arrowInk([x, y], [x, y - action.h], 2.2), ...arrowInk([x, y], [x + action.w, y], 2.2)]; }
      case 'plot': return [action.points.map(p => [p[0], p[1]])];
      case 'dot': return squareInk(action.at, action.r || 1.4);
      default: return [];
    }
  }
  // Does the segment p-q touch the box [x0, y0, x1, y1] (Liang-Barsky)?
  function segmentHitsBox(p, q, box) {
    const dx = q[0] - p[0], dy = q[1] - p[1];
    let t0 = 0, t1 = 1;
    for (const [d, gap] of [[-dx, p[0] - box[0]], [dx, box[2] - p[0]], [-dy, p[1] - box[1]], [dy, box[3] - p[1]]]) {
      if (d === 0) { if (gap < 0) return false; continue; }
      const r = gap / d;
      if (d < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; }
    }
    return true;
  }
  const polyHitsBox = (poly, box) => (poly.length === 1 ? poly[0][0] >= box[0] && poly[0][0] <= box[2] && poly[0][1] >= box[1] && poly[0][1] <= box[3] : poly.some((p, k) => k > 0 && segmentHitsBox(poly[k - 1], p, box)));
  const boxesTouch = (a, b, pad) => a[0] < b[2] + pad && b[0] < a[2] + pad && a[1] < b[3] + pad && b[1] < a[3] + pad;
  const grow = (box, pad) => [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad];
  const num1 = n => (Math.round(n * 10) / 10).toString();

  // The state of a board: what is on it, where, and the problems found placing it. `shift` is for the live page, where a new item that would land on something
  // else is moved down to the next free slot; a script check leaves positions alone and reports.
  function createLayout(options) {
    const shift = !!(options && options.shift);
    const alive = [], moved = [], problems = [], seen = new Set();
    const note = (where, text) => problems.push({message: `layout ${where}: ${text}`});
    const pair = (where, a, b) => {
      const key = [a.key, b.key].sort().join('|');
      if (seen.has(key)) return;
      seen.add(key);
      note(where, `${a.label} collides with ${b.label}${b.step ? ` (step '${b.step}')` : ''}`);
    };
    const clash = (box, pad) => alive.find(e => (e.kind === 'text' ? boxesTouch(box, e.box, pad) : e.polys.some(p => polyHitsBox(p, grow(box, pad / 2))))) || null;
    const cursor = name => alive.reduce((y, e) => (e.zone === name ? Math.max(y, e.full[3] + GAP) : y), ZONES[name].y);
    const drop = key => { const k = alive.findIndex(e => e.key === key); if (k >= 0) alive.splice(k, 1); };
    return {
      get alive() { return alive; }, moved, problems,
      cursor,
      // spec: {key, label, where, step, zone | null, at, w, h, fs, wide}; w and h are the item's own width and height.
      addText(s) {
        drop(s.key);
        const z = s.zone ? ZONES[s.zone] : null;
        const x = z ? z.x : s.at[0], y0 = z ? cursor(s.zone) : s.at[1];
        let y = y0;
        const limit = z ? z.y + z.h : HEIGHT - EDGE;
        const boxOf = yy => [x + INSET_X * s.fs, yy + INSET_Y * s.fs, x + s.w - INSET_X * s.fs, yy + s.h - INSET_Y * s.fs];
        let box = boxOf(y), hit = clash(box, z ? PAD : 0), settled = false;
        if (z && y + s.h > limit + 1e-9) { note(s.where, `zone '${s.zone}' is full: no room for ${s.label} (${num1(s.h)} units tall)`); settled = true; hit = null; }
        else if (hit && (z || shift)) {
          let found = null;
          for (let yy = y + STEP; yy + s.h <= limit + 1e-9; yy += STEP) if (!clash(boxOf(yy), PAD)) { found = yy; break; }
          if (found !== null) { y = found; box = boxOf(y); hit = null; moved.push({key: s.key, label: s.label, step: s.step, from: [x, y0], to: [x, y]}); }
          else if (z) { note(s.where, `zone '${s.zone}' is full: no room for ${s.label} below what is already there`); hit = null; settled = true; }
        }
        if (s.wide) note(s.where, z ? `${s.label} is too wide for zone '${s.zone}' (${num1(s.w)} units, the zone is ${z.w})` : `${s.label} is too wide (${num1(s.w)} units): give it a smaller size or a width`);
        if (!settled && (box[2] > WIDTH - EDGE + 1e-9 || box[0] < EDGE - 1e-9 || box[3] > HEIGHT - EDGE + 1e-9 || box[1] < EDGE - 1e-9)) note(s.where, `${s.label} leaves the board (it spans x ${num1(x)} to ${num1(x + s.w)}, y ${num1(y)} to ${num1(y + s.h)})`);
        if (hit) pair(s.where, {key: s.key, label: s.label}, hit);
        alive.push({key: s.key, kind: 'text', label: s.label, step: s.step, zone: s.zone || null, box, full: [x, y, x + s.w, y + s.h]});
        return {x, y, moved: y !== y0};
      },
      // spec: {key, label, where, step, polys}
      addInk(s) {
        drop(s.key);
        const outside = s.polys.some(p => p.some(q => q[0] < -1e-9 || q[0] > WIDTH + 1e-9 || q[1] < -1e-9 || q[1] > HEIGHT + 1e-9));
        if (outside) note(s.where, `${s.label} leaves the board`);
        for (const e of alive) if (e.kind === 'text' && s.polys.some(p => polyHitsBox(p, e.box))) pair(s.where, {key: s.key, label: s.label}, e);
        alive.push({key: s.key, kind: 'ink', label: s.label, step: s.step, polys: s.polys, radius: s.radius || 0});
      },
      // A dot has moved to a new centre.
      moveInk(key, where, to) {
        const e = alive.find(a => a.key === key);
        if (!e || e.kind !== 'ink' || !e.radius) return;
        e.polys = squareInk(to, e.radius);
        if (e.polys.some(p => p.some(q => q[0] < 0 || q[0] > WIDTH || q[1] < 0 || q[1] > HEIGHT))) note(where, `${e.label} moves off the board`);
        for (const o of alive) if (o.kind === 'text' && e.polys.some(p => polyHitsBox(p, o.box))) pair(where, e, o);
      },
      remove: drop,
      clear() { alive.length = 0; },
      report() { return {moved: moved.slice(), problems: problems.map(p => p.message), items: alive.map(e => ({key: e.key, kind: e.kind, label: e.label, step: e.step, zone: e.zone || null, box: e.full || null}))}; },
      reset() { alive.length = 0; moved.length = 0; problems.length = 0; seen.clear(); }
    };
  }

  const snippet = s => { const flat = String(s).replace(/\s+/g, ' ').trim(); return flat.length > 28 ? flat.slice(0, 25) + '...' : flat; };
  function labelOf(action) {
    if (action.op === 'write') return `text "${snippet(action.text)}"`;
    if (action.op === 'math') return `formula "${snippet(action.tex)}"`;
    return `the ${action.op}${action.id ? ` '${action.id}'` : ''}`;
  }
  // Applies one action to a layout. measure(action) -> {w, h, fs, wide} gives a write or math item's size (estimated for a script check, measured by the page).
  // ctx: {where, step (id), i, j}. Returns the placement of a write or math item.
  function layOut(layout, action, ctx, measure) {
    const key = action.id || `#${ctx.i}.${ctx.j}`;
    switch (action.op) {
      case 'write': case 'math': {
        const m = measure(action);
        return layout.addText({key, label: labelOf(action), where: ctx.where, step: ctx.step, zone: action.zone || null, at: action.at, w: m.w, h: m.h, fs: m.fs, wide: m.wide});
      }
      case 'move': {
        const route = normalizePath(action.path);
        if (!route) return null;
        const polys = sampledPath(route), end = polys.length ? polys[polys.length - 1][polys[polys.length - 1].length - 1] : null;
        if (end) layout.moveInk(action.target, ctx.where, end);
        return null;
      }
      case 'erase': if (action.target === 'all') layout.clear(); else layout.remove(action.target); return null;
      case 'highlight': return null;
      default: layout.addInk({key, label: labelOf(action), where: ctx.where, step: ctx.step, polys: inkOf(action), radius: action.op === 'dot' ? (action.r || 1.4) : 0}); return null;
    }
  }

  // The layout of a whole script as estimated from the text's glyph widths: {moved, problems (strings), items}. The script must be valid.
  function layoutScript(script) {
    const layout = createLayout({shift: false});
    (script.steps || []).forEach((step, i) => (step.do || []).forEach((action, j) => layOut(layout, action, {where: `steps[${i}] (step '${step.id}') do[${j}]`, step: step.id, i, j}, estimateItem)));
    return layout.report();
  }
  function layoutProblems(script) { return validate(script).length ? [] : layoutScript(script).problems; }

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

  // Recorded sentences: a clip per step (found by the step's id), played through an audio element; the silence the delivery puts after a sentence is waited out
  // afterwards, with timers that can be paused. A step with no clip, a clip that will not play, and one that never ends are said by `fallback` instead (the device
  // voice, or timed captions), so the lecture never stops. clips: {stepId: {url, seconds, pause}}, built by the page's builder, never by the script.
  const clipOk = c => !!c && typeof c.url === 'string' && c.url.length > 0 && (c.url.startsWith('data:audio/') || !/^[a-z][a-z0-9+.-]*:/i.test(c.url)) &&
    num(c.seconds, 0.1, 600) && num(c.pause, 0, 5);
  function audioSpeaker(win, clips, fallback, clock) {
    clock = clock || realClock;
    const Player = win && win.Audio;
    const ready = {};
    for (const id of Object.keys(clips || {})) if (clipOk(clips[id])) ready[id] = clips[id];
    const supported = typeof Player === 'function' && Object.keys(ready).length > 0;
    const timers = createTimers(clock);
    let rate = 1, current = null;
    function release(entry) {
      clock.clearTimeout(entry.watchdog);
      if (entry.audio) {
        for (const [type, fn] of entry.listeners) entry.audio.removeEventListener(type, fn);
        try { entry.audio.pause(); } catch (_) { /* nothing playing */ }
      }
    }
    function finish(entry) {
      if (entry.done) return;
      entry.done = true; release(entry);
      if (current === entry) current = null;
      entry.resolve();
    }
    // The sentence is said by the fallback voice from the start (the clip failed or is missing).
    function useFallback(entry) {
      if (entry.done || entry.delegate) return;
      release(entry); entry.audio = null;
      entry.delegate = fallback;
      fallback.speak(entry.text, entry.opts).then(() => finish(entry), () => finish(entry));
      if (entry.paused) fallback.pause();
    }
    function arm(entry) {
      clock.clearTimeout(entry.watchdog);
      entry.watchdog = clock.setTimeout(() => useFallback(entry), (entry.clip.seconds / rate * 1.5 + 5) * 1000);
    }
    function play(entry) {
      try {
        const started = entry.audio.play();
        if (started && typeof started.catch === 'function') started.catch(() => useFallback(entry));
      } catch (_) { useFallback(entry); }
    }
    return {
      kind: 'recorded', supported, fallback, clips: ready,
      has: id => supported && has(ready, id),
      speak(text, opts) {
        const clip = supported && opts && typeof opts.id === 'string' && has(ready, opts.id) ? ready[opts.id] : null;
        return new Promise(resolve => {
          const entry = {text, opts, clip, resolve, done: false, paused: false, ended: false, delegate: null, audio: null, listeners: [], watchdog: null};
          current = entry;
          if (!clip) { useFallback(entry); return; }
          let audio;
          try { audio = new Player(clip.url); } catch (_) { useFallback(entry); return; }
          entry.audio = audio;
          audio.playbackRate = rate;
          const onEnded = () => {
            entry.ended = true;
            clock.clearTimeout(entry.watchdog);
            timers.sleep(clip.pause / rate * 1000).then(() => finish(entry));
          };
          entry.listeners = [['ended', onEnded], ['error', () => useFallback(entry)]];
          for (const [type, fn] of entry.listeners) audio.addEventListener(type, fn);
          arm(entry);
          play(entry);
        });
      },
      pause() {
        timers.pause();
        const entry = current;
        if (!entry || entry.done || entry.paused) return;
        entry.paused = true;
        if (entry.delegate) { fallback.pause(); return; }
        clock.clearTimeout(entry.watchdog);
        try { if (entry.audio && !entry.ended) entry.audio.pause(); } catch (_) { /* nothing playing */ }
      },
      resume() {
        timers.resume();
        const entry = current;
        if (!entry || entry.done || !entry.paused) return;
        entry.paused = false;
        if (entry.delegate) { fallback.resume(); return; }
        if (entry.audio && !entry.ended) { arm(entry); play(entry); }
      },
      cancel() {
        const entry = current;
        current = null;
        timers.resume(); timers.flush();
        if (!entry) return;
        if (entry.delegate) fallback.cancel();
        finish(entry);
      },
      setRate(r) {
        rate = r > 0 ? r : 1;
        if (current && current.audio) current.audio.playbackRate = rate;
        fallback.setRate(rate);
      },
      setVoice(uri) { if (fallback.setVoice) fallback.setVoice(uri); }
    };
  }

  // The tutor's live voice. Nothing is recorded in advance: each sentence is turned into speech when it is wanted (the page asks for the next one or two while the
  // current one plays, so the voice runs on without gaps), by whatever `live.request(id, text)` reaches (the Obsidian host and its voice worker). The audio is
  // played with Web Audio, so a page that may not fetch media can still speak and pausing is exact. If a sentence cannot be spoken live (no worker, an error,
  // too slow), `fallback` says it and the reason is reported once; the lecture never stops. live: {request(id, text) -> Promise<{wav}>, cancel(id), pause, audioContext?}.
  function liveSpeaker(win, live, fallback, clock) {
    clock = clock || realClock;
    const Context = win && (win.AudioContext || win.webkitAudioContext);
    const supported = !!(live && typeof live.request === 'function' && (typeof live.audioContext === 'function' || typeof Context === 'function'));
    const gap = live && num(live.pause, 0, 5) ? live.pause : 0.5;
    const timers = createTimers(clock);
    const cache = new Map();
    let context = null, rate = 1, serial = 0, current = null, paused = false, failed = null, reported = false;
    const speaker = {kind: 'live', supported, fallback, onProblem: null, onWait: null};
    const audio = () => { if (!context) context = typeof live.audioContext === 'function' ? live.audioContext() : new Context(); return context; };
    function decode(bytes) {
      return new Promise((resolve, reject) => { const result = audio().decodeAudioData(bytes, resolve, reject); if (result && typeof result.then === 'function') result.then(resolve, reject); });
    }
    function fetchBuffer(text) {
      if (cache.has(text)) return cache.get(text).promise;
      const entry = {id: 'u' + (++serial), done: false};
      entry.promise = Promise.resolve().then(() => live.request(entry.id, text)).then(result => {
        if (!result || !result.wav || !result.wav.byteLength) throw new Error('The live voice sent no audio.');
        return decode(result.wav);
      }).then(buffer => { entry.done = true; return buffer; }, error => { cache.delete(text); failed = failed || String(error && error.message || error).slice(0, 300); throw error; });   // one failure stops the asking
      entry.promise.catch(() => {});   // a sentence fetched ahead that nobody wanted must not report an unhandled failure
      cache.set(text, entry);
      while (cache.size > 8) { const [oldText, old] = cache.entries().next().value; cache.delete(oldText); if (!old.done && typeof live.cancel === 'function') live.cancel(old.id); }
      return entry.promise;
    }
    Object.assign(speaker, {
      // Called from a click, so the browser lets the audio start later without a fresh gesture.
      unlock() { if (!supported) return; const c = audio(); if (c.state === 'suspended' && typeof c.resume === 'function') { const r = c.resume(); if (r && r.catch) r.catch(() => {}); } },
      retry() { failed = null; reported = false; },
      prefetch(texts) {
        if (!supported || failed) return;
        for (const text of (texts || []).slice(0, 3)) { const clean = typeof text === 'string' ? text.trim() : ''; if (clean) fetchBuffer(clean); }
      },
      speak(text, opts) {
        const clean = String(text || '').trim();
        if (!clean) return Promise.resolve();
        return new Promise(resolve => {
          const entry = {done: false, source: null, delegate: false};
          current = entry;
          const finish = () => { if (entry.done) return; entry.done = true; clock.clearTimeout(entry.wait); if (current === entry) current = null; resolve(); };
          entry.finish = finish;
          const delegate = (reason, quiet) => {
            if (entry.done || entry.delegate) return;
            clock.clearTimeout(entry.wait); if (speaker.onWait) speaker.onWait(false);
            failed = failed || reason;
            if (!quiet && !reported) { reported = true; if (speaker.onProblem) speaker.onProblem(failed); }   // said once, whichever request failed first
            entry.delegate = true;
            fallback.speak(clean, opts).then(finish, finish);
            if (paused) fallback.pause();
          };
          if (!supported) { delegate('this page cannot play live audio', true); return; }
          if (failed) { delegate(failed, false); return; }
          entry.wait = clock.setTimeout(() => { if (!entry.done && speaker.onWait) speaker.onWait(true); }, 400);
          fetchBuffer(clean).then(buffer => {
            clock.clearTimeout(entry.wait); if (speaker.onWait) speaker.onWait(false);
            if (entry.done) return;
            const c = audio(), source = c.createBufferSource();
            source.buffer = buffer; source.playbackRate.value = rate; source.connect(c.destination);
            entry.source = source;
            source.onended = () => { if (!entry.done && !entry.delegate) timers.sleep(gap / rate * 1000).then(finish); };
            const go = () => { try { source.start(0); } catch (_) { delegate('the audio could not start'); } };
            if (c.state === 'suspended' && !paused && typeof c.resume === 'function') { const r = c.resume(); if (r && r.then) r.then(go, go); else go(); } else go();
          }).catch(error => delegate(String(error && error.message || error).slice(0, 300)));
        });
      },
      pause() {
        paused = true; timers.pause();
        if (current && current.delegate) fallback.pause();
        else if (context && typeof context.suspend === 'function') { const r = context.suspend(); if (r && r.catch) r.catch(() => {}); }
      },
      resume() {
        paused = false; timers.resume();
        if (current && current.delegate) fallback.resume();
        else if (context && typeof context.resume === 'function') { const r = context.resume(); if (r && r.catch) r.catch(() => {}); }
      },
      cancel() {
        const entry = current; paused = false;
        if (entry) {
          if (entry.source) { entry.source.onended = null; try { entry.source.stop(); } catch (_) { /* not started */ } }
          if (entry.delegate) fallback.cancel();
        }
        timers.resume(); timers.flush();
        if (context && context.state === 'suspended' && typeof context.resume === 'function') { const r = context.resume(); if (r && r.catch) r.catch(() => {}); }
        if (entry) entry.finish();
      },
      setRate(r) { rate = r > 0 ? r : 1; if (current && current.source) { try { current.source.playbackRate.value = rate; } catch (_) { /* ended */ } } fallback.setRate(rate); },
      setVoice() {}
    });
    return speaker;
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
        // A live voice stays a sentence or two ahead, so the next one is ready when this one ends.
        if (typeof speaker.prefetch === 'function') speaker.prefetch(steps.slice(i, i + 3).map(s => s.say));
        const jobs = [];
        if (typeof step.say === 'string' && step.say.trim()) jobs.push(Promise.resolve().then(() => speaker.speak(step.say.trim(), {index: i, id: step.id})).catch(() => {}));
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
      // Resume: from idle, draw everything the steps before `id` put on the board at once (nothing is said) and wait to play from `id`. False when it cannot.
      seek(id) {
        const target = steps.findIndex(s => s.id === id);
        if (status !== 'idle' || index !== 0 || target < 1) return false;
        for (let i = 0; i < target; i++) for (const action of steps[i].do || []) { try { Promise.resolve(effects.apply(action, {instant: true, index: i})).catch(() => {}); } catch (_) { /* one bad action must not stop the rest */ } }
        index = target;
        onEvent('seek', {index: target});
        return true;
      },
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
    // ------------------------------------------------------------------------------------------------- where things go
    // Everything is placed in board units, text and drawings alike. Each text item is measured after it is rendered and put through the same layout the script check
    // uses; one that would land on something else is moved to the next free slot of its zone (or below, for a point) and the move is reported.
    const layout = createLayout({shift: true});
    const stepIdOf = ctx.stepOf || (() => '');
    let chain = Promise.resolve(), counter = 0;
    const unitPx = () => { const r = surface.getBoundingClientRect ? surface.getBoundingClientRect() : null; return r && r.width > 20 ? r.width / WIDTH : 0; };
    const settled = el => {   // fonts used by the item are loaded (or a couple of seconds have passed) before it is measured
      const fonts = doc.fonts;
      void el.offsetWidth;
      if (!fonts || !fonts.ready || typeof fonts.ready.then !== 'function') return Promise.resolve();
      let timer = null;
      return Promise.race([fonts.ready, new Promise(resolve => { timer = setTimeout(resolve, 2500); })]).then(() => clearTimeout(timer), () => clearTimeout(timer));
    };
    // The ink of a formula: its glyphs, radicals and rules (a fraction's numerator rises above the line box).
    function inkRect(el) {
      const root = el.querySelector('.katex-html') || el, rects = [];
      const walker = doc.createTreeWalker(root, 4);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!/[^\s​]/.test(n.nodeValue)) continue;
        const range = doc.createRange();
        range.selectNodeContents(n);
        for (const q of range.getClientRects()) if (q.width > 0) rects.push(q);
      }
      for (const q of root.querySelectorAll('svg,.frac-line,.sqrt-line,.rule,.overline-line,.underline-line')) rects.push(q.getBoundingClientRect());
      if (!rects.length) return el.getBoundingClientRect();
      const left = Math.min(...rects.map(q => q.left)), right = Math.max(...rects.map(q => q.right)), top = Math.min(...rects.map(q => q.top)), bottom = Math.max(...rects.map(q => q.bottom));
      return {left, right, top, bottom, width: right - left, height: bottom - top};
    }
    // The size of a rendered item in board units: {w, h, fs, wide}. Text wraps to its zone (or its `w`); a formula too wide for its place shrinks to fit.
    function measure(el, action, u) {
      const size = action.size || 'medium', zone = action.zone ? ZONES[action.zone] : null;
      const limit = zone ? zone.w : (has(action, 'w') ? action.w : null);
      const base = fontUnits(size);
      let fs = base, wide = false;
      el.setAttribute('data-wrap', limit ? '1' : '0');
      el.style.width = limit ? f(limit / WIDTH * 100) + '%' : '';
      el.style.paddingTop = el.style.paddingBottom = '';
      el.style.setProperty('--fs', String(SIZES[size] || SIZES.medium));
      if (action.op === 'math') {
        let box = inkRect(el);
        if (limit && box.width / u > limit + 1e-6) {
          const k = Math.max(MIN_SHRINK, limit / (box.width / u));
          fs = base * k;
          el.style.setProperty('--fs', String((SIZES[size] || SIZES.medium) * k));
          box = inkRect(el);
          wide = box.width / u > limit + 0.05;
        }
        const own = el.getBoundingClientRect();
        if (box.height > own.height + 0.5) el.style.paddingTop = el.style.paddingBottom = f((box.height - own.height) / 2) + 'px';   // the box now holds all the ink
        return {w: box.width / u, h: el.getBoundingClientRect().height / u, fs, wide};
      }
      const range = doc.createRange();
      range.selectNodeContents(el);
      const w = range.getBoundingClientRect().width / u;
      return {w: limit ? Math.min(w, limit) : w, h: el.getBoundingClientRect().height / u, fs, wide};   // the box is as wide as its line at most (the range also counts the last letter's spacing)
    }
    // Renders, measures and places one text item. Items are placed one at a time in the order they were asked for, so a zone stacks in the order of the script.
    function place(el, action, how) {
      el.style.visibility = 'hidden';
      const run = chain.then(() => settled(el)).then(() => {
        if (!el.isConnected) return;
        const u = unitPx();
        const stepId = stepIdOf(how && how.index);
        let m = u ? measure(el, action, u) : estimateItem(action);
        const spec = {where: `step '${stepId}'`, step: stepId, i: (how && how.index) || 0, j: ++counter};
        // A line placed with `at` and no width that would leave the right edge wraps there instead.
        if (u && !action.zone && !has(action, 'w') && action.op === 'write' && action.at[0] + m.w > WIDTH - EDGE) {
          const room = Math.max(5, WIDTH - EDGE - action.at[0]);
          el.setAttribute('data-wrap', '1'); el.style.width = f(room / WIDTH * 100) + '%';
          const range = doc.createRange();
          range.selectNodeContents(el);
          m = {w: Math.min(range.getBoundingClientRect().width / u, room), h: el.getBoundingClientRect().height / u, fs: m.fs, wide: false};
          layout.moved.push({key: action.id || `#${spec.i}.${spec.j}`, label: action.text, step: stepId, wrapped: true});
        }
        const placed = layOut(layout, action, {where: spec.where, step: stepId, i: spec.i, j: spec.j}, () => m);
        el.style.left = f(placed.x / WIDTH * 100) + '%';
        el.style.top = f(placed.y / HEIGHT * 100) + '%';
        el.style.visibility = '';
        if (ctx.onLayout) ctx.onLayout(layout.report());
      });
      chain = run.catch(() => {});
      return run;
    }
    // Drawings are registered in the same order as the text, after the text asked for before them has been placed.
    function registerInk(action, how) {
      const stepId = stepIdOf(how && how.index), spec = {where: `step '${stepId}'`, step: stepId, i: (how && how.index) || 0, j: ++counter};
      chain = chain.then(() => {
        const before = layout.problems.length;
        layOut(layout, action, spec, null);
        if (ctx.onLayout && layout.problems.length !== before) ctx.onLayout(layout.report());
      }).catch(() => {});
    }
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
      el.style.left = '0%';
      el.style.top = '0%';
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
            return place(el, action, how).then(() => wipe(el, d || Math.min(6, Math.max(0.5, action.text.length * 0.055)), instant));
          }
          case 'math': {
            const el = textItem(action, 'ros-board-math');
            el.setAttribute('data-tex', action.tex);
            el.textContent = action.tex;
            if (renderMath) renderMath(el);
            return place(el, action, how).then(() => wipe(el, d || Math.min(5, Math.max(0.8, action.tex.length * 0.05)), instant));
          }
          case 'draw': registerInk(action, how); return drawPath(normalizePath(action.path), action, d || 1.4, instant);
          case 'arrow': registerInk(action, how); return drawPath(arrowPath(action.from, action.to), action, d || 0.9, instant);
          case 'circle': { registerInk(action, how); const [x, y] = action.at, r = action.r; return drawPath(`M ${f(x - r)} ${y} A ${r} ${r} 0 1 0 ${f(x + r)} ${y} A ${r} ${r} 0 1 0 ${f(x - r)} ${y}`, action, d || 1.1, instant); }
          case 'rect': { registerInk(action, how); const [x, y] = action.at; return drawPath(`M ${x} ${y} H ${f(x + action.w)} V ${f(y + action.h)} H ${x} Z`, action, d || 1.2, instant); }
          case 'axes': {
            registerInk(action, how);
            const [x, y] = action.at;
            return drawPath(arrowPath([x, y], [x, f(y - action.h)], 2.2) + ' ' + arrowPath([x, y], [f(x + action.w), y], 2.2), action, d || 1.4, instant);
          }
          case 'plot': registerInk(action, how); return drawPath('M ' + action.points.map(p => `${p[0]} ${p[1]}`).join(' L '), action, d || 1.8, instant);
          case 'dot': {
            registerInk(action, how);
            const el = svg('circle', {cx: action.at[0], cy: action.at[1], r: action.r || 1.4, fill: colour(action)});
            el.setAttribute('class', 'ros-board-dot');
            ink.append(el); remember(action, el);
            if (instant || !el.animate) return Promise.resolve();
            return track(el.animate([{opacity: 0}, {opacity: 1}], {duration: 250, fill: 'backwards'}));
          }
          case 'move': {
            const el = items.get(action.target), route = normalizePath(action.path);
            if (!el || !route) return Promise.resolve();
            registerInk(action, how);
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
            registerInk(action, how);
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
        chain = chain.then(() => layout.reset()).catch(() => {});
      },
      // What the board did to lay itself out: items moved to a free slot, and problems that no move could fix (overlaps, items off the board, a full zone).
      layout: () => layout.report()
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
    ink.setAttribute('class', 'ros-board-ink'); ink.setAttribute('viewBox', `0 0 ${WIDTH} ${HEIGHT}`); ink.setAttribute('preserveAspectRatio', 'none'); ink.setAttribute('aria-hidden', 'true');   // one coordinate space: drawing and text scale together
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
    const voiceNote = node('p', '', 'ros-board-voice-note'); voiceNote.setAttribute('role', 'status');
    const transcript = node('details', undefined, 'ros-board-transcript');
    transcript.append(node('summary', 'Transcript and what is written on the board'));
    const list = node('ol');
    transcript.append(list);
    figure.append(frame, bar, voiceNote, caption, transcript);
    container.append(figure);

    const speakers = {};
    const device = deviceSpeaker(win, options.clock);
    if (device.supported) speakers.device = device;
    speakers.captions = silentSpeaker(options.clock);
    // Recorded sentences (the page's builder gives one clip per step whose sentence still matches its recording); any step without one is said by the voice below.
    let recorded = null;
    if (options.clips) {
      recorded = audioSpeaker(win, options.clips, speakers.device || speakers.captions, options.clock);
      if (recorded.supported) speakers.recorded = recorded; else recorded = null;
    }
    for (const [id, extra] of Object.entries(options.speakers || {})) if (extra && typeof extra.speak === 'function') speakers[id] = extra;
    const labels = Object.assign({device: 'Device voice', captions: 'Captions only (timed)', recorded: 'Recorded voice', live: 'Live voice'}, options.speakerLabels || {});
    const spoken = s => s.steps.filter(step => typeof step.say === 'string' && step.say.trim());
    const coverage = s => { const all = spoken(s), have = all.filter(step => recorded.has(step.id)).length; return have === all.length ? 'Recorded voice' : `Recorded voice (${have} of ${all.length} sentences)`; };
    if (recorded) labels.recorded = coverage(script);
    const complete = !!recorded && spoken(script).every(step => recorded.has(step.id));
    // The live voice (the host's voice worker): sentences are spoken as they are wanted. What says a sentence it cannot is the best of the other voices.
    let liveVoice = null;
    if (options.live) {
      liveVoice = liveSpeaker(win, options.live, complete ? recorded : (speakers.device || speakers.captions), options.clock);
      if (liveVoice.supported) speakers.live = liveVoice; else liveVoice = null;
    }
    if (liveVoice) {
      liveVoice.onProblem = reason => { voiceNote.textContent = 'The live voice is not available (' + reason + '), so this uses the ' + (complete ? 'recorded' : speakers.device ? 'device' : 'caption') + ' voice instead.'; voiceNote.dataset.problem = 'true'; };
      liveVoice.onWait = waiting => { if (voiceNote.dataset.problem !== 'true') voiceNote.textContent = waiting ? 'Preparing the voice…' : ''; };
    }
    const order = ['live', 'recorded', 'device', 'captions'];   // the best voice first; anything a host adds follows
    for (const id of [...order.filter(k => speakers[k]), ...Object.keys(speakers).filter(k => !order.includes(k))]) { const o = node('option', labels[id] || id); o.value = id; voice.append(o); }
    const initial = options.speaker && speakers[options.speaker] ? options.speaker : (liveVoice ? 'live' : complete ? 'recorded' : speakers.device ? 'device' : 'captions');
    let speaker = speakers[initial];
    voice.value = initial;
    const warmUp = () => { if (speaker === liveVoice && liveVoice) liveVoice.prefetch(spoken(script).slice(0, 2).map(step => step.say)); };
    warmUp();

    const reduced = options.reducedMotion !== undefined ? !!options.reducedMotion : !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const effects = createEffects({doc, surface, ink, layer, pen, renderMath: options.renderMath, stepOf: i => (player.steps[i] ? player.steps[i].id : ''),
      onLayout: report => { if (options.onEvent) options.onEvent('layout', report); }});
    const speakerProxy = {speak: (t, o) => speaker.speak(t, o), pause: () => speaker.pause(), resume: () => speaker.resume(), cancel: () => speaker.cancel(),
      prefetch: texts => { if (typeof speaker.prefetch === 'function') speaker.prefetch(texts); }};
    // Text is sized from the board's own width in pixels, so it scales with the board without container-query units.
    function fitText() { const box = surface.getBoundingClientRect ? surface.getBoundingClientRect() : null; surface.style.setProperty('--bw', ((box && box.width) || surface.clientWidth || 800) + 'px'); }
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
      play.textContent = s === 'playing' ? 'Pause' : s === 'paused' ? 'Resume' : s === 'done' ? 'Play again' : s === 'waiting' ? 'Waiting…' : s === 'revised' ? 'Replay' : player.index > 0 ? 'Continue' : 'Start';
      play.disabled = s === 'waiting';
      skip.disabled = !(s === 'playing' || s === 'paused');
      figure.setAttribute('data-status', s);
    }
    const player = createPlayer({
      script, speaker: speakerProxy, effects, clock: options.clock, reducedMotion: reduced,
      onEvent(type, data) {
        if (type === 'step') { hint.hidden = true; caption.textContent = data.step.say || ''; mark(data.index); }
        if (type === 'reset') { hint.hidden = false; caption.textContent = ''; mark(-1); }
        if (type === 'seek') { hint.hidden = true; caption.textContent = (script.steps[data.index - 1] || {}).say || ''; mark(data.index - 1); }
        if (type === 'status' || type === 'reset' || type === 'seek') refresh();
        if (options.onEvent) options.onEvent(type, data);
      }
    });
    if (options.startAt) player.seek(options.startAt);   // a resumed lecture waits at the step it had reached, with the board drawn as it was
    play.addEventListener('click', () => {
      const s = player.status;
      if (typeof speaker.unlock === 'function') speaker.unlock();   // the click is what lets live audio start
      if (s === 'playing') player.pause(); else if (s === 'paused') player.resume(); else player.start();
    });
    skip.addEventListener('click', () => player.skip());
    replay.addEventListener('click', () => player.replay());
    voice.addEventListener('change', () => {
      if (player.status === 'playing' || player.status === 'paused') speaker.cancel();
      speaker = speakers[voice.value];
      speaker.setRate(Number(rate.value));
      if (speaker === liveVoice) { liveVoice.retry(); voiceNote.textContent = ''; delete voiceNote.dataset.problem; warmUp(); }
    });
    rate.addEventListener('change', () => { for (const s of Object.values(speakers)) s.setRate(Number(rate.value)); });
    refresh();

    return {
      player, figure, layout: () => effects.layout(),
      get status() { return player.status; },
      start: () => player.start(), pause: () => player.pause(), resume: () => player.resume(), skip: () => player.skip(), replay: () => player.replay(),
      update(next) {
        const result = player.update(next);
        if (result.ok) {
          figure.setAttribute('data-hand', next.hand || DEFAULT_HAND);
          renderTranscript(next);
          if (recorded) { const option = [...voice.children].find(o => o.value === 'recorded'); if (option) option.textContent = coverage(next); }
          mark(player.status === 'playing' || player.status === 'paused' ? player.index : -1);
          refresh();
        }
        return result;
      },
      destroy() { player.stop(); effects.reset(); if (observer) observer.disconnect(); figure.remove(); }
    };
  }

  return {SCHEMA, WIDTH, HEIGHT, COLORS, SIZES, HANDS, MAX, ZONES, FONT, validate, pathProblem, normalizePath, estimate, layoutProblems, layoutScript, estimateItem, mathBox, wrapText, createLayout, inkOf, sampledPath,
    createTimers, silentSpeaker, deviceSpeaker, audioSpeaker, liveSpeaker, createPlayer, mount};
});
