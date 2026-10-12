"""HTML-primary sessions, exact Markdown bridges, and reversible migration.

Structured JSON owns content. HTML and Markdown are deterministic projections;
browser interaction is pending review and cannot confer learning credit.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import base64
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

from common import load_config, parse_frontmatter

SCHEMA_VERSION = 1
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10000
BRIDGE_MARKER = "\n<!-- research-os:html-session -->\n"
RUNTIME = Path(__file__).resolve().parents[1] / "assets" / "html-runtime"


class Lock:
    """Filesystem lock shared with the host's session update protocol."""
    def __init__(self, path, timeout=3.0):
        self.path, self.timeout = path, timeout

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() - start > self.timeout:
                    raise ValueError(f"Session is being updated: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *args):
        os.close(self.fd)
        self.path.unlink(missing_ok=True)


def install_runtime(root):
    destination = _path(root, ".research-os/runtime")
    if not RUNTIME.is_dir():
        raise ValueError("Bundled HTML runtime missing")
    copies = []
    for source in RUNTIME.rglob("*"):
        if source.is_file():
            target = _path(root, Path(".research-os/runtime") / source.relative_to(RUNTIME))
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError(f"Runtime resource conflict: {target}; update explicitly after backup")
            copies.append((source, target))
    destination.mkdir(parents=True, exist_ok=True)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, relative):
    root = Path(root).resolve()
    lexical = root / relative
    for part in (lexical, *lexical.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Symlink session paths are unsupported")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Session path must stay within the vault")
    return path


def paths(root, relative_md):
    md = _path(root, relative_md)
    if md.suffix.lower() != ".md":
        raise ValueError("Session compatibility path must end in .md")
    return md, md.with_suffix(".html"), md.with_suffix(".state.json")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _approved_module(root, path, resource):
    registry = _path(root, '.research-os/runtime/extensions/trusted-modules.json')
    approved = json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else {}
    relative = path.relative_to(Path(root).resolve()).as_posix()
    digest = _hash(path.read_bytes())
    if resource.get('sha256') != digest or approved.get(relative) != digest:
        raise ValueError('Local module requires a matching independently approved SHA-256 trust entry')


def validate_interaction(event, question_ids):
    if not isinstance(event, dict) or set(event) - {'event_id','type','question_id','response','created_at','status'}:
        raise ValueError('Unknown interaction event field')
    if not isinstance(event.get('event_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', event['event_id']):
        raise ValueError('Invalid interaction event ID')
    if event.get('created_at') is not None:
        try:
            dt.datetime.fromisoformat(event['created_at'].replace('Z','+00:00'))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid interaction timestamp') from None
    if event.get('type') in {'open-question','checkpoint'}:
        if not isinstance(event.get('response'), str) or not event['response'].strip():
            raise ValueError('Question/checkpoint requires bounded nonempty text')
    else:
        if event.get('question_id') not in question_ids:
            raise ValueError('Unknown interaction question')
    def bounded(value, depth=0):
        if depth > 4:
            raise ValueError('Response nesting limit exceeded')
        if value is None or isinstance(value, (str,bool)):
            return
        if isinstance(value,(int,float)) and math.isfinite(value):
            return
        if isinstance(value,list) and len(value) <= 100:
            for item in value: bounded(item,depth+1)
            return
        if isinstance(value,dict) and len(value) <= 100:
            for key,item in value.items():
                if key in {'__proto__','constructor','prototype'}: raise ValueError('Invalid response key')
                bounded(item,depth+1)
            return
        raise ValueError('Invalid bounded response')
    bounded(event.get('response'))
    if len(json.dumps(event,ensure_ascii=False,allow_nan=False)) > 16384:
        raise ValueError('Interaction event exceeds limit')


REVIEW_VERDICTS = ("correct", "partially-correct", "incorrect", "reviewed")
QUESTION_KINDS = {"mcq", "multi", "numeric", "matching", "ordering", "free-response"}


def _validate_reviews(reviews):
    """Tutor verdicts on actual responses: shown beside the question, never ledger credit."""
    if not isinstance(reviews, list) or len(reviews) > 200:
        raise ValueError("Invalid question reviews")
    for review in reviews:
        if not isinstance(review, dict) or set(review) - {"response_event_id", "verdict", "feedback", "reviewed_at"}:
            raise ValueError("Invalid question review")
        if review.get("verdict") not in REVIEW_VERDICTS:
            raise ValueError("Unsupported review verdict")
        if not isinstance(review.get("feedback", ""), str) or len(review.get("feedback", "")) > 32000:
            raise ValueError("Review feedback must be bounded text")
        if review.get("response_event_id") is not None and not (isinstance(review["response_event_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", review["response_event_id"])):
            raise ValueError("Invalid reviewed response identity")
        try:
            dt.datetime.fromisoformat(str(review.get("reviewed_at")).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid review timestamp") from None


def _validate_context(context):
    """Optional binding to a context receipt; absent in historical sessions, never required to read one."""
    if not isinstance(context, dict):
        raise ValueError("Invalid session context")
    if context.get("waived") is True:
        if set(context) - {"waived", "reason", "bound_at"} or not isinstance(context.get("reason"), str) or not context["reason"].strip():
            raise ValueError("A context waiver needs a reason")
        return
    if set(context) - {"binding", "request", "bound_at", "refreshed_at"} or not isinstance(context.get("binding"), dict) \
            or not isinstance(context.get("request"), dict):
        raise ValueError("Invalid session context binding")
    binding = context["binding"]
    if not isinstance(binding.get("receipt_id"), str) or binding.get("outcome") not in {"ready", "degraded"} \
            or not isinstance(binding.get("sources"), list) or not isinstance(binding.get("workflow"), str):
        raise ValueError("Invalid session context binding")


def validate_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported HTML session schema")
    for key in ("session_id", "type", "title", "source_markdown"):
        if not isinstance(state.get(key), str):
            raise ValueError(f"Invalid {key}")
    if not state["session_id"] or len(state["session_id"]) > 256:
        raise ValueError("Invalid session identity")
    if not isinstance(state.get("metadata"), dict):
        raise ValueError("Invalid metadata")
    for key in ("questions", "events", "open_questions"):
        if not isinstance(state.get(key), list):
            raise ValueError(f"Invalid {key}")
    for widget in state.get("widgets", []):
        if not isinstance(widget, dict) or widget.get("kind") not in {"sampling", "vector"} or not isinstance(widget.get("id"), str):
            raise ValueError("Unsupported session widget")
    if "context" in state:
        _validate_context(state["context"])
    if not isinstance(state.get("resources", []), list):
        raise ValueError("Invalid session resources")
    for resource in state.get("resources", []):
        if not isinstance(resource, dict) or resource.get("kind") not in {"module", "image"} or not isinstance(resource.get("path"), str):
            raise ValueError("Invalid local session resource")
        value = resource["path"]
        if re.search(r"[:\\\\%?#]", value) or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Unsafe local session resource path")
        suffix = Path(value).suffix.lower()
        if resource["kind"] == "image" and suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Unsupported session image")
        if resource["kind"] == "module" and suffix != ".js":
            raise ValueError("Unsupported session module")
    if len(state["events"]) > MAX_EVENTS or len(_json(state)) > MAX_STATE_BYTES:
        raise ValueError("Session state exceeds limits")
    ids = set()
    for q in state["questions"]:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q["id"] or len(q["id"]) > 128 or q["id"] in ids:
            raise ValueError("Invalid or duplicate question identity")
        ids.add(q["id"])
        _validate_reviews(q.get("reviews", []))
    event_ids = set()
    for event in state["events"]:
        validate_interaction(event, ids)
        if not isinstance(event, dict) or event.get("type") not in {"response", "hint", "solution", "confidence", "checkpoint", "reset", "open-question"}:
            raise ValueError("Unsupported interaction event")
        if not isinstance(event.get("event_id"), str) or event["event_id"] in event_ids:
            raise ValueError("Invalid or duplicate event identity")
        event_ids.add(event["event_id"])
        if event.get("type") not in {"open-question", "checkpoint"} and event.get("question_id") not in ids:
            raise ValueError("Unknown interaction question")
        if event.get("status") not in (None, "pending-review"):
            raise ValueError("Browser evidence must remain pending review")
        if any(k in event for k in ("mastery", "retained", "credit", "reviewed_by")):
            raise ValueError("Browser event cannot award learning evidence")
        if len(json.dumps(event, ensure_ascii=False)) > 20000:
            raise ValueError("Interaction event exceeds limit")
    return state


def _inline(text):
    """Render supported inline syntax without interpreting markup inside TeX/code."""
    pattern = re.compile(r'\$[^$\n]+\$|`[^`\n]+`|\[\[[^\]\n]+\]\]|\[[^\]\n]+\]\([^()\s]+(?:\s+"[^"\n]*")?\)|\*\*.+?\*\*|__.+?__|(?<!\w)\*[^*\n]+\*(?!\w)|(?<!\w)_[^_\n]+_(?!\w)')
    result, position = [], 0
    for match in pattern.finditer(text):
        result.append(html.escape(text[position:match.start()]))
        token = match.group()
        if token.startswith('$'):
            result.append('<span data-ros="equation" data-tex="' + html.escape(token[1:-1], quote=True) + '" class="ros-math">' + html.escape(token) + '</span>')
        elif token.startswith('`'):
            result.append('<code>' + html.escape(token[1:-1]) + '</code>')
        elif token.startswith('[['):
            parts = token[2:-2].split('|', 1)
            result.append('<span class="ros-note-link" title="' + html.escape(parts[0], quote=True) + '">' + _inline(parts[-1]) + '</span>')
        elif token.startswith('['):
            link = re.fullmatch(r'\[([^\]]+)\]\(([^\s]+)(?:\s+"([^"]*)")?\)', token)
            label, target = _inline(link[1]), link[2]
            if re.fullmatch(r'#[A-Za-z0-9_-]+', target):
                result.append('<a href="' + target + '">' + label + '</a>')
            else:
                result.append('<span class="ros-link">' + label + ' <span class="ros-link-target">(' + html.escape(target) + ')</span></span>')
        elif token.startswith(('**', '__')):
            result.append('<strong>' + _inline(token[2:-2]) + '</strong>')
        else:
            result.append('<em>' + _inline(token[1:-1]) + '</em>')
        position = match.end()
    result.append(html.escape(text[position:]))
    return ''.join(result)


_LIST_MARKER = re.compile(r'^( *)([-+*]|\d+[.)])\s+(.+)$')
_HEADING = re.compile(r'^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$')
_CALLOUT = re.compile(r'^\[!([a-zA-Z][\w-]*)\]([+-]?)\s*(.*)$')
# A question sits where its marker is, so probes and teaching read in the order they happened.
QUESTION_MARKER = re.compile(r'^<!--\s*ros-question:\s*([A-Za-z0-9_.:-]{1,128})\s*-->\s*$')
_IMAGE = re.compile(r'^!\[([^\]]*)\]\(resource:([a-zA-Z0-9_-]+)(?:\s+"([^"]*)")?\)\s*$')


def _table_cells(line):
    """Split unescaped pipes outside inline code; retain escaped literal pipes."""
    cells, cell, code = [], [], False
    line = line.strip()
    if line.startswith('|'): line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'): line = line[:-1]
    i = 0
    while i < len(line):
        char = line[i]
        if char == '\\' and i + 1 < len(line) and line[i + 1] == '|':
            cell.append('|'); i += 2; continue
        if char == '`': code = not code
        if char == '|' and not code:
            cells.append(''.join(cell).strip()); cell = []
        else: cell.append(char)
        i += 1
    return cells + [''.join(cell).strip()]


def markdown_html(source, page_title=None, questions=None, placed=None):
    """Component-oriented structural conversion; never infer assessments or answers.

    Authored source is unchanged. The renderer supports lists, quotations, callouts,
    fences, headings, emphasis and literal math; raw executable HTML is escaped.
    """
    _, body = parse_frontmatter(source.replace('\r\n', '\n'))
    used_anchors = {}
    source_h1_seen = False

    def anchor_for(title):
        base = 'section-' + _hash(title.encode())[:12]
        used_anchors[base] = used_anchors.get(base, 0) + 1
        return base if used_anchors[base] == 1 else base + '-' + str(used_anchors[base])

    def render(lines, depth=0):
        nonlocal source_h1_seen
        if depth > 32:
            return '<pre data-ros="legacy">' + html.escape('\n'.join(lines)) + '</pre>'
        out, i = [], 0
        def block_start(line):
            return (not line.strip() or _HEADING.match(line) or _LIST_MARKER.match(line) or QUESTION_MARKER.match(line.strip())
                    or line.startswith('>') or re.match(r'^\s*(?:```|~~~|\$\$)', line)
                    or re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*', line))
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            marker = QUESTION_MARKER.match(line.strip())
            if marker:
                question = (questions or {}).get(marker[1])
                if question is not None and (placed is None or marker[1] not in placed):
                    out.append(_question_html(question))
                    if placed is not None: placed.add(marker[1])
                i += 1; continue
            image = _IMAGE.fullmatch(line.strip())
            if image:
                out.append('<figure class="ros-figure" data-ros="figure"><img data-resource-id="' + html.escape(image[2], quote=True) + '" alt="' + html.escape(image[1], quote=True) + '">' + ('<figcaption>' + _inline(image[3]) + '</figcaption>' if image[3] else '') + '</figure>')
                i += 1; continue
            if i + 1 < len(lines) and '|' in line:
                headings, rules = _table_cells(line), _table_cells(lines[i + 1])
                if len(headings) == len(rules) and all(re.fullmatch(r':?-{3,}:?', r) for r in rules):
                    classes = ['ros-align-center' if r.startswith(':') and r.endswith(':') else 'ros-numeric' if r.endswith(':') else 'ros-align-left' for r in rules]
                    table = '<div class="ros-table-wrap" tabindex="0" role="region" aria-label="Scrollable table"><table><thead><tr>'
                    table += ''.join('<th scope="col" class="' + c + '">' + _inline(h) + '</th>' for h, c in zip(headings, classes)) + '</tr></thead><tbody>'
                    i += 2
                    while i < len(lines) and '|' in lines[i] and lines[i].strip():
                        cells = _table_cells(lines[i])
                        if len(cells) != len(headings): break
                        table += '<tr>' + ''.join('<td class="' + c + '">' + _inline(v) + '</td>' for v, c in zip(cells, classes)) + '</tr>'
                        i += 1
                    out.append(table + '</tbody></table></div>'); continue
            fence = re.match(r'^\s*(`{3,}|~{3,})([^\s`]*)\s*$', line)
            if fence:
                code, i = [], i + 1
                while i < len(lines) and not re.fullmatch(r'\s*' + re.escape(fence[1][0]) + '{' + str(len(fence[1])) + r',}\s*', lines[i]):
                    code.append(lines[i]); i += 1
                closed = i < len(lines)
                if closed: i += 1
                language = fence[2] if re.fullmatch(r'[\w+-]{1,32}', fence[2]) else ''
                attr = ' data-language="' + language + '"' if language else ''
                out.append('<pre class="ros-code" data-ros="' + ('code' if closed else 'legacy') + '"' + attr + '><code>' + html.escape('\n'.join(code)) + '</code></pre>')
                continue
            if line.strip().startswith('$$'):
                equation, i = [line.strip()], i + 1
                if len(equation[0]) <= 4 or not equation[0].endswith('$$'):
                    while i < len(lines):
                        equation.append(lines[i]); i += 1
                        if equation[-1].strip().endswith('$$'): break
                text = '\n'.join(equation)
                if len(text) > 4 and text.endswith('$$'):
                    out.append('<div class="ros-formula ros-math" data-ros="equation" data-display="true" data-tex="' + html.escape(text[2:-2].strip(), quote=True) + '">' + html.escape(text) + '</div>')
                else:
                    out.append('<pre data-ros="legacy">' + html.escape(text) + '</pre>')
                continue
            heading = _HEADING.match(line)
            if heading:
                level, title = len(heading[1]), heading[2]
                anchor = anchor_for(title)
                if level == 1:
                    prior_h1 = source_h1_seen
                    duplicate = page_title is not None and not source_h1_seen and title.strip() == page_title.strip()
                    source_h1_seen = True
                    if duplicate:
                        # Keep historical fragment targets without a duplicate H1/TOC entry.
                        out.append('<span class="ros-heading-anchor" aria-hidden="true" id="' + anchor + '"></span>')
                        i += 1
                        continue
                    if page_title is not None or prior_h1: level = 2
                kind = {'concept':'concept','definition':'definition','derivation':'derivation','intuition':'intuition','evidence':'evidence','decision':'decision','research decision':'decision','questions':'question','questions asked':'question','open questions':'question','code':'code','reflection':'reflection','checkpoint':'checkpoint'}.get(title.lower().rstrip(':'))
                attr = ' data-ros="' + kind + '"' if kind else ''
                out.append(f'<h{level} class="ros-section-heading" id="{anchor}"{attr}>' + _inline(title) + f'</h{level}>')
                i += 1
                continue
            if line.startswith('>'):
                quoted = []
                while i < len(lines) and lines[i].startswith('>'):
                    quoted.append(re.sub(r'^> ?', '', lines[i])); i += 1
                callout = _CALLOUT.match(quoted[0])
                if callout:
                    kind, fold, title = callout[1].lower(), callout[2], callout[3]
                    title = title or kind.replace('-', ' ').capitalize()
                    component = 'details' if fold else 'aside'
                    label = 'summary' if fold else 'div'
                    opened = ' open' if fold == '+' else ''
                    out.append('<' + component + ' class="ros-callout ros-callout-' + kind + '" data-ros="' + kind + '"' + opened + '><' + label + ' class="ros-callout-header">' + _inline(title) + '</' + label + '><div class="ros-callout-body">' + render(quoted[1:], depth + 1) + '</div></' + component + '>')
                else:
                    out.append('<blockquote class="ros-quotation">' + render(quoted, depth + 1) + '</blockquote>')
                continue
            marker = _LIST_MARKER.match(line)
            if marker:
                indent, ordered = len(marker[1]), marker[2][0].isdigit()
                tag = 'ol' if ordered else 'ul'
                start = int(re.match(r'\d+', marker[2])[0]) if ordered else 1
                attrs = ' start="' + str(start) + '"' if ordered and start != 1 else ''
                items = []
                while i < len(lines):
                    current = _LIST_MARKER.match(lines[i])
                    if not current or len(current[1]) != indent or current[2][0].isdigit() != ordered: break
                    content_indent = current.start(3)
                    item = [current[3]]
                    number = int(re.match(r'\d+', current[2])[0]) if ordered else None
                    i += 1
                    while i < len(lines):
                        next_item = _LIST_MARKER.match(lines[i])
                        if next_item and len(next_item[1]) <= indent: break
                        if not lines[i].strip():
                            probe = i + 1
                            while probe < len(lines) and not lines[probe].strip(): probe += 1
                            if probe >= len(lines): i = probe; break
                            next_indent = len(lines[probe]) - len(lines[probe].lstrip(' '))
                            if next_indent <= indent: i = probe; break
                            item.append(''); i += 1; continue
                        leading = len(lines[i]) - len(lines[i].lstrip(' '))
                        if leading <= indent: break
                        item.append(lines[i][min(leading, content_indent):]); i += 1
                    task = re.match(r'^\[([ xX])\]\s+(.*)$', item[0])
                    checkbox = ''
                    if task:
                        item[0] = task[2]
                        checkbox = '<input type="checkbox" disabled aria-label="Recorded task status"' + (' checked' if task[1].lower() == 'x' else '') + '>'
                    value = ' value="' + str(number) + '"' if ordered else ''
                    items.append('<li' + value + '>' + checkbox + render(item, depth + 1) + '</li>')
                out.append('<' + tag + ' class="ros-list"' + attrs + '>' + ''.join(items) + '</' + tag + '>')
                continue
            if re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*', line):
                out.append('<hr>'); i += 1; continue
            paragraph = [line]; i += 1
            while i < len(lines) and not block_start(lines[i]) and not _IMAGE.fullmatch(lines[i].strip()):
                if i + 1 < len(lines) and '|' in lines[i]:
                    cells, rules = _table_cells(lines[i]), _table_cells(lines[i + 1])
                    if len(cells) == len(rules) and all(re.fullmatch(r':?-{3,}:?', r) for r in rules): break
                paragraph.append(lines[i]); i += 1
            fragments = []
            for j, text in enumerate(paragraph):
                hard_break = text.endswith('  ') or text.endswith('\\')
                fragments.append(_inline(text[:-1].rstrip() if text.endswith('\\') else text.rstrip()))
                if j < len(paragraph) - 1: fragments.append('<br>' if hard_break else ' ')
            out.append('<p>' + ''.join(fragments) + '</p>')
        return '\n'.join(out)

    return render(body.splitlines())


def _question_html(q):
    """Static fallback markup for one question; the runtime replaces it with the interactive panel."""
    kind = q.get("kind", "free-response")
    if kind not in QUESTION_KINDS:
        kind = "free-response"
    content = '<section data-ros="' + kind + '" data-question-id="' + html.escape(q["id"], quote=True) + '"><h3>' + html.escape(str(q.get("prompt", ""))) + '</h3><form>'
    if kind in {"mcq", "multi"}:
        for i, option in enumerate(q.get("options", [])):
            value = option.get("value", str(i)) if isinstance(option, dict) else str(i)
            label = option.get("label", "") if isinstance(option, dict) else str(option)
            content += '<label><input name="answer" type="' + ("radio" if kind == "mcq" else "checkbox") + '" value="' + html.escape(str(value), quote=True) + '">' + html.escape(str(label)) + '</label>'
    else:
        content += '<textarea name="answer" aria-label="Your response"></textarea>'
    content += '<button type="submit">Save response</button><button type="button" data-ros-action="reset">Reset</button><output data-ros-feedback></output></form>'
    for hint in q.get("hints", []):
        content += '<details data-ros="hint"><summary>Hint</summary>' + html.escape(str(hint)) + '</details>'
    if "solution" in q:
        content += '<details data-ros="solution"><summary>Solution</summary>' + html.escape(str(q["solution"])) + '</details>'
    return content + '</section>'


def _questions_html(state, placed=()):
    """Questions without a marker in the source (older sessions) follow the content."""
    return "\n".join(_question_html(q) for q in state["questions"] if q["id"] not in placed)


def _widgets_html(state):
    return "".join('<section data-ros="widget" data-widget="' + html.escape(w["kind"], quote=True) + '" id="' + html.escape(w["id"], quote=True) + '"><h3>' + html.escape(w.get("title", w["kind"].title() + " demonstration")) + '</h3></section>' for w in state.get("widgets", []))


def render_html(state, runtime_prefix=".research-os/runtime", standalone=False, resource_markup="", resource_scripts="", resource_images=None):
    validate_state(state)
    placed = set()
    content = markdown_html(state["source_markdown"], page_title=state["title"], questions={q["id"]: q for q in state["questions"]}, placed=placed)
    if resource_images:
        def embed_image(match):
            image = match.group()
            identifier = re.search(r'data-resource-id="([^"]+)"', image)[1]
            data = resource_images.get(identifier)
            return image[:-1] + ' src="' + html.escape(data, quote=True) + '">' if data else image
        content = re.sub(r'<img data-resource-id="[^"]+"[^>]*>', embed_image, content)
    anchors = re.findall(r'<h([1-6])\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h\1>', content, re.S)
    navigation = ('<nav class="ros-toc" aria-label="Session sections"><details class="ros-toc-panel" open><summary>Contents</summary><ul>'
                  + ''.join('<li data-level="' + level + '"><a href="#' + anchor + '">' + label + '</a></li>' for level,anchor,label in anchors)
                  + '</ul></details></nav>') if anchors else ''
    # The title and optional subtitle are the whole header: kind/status/date badges added noise, not orientation.
    subtitle = state.get('metadata', {}).get('subtitle')
    subtitle_markup = ('<p class="ros-session-context">' + html.escape(subtitle) + '</p>') if isinstance(subtitle, str) and subtitle.strip() else ''
    header = '<header class="ros-session-header"><h1>' + html.escape(state['title']) + '</h1>' + subtitle_markup + '</header>'
    # The context binding holds local paths and is for agents, not the page or a shared export.
    data = json.dumps({k: v for k, v in state.items() if k != "context"}, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    if standalone:
        css = (RUNTIME / "session.css").read_text(encoding="utf-8")
        js = (RUNTIME / "session.js").read_text(encoding="utf-8")
        resources = "<style>" + css + "</style>"
        script = "<script>" + js.replace("</script", "<\\/script") + "</script>"
    else:
        prefix = html.escape(runtime_prefix, quote=True)
        resources = '<link rel="stylesheet" href="' + prefix + '/session.css">'
        script = '<script src="' + prefix + '/session.js"></script>'
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\' \'unsafe-inline\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data:; font-src data:; connect-src \'none\'; form-action \'none\'; base-uri \'none\'">'
            + '<title>' + html.escape(state["title"]) + '</title>' + resources + '</head><body><main class="ros-document" id="ros-session">'
            + header
            + navigation + content + _questions_html(state, placed) + _widgets_html(state) + resource_markup
            + '<details data-ros="legacy"><summary>Exact original Markdown</summary><pre>' + html.escape(state["source_markdown"]) + '</pre></details>'
            + '</main><script type="application/json" id="ros-session-data">' + data + '</script>' + script + resource_scripts + '</body></html>\n')


def render_bridge(state, relative_html):
    # Preserve the full note for existing Markdown-based graph/protocol readers.
    return state["source_markdown"] + BRIDGE_MARKER + '\n```ros-session\n' + relative_html + '\n```\n'


def _transaction_path(root, relative_md):
    md, _, _ = paths(root, relative_md)
    relative = md.relative_to(Path(root).resolve()).as_posix()
    return _path(root, '.research-os/transactions/' + _hash(relative.encode()) + '.json')


def recover_session(root, relative_md, apply=False):
    """Recover under the same lock used by authoring and browser state writes."""
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        return _recover_session_locked(root, relative_md, apply)


def _recover_session_locked(root, relative_md, apply=False):
    """Recover a journaled projection write only if no subsequent edits conflict."""
    journal = _transaction_path(root, relative_md)
    if not journal.exists():
        return {"pending": False, "dry_run": not apply}
    transaction = json.loads(journal.read_text(encoding='utf-8'))
    expected = {p.relative_to(Path(root).resolve()).as_posix() for p in paths(root, relative_md)}
    if transaction.get('schema_version') != 1 or {f['path'] for f in transaction.get('files', [])} != expected:
        raise ValueError('Invalid session recovery journal')
    for entry in transaction['files']:
        path = _path(root, entry['path'])
        raw = base64.b64decode(entry['after'], validate=True)
        if _hash(raw) != entry['after_sha256']:
            raise ValueError('Session recovery integrity failure')
        current = _hash(path.read_bytes()) if path.exists() else None
        if current not in {entry['before_sha256'], entry['after_sha256']}:
            raise ValueError('Session recovery conflict; later edits preserved')
    if apply:
        for entry in transaction['files']:
            _write(_path(root, entry['path']), base64.b64decode(entry['after'], validate=True))
        journal.unlink()
    return {"pending": True, "dry_run": not apply, "session": str(relative_md)}


def load_session(root, relative_md, check_bridge=True):
    md, view, data = paths(root, relative_md)
    if _transaction_path(root, relative_md).exists():
        raise ValueError("Interrupted session write; run recover before resuming")
    state = validate_state(json.loads(data.read_text(encoding="utf-8")))
    if check_bridge and md.read_bytes() != render_bridge(state, view.relative_to(Path(root).resolve()).as_posix()).encode("utf-8"):
        raise ValueError(f"Conflicting manual Markdown bridge edit: {relative_md}")
    return state


def _save(root, relative_md, state):
    md, view, data = paths(root, relative_md)
    validate_state(state)
    for resource in state.get("resources", []):
        value = resource["path"]
        allowed = (view.stem + ".assets/", ".research-os/runtime/extensions/")
        if not value.startswith(allowed):
            raise ValueError("Resource outside approved local session directories")
        resource_path = _path(root, md.parent.relative_to(Path(root).resolve()) / value) if value.startswith(allowed[0]) else _path(root, value)
        if not resource_path.is_file() or resource_path.stat().st_size > 1024 * 1024:
            raise ValueError("Local session resource missing or exceeds limit")
        if resource["kind"] == "module":
            _approved_module(root, resource_path, resource)
    prefix = os.path.relpath(Path(root).resolve() / ".research-os/runtime", view.parent).replace(os.sep, "/")
    outputs = {data: _json(state), view: render_html(state, prefix).encode("utf-8"),
               md: render_bridge(state, view.relative_to(Path(root).resolve()).as_posix()).encode("utf-8")}
    journal = _transaction_path(root, relative_md)
    if journal.exists():
        raise ValueError("Interrupted session write exists; use recover before updating")
    transaction = {"schema_version": 1, "session": str(relative_md), "files": []}
    for path, raw in outputs.items():
        before = path.read_bytes() if path.exists() else None
        transaction["files"].append({"path": path.relative_to(Path(root).resolve()).as_posix(),
            "before_sha256": _hash(before) if before is not None else None,
            "before": base64.b64encode(before).decode() if before is not None else None,
            "after_sha256": _hash(raw), "after": base64.b64encode(raw).decode()})
    _write(journal, _json(transaction))
    for path, raw in outputs.items():
        _write(path, raw)
    journal.unlink()
    return state


def create_session(root, relative_md, text, session_type=None, title=None, metadata=None, questions=None, widgets=None, resources=None, context=None):
    md, _, _ = paths(root, relative_md)
    md.parent.mkdir(parents=True, exist_ok=True)
    with Lock(md.with_suffix('.session.lock')):
        return _create_session(root, relative_md, text, session_type, title, metadata, questions, widgets, resources, context)


def _create_session(root, relative_md, text, session_type=None, title=None, metadata=None, questions=None, widgets=None, resources=None, context=None):
    md, view, data = paths(root, relative_md)
    if data.exists() or view.exists():
        raise ValueError(f"Session already exists: {relative_md}")
    if md.exists() and md.read_bytes() != text.encode("utf-8"):
        raise ValueError("Existing Markdown differs from requested session source")
    front, _ = parse_frontmatter(text.replace("\r\n", "\n"))
    state = {"schema_version": 1, "session_id": uuid.uuid4().hex,
             "type": session_type or front.get("type", "research-session"),
             "title": title or front.get("title", md.stem), "metadata": dict(metadata or front),
             "source_markdown": text, "events": [], "questions": list(questions or []),
             "open_questions": [], "lifecycle": front.get("status", "active"), "created_at": _now(), "updated_at": _now()}
    state["widgets"] = list(widgets or [])
    state["resources"] = list(resources or [])
    if context is not None:
        state["context"] = context
    if front.get("session_id"):
        state["session_id"] = front["session_id"]
    return _save(root, relative_md, state)


def update_session(root, relative_md, text=None, **changes):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        allowed = {"title", "metadata", "questions", "open_questions", "lifecycle", "widgets", "resources"}
        if set(changes) - allowed:
            raise ValueError("Unsupported session update fields")
        source = state["source_markdown"] if text is None else text
        front, _ = parse_frontmatter(source.replace("\r\n", "\n"))
        proposed_metadata = changes.get("metadata", {})
        if any(key in front and value != front[key] for key,value in proposed_metadata.items()):
            raise ValueError('Metadata contradicts source frontmatter; update the source explicitly')
        if 'lifecycle' in changes and front.get('status', changes['lifecycle']) != changes['lifecycle']:
            raise ValueError('Lifecycle contradicts source status; update the source explicitly')
        state.update(changes)
        state["source_markdown"] = source
        state['metadata'].update(front)
        state['type'] = front.get('type', state['type'])
        state['lifecycle'] = front.get('status', state['lifecycle'])
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def bind_context(receipt, request=None):
    """The durable form of a context receipt stored in a session (a binding, not the receipt)."""
    import context_kernel as ck
    return {"binding": ck.summary(receipt), "request": request or receipt["request"], "bound_at": _now(), "refreshed_at": None}


def waive_context(reason):
    """An explicit, recorded decision to work without graph context (never a default)."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A context waiver needs a reason")
    return {"waived": True, "reason": reason.strip(), "bound_at": _now()}


def bind_session_context(root, relative_md, receipt):
    """Adopt a context binding for an existing (e.g. historical) session; refuses a blocked receipt."""
    import context_kernel as ck
    ck.require(receipt)
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        state["context"] = bind_context(receipt)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def _ensure_context(state):
    """Precondition for tutoring actions: the bound context must still describe the canonical records.

    Sessions created without a binding (historical ones) are unaffected. A stale binding is rebuilt from
    its stored request; if the rebuilt context is blocked, the action is refused and nothing is written.
    """
    bound = state.get("context")
    if bound is None or bound.get("waived"):
        return
    import context_kernel as ck
    try:
        ck.require(bound["binding"], summary_only=True)
    except ck.ContextError as exc:
        if exc.code != "CONTEXT_STALE":
            raise
        receipt = ck.build(bound["request"])
        ck.require(receipt)
        state["context"] = dict(bound, binding=ck.summary(receipt), refreshed_at=_now())


def answer_open_question(root, relative_md, question_id, answer):
    """Record an actual agent answer without inventing assessment evidence."""
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 32000:
        raise ValueError('A nonempty bounded answer is required')
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        state = load_session(root, relative_md)
        record = next((q for q in state['open_questions'] if q.get('id') == question_id), None)
        if record is None:
            raise ValueError('Unknown open question')
        if record.get('answer'):
            if record['answer'] == answer:
                return state
            raise ValueError('Question already answered; existing answer preserved')
        record.update(answer=answer, status='answered', answered_at=_now())
        return _save(root, relative_md, state)


def append_session(root, relative_md, block):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        _ensure_context(state)
        state["source_markdown"] += block
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def append_event(root, relative_md, event):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        event = dict(event)
        event.setdefault("event_id", uuid.uuid4().hex)
        if any(e["event_id"] == event["event_id"] for e in state["events"]):
            return state
        event["status"] = "pending-review"
        event.setdefault("created_at", _now())
        state["events"].append(event)
        if event["type"] == "open-question":
            state["open_questions"].append({"id": event["event_id"], "session_id": state["session_id"], "concept": state["metadata"].get("concept"), "prompt": event.get("response", ""), "status": "open", "created_at": event["created_at"], "explanation_refs": []})
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def _append_question(state, question):
    if not isinstance(question, dict) or not isinstance(question.get("id"), str) or not question["id"]:
        raise ValueError("A question needs a nonempty id")
    if any(q["id"] == question["id"] for q in state["questions"]):
        raise ValueError(f"Question already exists: {question['id']}")
    if question.get("kind", "free-response") not in QUESTION_KINDS:
        raise ValueError("Unsupported question kind")
    if not isinstance(question.get("prompt"), str) or not question["prompt"].strip():
        raise ValueError("A question needs a prompt")
    if "reviews" in question:
        raise ValueError("Reviews are recorded with review_response, not authored")
    if not QUESTION_MARKER.match("<!-- ros-question: " + question["id"] + " -->"):
        raise ValueError("Question ids use letters, digits, dot, underscore, colon or hyphen")
    state["questions"].append(dict(question))
    # Place the question where the session currently ends: after the teaching that led to it.
    if not re.search(r"^<!--\s*ros-question:\s*" + re.escape(question["id"]) + r"\s*-->\s*$", state["source_markdown"], re.M):
        source = state["source_markdown"]
        separator = "" if source.endswith("\n\n") else "\n" if source.endswith("\n") else "\n\n"
        state["source_markdown"] = source + separator + "<!-- ros-question: " + question["id"] + " -->\n"


def add_question(root, relative_md, question):
    """Post one new question; open session views show it live without reloading."""
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        _ensure_context(state)
        _append_question(state, question)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def review_response(root, relative_md, question_id, verdict, feedback="", next_question=None, transcript=None):
    """Record the tutor's verdict on the learner's latest actual response.

    The verdict and the question's prepared explanation appear in place of the
    learner's "Checking..." state. It is pending tutor feedback, not ledger
    evidence: canonical attempts still follow the learning protocol. One save can
    also post the next question and a transcript entry so the page updates once.
    """
    if verdict not in REVIEW_VERDICTS:
        raise ValueError("Verdict must be one of: " + ", ".join(REVIEW_VERDICTS))
    if not isinstance(feedback, str) or len(feedback) > 32000:
        raise ValueError("Feedback must be bounded text")
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        question = next((q for q in state["questions"] if q["id"] == question_id), None)
        if question is None:
            raise ValueError("Unknown question")
        if transcript or next_question is not None:
            _ensure_context(state)  # a verdict alone teaches nothing new; new teaching or probes need current context
        response = next((e for e in reversed(state["events"]) if e["type"] == "response" and e.get("question_id") == question_id), None)
        if response is None:
            raise ValueError("No learner response to review; never invent an answer")
        review = {"response_event_id": response["event_id"], "verdict": verdict, "feedback": feedback.strip(), "reviewed_at": _now()}
        reviews = question.setdefault("reviews", [])
        if not reviews or {k: v for k, v in reviews[-1].items() if k != "reviewed_at"} != {k: v for k, v in review.items() if k != "reviewed_at"}:
            reviews.append(review)
        # Transcript first, then the next question, so the page reads in the order things happened.
        if transcript:
            separator = "" if state["source_markdown"].endswith("\n\n") else "\n" if state["source_markdown"].endswith("\n") else "\n\n"
            state["source_markdown"] += separator + transcript.strip("\n") + "\n"
        if next_question is not None:
            _append_question(state, next_question)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def pending_activity(state):
    """Learner activity awaiting the session agent: unreviewed latest responses and unanswered questions."""
    items = []
    for q in state["questions"]:
        events = [e for e in state["events"] if e.get("question_id") == q["id"]]
        responses = [e for e in events if e["type"] == "response"]
        if not responses:
            continue
        latest = responses[-1]
        if latest["event_id"] in {r.get("response_event_id") for r in q.get("reviews", [])}:
            continue
        confidence = next((e["response"] for e in reversed(events) if e["type"] == "confidence"), None)
        items.append({"kind": "response", "question_id": q["id"], "question_kind": q.get("kind", "free-response"),
                      "prompt": q.get("prompt", ""), "event_id": latest["event_id"], "response": latest.get("response"),
                      "created_at": latest.get("created_at"), "attempts": len(responses), "confidence": confidence,
                      "hints_revealed": max([int(e["response"]) for e in events if e["type"] == "hint" and isinstance(e.get("response"), int)] or [0]),
                      "solution_seen_before_response": any(e["type"] == "solution" and e.get("created_at", "") < latest.get("created_at", "") for e in events)})
    for record in state.get("open_questions", []):
        if not (isinstance(record.get("answer"), str) and record["answer"].strip()):
            items.append({"kind": "open-question", "id": record.get("id"), "prompt": record.get("prompt"), "created_at": record.get("created_at")})
    return items


def wait_for_activity(root, relative_md, timeout=900.0, interval=1.0):
    """Bounded poll for an explicit learner submission; returns immediately if work is pending.

    Only explicit submissions count (Submit/Send), never idle timers or typing.
    """
    _, _, data = paths(root, relative_md)
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        try:
            items = pending_activity(validate_state(json.loads(data.read_text(encoding="utf-8"))))
        except (OSError, ValueError, json.JSONDecodeError):
            items = []  # A writer may be mid-replace; the next poll rereads.
        if items or time.monotonic() >= deadline:
            return {"session": str(relative_md), "pending": items, "timed_out": not items}
        time.sleep(interval)


SESSION_WORKFLOWS = {"tutor-session": "tutor", "course-session": "course-study", "research-session": "research-plan"}


def context_request(root, metadata, session_type=None, session=None, **overrides):
    """Kernel request for a session: its project and concept come from its own frontmatter."""
    import context_kernel as ck
    request = {"workflow": SESSION_WORKFLOWS.get(session_type, "tutor"), "vault": str(Path(root).resolve())}
    project = ck.wikilink_target(metadata.get("project")) or ck.wikilink_target(metadata.get("up"))
    if project:
        request["project"] = project
    concept = ck.wikilink_target(metadata.get("concept"))
    if concept and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", concept):
        request["target"] = {"kind": "concept", "id": concept}
    if session:
        request["session"] = session
    request.update({k: v for k, v in overrides.items() if v is not None})
    return request


def session_context(root, relative_md, project_root=None, learning_root=None, as_of=None, library_root=None):
    """Resume brief built on the context kernel; also works before the session exists (bootstrap).

    The HTML page is a view, not memory. Nothing here grades, accepts or edits a session; the only
    write is the kernel's receipt cache under the vault's .research-os/context.
    """
    import context_kernel as ck
    root = Path(root).resolve()
    md, _, data = paths(root, relative_md)
    state = load_session(root, relative_md) if data.exists() else None
    if state is not None:
        metadata, session_type, source = state["metadata"], state["type"], state["source_markdown"]
    else:
        metadata, source = parse_frontmatter(md.read_text(encoding="utf-8").replace("\r\n", "\n")) if md.exists() else ({}, "")
        session_type = metadata.get("type")
    mentioned = sorted(set(re.findall(r"\b(?:RQ|H|EXP|DEC)-\d{3,}\b", source)))
    request = context_request(root, metadata, session_type, str(relative_md), project_root=project_root,
                              learning_root=learning_root, library_root=library_root, as_of=as_of, records=mentioned or None)
    receipt, receipt_file, _ = ck.preflight(request)
    retrieval = receipt["retrieval"]
    learner, research = retrieval["learner"], retrieval["research"]
    sources = {s["name"]: s for s in receipt["sources"]}
    brief = {"session": str(relative_md), "exists": state is not None,
             "title": state["title"] if state else metadata.get("title", md.stem),
             "type": session_type, "lifecycle": state.get("lifecycle") if state else None,
             "updated_at": state.get("updated_at") if state else None,
             "pending": pending_activity(state) if state else [], "questions": [], "project": retrieval["project"],
             "research": None, "knowledge": None, "notes": [], "receipt": receipt,
             "receipt_file": str(receipt_file) if receipt_file else None, "blocked": receipt["outcome"] == "blocked"}
    for q in (state["questions"] if state else []):
        responses = [e for e in state["events"] if e["type"] == "response" and e.get("question_id") == q["id"]]
        review = (q.get("reviews") or [None])[-1]
        brief["questions"].append({"id": q["id"], "kind": q.get("kind", "free-response"), "attempts": len(responses),
                                   "latest_response": responses[-1].get("response") if responses else None,
                                   "verdict": review["verdict"] if review and responses and review.get("response_event_id") == responses[-1]["event_id"] else None})
    if research:
        brief["research"] = {"root": sources["research"]["path"], "records": research["records_total"],
                             "errors": sources["research"]["counts"].get("errors", 0),
                             "active_questions": research["active_questions"], "active_hypotheses": research["active_hypotheses"],
                             "frontier": research["frontier"], "pending_validation": research["pending_validation"],
                             "pending_human_decisions": research["pending_human_decisions"],
                             "accepted_decisions": research["accepted_decisions"],
                             "session_records": [{"id": r["id"], "type": r["type"], "status": r["status"], "title": r["title"]}
                                                 for r in research["relevant_records"] if "requested" in r["relevance"]]}
    if learner:
        pick = lambda test: [{"id": n["id"], "title": n["title"], "state": n["state"], "freshness": n["freshness"]}
                             for n in learner["nodes"] if test(n)][:15]
        brief["knowledge"] = {"root": sources["learning"]["path"], "project": receipt["request"].get("project_id"),
                              "capabilities": learner["capabilities_total"], "states": learner["states"],
                              "frontier": pick(lambda n: n["frontier"]),
                              "stale_or_due": pick(lambda n: n["freshness"] in {"due", "overdue"} or n["state"] in {"stale", "fragile"}),
                              "diagnostics": learner["diagnostics"][:10]}
    return brief


def render_context(brief):
    """Compact Markdown for an agent resuming the session."""
    lines = [f"# Resume brief: {brief['title']}", "", f"Session `{brief['session']}` ({brief['type']}, {brief['lifecycle']}), updated {brief['updated_at']}." + ("" if brief.get("exists", True) else " Not created yet (bootstrap)."), ""]
    receipt = brief.get("receipt")
    if receipt:
        lines += [f"## Context: {receipt['outcome'].upper()}", "",
                  f"- Receipt `{receipt['receipt_id']}` ({receipt['workflow']}, {receipt['mode']})" + (f", file `{brief['receipt_file']}`" if brief.get("receipt_file") else "")]
        if receipt["outcome"] == "blocked":
            lines.append("- BLOCKED: essential context is unavailable (" + ", ".join(receipt["blocking"]) + "). Do not teach, post questions or edit this session until it is repaired.")
        lines += [f"- Limitation: {x}" for x in receipt["limitations"]] + [""]
    lines += ["## Awaiting you", ""]
    for item in brief["pending"]:
        if item["kind"] == "response":
            lines.append(f"- Review `{item['question_id']}` ({item['question_kind']}, attempt {item['attempts']}, confidence {item['confidence']}, hints {item['hints_revealed']}): {json.dumps(item['response'], ensure_ascii=False)[:400]}")
        else:
            lines.append(f"- Answer open question `{item['id']}`: {str(item['prompt'])[:400]}")
    if not brief["pending"]:
        lines.append("- Nothing pending. Run `wait` to listen for the next submission.")
    lines += ["", "## Questions", ""] + [f"- `{q['id']}` {q['kind']}: {q['attempts']} attempt(s), verdict {q['verdict'] or '-'}" for q in brief["questions"]]
    if brief["project"]:
        lines += ["", "## Project memory", "", f"- Project note: `{brief['project']['note']}` (read its current state before teaching or deciding)", f"- Project ID `{brief['project']['id']}`, root `{brief['project']['path']}`"]
    research = brief["research"]
    if research:
        lines += ["", "## Research graph", "", f"- {research['records']} records under `{research['root']}`, {research['errors']} validation error(s)",
                  "- Active questions: " + (", ".join(research["active_questions"]) or "none"), "- Active hypotheses: " + (", ".join(research["active_hypotheses"]) or "none"),
                  "- Frontier (unranked): " + (", ".join(f"{f['id']} {f['transition']}" for f in research["frontier"]) or "none"),
                  "- Awaiting human decision: " + (", ".join(research["pending_human_decisions"]) or "none") + "; awaiting result validation: " + (", ".join(research["pending_validation"]) or "none")]
        lines += [f"- Accepted decision {d['id']}: {d['title']}" + (f" ({'; '.join(d['relevance'])})" if d["relevance"] else "")
                  for d in research.get("accepted_decisions", [])]
        for record in research["session_records"]:
            lines.append(f"- Session refers to {record['id']} ({record['type']}, {record['status']}): {record['title']}; load it with `research.py context --root \"{research['root']}\" --{ {'research-question': 'question', 'research-decision': 'decision'}.get(record['type'], record['type'])} {record['id']}`")
    knowledge = brief["knowledge"]
    if knowledge:
        lines += ["", "## Knowledge graph", "", f"- {knowledge['capabilities']} capabilities for `{knowledge['project']}` under `{knowledge['root']}`: " + ", ".join(f"{k} {v}" for k, v in sorted(knowledge["states"].items()))]
        lines += [f"- Frontier: {n['title']} ({n['id']}, {n['state']})" for n in knowledge["frontier"]]
        lines += [f"- Stale, fragile or due: {n['title']} ({n['id']}, {n['state']}, {n['freshness']})" for n in knowledge["stale_or_due"]]
    lines += [f"- Note: {n}" for n in brief["notes"]]
    return "\n".join(lines) + "\n"


def export_session(root, relative_md, destination):
    state = load_session(root, relative_md)
    md, view, _ = paths(root, relative_md)
    markup, scripts, images = "", "", {}
    used_images = set(re.findall(r'data-resource-id="([^"]+)"', markdown_html(state['source_markdown'])))
    for resource in state.get("resources", []):
        value = resource["path"]
        if value.startswith(view.stem + ".assets/"):
            path = _path(root, md.parent.relative_to(Path(root).resolve()) / value)
        elif value.startswith(".research-os/runtime/extensions/"):
            path = _path(root, value)
        else:
            raise ValueError("Unapproved export resource")
        raw = path.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("Export resource exceeds limit")
        if resource["kind"] == "image":
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]
            data_url = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()
            images[resource['id']] = data_url
            if resource['id'] not in used_images:
                markup += '<figure class="ros-figure"><img src="' + data_url + '" alt="' + html.escape(str(resource.get("alt", "Session illustration")), quote=True) + '"></figure>'
        else:
            _approved_module(root, path, resource)
            scripts += '<script>document.addEventListener("DOMContentLoaded",function(){' + raw.decode("utf-8").replace("</script", "<\\/script") + '\n},{once:true});</script>'
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Export destination already exists; choose a new file to preserve user data")
    _write(destination, render_html(state, standalone=True, resource_markup=markup, resource_scripts=scripts, resource_images=images).encode("utf-8"))
    return destination


def refresh_projection(root, relative_md, backup_directory, apply=False):
    """Refresh only generated HTML, preserving canonical JSON and Markdown bytes."""
    md, view, data = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        state = load_session(root, relative_md)
        protected = {md: md.read_bytes(), data: data.read_bytes()}
        before = view.read_bytes()
        prefix = os.path.relpath(Path(root).resolve() / '.research-os/runtime', view.parent).replace(os.sep, '/')
        after = render_html(state, prefix).encode('utf-8')
        report = {'path': view.relative_to(Path(root).resolve()).as_posix(), 'changed': before != after,
                  'before_sha256': _hash(before), 'after_sha256': _hash(after), 'dry_run': not apply}
        if apply and before != after:
            backup = Path(backup_directory) / view.relative_to(Path(root).resolve())
            if backup.exists(): raise ValueError('Projection backup already exists; choose a new backup directory')
            _write(backup, before)
            _write(view, after)
            report['backup'] = str(backup)
        if any(path.read_bytes() != raw for path, raw in protected.items()):
            raise ValueError('Protected session content changed during projection refresh')
        return report


def import_bridge(root, relative_md, apply=False):
    """Explicitly review and import a bridge edit; normal updates reject it."""
    md, view, data = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md, check_bridge=False)
        raw = md.read_bytes().decode("utf-8")
        if raw.count(BRIDGE_MARKER) != 1:
            raise ValueError("Bridge import requires exactly one intact session marker")
        source, trailer = raw.split(BRIDGE_MARKER)
        expected = render_bridge({**state, "source_markdown": ""}, view.relative_to(Path(root).resolve()).as_posix())[len(BRIDGE_MARKER):]
        if trailer != expected:
            raise ValueError("Bridge import cannot alter session embed or paths")
        result = {"path": str(relative_md), "changed": source != state["source_markdown"], "dry_run": not apply, "before_sha256": _hash(state["source_markdown"].encode()), "after_sha256": _hash(source.encode())}
        if apply and result["changed"]:
            backup = _path(root, ".research-os/imports/" + uuid.uuid4().hex)
            backup.mkdir(parents=True)
            for path in (md, view, data):
                _write(backup / path.name, path.read_bytes())
            _write(backup / "manifest.json", _json(result))
            state["source_markdown"] = source
            state["updated_at"] = _now()
            _save(root, relative_md, state)
            result["backup"] = backup.relative_to(Path(root).resolve()).as_posix()
        return result


def session_exceptions(root):
    path = Path(root) / ".research-os/session-exceptions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("exceptions"), list):
        raise ValueError("Invalid session exceptions manifest")
    for entry in data["exceptions"]:
        if not isinstance(entry, dict) or not entry.get("reason") or entry.get("kind") not in {"imported-archive", "pending-migration"}:
            raise ValueError("Invalid session exception")
        _path(root, entry["path"])
    return data["exceptions"]


def validate_sessions(root, exceptions=None):
    errors = []
    excluded = {e["path"] for e in session_exceptions(root)}
    excluded.update(exceptions or [])
    for candidate in inventory(root):
        if candidate["path"] in excluded or candidate["status"] == "exception":
            continue
        if candidate["status"] != "migrated":
            errors.append(f"{candidate['path']}: {candidate['status']} session missing HTML/state sidecars")
    for data in Path(root).rglob("*.state.json"):
        md = data.with_name(data.name[:-11] + ".md")
        try:
            state = load_session(root, md.relative_to(Path(root)))
            view = md.with_suffix(".html")
            prefix = os.path.relpath(Path(root).resolve() / ".research-os/runtime", view.parent).replace(os.sep, "/")
            # Host interaction writes state alone; the rendered content remains a
            # valid projection while bootstrap events are refreshed on next open.
            def without_bootstrap(value):
                return re.sub(r'(<script type="application/json" id="ros-session-data">).*?(</script>)', r'\1\2', value, flags=re.S)
            if without_bootstrap(view.read_bytes().decode("utf-8")) != without_bootstrap(render_html(state, prefix)):
                raise ValueError("HTML projection differs from structured state")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{data.relative_to(root)}: {exc}")
    return errors


def inventory(root):
    report = []
    exceptions = {e["path"]: e for e in session_exceptions(root)}
    for md in sorted(Path(root).rglob("*.md")):
        rel = md.relative_to(root).as_posix()
        if md.name.upper() in {"SKILL.MD", "README.MD", "AGENTS.MD", "CLAUDE.MD"}:
            continue
        if any(part.lower() in {"docs", "policies", "scripts", "tests", "skills"} for part in md.relative_to(root).parts[:-1]):
            continue
        if any(part.startswith(".") for part in md.relative_to(root).parts) or any(part.lower() in {"templates", "90 templates"} for part in md.relative_to(root).parts[:-1]):
            continue
        try:
            source = md.read_bytes().decode("utf-8")
        except (UnicodeError, OSError) as exc:
            if any("session" in part.lower() for part in md.relative_to(root).parts[:-1]):
                report.append({"path": rel, "signals": ["session directory"], "status": "blocked", "error": str(exc)})
            continue
        front, body = parse_frontmatter(source.replace("\r\n", "\n"))
        if rel.startswith("assets/obsidian/") and re.search(r"^# \{\{title\}\}", body, re.M):
            continue
        signals = []
        type_ = front.get("type", "").lower()
        # Explicit record types take precedence over incidental narrative mentions.
        if type_ and "session" not in type_ and not front.get("session_type"):
            continue
        if "session" in type_:
            signals.append("frontmatter type")
        if any(part.lower() in {"sessions", "00 tutor sessions", "tutor sessions", "research sessions", "learning sessions", "study sessions", "course sessions"} for part in md.relative_to(root).parts[:-1]):
            signals.append("session directory")
        if re.search(r"^#{1,2}\s+.*(?:Tutor|Research|Learning|Study|Course|Recitation)\s+Session", body, re.M | re.I):
            signals.append("session heading")
        if front.get("session_id") or front.get("session_type"):
            signals.append("session metadata")
        if not signals:
            continue
        state_path = md.with_suffix(".state.json")
        status = "migrated" if state_path.exists() else ("ambiguous" if signals in (["session directory"], ["session heading"]) else "candidate")
        if rel in exceptions:
            status = "exception"
        candidate = {"path": rel, "signals": signals, "status": status, "sha256": _hash(md.read_bytes())}
        if rel in exceptions:
            candidate["exception"] = exceptions[rel]
        report.append(candidate)
    return report


def legacy_questions(source, metadata):
    """Recover only explicit active Q headings with a learner answer slot.

    Historical text is retained, never graded or treated as fresh evidence.
    Unrecognized formats remain visibly available in the exact-source panel.
    """
    if metadata.get("status", "").lower() not in {"active", "in-progress", "in_progress"}:
        return []
    lines = source.replace("\r\n", "\n").splitlines()
    questions = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{2,4})\s+(?:Q(?:uestion)?\s*\d+)[.\s:—-]*(.*)$", line, re.I)
        if not match:
            continue
        end = index + 1
        while end < len(lines) and not re.match(r"^#{1," + str(len(match[1])) + r"}\s", lines[end]):
            end += 1
        block = "\n".join(lines[index + 1:end])
        slot = re.search(r"(?:\*\*|#{1,6}\s*)?My answer(?:\*\*)?\s*:(?:\*\*)?\s*(.*)", block, re.I)
        if not slot:
            continue
        prompt = match[2].strip() or block[:slot.start()].strip()
        if not prompt:
            continue
        questions.append({"id": "legacy-q-" + str(len(questions) + 1), "kind": "free-response", "prompt": prompt, "historical_response": slot[1], "historical_source": block, "review_status": "unreviewed", "provenance": "explicit legacy question and learner answer slot"})
    return questions


def migrate(root, apply=False, journal=None, resume=False, rollback=False):
    root = Path(root).resolve()
    if not apply and not resume and not rollback:
        return _migrate_locked(root, apply, journal, resume, rollback)
    journal_path = _path(root, journal or '.research-os/migrations/v0.8.5/manifest.json')
    candidates = {r['path'] for r in inventory(root)}
    if journal_path.exists():
        log = json.loads(journal_path.read_text(encoding='utf-8'))
        candidates.update(r['path'] for r in log.get('records', []))
    with ExitStack() as locks:
        for relative in sorted(candidates):
            md, _, _ = paths(root, relative)
            locks.enter_context(Lock(md.with_suffix('.session.lock')))
        return _migrate_locked(root, apply, journal, resume, rollback)


def _migrate_locked(root, apply=False, journal=None, resume=False, rollback=False):
    """Journal all intended hashes and exact bytes before changing any candidate.

    Resume repairs only files whose hashes match either the recorded original or
    intended projection. Rollback has the same guard against concurrent edits.
    """
    root = Path(root).resolve()
    journal = _path(root, journal or ".research-os/migrations/v0.8.5/manifest.json")
    if not apply and not resume and not rollback:
        return {"dry_run": True, "candidates": inventory(root)}
    verify_only = False
    if journal.exists():
        log = json.loads(journal.read_text(encoding="utf-8"))
        if not resume and not rollback:
            if log.get("status") == "complete":
                candidates = inventory(root)
                if any(c["status"] in {"candidate", "blocked", "ambiguous"} for c in candidates):
                    raise ValueError("New unmigrated candidates found; use a new --journal for a new batch")
                # A complete journal is still verified against current files below.
                resume = True
                verify_only = True
            else:
                raise ValueError("Migration journal exists; use --resume or --rollback")
    else:
        if resume or rollback:
            raise ValueError("Migration journal missing")
        records = []
        for candidate in inventory(root):
            if candidate["status"] in {"migrated", "exception"}:
                continue
            if candidate["status"] in {"blocked", "ambiguous"}:
                raise ValueError(f"Unresolved {candidate['status']} session candidate: {candidate['path']}; review inventory and add a documented exception when appropriate")
            md, view, data = paths(root, candidate["path"])
            if view.exists() or data.exists():
                raise ValueError(f"Existing sidecar conflict: {candidate['path']}")
            raw = md.read_bytes()
            backup = journal.parent / "backups" / (uuid.uuid4().hex + ".md")
            _write(backup, raw)
            front, _ = parse_frontmatter(raw.decode("utf-8").replace("\r\n", "\n"))
            source = raw.decode("utf-8")
            state = {"schema_version": 1, "session_id": front.get("session_id", uuid.uuid4().hex), "type": front.get("type", "legacy-session"), "title": front.get("title", md.stem), "metadata": front, "source_markdown": source, "events": [], "questions": legacy_questions(source, front), "open_questions": [], "lifecycle": front.get("status", "legacy"), "created_at": _now(), "updated_at": _now(), "migration": {"conversion": "conservative structural HTML; unknown interactions preserved as legacy source", "historical_answers_reviewed": False}}
            prefix = os.path.relpath(root / ".research-os/runtime", view.parent).replace(os.sep, "/")
            outputs = {md.relative_to(root).as_posix(): render_bridge(state, view.relative_to(root).as_posix()).encode("utf-8"), view.relative_to(root).as_posix(): render_html(state, prefix).encode("utf-8"), data.relative_to(root).as_posix(): _json(state)}
            records.append({"path": candidate["path"], "signals": candidate["signals"], "backup": backup.relative_to(root).as_posix(), "before_hash": _hash(raw), "state": state, "outputs": {p: {"sha256": _hash(b), "content": b.decode("utf-8")} for p, b in outputs.items()}, "status": "prepared"})
        log = {"schema_version": 1, "root": str(root), "status": "prepared", "records": records, "discovery": inventory(root), "created_at": _now(), "recovery": "Run migrate --resume to finish unchanged projections, or migrate --rollback to restore verified exact originals."}
        _write(journal, _json(log))
    if log.get("root") != str(root) or log.get("schema_version") != 1:
        raise ValueError("Migration journal belongs to a different root/schema")
    # Preflight entire batch before changing a single file.
    for record in log["records"]:
        backup = _path(root, record["backup"])
        if _hash(backup.read_bytes()) != record["before_hash"]:
            raise ValueError("Migration backup integrity failure")
        for rel, projection in record["outputs"].items():
            path = _path(root, rel)
            if _hash(projection["content"].encode("utf-8")) != projection["sha256"]:
                raise ValueError("Migration journal integrity failure")
            if path.exists():
                digest = _hash(path.read_bytes())
                allowed = {projection["sha256"]}
                if rel == record["path"]:
                    allowed.add(record["before_hash"])
                if digest not in allowed:
                    raise ValueError(f"Migration conflict; refusing overwrite: {rel}")
            elif rel == record["path"]:
                raise ValueError(f"Missing migration source: {rel}")
    if verify_only:
        return {"dry_run": False, "status": "complete", "candidates": inventory(root), "journal": journal.relative_to(root).as_posix()}
    for record in log["records"]:
        if rollback:
            _write(_path(root, record["path"]), _path(root, record["backup"]).read_bytes())
            for rel in record["outputs"]:
                if rel != record["path"]:
                    _path(root, rel).unlink(missing_ok=True)
            record["status"] = "rolled-back"
        else:
            for rel, projection in record["outputs"].items():
                _write(_path(root, rel), projection["content"].encode("utf-8"))
            record["status"] = "complete"
        _write(journal, _json(log))
    log["status"] = "rolled-back" if rollback else "complete"
    _write(journal, _json(log))
    rows = ''.join('<tr><td>' + html.escape(r['path']) + '</td><td>' + html.escape(r['status']) + '</td><td>' + html.escape(', '.join(r['signals'])) + '</td><td>Conservative structural conversion. Original source retained in full; unknown question/solution pairings, tables, wikilinks and attachments remain legacy content. Historical answers are unreviewed.</td></tr>' for r in log['records'])
    _write(journal.parent / 'report.html', ('<!doctype html><meta charset="utf-8"><title>Research OS migration report</title><h1>v0.8.5 migration</h1><p>' + html.escape(log['status']) + '</p><table><thead><tr><th>Session</th><th>Status</th><th>Discovery</th><th>Conversion limitations</th></tr></thead><tbody>' + rows + '</tbody></table>').encode('utf-8'))
    updated = {r["path"]: {"path": r["path"], "signals": r["signals"], "status": r["status"]} for r in log["records"]}
    candidates = [updated.get(r["path"], r) for r in log.get("discovery", [])]
    return {"dry_run": False, "status": log["status"], "candidates": candidates, "journal": journal.relative_to(root).as_posix(), "recovery": log.get("recovery")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("validate")
    create = sub.add_parser("create", help="Create a session after a context preflight; refused when essential context is blocked")
    create.add_argument("session"); create.add_argument("--source", required=True, type=Path); create.add_argument("--type", dest="session_type"); create.add_argument("--title")
    create.add_argument("--workflow", help="context workflow (default follows the session type)")
    create.add_argument("--project"); create.add_argument("--target", help="concept:ID, capability:ID or record:ID")
    create.add_argument("--project-root", type=Path); create.add_argument("--learning-root", type=Path); create.add_argument("--library-root", type=Path)
    create.add_argument("--expect-empty", action="store_true", help="a new learner or project: empty graphs are expected")
    create.add_argument("--waive-context", metavar="REASON", help="record an explicit decision to work without graph context")
    update = sub.add_parser("update"); update.add_argument("session"); update.add_argument("--source", required=True, type=Path)
    append = sub.add_parser("append"); append.add_argument("session"); append.add_argument("--source", required=True, type=Path)
    event = sub.add_parser("event"); event.add_argument("session"); event.add_argument("--source", required=True, type=Path)
    answer = sub.add_parser("answer"); answer.add_argument("session"); answer.add_argument("question_id"); answer.add_argument("--source", required=True, type=Path)
    question = sub.add_parser("add-question", help="Post one question (JSON); open views show it live")
    question.add_argument("session"); question.add_argument("--source", required=True, type=Path)
    review = sub.add_parser("review", help="Record the tutor verdict on the latest response; shown in place of 'Checking...'")
    review.add_argument("session"); review.add_argument("question_id")
    review.add_argument("--verdict", required=True, choices=REVIEW_VERDICTS)
    review.add_argument("--feedback", type=Path, help="UTF-8 text file with the feedback shown beside the question")
    review.add_argument("--next-question", type=Path, help="JSON question posted in the same save")
    review.add_argument("--transcript", type=Path, help="Markdown appended to the session transcript in the same save")
    wait = sub.add_parser("wait", help="Block until an explicit learner submission awaits the agent (bounded)")
    wait.add_argument("session"); wait.add_argument("--timeout", type=float, default=900.0)
    resume = sub.add_parser("context", help="Resume brief: pending learner activity plus research and knowledge graph state")
    resume.add_argument("session"); resume.add_argument("--project-root", type=Path); resume.add_argument("--learning-root", type=Path)
    resume.add_argument("--library-root", type=Path)
    resume.add_argument("--as-of"); resume.add_argument("--json", action="store_true")
    resume.add_argument("--bind", action="store_true", help="store this context as the session's binding (adopts a historical session)")
    recovery = sub.add_parser("recover"); recovery.add_argument("session"); recovery.add_argument("--apply", action="store_true")
    bridge = sub.add_parser("import"); bridge.add_argument("session"); bridge.add_argument("--apply", action="store_true")
    export = sub.add_parser("export"); export.add_argument("session"); export.add_argument("destination", type=Path)
    refresh = sub.add_parser("refresh-projection", help="Regenerate only HTML; preserve source and canonical state")
    refresh.add_argument("session"); refresh.add_argument("--backup-directory", required=True, type=Path)
    refresh.add_argument("--apply", action="store_true")
    migration = sub.add_parser("migrate")
    mode = migration.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true"); mode.add_argument("--resume", action="store_true"); mode.add_argument("--rollback", action="store_true")
    migration.add_argument("--journal")
    args = parser.parse_args()
    root = args.root or Path(load_config()["vault"]["path"]).expanduser()
    if args.command == "inventory":
        result = inventory(root)
    elif args.command == "validate":
        result = validate_sessions(root)
    elif args.command == "export":
        result = str(export_session(root, args.session, args.destination))
    elif args.command == "refresh-projection":
        result = refresh_projection(root, args.session, args.backup_directory, args.apply)
    elif args.command == "create":
        install_runtime(root)
        text = args.source.read_bytes().decode("utf-8")
        if args.waive_context:
            context = waive_context(args.waive_context)
        else:
            import context_kernel as ck
            front = parse_frontmatter(text.replace("\r\n", "\n"))[0]
            request = context_request(root, front, args.session_type or front.get("type"), args.session, workflow=args.workflow,
                                      project=args.project, target=ck.parse_target(args.target), project_root=args.project_root,
                                      learning_root=args.learning_root, library_root=args.library_root,
                                      expect_empty=True if args.expect_empty else None)
            receipt, receipt_file, _ = ck.preflight(request)
            if receipt["outcome"] == "blocked":
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")
                print(json.dumps({"created": False, "reason": "essential context is unavailable", "blocking": receipt["blocking"],
                                  "limitations": receipt["limitations"], "receipt_file": str(receipt_file) if receipt_file else None},
                                 ensure_ascii=False, indent=2))
                raise SystemExit(2)
            context = bind_context(receipt)
        result = create_session(root, args.session, text, args.session_type, args.title, context=context)
    elif args.command == "update":
        result = update_session(root, args.session, args.source.read_bytes().decode("utf-8"))
    elif args.command == "append":
        result = append_session(root, args.session, args.source.read_bytes().decode("utf-8"))
    elif args.command == "event":
        result = append_event(root, args.session, json.loads(args.source.read_text(encoding="utf-8")))
    elif args.command == "answer":
        result = answer_open_question(root, args.session, args.question_id, args.source.read_text(encoding="utf-8"))
    elif args.command == "add-question":
        result = add_question(root, args.session, json.loads(args.source.read_text(encoding="utf-8")))
    elif args.command == "review":
        result = review_response(root, args.session, args.question_id, args.verdict,
                                 args.feedback.read_text(encoding="utf-8") if args.feedback else "",
                                 json.loads(args.next_question.read_text(encoding="utf-8")) if args.next_question else None,
                                 args.transcript.read_text(encoding="utf-8") if args.transcript else None)
    elif args.command == "wait":
        result = wait_for_activity(root, args.session, args.timeout)
    elif args.command == "context":
        brief = session_context(root, args.session, args.project_root, args.learning_root, args.as_of, args.library_root)
        if args.bind:
            if brief["blocked"] or not brief["exists"]:
                raise SystemExit("Cannot bind: " + ("essential context is blocked" if brief["blocked"] else "the session does not exist yet"))
            bind_session_context(root, args.session, brief["receipt"])
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if not args.json:
            sys.stdout.write(render_context(brief))
        else:
            print(json.dumps(brief, ensure_ascii=False, indent=2))
        raise SystemExit(2 if brief["blocked"] else 0)
    elif args.command == "recover":
        result = recover_session(root, args.session, args.apply)
    elif args.command == "import":
        result = import_bridge(root, args.session, args.apply)
    else:
        result = migrate(root, args.apply, args.journal, args.resume, args.rollback)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if isinstance(result, dict) and "source_markdown" in result:
        # Write commands report what changed, not the whole session body.
        result = {"session": args.session, "updated_at": result.get("updated_at"), "questions": len(result["questions"]), "pending": pending_activity(result)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "validate" and result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
