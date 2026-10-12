"""Shared scientific inline grammar for session text.

One grammar, two implementations: this module and assets/html-runtime/richtext.js. A shared
conformance corpus (tests/fixtures/richtext-cases.json) holds both to identical HTML.

Parsing is a single left-to-right scan that extracts atomic tokens first (code spans, TeX math,
links, tags), then resolves emphasis with the CommonMark delimiter-stack algorithm. Because TeX
and code are atomic, a ``*`` or ``_`` inside ``$x_i^2$`` can never be taken for emphasis, and
unsupported or unterminated syntax stays visible as the author wrote it (with a diagnostic where
the intent is unambiguous). Authored text is never rewritten; only a rendering is produced.

Supported inline syntax: ``*em*`` ``_em_`` ``**strong**`` ``__strong__`` nested freely;
``~~strike~~``; ``==highlight==``; ``<sub>``/``<sup>``/``<mark>``/``<br>``; `` `code` ``;
math ``$x$`` (Pandoc rules, so ``$5 and $6`` is prose) ``$$x$$`` ``\\(x\\)`` ``\\[x\\]``;
``[label](#anchor)``; ``[[note|alias]]``; equation references ``\\eqref{name}`` and ``[@eq:name]``;
backslash escapes of ASCII punctuation; soft and hard line breaks.
"""
from __future__ import annotations

import html
import re
import unicodedata

ESCAPABLE = frozenset('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~')
TAGS = ('sub', 'sup', 'mark')
MATH_ENVIRONMENTS = ('equation', 'equation*', 'align', 'align*', 'aligned', 'gather', 'gather*', 'gathered',
                     'multline', 'multline*', 'alignat', 'alignat*', 'eqnarray', 'eqnarray*', 'split', 'cases')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}')
MAX_DEPTH = 24
MAX_EMPHASIS = 32  # deepest em/strong nesting that is resolved; the same constant is in richtext.js


def is_space(char):
    return char == '' or char.isspace()


def is_punct(char):
    return char != '' and unicodedata.category(char)[0] in ('P', 'S')


def normalize_label(value):
    value = value.strip()
    return value[3:] if value.startswith('eq:') else value


def _text(value):
    return {'t': 'text', 'v': value}


def _group(kind, children):
    return {'t': kind, 'c': children}


def _escaped(text, index):
    """True when the character at ``index`` is preceded by an odd number of backslashes."""
    count = 0
    while index - 1 - count >= 0 and text[index - 1 - count] == '\\':
        count += 1
    return count % 2 == 1


def _closing_dollar(text, start):
    """Index of the ``$`` closing a math span whose content starts at ``start``, or -1 (Pandoc rules)."""
    j = start
    while j < len(text):
        char = text[j]
        if char == '\\':
            j += 2
            continue
        if char == '$' and j > start and not text[j - 1].isspace() and not (j + 1 < len(text) and text[j + 1].isdigit()):
            return j
        j += 1
    return -1


closing_dollar = _closing_dollar  # public alias for block-level callers (table cells)


def _find(text, needle, start):
    """First unescaped occurrence of ``needle`` at or after ``start``."""
    j = text.find(needle, start)
    while j != -1 and _escaped(text, j):
        j = text.find(needle, j + 1)
    return j


def _matching_bracket(text, start):
    """Index of the ``]`` matching the ``[`` at ``start``, skipping escapes and code spans; -1 if none."""
    depth, j = 0, start
    while j < len(text):
        char = text[j]
        if char == '\\':
            j += 2
            continue
        if char == '`':
            run = len(text) - j - len(text[j:].lstrip('`'))
            end = text.find('`' * run, j + run)
            j = end + run if end != -1 else j + run
            continue
        if char == '[':
            depth += 1
        elif char == ']':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _link_target(text, close):
    """Parse ``(dest "title")`` right after a label's closing bracket. Returns (dest, title, end) or None."""
    if close + 1 >= len(text) or text[close + 1] != '(':
        return None
    match = re.compile(r'\(([^()\s]+)(?:\s+"([^"\n]*)")?\)').match(text, close + 1)
    return (match[1], match[2], match.end()) if match else None


def _flags(prev, char, following):
    left = not is_space(following) and (not is_punct(following) or is_space(prev) or is_punct(prev))
    right = not is_space(prev) and (not is_punct(prev) or is_space(following) or is_punct(following))
    if char == '*':
        return left, right
    return left and (not right or is_punct(prev)), right and (not left or is_punct(following))


def _scan(text, depth):
    """Tokenize: atomic nodes plus delimiter runs awaiting emphasis resolution."""
    tokens, buf, i, n = [], [], 0, len(text)

    def flush():
        if buf:
            tokens.append(_text(''.join(buf)))
            buf.clear()

    def emit(token):
        flush()
        tokens.append(token)

    while i < n:
        c = text[i]
        if c == '\n':
            raw = ''.join(buf)
            stripped = raw.rstrip(' ')
            hard = len(raw) - len(stripped) >= 2
            buf.clear()
            if stripped:
                buf.append(stripped)
            emit({'t': 'br'} if hard else _text(' '))
            i += 1
            while i < n and text[i] == ' ':
                i += 1
            continue
        if c == '\\':
            following = text[i + 1] if i + 1 < n else ''
            if following == '\n':
                emit({'t': 'br'})
                i += 2
                while i < n and text[i] == ' ':
                    i += 1
                continue
            if following in ('(', '['):
                closer = '\\)' if following == '(' else '\\]'
                end = _find(text, closer, i + 2)
                if end > i + 2:
                    emit({'t': 'math', 'v': text[i + 2:end].strip(), 'display': following == '[', 'src': text[i:end + 2]})
                    i = end + 2
                else:
                    emit({'t': 'diag', 'code': 'unclosed-math', 'v': '\\' + following})
                    i += 2
                continue
            ref = re.compile(r'\\eqref\{([^{}\s]+)\}').match(text, i)
            if ref:
                emit({'t': 'ref', 'label': normalize_label(ref[1]), 'src': ref[0]})
                i = ref.end()
                continue
            if following and following in ESCAPABLE:
                buf.append(following)
                i += 2
            else:
                buf.append('\\')
                i += 1
            continue
        if c == '`':
            run = n - i - len(text[i:].lstrip('`'))
            end = -1
            for found in re.finditer(r'`+', text[i + run:]):
                if len(found[0]) == run:
                    end = i + run + found.start()
                    break
            if end == -1:
                buf.append('`' * run)
                i += run
                continue
            content = text[i + run:end].replace('\n', ' ')
            if len(content) > 2 and content[0] == ' ' and content[-1] == ' ' and content.strip():
                content = content[1:-1]
            emit({'t': 'code', 'v': content})
            i = end + run
            continue
        if c == '$':
            if text.startswith('$$', i):
                end = _find(text, '$$', i + 2)
                if end > i + 2:
                    emit({'t': 'math', 'v': text[i + 2:end].strip(), 'display': True, 'src': text[i:end + 2]})
                    i = end + 2
                    continue
            elif i + 1 < n and not text[i + 1].isspace():
                end = _closing_dollar(text, i + 1)
                if end != -1:
                    emit({'t': 'math', 'v': text[i + 1:end], 'display': False, 'src': text[i:end + 1]})
                    i = end + 1
                    continue
            buf.append('$')
            i += 1
            continue
        if c == '<':
            tag = re.compile(r'<(sub|sup|mark)>', re.I).match(text, i)
            if tag and depth < MAX_DEPTH:
                name = tag[1].lower()
                nesting, end = 1, -1
                for part in re.finditer(r'<(/?)' + name + r'>', text[tag.end():], re.I):
                    nesting += -1 if part[1] else 1
                    if nesting == 0:
                        end = tag.end() + part.start()
                        break
                if end != -1:
                    emit(_group(name, parse_inline(text[tag.end():end], depth + 1)))
                    i = end + len(name) + 3
                    continue
            lone = re.compile(r'<br\s*/?>', re.I).match(text, i)
            if lone:
                emit({'t': 'br'})
                i = lone.end()
                continue
            buf.append('<')
            i += 1
            continue
        if c == '[':
            if text.startswith('[[', i):
                end = text.find(']]', i + 2)
                inner = text[i + 2:end] if end != -1 else ''
                if end != -1 and inner and not re.search(r'[\[\]\n]', inner):
                    target, _, alias = inner.partition('|')
                    label = alias or target.split('#')[0]
                    emit({'t': 'wikilink', 'target': target.strip(),
                          'c': parse_inline(label, depth + 1) if depth < MAX_DEPTH else [_text(label)]})
                    i = end + 2
                    continue
            ref = re.compile(r'\[@([A-Za-z0-9][A-Za-z0-9_.:-]*)\]').match(text, i)
            if ref:
                emit({'t': 'ref', 'label': normalize_label(ref[1]), 'src': ref[0]})
                i = ref.end()
                continue
            close = _matching_bracket(text, i)
            target = _link_target(text, close) if close != -1 else None
            if target and depth < MAX_DEPTH:
                emit({'t': 'link', 'href': target[0], 'title': target[1], 'c': parse_inline(text[i + 1:close], depth + 1)})
                i = target[2]
                continue
            buf.append('[')
            i += 1
            continue
        if c in ('~', '=') and text.startswith(c * 2, i) and not text.startswith(c * 3, i) and depth < MAX_DEPTH:
            after = text[i + 2] if i + 2 < n else ''
            end = text.find(c * 2, i + 2)
            if after and not after.isspace() and end > i + 2 and not text[end - 1].isspace() and not _escaped(text, end):
                emit(_group('del' if c == '~' else 'mark', parse_inline(text[i + 2:end], depth + 1)))
                i = end + 2
                continue
        if c in ('*', '_'):
            j = i
            while j < n and text[j] == c:
                j += 1
            prev = text[i - 1] if i else ''
            following = text[j] if j < n else ''
            can_open, can_close = _flags(prev, c, following)
            emit({'t': 'delim', 'ch': c, 'n': j - i, 'orig': j - i, 'open': can_open, 'close': can_close})
            i = j
            continue
        buf.append(c)
        i += 1
    flush()
    return tokens


def _resolve_emphasis(tokens):
    """CommonMark "process emphasis", including the rule of three."""
    i = 0
    while i < len(tokens):
        closer = tokens[i]
        if closer['t'] != 'delim' or not closer['close'] or closer['n'] == 0:
            i += 1
            continue
        found = -1
        for j in range(i - 1, -1, -1):
            opener = tokens[j]
            if opener['t'] != 'delim' or opener['ch'] != closer['ch'] or not opener['open'] or opener['n'] == 0:
                continue
            odd = (opener['close'] or closer['open']) and (opener['orig'] + closer['orig']) % 3 == 0 \
                and not (opener['orig'] % 3 == 0 and closer['orig'] % 3 == 0)
            if not odd:
                found = j
                break
        if found < 0:
            if not closer['open']:
                closer['close'] = False
            i += 1
            continue
        opener = tokens[found]
        use = 2 if opener['n'] >= 2 and closer['n'] >= 2 else 1
        inner = tokens[found + 1:i]
        depth = 1 + max([t.get('d', 0) for t in inner] or [0])
        if depth > MAX_EMPHASIS:
            # Pathological nesting (thousands of stacked delimiters) stays literal rather than exhausting the stack.
            closer['close'] = False
            i += 1
            continue
        group = _group('strong' if use == 2 else 'em', inner)
        group['d'] = depth
        opener['n'] -= use
        closer['n'] -= use
        tokens[found + 1:i] = [group]
        i = found + 2
        if opener['n'] == 0:
            del tokens[found]
            i -= 1
        if closer['n'] == 0:
            del tokens[i]
    return tokens


def _build(tokens):
    out = []
    for token in tokens:
        if token['t'] == 'delim':
            node = _text(token['ch'] * token['n']) if token['n'] else None
        elif token['t'] in ('em', 'strong'):
            node = _group(token['t'], _build(token['c']))
        else:
            node = token
        if node is None:
            continue
        if node['t'] == 'text' and out and out[-1]['t'] == 'text':
            out[-1] = _text(out[-1]['v'] + node['v'])
        else:
            out.append(node)
    return out


def parse_inline(text, depth=0):
    """Parse a paragraph of authored text into a node list. Never raises on any input."""
    if not text:
        return []
    return _build(_resolve_emphasis(_scan(text, depth)))


# --- rendering ------------------------------------------------------------------------------

def _esc(value):
    return html.escape(value, quote=True)


def to_html(nodes, labels=None):
    """Static HTML. Every authored string is escaped; links are inert except same-page anchors."""
    labels = labels or {}
    out = []
    for node in nodes:
        kind = node['t']
        if kind == 'text':
            out.append(_esc(node['v']))
        elif kind == 'code':
            out.append('<code>' + _esc(node['v']) + '</code>')
        elif kind == 'math':
            display = ' data-display="true"' if node['display'] else ''
            out.append('<span data-ros="equation"' + display + ' data-tex="' + _esc(node['v']) + '" class="ros-math">' + _esc(node['src']) + '</span>')
        elif kind in ('em', 'strong', 'del', 'mark', 'sub', 'sup'):
            out.append('<' + kind + '>' + to_html(node['c'], labels) + '</' + kind + '>')
        elif kind == 'br':
            out.append('<br>')
        elif kind == 'link':
            label = to_html(node['c'], labels)
            if re.fullmatch(r'#[A-Za-z0-9_-]+', node['href']):
                out.append('<a href="' + node['href'] + '">' + label + '</a>')
            else:
                out.append('<span class="ros-link">' + label + ' <span class="ros-link-target">(' + _esc(node['href']) + ')</span></span>')
        elif kind == 'wikilink':
            out.append('<span class="ros-note-link" data-ros-target="' + _esc(node['target']) + '" title="' + _esc(node['target']) + '">'
                       + to_html(node['c'], labels) + '</span>')
        elif kind == 'ref':
            number = labels.get(node['label'])
            if number is None:
                out.append('<span class="ros-diagnostic" data-ros="diagnostic" data-code="unresolved-reference" title="No equation has this label">'
                           + _esc(node['src']) + '</span>')
            else:
                out.append('<a class="ros-eqref" href="#eq-' + _esc(node['label']) + '" data-ros-ref="' + _esc(node['label']) + '">('
                           + str(number) + ')</a>')
        elif kind == 'diag':
            out.append('<span class="ros-diagnostic" data-ros="diagnostic" data-code="' + _esc(node['code']) + '" title="Unterminated syntax; shown as written">'
                       + _esc(node['v']) + '</span>')
    return ''.join(out)


def render_inline(text, labels=None):
    return to_html(parse_inline(text), labels)


def plain_text(nodes):
    """Readable text with markup removed and TeX source kept: for accessible names and <option> labels."""
    out = []
    for node in nodes:
        kind = node['t']
        if kind in ('text', 'code', 'math', 'diag'):
            out.append(node['v'])
        elif kind == 'br':
            out.append(' ')
        elif kind == 'ref':
            out.append(node['src'])
        elif 'c' in node:
            out.append(plain_text(node['c']))
    return ''.join(out)


def diagnostics(nodes):
    found = []
    for node in nodes:
        if node['t'] == 'diag':
            found.append({'code': node['code'], 'text': node['v']})
        elif node['t'] == 'ref':
            found.append({'code': 'reference', 'label': node['label']})
        elif 'c' in node:
            found.extend(diagnostics(node['c']))
    return found


def references(nodes):
    return [d['label'] for d in diagnostics(nodes) if d['code'] == 'reference']


# --- display math at block level ------------------------------------------------------------

def starts_display_math(line):
    """Whether a line opens a display equation (``$$``, ``\\[`` or a known math environment)."""
    stripped = line.strip()
    if stripped.startswith('$$') or stripped.startswith('\\['):
        return True
    env = re.match(r'\\begin\{([a-z]+\*?)\}', stripped)
    return bool(env and env[1] in MATH_ENVIRONMENTS)


def read_display_math(lines, i):
    """Read a display equation starting at ``lines[i]``: ``$$..$$``, ``\\[..\\]`` or a math environment.

    Returns ``{'tex', 'label', 'next', 'source'}`` or None when the block is not terminated (the caller keeps
    it as legacy preformatted text rather than guessing). The authored text is never altered.
    """
    first = lines[i].strip()
    if first.startswith('$$'):
        opener, closer = '$$', '$$'
    elif first.startswith('\\['):
        opener, closer = '\\[', '\\]'
    else:
        env = re.match(r'\\begin\{([a-z]+\*?)\}', first)
        if not env or env[1] not in MATH_ENVIRONMENTS:
            return None
        opener, closer = '', '\\end{' + env[1] + '}'
    block, j = [first], i + 1
    if opener:
        done = len(first) >= len(opener) + len(closer) + 1 and first.endswith(closer)
    else:
        done = closer in first
    while not done and j < len(lines):
        block.append(lines[j].rstrip())
        done = closer in lines[j]
        j += 1
    text = '\n'.join(block).strip()
    trailer = re.search(r'\{#([A-Za-z0-9][A-Za-z0-9_.:-]*)\}\s*$', text)
    label = normalize_label(trailer[1]) if trailer else None
    if trailer:
        text = text[:trailer.start()].rstrip()
    if opener:
        if not (text.startswith(opener) and text.endswith(closer) and len(text) >= len(opener) + len(closer) + 1):
            return None
        tex = text[len(opener):len(text) - len(closer)].strip()
    else:
        if not text.endswith(closer):
            return None
        tex = text
    inner = re.search(r'\\label\{([^{}\s]+)\}', tex)
    if inner:
        label = label or normalize_label(inner[1])
        tex = (tex[:inner.start()] + tex[inner.end():]).strip()
    if not tex or (label and not LABEL.fullmatch(label)):
        return None
    return {'tex': tex, 'label': label, 'next': j, 'source': text}


def display_math_html(block, number=None):
    """The display-equation element; a labelled equation is numbered with ``\\tag`` and addressable."""
    tex, attributes = block['tex'], ''
    if block['label']:
        if number is not None and '\\tag' not in tex:
            tex = tex + ' \\tag{' + str(number) + '}'
        attributes = ' id="eq-' + _esc(block['label']) + '" data-eq-label="' + _esc(block['label']) + '" data-eq-number="' + str(number) + '"'
    return ('<div class="ros-formula ros-math" data-ros="equation" data-display="true"' + attributes + ' data-tex="' + _esc(tex) + '">'
            + _esc(block['source']) + '</div>')
