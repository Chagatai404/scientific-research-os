"""Study handouts as documents: a small Markdown (with LaTeX math) is turned into an Obsidian note, a LaTeX source, or a
self-contained HTML page, and the last two into a PDF with whatever toolchain the computer has. Standard library only,
and nothing from the rest of ``ros``; run it on its own::

    python -m ros.lib.pdf detect                       which PDF toolchains this computer has
    python -m ros.lib.pdf template                     the boxes and macros a handout may use
    python -m ros.lib.pdf build --dir DIR [--source HASH] [--engine auto|latex|chromium]
                                                       DIR holds main.tex (+ roshandout.sty) and/or index.html

The toolchain ladder, each step tried only when the one before is absent or fails: ``xelatex`` (MiKTeX or TeX Live,
with the restored study-handout style), then a headless Chromium-family browser (Chrome, Edge, Chromium, Playwright's)
printing the HTML with KaTeX. With neither, ``build`` reports what is missing and returns; it never raises, because a
handout is always readable as the Markdown note and a PDF is a convenience, not a gate.

The LaTeX body is **generated** from the Markdown, with text escaped, but math is passed through, so every body is linted
for commands that could read or write files, run a program or change the template; it is compiled with shell escape and
the package installer off, in a scratch folder.

Markdown subset: paragraphs, ``#`` headings, ``-``/``1.`` lists, pipe tables, ``**bold**``, ``*italic*``, ``code``,
``$inline$`` and ``$$display$$`` math, ``![caption](figures/x.png)``, ``[text](url)``, citations ``[@key]`` and fenced boxes::

    :::definition Variance            (also: rule, keyidea, mistake, remark, example, exercise, question)
    text ...
    === solution                      (example, exercise: the part kept apart; question: the answer)
    text ...
    :::
"""
from __future__ import annotations

import glob
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ASSETS = Path(__file__).resolve().parent / "pdf_assets"
KATEX = Path(__file__).resolve().parents[1] / "portal" / "vendor" / "katex"
TEMPLATE_VERSION = "2"
FIGURE_TYPES = (".pdf", ".png", ".jpg", ".jpeg", ".svg")
BOXES = {"definition": "Definition", "rule": "Rule", "keyidea": "Key idea", "mistake": "Common slip", "remark": "Note",
         "example": "Example", "exercise": "Exercise", "question": "Recall"}
BOX_ENV = {"definition": "definition", "rule": "rulebox", "keyidea": "keyidea", "mistake": "commonmistake",
           "remark": "remark"}
CALLOUT = {"definition": "definition", "rule": "abstract", "keyidea": "tip", "mistake": "warning", "remark": "note",
           "example": "example", "exercise": "question", "question": "question"}
SPLIT = re.compile(r"^===\s*(?:solution|answer)\s*$", re.I | re.M)


# ---- the Markdown subset -------------------------------------------------------------------------------------------
def parse(text: str) -> list[dict]:
    """Blocks of a Markdown body: ``p``, ``h``, ``ul``/``ol``, ``table``, ``math``, ``img``, ``quote``, ``code`` and
    ``box`` (with ``body`` blocks and, when it has a ``=== solution`` part, ``extra`` blocks)."""
    lines, i, out = text.replace("\r\n", "\n").split("\n"), 0, []
    para: list[str] = []

    def flush():
        if para:
            out.append({"t": "p", "text": " ".join(s.strip() for s in para)})
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = re.match(r":::\s*([a-z]+)\s*(.*)$", s)
        if m and m.group(1) in BOXES:
            flush()
            j = i + 1
            while j < len(lines) and lines[j].strip() != ":::":
                j += 1
            inner = "\n".join(lines[i + 1:j])
            parts = SPLIT.split(inner, maxsplit=1)
            out.append({"t": "box", "kind": m.group(1), "title": m.group(2).strip(), "body": parse(parts[0]),
                        "extra": parse(parts[1]) if len(parts) > 1 else None})
            i = j + 1
            continue
        if s.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append({"t": "code", "lang": s[3:].strip(), "text": "\n".join(lines[i + 1:j])})
            i = j + 1
            continue
        if s.startswith("$$"):
            flush()
            if s.endswith("$$") and len(s) > 4:
                out.append({"t": "math", "tex": s[2:-2].strip()})
                i += 1
                continue
            j = i + 1
            buf = [s[2:]]
            while j < len(lines) and "$$" not in lines[j]:
                buf.append(lines[j])
                j += 1
            if j < len(lines):
                buf.append(lines[j].split("$$")[0])
            out.append({"t": "math", "tex": "\n".join(buf).strip()})
            i = j + 1
            continue
        m = re.match(r"(#{1,4})\s+(.*)$", s)
        if m:
            flush()
            out.append({"t": "h", "n": len(m.group(1)), "text": m.group(2).strip()})
            i += 1
            continue
        m = re.match(r"!\[([^\]]*)\]\(([^)\s]+)\)$", s)
        if m:
            flush()
            out.append({"t": "img", "cap": m.group(1), "src": m.group(2)})
            i += 1
            continue
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            out.append({"t": "table", "rows": rows})
            continue
        if re.match(r"([-*]|\d+\.)\s+", s):
            flush()
            ordered = bool(re.match(r"\d+\.", s))
            items: list[str] = []
            while i < len(lines) and (re.match(r"\s*([-*]|\d+\.)\s+", lines[i]) or (items and lines[i].startswith("  ") and lines[i].strip())):
                m2 = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", lines[i])
                if m2:
                    items.append(m2.group(1).strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append({"t": "ol" if ordered else "ul", "items": items})
            continue
        if s.startswith(">"):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append({"t": "quote", "text": " ".join(buf)})
            continue
        if not s:
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    return out


INLINE = re.compile(
    r"(?P<dollar>\\\$)|(?P<code>`[^`\n]+`)|(?P<dmath>\$\$.+?\$\$)|(?P<math>\$[^$\n]+?\$)|(?P<bold>\*\*.+?\*\*)"
    r"|(?P<em>(?<![\w*])\*[^*\n]+?\*(?![\w*]))|(?P<cite>\[@[A-Za-z0-9_:-]+(?:;\s*@[A-Za-z0-9_:-]+)*\])"
    r"|(?P<wiki>\[\[[^\]\n]+\]\])|(?P<link>\[[^\]\n]+\]\([^)\s]+\))", re.S)


def math_spans(text: str) -> list[str]:
    """Every math expression in a Markdown text, display and inline (for the math checks)."""
    out = []
    for m in INLINE.finditer(text):
        if m.lastgroup == "dmath":
            out.append(m.group()[2:-2])
        elif m.lastgroup == "math":
            out.append(m.group()[1:-1])
    for b in _walk(parse(text)):
        if b["t"] == "math":
            out.append(b["tex"])
    return out


def _walk(blocks):
    for b in blocks:
        yield b
        if b["t"] == "box":
            yield from _walk(b["body"])
            yield from _walk(b["extra"] or [])


def tex_escape(text: str) -> str:
    table = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#", "%": r"\%",
             "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "<": r"\textless{}",
             ">": r"\textgreater{}"}
    return "".join(table.get(ch, ch) for ch in re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text)))


def inline(text: str, fmt: str) -> str:
    out, pos = [], 0
    esc = html.escape if fmt == "html" else tex_escape
    for m in INLINE.finditer(text):
        out.append(esc(text[pos:m.start()]) if fmt == "html" else tex_escape(text[pos:m.start()]))
        g, raw = m.lastgroup, m.group()
        if g == "dollar":
            out.append("$" if fmt == "html" else r"\$")
        elif g == "code":
            out.append(f"<code>{html.escape(raw[1:-1])}</code>" if fmt == "html" else r"\texttt{" + tex_escape(raw[1:-1]) + "}")
        elif g in ("math", "dmath"):
            tex = raw[2:-2] if g == "dmath" else raw[1:-1]
            if fmt == "html":
                out.append(f'<span class="m{" d" if g == "dmath" else ""}" data-tex="{html.escape(tex, quote=True)}">'
                           f"{html.escape(tex)}</span>")
            else:
                out.append(f"\\({tex}\\)" if g == "math" else f"\\[{tex}\\]")
        elif g == "bold":
            out.append(f"<strong>{inline(raw[2:-2], fmt)}</strong>" if fmt == "html" else r"\textbf{" + inline(raw[2:-2], fmt) + "}")
        elif g == "em":
            out.append(f"<em>{inline(raw[1:-1], fmt)}</em>" if fmt == "html" else r"\emph{" + inline(raw[1:-1], fmt) + "}")
        elif g == "cite":
            keys = [k.strip().lstrip("@") for k in raw[1:-1].split(";")]
            out.append("".join(f'<sup class="cite"><a href="#src-{html.escape(k)}">[{html.escape(k)}]</a></sup>' for k in keys)
                       if fmt == "html" else r"\cite{" + ",".join(keys) + "}")
        elif g == "wiki":
            label = raw[2:-2].split("|")[-1]
            out.append(html.escape(label) if fmt == "html" else tex_escape(label))
        elif g == "link":
            label, url = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", raw).groups()
            out.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>' if fmt == "html"
                       else r"\href{" + url.replace("%", r"\%").replace("#", r"\#") + "}{" + tex_escape(label) + "}")
        pos = m.end()
    out.append(html.escape(text[pos:]) if fmt == "html" else tex_escape(text[pos:]))
    return "".join(out)


# ---- renderers ----------------------------------------------------------------------------------------------------
class Counter:
    def __init__(self):
        self.n = 0
        self.solutions: list[tuple[int, str, list, str]] = []


def to_html(blocks: list[dict], c: Counter) -> str:
    out = []
    for b in blocks:
        t = b["t"]
        if t == "p":
            out.append(f"<p>{inline(b['text'], 'html')}</p>")
        elif t == "h":
            out.append(f"<h{b['n'] + 2}>{inline(b['text'], 'html')}</h{b['n'] + 2}>")
        elif t in ("ul", "ol"):
            out.append(f"<{t}>" + "".join(f"<li>{inline(i, 'html')}</li>" for i in b["items"]) + f"</{t}>")
        elif t == "table":
            rows = b["rows"]
            head = "<thead><tr>" + "".join(f"<th>{inline(x, 'html')}</th>" for x in rows[0]) + "</tr></thead>" if rows else ""
            body = "".join("<tr>" + "".join(f"<td>{inline(x, 'html')}</td>" for x in r) + "</tr>" for r in rows[1:])
            out.append(f"<table>{head}<tbody>{body}</tbody></table>")
        elif t == "math":
            out.append(f'<div class="m d" data-tex="{html.escape(b["tex"], quote=True)}">{html.escape(b["tex"])}</div>')
        elif t == "img":
            out.append(f'<figure><img src="{html.escape(b["src"], quote=True)}" alt="">'
                       + (f"<figcaption>{inline(b['cap'], 'html')}</figcaption>" if b["cap"] else "") + "</figure>")
        elif t == "quote":
            out.append(f"<blockquote>{inline(b['text'], 'html')}</blockquote>")
        elif t == "code":
            out.append(f"<pre><code>{html.escape(b['text'])}</code></pre>")
        elif t == "box":
            kind, title = b["kind"], b["title"]
            head = BOXES[kind]
            if kind in ("exercise", "question"):
                c.n += 1
                head = f"{head} {c.n}"
                c.solutions.append((c.n, title, b["extra"] or [], kind))
            body = to_html(b["body"], c)
            if kind == "example" and b["extra"]:
                body += '<p class="sol"><strong>Solution.</strong></p>' + to_html(b["extra"], c)
            out.append(f'<div class="box {kind}"><span class="bt">{html.escape(head + (" — " + title if title else ""))}'
                       f"</span>{body}</div>")
    return "\n".join(out)


def to_tex(blocks: list[dict], c: Counter) -> str:
    out = []
    for b in blocks:
        t = b["t"]
        if t == "p":
            out.append(inline(b["text"], "tex") + "\n")
        elif t == "h":
            out.append("\\" + ("subsection", "subsection", "subsubsection", "subsubsection")[b["n"] - 1] + "*{" + inline(b["text"], "tex") + "}")
        elif t in ("ul", "ol"):
            env = "itemize" if t == "ul" else "enumerate"
            out.append(f"\\begin{{{env}}}\n" + "\n".join("\\item " + inline(i, "tex") for i in b["items"]) + f"\n\\end{{{env}}}")
        elif t == "table":
            rows = b["rows"]
            if rows:
                n = max(len(r) for r in rows)
                lines = [" & ".join(inline(x, "tex") for x in r + [""] * (n - len(r))) + r" \\" for r in rows]
                out.append("\\begin{longtable}{" + "l" * n + "}\n\\toprule\n" + lines[0] + "\n\\midrule\n" + "\n".join(lines[1:])
                           + "\n\\bottomrule\n\\end{longtable}")
        elif t == "math":
            out.append("\\[\n" + b["tex"] + "\n\\]")
        elif t == "img":
            out.append("\\begin{figure}[h]\\centering\\includegraphics[width=0.8\\linewidth]{" + b["src"] + "}"
                       + ("\\caption{" + inline(b["cap"], "tex") + "}" if b["cap"] else "") + "\\end{figure}")
        elif t == "quote":
            out.append("\\begin{quote}" + inline(b["text"], "tex") + "\\end{quote}")
        elif t == "code":
            out.append("\\begin{quote}\\texttt{" + tex_escape(b["text"]).replace("\n", "\\\\\n") + "}\\end{quote}")
        elif t == "box":
            kind, title = b["kind"], b["title"]
            opt = "[" + inline(title, "tex") + "]" if title else ""
            body = to_tex(b["body"], c)
            if kind in ("exercise", "question"):
                label = "[Recall]" if kind == "question" else opt
                out.append("\\exercise" + label + "{" + body + "}{" + to_tex(b["extra"] or parse("(no solution given)"), c) + "}")
            elif kind == "example":
                sol = "\\solution " + to_tex(b["extra"], c) if b["extra"] else ""
                out.append("\\begin{workedexample}" + opt + "\n" + body + "\n" + sol + "\n\\end{workedexample}")
            else:
                out.append(f"\\begin{{{BOX_ENV[kind]}}}{opt}\n{body}\n\\end{{{BOX_ENV[kind]}}}")
    return "\n\n".join(out)


def to_obsidian(blocks: list[dict]) -> str:
    """The Markdown for an Obsidian note: boxes become callouts, solutions and answers are collapsed."""
    out = []

    def quote(text: str) -> str:
        return "\n".join("> " + ln if ln.strip() else ">" for ln in text.split("\n"))

    for b in blocks:
        t = b["t"]
        if t == "p":
            out.append(b["text"])
        elif t == "h":
            out.append("#" * (b["n"] + 2) + " " + b["text"])
        elif t in ("ul", "ol"):
            out.append("\n".join((f"{n}. " if t == "ol" else "- ") + i for n, i in enumerate(b["items"], 1)))
        elif t == "table":
            rows = b["rows"]
            if rows:
                out.append("\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
                                     + ["| " + " | ".join(r) + " |" for r in rows[1:]]))
        elif t == "math":
            out.append("$$\n" + b["tex"] + "\n$$")
        elif t == "img":
            out.append(f"![{b['cap']}]({b['src']})")
        elif t == "quote":
            out.append("> " + b["text"])
        elif t == "code":
            out.append("```" + b["lang"] + "\n" + b["text"] + "\n```")
        elif t == "box":
            kind, title = b["kind"], b["title"]
            body = to_obsidian(b["body"])
            head = f"> [!{CALLOUT[kind]}] {BOXES[kind]}" + (f" — {title}" if title else "")
            text = head + "\n" + quote(body)
            if b["extra"]:
                label = "Answer" if kind == "question" else "Solution"
                text += f"\n>\n> > [!success]- {label}\n" + "\n".join("> " + ln if ln.strip() else ">" for ln in quote(to_obsidian(b["extra"])).split("\n"))
            out.append(text)
    return "\n\n".join(out)


# ---- documents ----------------------------------------------------------------------------------------------------
def html_document(meta: dict, sections: list[dict], sources: list[dict]) -> str:
    """A self-contained page: the print CSS, KaTeX from the portal's vendored copy, math rendered on load."""
    c = Counter()
    body = []
    for s in sections:
        if not (s.get("text") or "").strip():
            continue
        body.append(f"<section><h2>{inline(s['title'], 'html')}</h2>\n{to_html(parse(s.get('text') or ''), c)}</section>")
    if c.solutions:
        sol = []
        for n, title, extra, kind in c.solutions:
            sol.append(f"<h4>{BOXES[kind]} {n}{' — ' + html.escape(title) if title else ''}</h4>"
                       + (to_html(extra, Counter()) if extra else "<p>(no solution given)</p>"))
        body.append('<section class="solutions"><h2>Solutions</h2>' + "\n".join(sol) + "</section>")
    if sources:
        body.append('<section class="src"><h2>Sources</h2><ol>' + "".join(
            f'<li id="src-{html.escape(s["key"])}">[{html.escape(s["key"])}] {inline(s["text"], "html")}</li>' for s in sources)
            + "</ol></section>")
    css = (ASSETS / "handout.css").read_text(encoding="utf-8")
    katex_css = (KATEX / "katex.min.css").as_uri()
    katex_js = (KATEX / "katex.min.js").as_uri()
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>" + html.escape(meta.get("title", ""))
            + f'</title><link rel="stylesheet" href="{katex_css}"><style>{css}</style></head><body>'
            + '<header class="title"><div class="meta"><span>' + html.escape(meta.get("course", "")) + "</span><span>"
            + html.escape(meta.get("date", "")) + "</span></div><h1>" + html.escape(meta.get("title", "")) + "</h1>"
            + (f'<div class="sub">{html.escape(meta["subtitle"])}</div>' if meta.get("subtitle") else "")
            + "<div class=\"meta\"><span>" + html.escape(meta.get("line", "")) + "</span></div></header>"
            + "\n".join(body) + f'<script src="{katex_js}"></script><script>'
            + "for(const e of document.querySelectorAll('.m')){try{katex.render(e.dataset.tex,e,"
              "{displayMode:e.classList.contains('d'),throwOnError:false})}catch(_){}}</script></body></html>\n")


def tex_body(sections: list[dict], sources: list[dict]) -> str:
    c = Counter()
    parts = [f"\\section*{{{inline(s['title'], 'tex')}}}\n\n{to_tex(parse(s.get('text') or ''), c)}" for s in sections if (s.get("text") or "").strip()]
    if any(b["t"] == "box" and b["kind"] in ("exercise", "question")
           for s in sections for b in _walk(parse(s.get("text") or ""))):
        parts.append("\\section*{Solutions}\n\\printsolutions")
    if sources:
        parts.append("\\begin{sources}\n" + "\n".join(f"\\bibitem{{{s['key']}}} {inline(s['text'], 'tex')}" for s in sources)
                     + "\n\\end{sources}")
    return "\n\n".join(parts)


def tex_document(meta: dict, sections: list[dict], sources: list[dict]) -> str:
    template = (ASSETS / "template.tex").read_text(encoding="utf-8")
    for key in ("title", "subtitle", "course", "date", "line"):
        template = template.replace(f"@@{key.upper()}@@", tex_escape(meta.get(key, "")).strip())
    return template.replace("%%BODY%%", tex_body(sections, sources).strip() + "\n")


def source_hash(meta: dict, sections: list[dict], sources: list[dict], engine: str = "") -> str:
    data = json.dumps([meta.get("title"), [[s["id"], s.get("title"), s.get("text")] for s in sections],
                       [[s["key"], s["text"]] for s in sources], TEMPLATE_VERSION, engine], sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


# ---- lint of LaTeX that came from a Markdown that may carry hostile math --------------------------------------------
FORBIDDEN = (
    "documentclass", "usepackage", "RequirePackage", "LoadClass", "input", "include", "includeonly", "InputIfFileExists",
    "IfFileExists", "import", "subimport", "write", "immediate", "newwrite", "openout", "openin", "newread", "read",
    "readline", "closein", "closeout", "catcode", "csname", "scantokens", "directlua", "luaexec", "special",
    "makeatletter", "makeatother", "includepdf", "includesvg", "lstinputlisting", "verbatiminput", "VerbatimInput",
    "tcbinputlisting", "tcbincludegraphics", "pgfimage", "pgfdeclareimage", "usetikzlibrary", "usepgfplotslibrary",
    "tikzexternalize", "ShellEscape", "pdfshellescape", "write18", "hypersetup", "pagestyle", "thispagestyle",
    "geometry", "newgeometry", "setmainfont", "setsansfont", "setmonofont", "setmathfont", "fontspec", "newfontfamily",
    "AtBeginDocument", "AtEndDocument", "lccode", "uccode", "uppercase", "lowercase", "def", "gdef", "edef", "xdef",
    "let", "futurelet", "expandafter", "newcommand", "renewcommand", "providecommand", "DeclareRobustCommand",
    "newenvironment", "renewenvironment", "title", "author")
BAD_TEXT = ((re.compile(r"\^\^"), "'^^' character escapes can hide a forbidden command"),
            (re.compile(r"\\[A-Za-z]*@[A-Za-z@]*"), "a command with '@' in its name reaches into the template"),
            (re.compile(r"(?<![A-Za-z])[A-Za-z]:/"), "an absolute drive path"),
            (re.compile(r"\.\.[\\/]"), "a path with '..'"),
            (re.compile(r"\{\s*(?:file|run):", re.I), "a file: or run: address"))


def forbidden_problems(tex: str) -> list[str]:
    """Every use of a command a handout may not use (math is passed through, so it must be checked)."""
    names = "|".join(sorted(map(re.escape, FORBIDDEN), key=len, reverse=True))
    command = re.compile(r"\\(" + names + r")(?![A-Za-z@])")
    out = []
    for number, line in enumerate(tex.splitlines(), 1):
        for m in command.finditer(line):
            out.append(f"line {number}: \\{m.group(1)} is not allowed (the template owns the document, files and fonts)")
        for pattern, why in BAD_TEXT:
            if pattern.search(line):
                out.append(f"line {number}: {why}")
    return out


def lint_math(spans: list[str]) -> list[str]:
    """Problems in math expressions: forbidden commands, unbalanced braces."""
    out = []
    for tex in spans:
        out += [f"in ${tex[:40]}$: {p.split(': ', 1)[-1]}" for p in forbidden_problems(tex)]
        depth = 0
        for ch in re.sub(r"\\[{}]", "", tex):
            depth += {"{": 1, "}": -1}.get(ch, 0)
            if depth < 0:
                break
        if depth:
            out.append(f"unbalanced braces in ${tex[:40]}$")
    return out


# ---- toolchains ---------------------------------------------------------------------------------------------------
def _tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = [os.environ.get("ROS_MIKTEX_BIN", "")]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(str(Path(local) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"))
    candidates += [r"C:\Program Files\MiKTeX\miktex\bin\x64", "/Library/TeX/texbin", "/usr/local/texlive/bin"]
    for folder in candidates:
        if folder:
            for suffix in ("", ".exe"):
                p = Path(folder) / (name + suffix)
                if p.is_file():
                    return str(p)
    return None


def browser() -> str | None:
    """A Chromium-family browser: ``ROS_BROWSER``, one on the path, the usual install places, or Playwright's."""
    env = os.environ.get("ROS_BROWSER")
    if env and Path(env).is_file():
        return env
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge",
                 "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    places = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for p in places:
        if Path(p).is_file():
            return p
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / ".cache" / "ms-playwright")
    for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe",
                    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
        hits = sorted(glob.glob(str(Path(root) / pattern)))
        if hits:
            return hits[-1]
    return None


def detect() -> dict:
    """What this computer can build a PDF with, in the order they are tried."""
    latex, chrome = _tool("xelatex"), browser()
    return {"latex": latex, "chromium": chrome, "pandoc": shutil.which("pandoc"),
            "engines": [n for n, p in (("latex", latex), ("chromium", chrome)) if p],
            "note": None if (latex or chrome) else "PDF needs a toolchain: MiKTeX or TeX Live (xelatex), or Edge, "
                                                  "Chrome or Chromium. The Markdown note works without one."}


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=20)
        else:
            process.kill()
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.wait(timeout=10)
    except subprocess.SubprocessError:
        pass


def _run(command: list, cwd: Path, timeout: float, env: dict | None = None) -> tuple[int | None, str]:
    process = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    try:
        out, _ = process.communicate(timeout=timeout)
        return process.returncode, out.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            out, _ = process.communicate(timeout=5)
        except (subprocess.SubprocessError, ValueError):
            out = b""
        return None, out.decode("utf-8", errors="replace")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def analyze_log(log: str, max_overfull: float = 10.0) -> dict:
    """The problems a LaTeX log shows, and how many pages the document has."""
    problems: list[str] = []

    def add(text: str) -> None:
        if text not in problems:
            problems.append(text)

    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!"):
            context = next((x for x in lines[i + 1:i + 8] if x.startswith("l.")), "")
            add(f"compile error: {line[1:].strip()}" + (f" ({context.strip()})" if context else ""))
        m = re.search(r"(Reference|Citation) `([^']*)' on page \d+ undefined", line)
        if m:
            add(f"undefined {m.group(1).lower()} '{m.group(2)}'")
        if "Label(s) may have changed" in line:
            add("labels were still changing on the last run (cross-references are out of date)")
        m = re.search(r"File `([^']*)' not found", line)
        if m:
            add(f"missing file '{m.group(1)}' (figure or package)")
        m = re.search(r"(Overfull \\[hv]box) \((\d+(?:\.\d+)?)pt too (?:wide|high)\)", line)
        if m and float(m.group(2)) > max_overfull:
            add(f"{m.group(1)} {m.group(2)}pt (limit {max_overfull:g}pt)")
        if "Missing character: There is no" in line:
            add("missing glyph: " + line.strip()[:120])
        if "runsystem(" in line:
            add("the document tried to run a program: " + line.strip()[:120])
        if re.search(r"Font .* not found|Cannot find font", line, re.I):
            add("font problem: " + line.strip()[:120])
    pages = 0
    for m in re.finditer(r"Output written on [^\n]*?\((\d+) pages?", log):
        pages = int(m.group(1))
    if not pages and not problems:
        problems.append("no output was produced (the compile did not finish)")
    return {"problems": problems, "pages": pages}


def compile_latex(folder: Path, main: str = "main.tex", timeout: float = 300, allow_install: bool = False) -> dict:
    """Compile ``main`` with xelatex: shell escape off, the package installer off unless allowed, bounded by ``timeout``
    seconds in all, the process tree killed on a timeout, scratch output beside the source."""
    folder = Path(folder)
    xelatex = _tool("xelatex")
    if xelatex is None:
        return {"ok": False, "pdf": None, "log": "", "timed_out": False, "missing": True}
    env = dict(os.environ, openin_any="p", openout_any="p", shell_escape="f", TEXMFOUTPUT=str(folder))
    if "miktex" in xelatex.lower():
        flags = ["-interaction=nonstopmode", "-halt-on-error", "-disable-write18",
                 "-enable-installer" if allow_install else "-disable-installer"]
    else:
        flags = ["-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape"]
    started, timed_out, stem = time.monotonic(), False, Path(main).stem
    for _ in range(4):  # until the cross-references settle
        left = timeout - (time.monotonic() - started)
        if left <= 0:
            timed_out = True
            break
        code, _out = _run([xelatex, *flags, main], folder, left, env)
        if code is None:
            timed_out = True
            break
        log = _read(folder / f"{stem}.log")
        if code != 0 or not re.search(r"Rerun to get|Label\(s\) may have changed", log):
            break
    pdf = folder / f"{stem}.pdf"
    return {"ok": pdf.is_file() and not timed_out, "pdf": pdf if pdf.is_file() else None,
            "log": _read(folder / f"{stem}.log"), "timed_out": timed_out, "missing": False,
            "seconds": round(time.monotonic() - started, 1)}


def print_chromium(page: Path, pdf: Path, timeout: float = 120) -> dict:
    """Print an HTML page to PDF with a headless browser, in a throwaway profile."""
    exe = browser()
    if exe is None:
        return {"ok": False, "missing": True, "timed_out": False}
    with tempfile.TemporaryDirectory(prefix="ros-chrome-") as profile:
        cmd = [exe, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--hide-scrollbars",
               "--virtual-time-budget=12000", f"--user-data-dir={profile}", f"--print-to-pdf={pdf}"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.append("--no-sandbox")
        code, out = _run(cmd + [Path(page).resolve().as_uri()], Path(page).parent, timeout)
    return {"ok": pdf.is_file() and pdf.stat().st_size > 0 and code is not None, "missing": False,
            "timed_out": code is None, "output": out[-1500:]}


def _pages(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf.read_bytes()))


def build(folder: Path, source: str = "", engine: str = "auto", timeout: float = 300, allow_install: bool = False) -> dict:
    """Build ``out/<source>.pdf`` from ``main.tex`` and/or ``index.html`` in ``folder`` with the first engine that works.
    Always returns a report; a missing toolchain or a failed compile is data, not an exception."""
    folder = Path(folder)
    name = source or "handout"
    out = folder / "out"
    out.mkdir(parents=True, exist_ok=True)
    tried, problems = [], []
    order = {"latex": ["latex"], "chromium": ["chromium"], "auto": ["latex", "chromium"]}.get(engine)
    if order is None:
        return {"ok": False, "engine": None, "pdf": None, "pages": 0, "problems": [f"unknown engine {engine!r}"],
                "missing": False, "tried": []}
    started = time.monotonic()
    for eng in order:
        if eng == "latex" and (folder / "main.tex").is_file():
            tex = _read(folder / "main.tex")
            bad = forbidden_problems(tex.split("\\begin{document}", 1)[-1])
            if bad:
                problems += bad
                tried.append({"engine": "latex", "ok": False, "why": "the body uses commands a handout may not use"})
                break  # the same content would go to the browser: refuse it everywhere
            if _tool("xelatex") is None:
                tried.append({"engine": "latex", "ok": False, "why": "xelatex was not found (MiKTeX or TeX Live)"})
                continue
            res = compile_latex(folder, "main.tex", timeout, allow_install)
            log = analyze_log(res["log"]) if res["log"] else {"problems": ["no log"], "pages": 0}
            if res["ok"] and not [p for p in log["problems"] if p.startswith(("compile error", "undefined", "missing"))]:
                pdf = out / f"{name}.pdf"
                shutil.copy2(res["pdf"], pdf)
                return _done(pdf, "latex", log["pages"] or _pages(pdf), tried, started)
            tried.append({"engine": "latex", "ok": False, "why": "; ".join(log["problems"][:5]) or "the compile failed"})
            problems += log["problems"][:8]
        elif eng == "chromium" and (folder / "index.html").is_file():
            if browser() is None:
                tried.append({"engine": "chromium", "ok": False, "why": "no Chrome, Edge or Chromium was found"})
                continue
            pdf = out / f"{name}.pdf"
            res = print_chromium(folder / "index.html", pdf, min(timeout, 180))
            if res["ok"]:
                return _done(pdf, "chromium", _pages(pdf), tried, started)
            tried.append({"engine": "chromium", "ok": False, "why": "the browser did not produce a PDF"
                          + (" (timed out)" if res.get("timed_out") else "")})
    missing = not any(t for t in tried if "why" in t and "not found" not in t["why"] and "no Chrome" not in t["why"]) \
        and not detect()["engines"]
    if missing:
        problems.insert(0, detect()["note"])
    return {"ok": False, "engine": None, "pdf": None, "pages": 0, "problems": problems or [t["why"] for t in tried],
            "missing": missing, "tried": tried, "seconds": round(time.monotonic() - started, 1)}


def _done(pdf: Path, engine: str, pages: int, tried: list, started: float) -> dict:
    return {"ok": True, "engine": engine, "pdf": str(pdf), "pages": pages, "bytes": pdf.stat().st_size,
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "problems": [], "missing": False, "tried": tried,
            "seconds": round(time.monotonic() - started, 1)}


# ---- the template's vocabulary (printed by ``template``; a test keeps it in step with the style) --------------------
ENVIRONMENTS = {
    "definition": "A named definition in a blue box (:::definition Name).",
    "rulebox": "A rule or result to remember, in a green box (:::rule Name).",
    "keyidea": "The one idea to take away, in an amber box (:::keyidea).",
    "commonmistake": "A slip learners make and why it is wrong, in a red box (:::mistake).",
    "remark": "A side note in a grey box (:::remark).",
    "workedexample": "A numbered worked example; the part after '=== solution' is the solution (:::example).",
    "sources": "The Sources section, generated from the handout's sources; cite with [@key].",
}
MACROS = ("\\exercise[label]{statement}{solution}", "\\printsolutions", "\\solution", "\\margin{text}",
          "\\Var \\Cov \\SD \\E \\Pr", "\\R \\N \\dd \\ind \\iid \\given \\eqdef")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("detect", "template", "build"):
        sys.stderr.write(__doc__ or "")
        return 2
    if argv[0] == "detect":
        print(json.dumps(detect(), indent=2))
        return 0
    if argv[0] == "template":
        print(json.dumps({"boxes": BOXES, "environments": ENVIRONMENTS, "macros": MACROS}, indent=2))
        return 0
    opts = {a: argv[i + 1] for i, a in enumerate(argv) if a.startswith("--") and i + 1 < len(argv)}
    if "--dir" not in opts:
        sys.stderr.write("build needs --dir\n")
        return 2
    result = build(Path(opts["--dir"]), opts.get("--source", ""), opts.get("--engine", "auto"),
                   float(opts.get("--timeout", 300)))
    (Path(opts["--dir"]) / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
