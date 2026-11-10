// Display-only repair of mechanical escaping defects in model-written Markdown math.
// A pure function on the render path: stored text is never changed, and only text inside
// $...$ / $$...$$ (or \(..\) / \[..\] delimiters that become those) can differ from the input.
// Code fences, indented code and inline code are left alone, as is all prose outside math.

// Commands whose first letter is also a JSON escape (\n \t \r \f \b, plus \a and \v) are the ones a decoder can eat.
const commandList = `
nu nabla neq newline neg ni notin not natural nless ngtr nmid ncong nsim nrightarrow
theta tau times text textbf textit textrm textsf texttt tan top to triangle therefore tilde tfrac tag tanh thinspace
rho right rightarrow rangle rbrace rceil rfloor
frac forall flat fbox footnotesize
beta bar binom begin bigcup bigcap bigoplus bullet boldsymbol bmod because bot bf bigl bigr bigg
alpha approx angle aleph asymp amalg
varphi varepsilon varrho vartheta varsigma vec vee vdots vert
gamma delta epsilon zeta eta iota kappa lambda mu xi pi sigma upsilon phi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega
sum prod int oint sqrt cdot cdots ldots dots partial infty lim sup inf min max log ln exp sin cos
leq geq le ge ne equiv sim simeq propto pm mp div ast star circ cup cap subset supset subseteq supseteq in
mathbb mathbf mathrm mathcal mathit mathfrak mathsf mathtt operatorname overline underline hat widehat widetilde dot ddot
left langle lbrace lceil lfloor quad qquad hbar ell Re Im wedge land lor lnot Rightarrow Leftarrow leftarrow Leftrightarrow leftrightarrow mapsto implies iff
`.split(/\s+/).filter(Boolean);
const commands = new Set(commandList);
// JSON-style escapes whose backslash and letter were turned into one control character.
const eaten: Record<string, string> = {'\t': 't', '\n': 'n', '\r': 'r', '\f': 'f', '\b': 'b', '\x07': 'a', '\x0b': 'v'};
const eatenClass = '[\\t\\n\\r\\f\\b\\x07\\x0b]';

function eatenCommand(control: string, run: string, display: boolean): string | null {
  const name = eaten[control] + run;
  if (!commands.has(name)) return null;
  // A newline then a lone "u" is also an ordinary line wrap before a variable; only an inline span cannot wrap.
  if (control === '\n' && display && name === 'nu') return null;
  return name;
}

const environment = /\\begin\{/;
const lineBreak = /\\\\(?:\s|$)/;

function repairSpan(body: string, display: boolean): string {
  let out = body;
  // \\frac -> \frac, unless the span has real line breaks or an environment where \\ means something.
  if (!environment.test(out) && !lineBreak.test(out)) {
    out = out.replace(/(?<!\\)\\\\([A-Za-z]+)/g, (whole, word: string) => commands.has(word) ? '\\' + word : whole);
  }
  return out.replace(new RegExp(`(${eatenClass})([A-Za-z]+)`, 'g'), (whole, control: string, run: string) => {
    const name = eatenCommand(control, run, display);
    return name ? '\\' + name : whole;
  });
}

function repairable(text: string, at: number): boolean {
  const control = text[at];
  if (!(control in eaten)) return false;
  const run = /^[A-Za-z]+/.exec(text.slice(at + 1, at + 40));
  return !!run && eatenCommand(control, run[0], false) !== null;
}

const blank = /\n[ \t]*\n/;

function repairMathIn(text: string): string {
  let out = '';
  let i = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (ch === '\\' && text[i + 1] === '$') {out += '\\$'; i += 2; continue;}
    if (ch !== '$') {out += ch; i += 1; continue;}
    if (text[i + 1] === '$') {
      let j = i + 2;
      while (j < n && !(text[j] === '$' && text[j + 1] === '$' && text[j - 1] !== '\\')) j += 1;
      const body = j < n ? text.slice(i + 2, j) : '';
      if (j >= n || !body.trim() || blank.test(body)) {out += '$$'; i += 2; continue;}
      out += '$$' + repairSpan(body, true) + '$$'; i = j + 2; continue;
    }
    const next = text[i + 1];
    if (next === undefined || (/\s/.test(next) && !repairable(text, i + 1))) {out += '$'; i += 1; continue;}
    let k = i + 1, closed = -1;
    for (; k < n && k - i < 2000; k += 1) {
      const c = text[k];
      if (c === '\\') {k += 1; continue;}
      if (c === '$') {
        if (!/\s/.test(text[k - 1]) && !/\d/.test(text[k + 1] || '') && k > i + 1) closed = k;
        break;
      }
      if (c === '\n' && !repairable(text, k)) break;
    }
    if (closed < 0) {out += '$'; i += 1; continue;}
    out += '$' + repairSpan(text.slice(i + 1, closed), false) + '$'; i = closed + 1;
  }
  return out;
}

// \( x \) and \[ x \] are the delimiters some models prefer. Escaped brackets are also legitimate Markdown
// (\[1\]), so a bracket pair is converted only when its content looks like TeX.
function convertDelimiters(text: string): string {
  return text
    .replace(/(?<!\\)\\\[((?:(?!\n[ \t]*\n)[\s\S])+?)\\\]/g, (whole, body: string) => /\\[A-Za-z]|[=^_]/.test(body) && !body.includes('$$') ? `$$${body}$$` : whole)
    .replace(/(?<!\\)\\\(((?:(?!\n[ \t]*\n)[\s\S])+?)\\\)/g, (whole, body: string) =>
      !body.includes('$') && body.trim() && (/\\[A-Za-z]|[=^_]/.test(body) || /^\s*[^\s]{1,3}\s*$/.test(body)) ? `$${body.trim()}$` : whole);
}

function repairProse(text: string): string {
  // Inline code spans (matching backtick runs) are copied through untouched.
  const parts: string[] = [];
  let last = 0;
  for (const code of text.matchAll(/(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)/g)) {
    parts.push(repairMathIn(convertDelimiters(text.slice(last, code.index))), code[0]);
    last = code.index + code[0].length;
  }
  parts.push(repairMathIn(convertDelimiters(text.slice(last))));
  return parts.join('');
}

export function repairMath(source: string): string {
  if (!/\$|\\[(\[]/.test(source)) return source;
  const out: string[] = [];
  let prose: string[] = [];
  const flush = () => {if (prose.length) {out.push(repairProse(prose.join('\n'))); prose = [];}};
  let fence: {character: string; width: number} | undefined;
  let indented = false, previousBlank = true, listAbove = false;
  for (const line of source.split('\n')) {
    const code = /^(?:[ \t]*(?:[-+*]|\d+[.)])[ \t]+)?[ \t]*(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      out.push(line);
      if (code && code[1][0] === fence.character && code[1].length >= fence.width && !code[2].trim()) fence = undefined;
      continue;
    }
    if (code) {flush(); fence = {character: code[1][0], width: code[1].length}; out.push(line); previousBlank = false; indented = false; continue;}
    const isBlank = !line.trim();
    const indent = /^(?: {4}|\t)/.test(line) && !isBlank && (previousBlank || indented) && !listAbove;
    if (indent) {flush(); out.push(line); indented = true; previousBlank = false; continue;}
    indented = false;
    if (!isBlank) listAbove = /^\s*(?:[-*+]|\d+[.)])\s/.test(line) || (listAbove && /^\s+\S/.test(line));
    else if (previousBlank) listAbove = false;
    previousBlank = isBlank;
    prose.push(line);
  }
  flush();
  return out.join('\n');
}
