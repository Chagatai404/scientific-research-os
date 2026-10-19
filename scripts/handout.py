"""The study handout: an agent-written LaTeX body becomes a detailed PDF that is saved in the course or project library, with a vault note.

Standard library only (and ``html_sessions`` / ``session_plan`` for the session and its plan). The body is **untrusted**: an agent wrote it, so it is linted
for anything that could read or write files, run a program or change the template, and compiled with shell escape and the package installer off in a scratch
folder outside the vault. A document that does not compile, has undefined references or citations, an overfull box beyond the threshold, a missing figure or
a missing glyph is not handed out; the problems are listed instead.

    handout.py check body.tex [--root VAULT --session NOTE | --plan plan.json]   lint without compiling
    handout.py template [--json]                                               the environments and macros a body may use
    handout.py build --root VAULT --session NOTE --body body.tex [--title T] [--library DIR] [--stage draft|built] [--figures DIR]
    handout.py locate --root VAULT --session NOTE                              where the latest handout of a session is

``references/HANDOUT_PROTOCOL.md`` says when to build, how the learner uses it and how its mathematics is checked.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "handout"
STYLE = "roshandout.sty"
SCHEMA = 1
MANIFEST = "handout.json"
MAX_BODY_BYTES = 400 * 1024
MAX_FIGURE_BYTES = 10 * 1024 * 1024
FIGURE_TYPES = (".pdf", ".png", ".jpg", ".jpeg")
MIN_WORDS = 300
DEFAULT_OVERFULL_PT = 10.0
DEFAULT_TIMEOUT = 300
STAGES = ("planned", "draft", "built")
COURSE_DIR = "Tutor Handouts"
PROJECT_DIR = "Library"

# What a body may use. ``handout.py template`` prints this; a test keeps it in step with the style file.
ENVIRONMENTS = {
    "definition": ("\\begin{definition}[Name] ... \\end{definition}", "A named definition in a blue box, numbered within the section."),
    "rulebox": ("\\begin{rulebox}[Name] ... \\end{rulebox}", "A rule or theorem to remember, in a green box (shares the definition counter)."),
    "keyidea": ("\\begin{keyidea}[Short title] ... \\end{keyidea}", "The one idea to take away, in an amber box."),
    "commonmistake": ("\\begin{commonmistake}[Short title] ... \\end{commonmistake}", "A slip learners make and why it is wrong, in a red box."),
    "remark": ("\\begin{remark}[Short title] ... \\end{remark}", "A side note, in a grey box."),
    "gaps": ("\\begin{gaps} ... \\end{gaps}", "A short section on the gaps the probe found; added when the handout is finished after the probe."),
    "workedexample": ("\\begin{workedexample}[Title] statement \\solution steps \\end{workedexample}", "A numbered worked example; \\solution starts the solution."),
    "parts": ("\\begin{parts} \\item ... \\item ... \\end{parts}", "Lettered sub-questions (a), (b), ... for an exercise or example."),
    "notationtable": ("\\begin{notationtable} $X$ & random variable \\\\ ... \\end{notationtable}", "A two-column symbol and meaning table that may run over a page."),
    "sources": ("\\begin{sources} \\bibitem{key} Author. Title. Year. \\end{sources}", "The Sources section; cite with \\cite{key}. Every handout has one."),
    "proposition": ("\\begin{proposition} ... \\end{proposition}", "Unboxed numbered statement, to be followed by a proof."),
    "proof": ("\\begin{proof} ... \\end{proof}", "A proof ending with a black square."),
    "figure": ("\\begin{figure}[h] \\centering \\includegraphics[width=0.8\\linewidth]{figures/name.pdf} \\caption{...} \\end{figure}", "A figure from the figures folder (pdf, png, jpg) or a tikz or pgfplots picture."),
}
MACROS = {
    "\\exercise[label]{statement}{full solution}": "An exercise printed here; its solution is collected and printed by \\printsolutions. Every exercise has a full solution.",
    "\\printsolutions": "Prints all collected solutions (put it in a section after the exercises).",
    "\\solution": "Inside workedexample: the bold Solution. run-in head.",
    "\\margin{text}": "A short note in the wide right margin.",
    "\\sourcenote{text}": "A small grey 'Source: ...' line, for example at the end of a box.",
    "\\Var \\Cov \\SD \\E \\Pr": "Operators: \\Var(X), \\Cov(X,Y), \\SD(X), \\E[X], \\Pr(A).",
    "\\R \\N \\dd \\ind \\iid \\given \\eqdef": "\\R, \\N number sets; \\dd the differential (\\int f(x)\\dd x); \\ind an indicator; \\iid; \\given for conditioning; \\eqdef for :=.",
    "\\section \\subsection \\subsubsection": "Numbered headings (green and blue).",
    "\\textbf \\emph \\cite{key} \\label \\ref \\eqref \\url": "As in ordinary LaTeX; amsmath, amssymb, mathtools, booktabs, enumitem, tikz and pgfplots are loaded.",
}
PACKAGES = ("amsmath", "amssymb", "amsthm", "mathtools", "fontspec", "unicode-math", "geometry", "xcolor", "microtype", "hyperref", "fancyhdr", "titlesec",
            "booktabs", "enumitem", "tcolorbox (skins, breakable)", "longtable", "array", "graphicx", "caption", "tikz", "pgfplots", "etoolbox",
            "Latin Modern fonts (lm, lm-math)")

# Commands a body may never use. Each could read or write a file, run a program, load code or reach internals of the template.
FORBIDDEN = (
    "documentclass", "usepackage", "RequirePackage", "LoadClass", "input", "include", "includeonly", "InputIfFileExists", "IfFileExists", "import", "subimport",
    "write", "immediate", "newwrite", "openout", "openin", "newread", "read", "readline", "closein", "closeout", "catcode", "csname", "scantokens",
    "directlua", "luaexec", "special", "makeatletter", "makeatother", "includepdf", "includesvg", "lstinputlisting", "verbatiminput", "VerbatimInput",
    "tcbinputlisting", "tcbincludegraphics", "pgfimage", "pgfdeclareimage", "usetikzlibrary", "usepgfplotslibrary", "tikzexternalize", "ShellEscape",
    "pdfshellescape", "write18", "href", "hypersetup", "pagestyle", "thispagestyle", "geometry", "newgeometry", "setmainfont", "setsansfont", "setmonofont",
    "setmathfont", "fontspec", "newfontfamily", "AtBeginDocument", "AtEndDocument", "lccode", "uccode", "uppercase", "lowercase",
)
FORBIDDEN_ENVIRONMENTS = ("document",)
BAD_TEXT = (
    (re.compile(r"\^\^"), "'^^' character escapes can hide a forbidden command"),
    (re.compile(r"\\[A-Za-z]*@[A-Za-z@]*"), "a command with '@' in its name reaches into the template's internals"),
    (re.compile(r"(?<![A-Za-z])[A-Za-z]:/"), "an absolute drive path"),               # a Windows path in TeX is written with forward slashes; f:\R is mathematics
    (re.compile(r"\.\.[\\/]"), "a path with '..'"),
    (re.compile(r"\{\s*(?:file|run):", re.I), "a file: or run: address"),
)
SLOT = re.compile(r"\[[^\]\n]*\b[A-Za-z]{2,}\s+[A-Za-z]{2,}\b[^\]\n]*\]")        # an unfilled [Name the concept]; E[X^2] and [a, b) are mathematics
UNFINISHED = re.compile(r"\\todo\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bTBD\b|lorem ipsum|\\lipsum|\\blindtext", re.I)
MATH_ENVIRONMENTS = ("equation", "equation*", "align", "align*", "gather", "gather*", "multline", "multline*", "flalign", "flalign*", "eqnarray", "eqnarray*",
                     "displaymath", "math", "split", "aligned", "alignedat", "gathered", "cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "array", "verbatim", "lstlisting")


class HandoutError(Exception):
    """A problem the caller can act on; ``problems`` lists each of them."""

    def __init__(self, message: str, problems: list | None = None):
        super().__init__(message)
        self.problems = problems or []


# ---------------------------------------------------------------------------------------------------- text helpers

def strip_comments(text: str) -> str:
    """Remove TeX comments (an unescaped % to the end of the line), keeping line numbers."""
    out = []
    for line in text.splitlines():
        end = len(line)
        backslashes = 0
        for i, ch in enumerate(line):
            if ch == "\\":
                backslashes += 1
                continue
            if ch == "%" and backslashes % 2 == 0:
                end = i
                break
            backslashes = 0
        out.append(line[:end])
    return "\n".join(out)


def tex_escape(text: str) -> str:
    """Plain text made safe for use inside a TeX argument (metadata, never the body)."""
    table = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(table.get(ch, ch) for ch in re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text))).strip()


def _strip_math(text: str) -> str:
    """The prose of a body: math, math environments and bracketed option lists are removed."""
    for name in MATH_ENVIRONMENTS:
        text = re.sub(r"\\begin\{" + re.escape(name) + r"\}.*?\\end\{" + re.escape(name) + r"\}", " ", text, flags=re.S)
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.S)
    text = re.sub(r"(?<!\\)\$.*?(?<!\\)\$", " ", text, flags=re.S)
    # An option list after a command or environment, such as \begin{definition}[Variance] or \item[(a)] or \exercise[hard], is a title, not a slot.
    return re.sub(r"(\\[A-Za-z]+\*?(?:\{[A-Za-z*]*\})?)\[[^\]\n]*\]", r"\1", text)


def words(body: str) -> int:
    prose = _strip_math(strip_comments(body))
    prose = re.sub(r"\\[A-Za-z]+\*?", " ", prose)
    return len(re.findall(r"[^\W\d_]{2,}", prose))


def headings(body: str) -> list[str]:
    text = strip_comments(body)
    found = [re.sub(r"\s+", " ", m.group(2)).strip() for m in re.finditer(r"\\(section|subsection)\*?\{((?:[^{}]|\{[^{}]*\})*)\}", text)]
    if re.search(r"\\begin\{sources\}", text):
        found.append("Sources")
    return found


def _norm(heading: str) -> str:
    heading = re.sub(r"\\[A-Za-z]+\*?|[{}$\\]", " ", heading)
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", heading.lower())).strip()


# ---------------------------------------------------------------------------------------------------- lint

def forbidden_problems(body: str) -> list[str]:
    """Every use of a command the body may not use, with its line. Used by ``check`` and, again, by ``build``."""
    text = strip_comments(body)
    problems = []
    names = "|".join(sorted(map(re.escape, FORBIDDEN), key=len, reverse=True))
    command = re.compile(r"\\(" + names + r")(?![A-Za-z@])")
    for number, line in enumerate(text.splitlines(), 1):
        for m in command.finditer(line):
            problems.append(f"line {number}: \\{m.group(1)} is not allowed in a handout body (the template owns the document, files and fonts)")
        for pattern, why in BAD_TEXT:
            if pattern.search(line):
                problems.append(f"line {number}: {why}")
    for name in FORBIDDEN_ENVIRONMENTS:
        for m in re.finditer(r"\\(?:begin|end)\{" + name + r"\}", text):
            problems.append(f"line {text.count(chr(10), 0, m.start()) + 1}: the {name} environment belongs to the template")
    return problems


def figure_paths(body: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", strip_comments(body))]


def figure_problems(body: str, figures: Path | None) -> list[str]:
    problems = []
    for name in figure_paths(body):
        if not name or name.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", name) or ".." in name.replace("\\", "/").split("/") or "://" in name:
            problems.append(f"figure '{name}': a figure is a relative file name inside the figures folder")
            continue
        if figures is None:
            problems.append(f"figure '{name}': no figures folder was given and none sits next to the body")
            continue
        relative = name.replace("\\", "/").removeprefix("figures/")
        candidates = [relative] if Path(relative).suffix.lower() in FIGURE_TYPES else [relative + ext for ext in FIGURE_TYPES]
        found = [figures / c for c in candidates if (figures / c).is_file()]
        if not found:
            problems.append(f"figure '{name}': file not found in {figures.name}/ (pdf, png, jpg)")
        elif found[0].stat().st_size > MAX_FIGURE_BYTES:
            problems.append(f"figure '{name}': larger than {MAX_FIGURE_BYTES // (1024 * 1024)} MB")
    return problems


def lint(body: str, plan_sections: list[str] | None = None, figures: Path | None = None, check_figures: bool = False) -> dict:
    """Problems that refuse a body (``errors``), advice (``warnings``) and a few counts. Nothing is compiled."""
    errors, warnings = [], []
    if not isinstance(body, str) or not body.strip():
        return {"errors": ["the body is empty"], "warnings": [], "stats": {}}
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        errors.append(f"the body is larger than {MAX_BODY_BYTES // 1024} KB")
    errors += forbidden_problems(body)
    text = strip_comments(body)
    prose = _strip_math(text)
    for number, line in enumerate(prose.splitlines(), 1):
        for m in SLOT.finditer(line):
            errors.append(f"line {number}: unfilled slot {m.group(0)!r}: write the content or remove it")
        marker = UNFINISHED.search(line)
        if marker:
            errors.append(f"line {number}: unfinished marker ({marker.group(0).strip()}): finish the passage")
    found = headings(body)
    if not re.search(r"\\section\*?\{", text):
        errors.append("the body has no \\section: a handout is a numbered, sectioned document")
    normalized = [_norm(h) for h in found]
    for section in (s for s in (plan_sections or []) if isinstance(s, str)):
        want = _norm(section)
        if want and not any(want == h or want in h or h in want for h in normalized if h):
            errors.append(f"missing section from the plan: {section!r}")
    exercises = len(re.findall(r"\\exercise\b", text))
    if exercises and "\\printsolutions" not in text:
        errors.append("exercises are given but \\printsolutions never prints their solutions: every exercise needs its full solution at the end")
    for m in re.finditer(r"\\exercise\s*(?:\[[^\]]*\])?\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})\s*\{\s*\}", text):
        errors.append(f"line {text.count(chr(10), 0, m.start()) + 1}: an exercise has an empty solution")
    bibitems = re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", text)
    if "\\begin{sources}" not in text or not bibitems:
        errors.append("the body has no sources: end with \\begin{sources} \\bibitem{key} ... \\end{sources} (SOURCE_POLICY.md)")
    for key in sorted({k.strip() for m in re.finditer(r"\\cite[a-z]*\s*(?:\[[^\]]*\])?\{([^}]+)\}", text) for k in m.group(1).split(",")}):
        if key not in bibitems:
            errors.append(f"\\cite{{{key}}} has no \\bibitem in the sources")
    labels = set(re.findall(r"\\label\{([^}]+)\}", text))
    for key in sorted(set(re.findall(r"\\(?:ref|eqref|pageref|autoref)\{([^}]+)\}", text)) - labels):
        errors.append(f"\\ref{{{key}}} points at a label that is never defined")
    if check_figures:
        errors += figure_problems(body, figures)
    count = words(body)
    stats = {"words": count, "sections": len([h for h in found if h != "Sources"]), "definitions": len(re.findall(r"\\begin\{(?:definition|rulebox)\}", text)),
             "examples": len(re.findall(r"\\begin\{workedexample\}", text)), "exercises": exercises, "sources": len(bibitems)}
    if count < MIN_WORDS:
        errors.append(f"only about {count} words of prose: a handout must be studied from alone (at least {MIN_WORDS})")
    if not stats["examples"]:
        warnings.append("no worked example: a handout teaches with at least one")
    if not stats["definitions"]:
        warnings.append("no definition or rule box")
    if 0 < exercises < 3:
        warnings.append("fewer than three exercises")
    if not exercises:
        warnings.append("no exercises: a handout ends with exercises and full solutions")
    return {"errors": errors, "warnings": warnings, "stats": stats}


# ---------------------------------------------------------------------------------------------------- compile and log

def _tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = [os.environ.get("ROS_MIKTEX_BIN", "")]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(str(Path(local) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"))
    candidates += [r"C:\Program Files\MiKTeX\miktex\bin\x64", "/usr/bin", "/usr/local/bin", "/Library/TeX/texbin"]
    for folder in candidates:
        if folder:
            for suffix in ("", ".exe"):
                path = Path(folder) / (name + suffix)
                if path.is_file():
                    return str(path)
    return None


def have_latex() -> bool:
    return _tool("xelatex") is not None


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


def _run(command: list, cwd: Path, timeout: float, env: dict) -> tuple[int | None, str]:
    process = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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


def compile_document(folder: Path, main: str = "main.tex", timeout: float = DEFAULT_TIMEOUT, allow_install: bool = False) -> dict:
    """Compile ``main`` in ``folder`` with xelatex, shell escape off, the package installer off (unless allowed), bounded by ``timeout`` seconds in all.

    Uses ``latexmk -xelatex`` when latexmk and perl are present, otherwise runs xelatex again until the cross-references settle (at most four runs).
    Returns ``{"ok", "pdf", "log", "tool", "timed_out", "seconds"}``; the log is read from ``main.log``.
    """
    folder = Path(folder)
    xelatex = _tool("xelatex")
    if xelatex is None:
        return {"ok": False, "pdf": None, "log": "", "tool": None, "timed_out": False, "seconds": 0.0, "output": "xelatex was not found (install MiKTeX or TeX Live)"}
    env = dict(os.environ, openin_any="p", openout_any="p", shell_escape="f", TEXMFOUTPUT=str(folder))
    if "miktex" in xelatex.lower():
        flags = ["-interaction=nonstopmode", "-halt-on-error", "-disable-write18", "-enable-installer" if allow_install else "-disable-installer"]
    else:
        flags = ["-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape"]
    started = time.monotonic()
    output, tool, timed_out = "", "xelatex", False
    latexmk, perl = _tool("latexmk"), shutil.which("perl")
    if latexmk and perl:
        tool = "latexmk"
        engine = "xelatex " + " ".join(flags) + " %O %S"
        code, output = _run([latexmk, "-pdfxe", "-silent", "-e", "$xelatex=q{" + engine + "};", main], folder, timeout, env)
        timed_out = code is None
    else:
        for _ in range(4):
            left = timeout - (time.monotonic() - started)
            if left <= 0:
                timed_out = True
                break
            code, chunk = _run([xelatex, *flags, main], folder, left, env)
            output += chunk
            if code is None:
                timed_out = True
                break
            log = _read(folder / (Path(main).stem + ".log"))
            if code != 0 or not re.search(r"Rerun to get|Label\(s\) may have changed|There were undefined (?:references|citations)", log):
                break
    stem = Path(main).stem
    pdf = folder / (stem + ".pdf")
    return {"ok": pdf.is_file() and not timed_out, "pdf": pdf if pdf.is_file() else None, "log": _read(folder / (stem + ".log")), "tool": tool,
            "timed_out": timed_out, "seconds": round(time.monotonic() - started, 1), "output": output[-4000:]}


def analyze_log(log: str, max_overfull: float = DEFAULT_OVERFULL_PT) -> dict:
    """The problems a compile log shows, and how many pages the document has."""
    problems: list[str] = []

    def add(text: str) -> None:
        if text not in problems:
            problems.append(text)

    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!"):
            context = next((l for l in lines[i + 1:i + 8] if l.startswith("l.")), "")
            add(f"compile error: {line[1:].strip()}" + (f" ({context.strip()})" if context else ""))
        m = re.search(r"(Reference|Citation) `([^']*)' on page \d+ undefined", line)
        if m:
            add(f"undefined {m.group(1).lower()} '{m.group(2)}'")
        if "There were undefined references" in line or "There were undefined citations" in line:
            add(line.strip().rstrip("."))
        if "Label(s) may have changed" in line:
            add("labels were still changing on the last run (cross-references are out of date)")
        m = re.search(r"File `([^']*)' not found", line)
        if m:
            add(f"missing file '{m.group(1)}' (figure or package)")
        m = re.search(r"(Overfull \\[hv]box) \((\d+(?:\.\d+)?)pt too (?:wide|high)\)", line)
        if m and float(m.group(2)) > max_overfull:
            add(f"{m.group(1)} {m.group(2)}pt (limit {max_overfull:g}pt) {line.split(')', 1)[1].strip()[:80]}".strip())
        if "Missing character: There is no" in line:
            add("missing glyph: " + line.strip()[:120])
        if "runsystem(" in line:
            add("the document tried to run a program: " + line.strip()[:120])
        if re.search(r"Font .* not found|Cannot find font|font .* cannot be found", line, re.I):
            add("font problem: " + line.strip()[:120])
    pages = 0
    for m in re.finditer(r"Output written on [^\n]*?\((\d+) pages?", log):
        pages = int(m.group(1))
    if not pages and not problems:
        problems.append("no output was produced (the compile did not finish)")
    return {"problems": problems, "pages": pages}


def assemble(body: str, meta: dict) -> str:
    template = (ASSETS / "template.tex").read_text(encoding="utf-8")
    slots = {"TITLE": meta["title"], "SUBTITLE": meta.get("subtitle", ""), "COURSE": meta.get("course", ""), "DATE": meta.get("date", ""), "LINE": meta.get("line", "")}
    for key, value in slots.items():
        template = template.replace(f"@@{key}@@", tex_escape(value))
    return template.replace("%%BODY%%", body.strip() + "\n")


def build_scratch(body: str, meta: dict, figures: Path | None, scratch: Path) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ASSETS / STYLE, scratch / STYLE)
    (scratch / "main.tex").write_text(assemble(body, meta), encoding="utf-8", newline="\n")
    if figures is not None and figures.is_dir():
        for source in sorted(figures.rglob("*")):
            if source.is_file() and not source.is_symlink() and source.suffix.lower() in FIGURE_TYPES and source.stat().st_size <= MAX_FIGURE_BYTES:
                target = scratch / "figures" / source.relative_to(figures)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


# ---------------------------------------------------------------------------------------------------- library, files, note

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(title: str) -> str:
    text = re.sub(r"[\\$^{}~#%&]", "", title)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", text)
    return (re.sub(r"\s+", " ", text).strip()[:80].rstrip(". ")) or "handout"


def _resolve(root: Path, relative: str, what: str) -> Path:
    """A path below ``root`` that exists or can be made, never through a symlink and never outside it."""
    root = Path(root).resolve()
    relative = relative.replace("\\", "/")
    if not relative or relative.startswith("/") or re.match(r"^[A-Za-z]:", relative) or any(p in ("", "..") or p.startswith(".") for p in relative.split("/")):
        raise HandoutError(f"{what} must be a plain folder path inside the library (relative, no '..', no drive, nothing hidden): {relative!r}")
    lexical = root / relative
    for part in (lexical, *lexical.parents):
        if part == root:
            break
        if part.is_symlink():
            raise HandoutError(f"{what} goes through a symlink: {part}")
    path = lexical.resolve()
    if not path.is_relative_to(root) or path == root:
        raise HandoutError(f"{what} escapes the library: {relative!r}")
    return path


def _front(text: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import parse_frontmatter
    return parse_frontmatter(text.replace("\r\n", "\n"))[0]


def library_of(root: Path, session: str, library: str | None) -> dict:
    """The course or project folder a session's handouts belong to: ``kind`` (course or project), ``path`` (vault-relative), ``name`` and its main note."""
    root = Path(root).resolve()
    if library:
        rel = library.replace("\\", "/").strip("/")
    else:
        parts = session.replace("\\", "/").split("/")
        if len(parts) >= 3 and parts[0] == "01 Projects":
            rel = "/".join(parts[:2])
        else:
            raise HandoutError("Cannot tell which course or project this session belongs to (it is not under '01 Projects/<name>/'): pass --library with the course or project folder")
    folder = _resolve(root, rel, "the library")
    if not folder.is_dir():
        raise HandoutError(f"The library folder does not exist: {rel} (create the course or project first; a handout never invents one)")
    main_note = folder / (folder.name + ".md")
    kind = "project"
    if main_note.is_file():
        kind = "course" if _front(main_note.read_text(encoding="utf-8")).get("type", "").lower() == "course" else "project"
    else:
        main_note = None
        for note in sorted(folder.glob("*.md")):
            if _front(note.read_text(encoding="utf-8")).get("type", "").lower() == "course":
                kind, main_note = "course", note
                break
    return {"kind": kind, "path": rel, "name": folder.name, "main_note": main_note.relative_to(root).as_posix() if main_note else None}


def default_directory(kind: str, title: str, date: str) -> str:
    return f"{COURSE_DIR}/{date} {_slug(title)}" if kind == "course" else f"{PROJECT_DIR}/{_slug(title)}"


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _manifest(directory: Path) -> dict:
    try:
        data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"schema": SCHEMA, "versions": []}


def _unchanged(directory: Path, entry: dict) -> bool:
    """True when every file of a recorded version is on disk exactly as this tool wrote it."""
    for key, suffix in (("tex_sha256", ".tex"), ("pdf_sha256", ".pdf"), ("note_sha256", ".md")):
        if not entry.get(key):
            continue
        path = directory / (str(entry.get("stem")) + suffix)
        if not path.is_file() or _sha(path.read_bytes()) != entry[key]:
            return False
    return True


def choose_stem(directory: Path, slug: str, session: str, on_conflict: str) -> tuple[str, dict | None]:
    """The file stem to write, and the earlier version it replaces (only an unchanged one from the same session).

    A handout whose files were edited since this tool wrote them, or one this tool did not write, is never replaced: the new one gets ``-v2``, ``-v3``...
    (or the build is refused with ``on_conflict='refuse'``).
    """
    entries = {v.get("stem"): v for v in _manifest(directory)["versions"] if isinstance(v, dict)}
    stem, n = slug, 1
    while True:
        if not any((directory / (stem + suffix)).exists() for suffix in (".tex", ".pdf", ".md")):
            return stem, None
        entry = entries.get(stem)
        if entry and entry.get("session") == session and _unchanged(directory, entry):
            return stem, entry
        if on_conflict == "refuse":
            raise HandoutError(f"A handout named '{stem}' already exists in {directory.name}/ and was edited or comes from elsewhere; not replacing it (use --on-conflict version to save a new version)")
        n += 1
        stem = f"{slug}-v{n}"


def _body_sources(body: str) -> list[str]:
    items = []
    for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{[^}]+\}(.*?)(?=\\bibitem|\\end\{sources\})", strip_comments(body), flags=re.S):
        item = re.sub(r"\\(?:emph|textit|textbf|textsc)\{([^}]*)\}", r"*\1*", m.group(1))
        item = re.sub(r"\\url\{([^}]*)\}", r"<\1>", item)
        item = re.sub(r"\\[A-Za-z]+\*?|[{}]", "", item.replace("--", "-").replace("~", " "))
        item = re.sub(r"\s+", " ", item).strip()
        if item:
            items.append(item)
    return items


def _yaml(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_note(title: str, session: str, library: dict, directory_rel: str, stem: str, stage: str, date: str, body: str, pages: int) -> str:
    session_link = session[:-3] if session.lower().endswith(".md") else session
    up = library["main_note"][:-3] if library.get("main_note") else session_link
    contents = "\n".join("- " + re.sub(r"[$\\{}]", "", h) for h in headings(body) if h != "Sources") or "- (see the PDF)"
    sources = "\n".join(f"- {s}" for s in _body_sources(body)) or "- (see the Sources section of the PDF)"
    one_line = re.sub(r"\s+", " ", title)
    plural = "s" if pages != 1 else ""
    return (
        "---\n"
        "type: handout\n"
        f"title: {_yaml(title)}\n"
        f"up: {_yaml('[[' + up + ']]')}\n"
        f"session: {_yaml('[[' + session_link + ']]')}\n"
        f"status: {stage}\n"
        f"date: {date}\n"
        "---\n\n"
        f"# {one_line}\n\n"
        f"Study handout for the session [[{session_link}]] ({pages} page{plural}; the LaTeX source `{stem}.tex` sits beside the PDF).\n\n"
        f"**PDF:** [[{directory_rel}/{stem}.pdf|{stem}.pdf]]\n\n"
        "It is study material to read during and after the session. It is not evidence of learning: what you can do without it is what the session's questions and checks show.\n\n"
        f"## Contents\n\n{contents}\n\n"
        f"## Sources\n\n{sources}\n"
    )


def save(root: Path, library: dict, directory_rel: str, slug: str, session: str, stage: str, files: dict, note_text_for, on_conflict: str) -> dict:
    """Write the handout's files into its directory: figures, ``.tex``, the style file, the PDF, the vault note, then the manifest.

    ``files`` maps names to bytes (``tex``, ``pdf``, ``sty``, ``figures``: {relative: bytes}). Each file is written atomically (a reader never sees half
    a file); the manifest is written last, so a record only exists for files that are complete.
    """
    root = Path(root).resolve()
    library_path = _resolve(root, library["path"], "the library")
    directory = _resolve(root, library["path"] + "/" + directory_rel, "the handout directory")
    if not directory.is_relative_to(library_path):
        raise HandoutError("the handout directory escapes the library")
    stem, replaced = choose_stem(directory, slug, session, on_conflict)
    note_text = note_text_for(stem)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    try:
        for relative, data in sorted(files.get("figures", {}).items()):
            target = _resolve(directory, "figures/" + relative, "a figure")
            if not target.exists() or target.read_bytes() != data:
                _atomic(target, data)
                written.append(target)
        for name, data in ((stem + ".tex", files["tex"]), (STYLE, files["sty"]), (stem + ".pdf", files["pdf"]), (stem + ".md", note_text.encode("utf-8"))):
            target = directory / name
            if name != STYLE or not target.exists() or target.read_bytes() != data:
                _atomic(target, data)
                written.append(target)
        data = _manifest(directory)
        entry = {"n": len(data["versions"]) + 1 if replaced is None else replaced.get("n", 1), "stem": stem, "session": session, "status": stage,
                 "tex_sha256": _sha(files["tex"]), "pdf_sha256": _sha(files["pdf"]), "note_sha256": _sha(note_text.encode("utf-8")),
                 "built_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        data["versions"] = [v for v in data["versions"] if not (isinstance(v, dict) and v.get("stem") == stem)] + [entry]
        _atomic(directory / MANIFEST, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except Exception:
        if replaced is None:
            for path in written:                                   # a new handout that did not finish leaves nothing half-written behind
                if path.name != STYLE:
                    path.unlink(missing_ok=True)
        raise
    return {"directory": directory.relative_to(root).as_posix(), "stem": stem, "replaced": replaced is not None, "version": entry["n"]}


# ---------------------------------------------------------------------------------------------------- session plan

def _session_api():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import html_sessions
    return html_sessions


def load_plan(root: Path, session: str) -> dict | None:
    return _session_api().load_session(root, session).get("plan")


def set_status(root: Path, session: str, stage: str, plan: dict) -> None:
    """Advance export status without overwriting work published during compilation."""
    import session_plan
    hs = _session_api()
    md, _, _ = hs.paths(root, session)
    with hs.Lock(md.with_suffix('.session.lock')):
        state = hs.load_session(root, session)
        new = copy.deepcopy(state.get('plan'))
        current = (new or {}).get('handout') or {}
        expected = plan.get('handout') or {}
        if not current or any(current.get(key) != expected.get(key) for key in ('title', 'directory')):
            raise HandoutError('The handout destination changed during export; the prepared resource is preserved')
        if STAGES.index(stage) < STAGES.index(current.get('status', 'planned')):
            raise HandoutError('The handout export status cannot move backwards')
        current['status'] = stage
        session_plan.check(new)
        state['plan'] = new
        state['updated_at'] = hs._now()
        hs._save(root, session, state)


# ---------------------------------------------------------------------------------------------------- build

def readable_markdown(title: str, session: str, content: dict) -> str:
    """A reusable resource with provenance, never a permanent knowledge promotion."""
    lines = ['---', 'type: tutor-handout', 'title: ' + json.dumps(title, ensure_ascii=False),
             'readable_revision: ' + str(content['revision']), '---', '', '# ' + title, '',
             'Teaching material; reading this is not evidence of learning.', '', 'Session: [[' + session + ']]', '']
    if content.get('focus'):
        lines += ['## Suggested focus', '', *('- ' + item for item in content['focus']), '']
    for section in content['sections']:
        lines += ['## ' + section['title'], '']
        if section.get('solution'):
            lines += ['> Solution appendix — reveal only after an attempt or an explicit request.', '']
        lines += ['\n\n'.join(section['paragraphs']), '']
    lines += ['## Sources', '']
    for source in content['sources']:
        lines += ['- ' + source['title'] + ' — ' + source['reference'] + '; ' + source['locator']]
    return '\n'.join(lines) + '\n'


def publish_readable(root, session: str, content: dict, library: str | None = None) -> dict:
    """Publish native content before diagnostics or PDF export, with isolated revisions.

    Uses the central session lock/writer, then a library lock. Old content and
    learner edits are retained; replay is idempotent. A failed session projection
    leaves its complete library artifact available for recovery, never deletes it.
    """
    import session_plan
    hs = _session_api()
    root = Path(root).resolve()
    md, _, _ = hs.paths(root, session)
    session = md.relative_to(root).as_posix()
    if not hs.rich_text.valid_note_target(session):
        raise HandoutError('The session path must be a valid Obsidian note reference')
    content = copy.deepcopy(content)
    if isinstance(content, dict) and 'note' in content:
        raise HandoutError('The publisher manages readable.note; supply content without a note path')
    problems = session_plan.readable_problems(content)
    if problems:
        raise HandoutError('Invalid readable handout', problems)
    with hs.Lock(md.with_suffix('.session.lock')):
        state = hs.load_session(root, session)
        hs._ensure_context(state)
        plan = copy.deepcopy(state.get('plan'))
        if not plan or not plan.get('handout'):
            raise HandoutError('Prepare a session plan with a handout declaration first')
        handout = plan['handout']
        previous = {k: v for k, v in handout.get('readable', {}).items() if k != 'note'}
        if content != previous and content['revision'] != previous.get('revision', 0) + 1:
            raise HandoutError('Use the next readable revision; earlier content is preserved')
        lib = library_of(root, session, library)
        directory = _resolve(root, lib['path'] + '/' + handout['directory'], 'the handout directory')
        data = readable_markdown(handout['title'], session, content).encode('utf-8')
        stem = re.sub(r'[\[\]|#]', '-', _slug(handout['title'])) + '-readable-r' + str(content['revision']) + '-' + _sha(data)[:16]
        note = directory / (stem + '.md')
        # Validate the final backlink/path before creating anything on disk.
        prospective = dict(content, note=note.relative_to(root).as_posix())
        problems = session_plan.readable_problems(prospective)
        if problems:
            raise HandoutError('Invalid readable handout path', problems)
        directory.mkdir(parents=True, exist_ok=True)
        with hs.Lock(directory / 'readable.lock'):
            version = 1
            while note.exists() and (note.is_symlink() or note.read_bytes() != data):
                version += 1
                if version > 1000:
                    raise HandoutError('Too many conflicting native handout files; inspect the library')
                note = directory / (stem + '-v' + str(version) + '.md')
            _resolve(root, note.relative_to(root).as_posix(), 'the readable handout')
            prospective['note'] = note.relative_to(root).as_posix()
            handout['readable'] = prospective
            session_plan.check(plan)
            if state['plan'] == plan and note.is_file() and note.read_bytes() == data:
                return {'note': prospective['note'], 'revision': content['revision'], 'unchanged': True, 'pdf_required': False}
            if not note.exists():
                _atomic(note, data)
            old_note = (state['plan']['handout'].get('readable') or {}).get('note')
            navigation = [item for item in state.get('navigation', []) if not
                          (item.get('kind') == 'related' and item.get('label') == 'Study handout' and item.get('target') == old_note)]
            navigation.append({'kind': 'related', 'label': 'Study handout', 'target': prospective['note']})
            state['navigation'] = navigation
            state['plan'] = plan
            state['updated_at'] = hs._now()
            hs._save(root, session, state)
        return {'note': prospective['note'], 'revision': content['revision'], 'unchanged': False, 'pdf_required': False}

def build(root, session: str, body_path, title: str | None = None, library: str | None = None, stage: str = "built", figures=None, subtitle: str = "",
          course: str | None = None, line: str = "", date: str | None = None, on_conflict: str = "version", max_overfull: float = DEFAULT_OVERFULL_PT,
          timeout: float = DEFAULT_TIMEOUT, allow_install: bool = False, compiler=compile_document, keep_build=None) -> dict:
    """Lint, compile, check the log, save to the library, write the vault note and advance the plan's handout status. Raises ``HandoutError`` with every problem."""
    root = Path(root).resolve()
    if stage not in ("draft", "built"):
        raise HandoutError("--stage is draft (to be finished after the probe) or built")
    body_path = Path(body_path)
    try:
        body = body_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise HandoutError(f"Cannot read the body: {error}")
    plan = load_plan(root, session)
    handout = (plan or {}).get("handout") or {}
    current = handout.get("status", "planned")
    if STAGES.index(stage) < STAGES.index(current):
        raise HandoutError(f"The plan says this handout is already '{current}'; a handout is never moved back to '{stage}'")
    title = title or handout.get("title")
    if not title or not title.strip():
        raise HandoutError("A handout needs a title (--title, or the handout title in the session plan)")
    if plan is None:
        print("note: the session has no plan, so no handout status will be recorded", file=sys.stderr)
    date = date or dt.date.today().isoformat()
    figures_dir = Path(figures) if figures else (body_path.parent / "figures" if (body_path.parent / "figures").is_dir() else None)
    report = lint(body, handout.get("sections"), figures_dir, check_figures=True)
    if report["errors"]:
        raise HandoutError("The body is not ready to be handed out", report["errors"])
    lib = library_of(root, session, library)
    directory_rel = handout.get("directory") or default_directory(lib["kind"], title, date)
    _resolve(root, lib["path"] + "/" + directory_rel, "the handout directory")                 # refuse an unsafe directory before compiling
    pretty_date = dt.date.fromisoformat(date).strftime("%d %B %Y").lstrip("0")
    meta = {"title": title, "subtitle": subtitle, "course": course or lib["name"], "date": pretty_date, "line": line}
    scratch = Path(tempfile.mkdtemp(prefix="ros-handout-"))
    try:
        build_scratch(body, meta, figures_dir, scratch)
        result = compiler(scratch, "main.tex", timeout=timeout, allow_install=allow_install)
        analysis = analyze_log(result.get("log", ""), max_overfull)
        problems = list(analysis["problems"])
        if result.get("timed_out"):
            problems.insert(0, f"the compile did not finish within {timeout:g} seconds and was stopped")
        if not result.get("pdf") and not problems:
            problems.append("no PDF was produced" + (": " + result.get("output", "")[-300:] if result.get("output") else ""))
        if problems:
            raise HandoutError("The document did not pass the build checks, so it is not handed out", problems)
        pdf = Path(result["pdf"]).read_bytes()
        if not pdf.startswith(b"%PDF") or len(pdf) < 1024:
            raise HandoutError("The compiled file is not a PDF", ["the output is not a valid PDF"])
        tex = (scratch / "main.tex").read_bytes()
        figure_files = {p.relative_to(scratch / "figures").as_posix(): p.read_bytes() for p in sorted((scratch / "figures").rglob("*")) if p.is_file()} if (scratch / "figures").is_dir() else {}
        pages = analysis["pages"]
        folder = (Path(lib["path"]) / directory_rel).as_posix()
        saved = save(root, lib, directory_rel, _slug(title), session, stage,
                     {"tex": tex, "pdf": pdf, "sty": (ASSETS / STYLE).read_bytes(), "figures": figure_files},
                     lambda stem: render_note(title, session, lib, folder, stem, stage, date, body, pages), on_conflict)
    finally:
        if keep_build:                                              # for debugging a refused build: the scratch folder with main.tex, main.log and the PDF
            shutil.rmtree(keep_build, ignore_errors=True)
            shutil.copytree(scratch, keep_build)
        shutil.rmtree(scratch, ignore_errors=True)
    if plan is not None:
        set_status(root, session, stage, plan)
    directory = saved["directory"]
    return {"pdf": f"{directory}/{saved['stem']}.pdf", "tex": f"{directory}/{saved['stem']}.tex", "note": f"{directory}/{saved['stem']}.md", "directory": directory,
            "version": saved["version"], "replaced_unchanged_earlier_build": saved["replaced"], "status": stage if plan is not None else None, "pages": pages,
            "seconds": result.get("seconds"), "tool": result.get("tool"), "warnings": report["warnings"], "stats": report["stats"],
            "latex_note": "compiled with shell escape and the package installer off" if not allow_install else "compiled with shell escape off; the package installer was allowed"}


def locate(root, session: str) -> dict:
    """The latest handout recorded for a session: where its PDF, source and note are."""
    root = Path(root).resolve()
    handout = (load_plan(root, session) or {}).get("handout") or {}
    lib = library_of(root, session, None)
    if not handout.get("directory"):
        raise HandoutError("The session plan declares no handout directory")
    directory = _resolve(root, lib["path"] + "/" + handout["directory"], "the handout directory")
    mine = [v for v in _manifest(directory)["versions"] if isinstance(v, dict) and v.get("session") == session]
    here = directory.relative_to(root).as_posix()
    if not mine:
        return {"built": False, "status": handout.get("status"), "directory": here}
    latest = max(mine, key=lambda v: v.get("n", 0))
    base = here + "/" + latest["stem"]
    return {"built": (directory / (latest["stem"] + ".pdf")).is_file(), "status": latest.get("status"), "pdf": base + ".pdf", "tex": base + ".tex", "note": base + ".md",
            "version": latest.get("n"), "directory": here}


# ---------------------------------------------------------------------------------------------------- template and CLI

def template_text() -> str:
    lines = ["A handout body is the text between \\begin{document} and \\end{document}: \\section commands and what follows. The template owns the title block,",
             "header, fonts, margins and packages. Write the body in plain LaTeX with the environments and macros below.", "", "Environments"]
    for usage, what in ENVIRONMENTS.values():
        lines += [f"  {usage}", f"      {what}"]
    lines += ["", "Macros"]
    for name, what in MACROS.items():
        lines += [f"  {name}", f"      {what}"]
    lines += ["", "Packages already loaded: " + ", ".join(PACKAGES), "",
              "Not allowed (the body is checked and a build refuses it): " + ", ".join("\\" + c for c in ("input", "include", "write", "openin", "openout", "usepackage", "documentclass", "catcode", "csname", "special")) + ", ... see `handout.py check`.",
              "Figures: put files in a figures folder next to the body and use \\includegraphics{figures/name.pdf} (pdf, png, jpg), or draw with tikz and pgfplots.",
              "A body ends with the exercises (\\exercise{...}{full solution}), \\printsolutions in a section of its own, and \\begin{sources}...\\end{sources}."]
    return "\n".join(lines)


def _plan_sections(args) -> list[str] | None:
    if getattr(args, "plan", None):
        return (json.loads(Path(args.plan).read_text(encoding="utf-8-sig")).get("handout") or {}).get("sections")
    if getattr(args, "session", None) and getattr(args, "root", None):
        return ((load_plan(Path(args.root), args.session) or {}).get("handout") or {}).get("sections")
    return None


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check", help="lint a body without compiling")
    c.add_argument("body", type=Path)
    c.add_argument("--plan", type=Path, help="a session plan JSON, to check its handout sections")
    c.add_argument("--root", type=Path)
    c.add_argument("--session")
    c.add_argument("--figures", type=Path)
    t = sub.add_parser("template", help="print the environments and macros a body may use")
    t.add_argument("--json", action="store_true")
    native = sub.add_parser('publish-readable', help='publish structured native handout content without a PDF compiler')
    native.add_argument('--root', required=True, type=Path)
    native.add_argument('--session', required=True)
    native.add_argument('--content', required=True, type=Path, help='JSON readable resource: revision, sections, sources, optional focus')
    native.add_argument('--library')
    b = sub.add_parser("build", help="lint, compile, check the log, save to the library and write the vault note")
    b.add_argument("--root", required=True, type=Path)
    b.add_argument("--session", required=True)
    b.add_argument("--body", required=True, type=Path)
    b.add_argument("--title")
    b.add_argument("--library", help="the course or project folder, relative to the vault (default: the one the session sits in)")
    b.add_argument("--stage", choices=["draft", "built"], default="built", help="draft while the probe's section is still to be added; built when it is finished")
    b.add_argument("--figures", type=Path)
    b.add_argument("--subtitle", default="")
    b.add_argument("--course")
    b.add_argument("--line", default="")
    b.add_argument("--date", help="YYYY-MM-DD (default today)")
    b.add_argument("--on-conflict", choices=["version", "refuse"], default="version", help="when an earlier handout was edited: save a -v2 version or refuse")
    b.add_argument("--max-overfull", type=float, default=DEFAULT_OVERFULL_PT, help="largest overfull box in points that is accepted")
    b.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds for the whole compile")
    b.add_argument("--allow-package-install", action="store_true", help="let MiKTeX download a missing package (off by default: no network)")
    b.add_argument("--keep-build", type=Path, help="copy the scratch build folder (main.tex, main.log, PDF) here, for debugging a refused build")
    loc = sub.add_parser("locate", help="where the latest handout of a session is")
    loc.add_argument("--root", required=True, type=Path)
    loc.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'publish-readable':
            content = json.loads(args.content.read_text(encoding='utf-8-sig'))
            print(json.dumps(publish_readable(args.root, args.session, content, args.library), indent=2, ensure_ascii=False))
            return 0
        if args.command == "template":
            print(json.dumps({"environments": {k: {"usage": u, "use": w} for k, (u, w) in ENVIRONMENTS.items()}, "macros": MACROS, "packages": PACKAGES}, indent=2) if args.json else template_text())
            return 0
        if args.command == "check":
            body = args.body.read_text(encoding="utf-8-sig")
            figures = args.figures or (args.body.parent / "figures" if (args.body.parent / "figures").is_dir() else None)
            report = lint(body, _plan_sections(args), figures, check_figures=bool(figure_paths(body)))
            print(json.dumps({"ok": not report["errors"], **report}, indent=2, ensure_ascii=False))
            return 1 if report["errors"] else 0
        if args.command == "locate":
            print(json.dumps(locate(args.root, args.session), indent=2, ensure_ascii=False))
            return 0
        result = build(args.root, args.session, args.body, title=args.title, library=args.library, stage=args.stage, figures=args.figures, subtitle=args.subtitle,
                       course=args.course, line=args.line, date=args.date, on_conflict=args.on_conflict, max_overfull=args.max_overfull, timeout=args.timeout,
                       allow_install=args.allow_package_install, keep_build=args.keep_build)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except HandoutError as error:
        print(f"refused: {error}", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
