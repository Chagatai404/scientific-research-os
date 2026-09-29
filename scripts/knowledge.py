"""Read opt-in Markdown learning records and emit an evidence-based Mermaid view.

Only the documented schema in assets/obsidian/README.md is supported, not YAML
in general. No input notes are modified and no answers are automatically graded.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import re
import sys


ID = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")
STATES = {"unknown", "learning", "demonstrated", "retained", "fragile", "stale"}
RETENTION_TARGETS = {"core", "working", "reference"}
FIELDS = {
    "learning_schema", "learning_id", "domain", "projects", "goals", "courses", "prerequisites",
    "learning_state", "first_learned", "last_retrieval", "next_review", "retention_target",
}
HEADER = ["Date", "Learning period", "Timing", "Method", "Outcome",
          "Assistance", "Evidence", "Next review"]
METHODS = {"recall", "explanation", "derivation", "prediction", "transfer", "computation", "mcq"}
RECONSTRUCTION = {"explanation", "derivation", "transfer", "computation"}


@dataclass
class Attempt:
    day: date
    period: str
    timing: str
    method: str
    outcome: str
    assistance: str
    evidence: str
    review: date | None


@dataclass
class Assessment:
    state: str
    first: date | None = None
    last: date | None = None
    review: date | None = None
    evidence: str = ""


@dataclass
class Node:
    id: str
    title: str
    path: str
    domain: str
    projects: list[str]
    prerequisites: list[str]
    meta: dict[str, object]
    attempts: list[Attempt]
    assessment: Assessment
    as_of: date
    issues: list[str] = field(default_factory=list)

    @property
    def retention_target(self) -> str:
        return self.meta.get("retention_target", "unspecified")

    @property
    def review_policy(self) -> str:
        return {"core": "maintain justified retrieval",
                "working": "refresh around use",
                "reference": "no routine spaced review",
                "unspecified": "target not chosen"}[self.retention_target]

    @property
    def freshness(self) -> str:
        if self.assessment.review and self.as_of > self.assessment.review:
            return "overdue"
        if self.assessment.review == self.as_of:
            return "due"
        return "unknown" if self.assessment.review is None else "scheduled"

    @property
    def ready(self) -> bool:
        return (not self.issues and self.assessment.state in {"demonstrated", "retained"}
                and self.assessment.review is not None)


@dataclass
class Collection:
    nodes: dict[str, Node] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    legacy: int = 0
    drafts: int = 0


def iso_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(value)


def scalar(raw: str) -> str:
    if raw.startswith('"'):
        value = json.loads(raw)
        if not isinstance(value, str) or any(c in value for c in "\r\n"):
            raise ValueError("expected one-line string")
        return value
    if not raw or re.search(r"[\s\[\]{}'\"&*!|>#:]", raw):
        raise ValueError(f"unsupported scalar syntax: {raw!r}")
    return raw


def metadata(text: str) -> tuple[dict[str, object] | None, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0] != "---":
        return None, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        if any(re.match(r"\s*learning_(schema|id)\s*:", line) for line in lines):
            raise ValueError("unterminated learning frontmatter")
        return None, text
    front = lines[1:end]
    if not any(re.match(r"\s*learning_(schema|id)\s*:", line) for line in front):
        return None, "\n".join(lines[end + 1:])
    data: dict[str, object] = {}
    active = ""
    for line in front:
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not match:
            if line.strip() and not line.lstrip().startswith("#"):
                if active in FIELDS or re.match(r"\s+(?:learning_\w+|prerequisites|projects|goals|courses|domain|retention_target):", line):
                    raise ValueError("nested/multiline learning fields are unsupported")
            continue
        key, raw = match.groups()
        active = key
        if key not in FIELDS:
            continue
        if key in data:
            raise ValueError(f"duplicate field: {key}")
        raw = raw.strip()
        if key in {"projects", "goals", "courses", "prerequisites"}:
            value = json.loads(raw)
            if not isinstance(value, list) or any(not isinstance(x, str) or not ID.fullmatch(x) for x in value):
                raise ValueError(f"{key}: expected inline list of IDs")
            if len(value) != len(set(value)):
                raise ValueError(f"{key}: duplicate ID")
            data[key] = value
        elif key == "learning_schema":
            if raw != "1":
                raise ValueError("unsupported learning_schema; expected integer 1")
            data[key] = 1
        else:
            data[key] = scalar(raw)
    if data.get("learning_schema") != 1 or "learning_id" not in data:
        raise ValueError("tracking requires learning_schema and learning_id")
    for key in ("learning_id", "domain"):
        value = data.get(key, "")
        if value and not ID.fullmatch(value):
            raise ValueError(f"invalid {key}: {value!r}")
    if data.get("learning_state", "unknown") not in STATES:
        raise ValueError("invalid learning_state")
    if "retention_target" in data and data["retention_target"] not in RETENTION_TARGETS:
        raise ValueError("invalid retention_target; expected core, working, or reference")
    for key in ("first_learned", "last_retrieval", "next_review"):
        if data.get(key):
            iso_date(data[key])
    return data, "\n".join(lines[end + 1:])


def unfenced_lines(body: str) -> list[str]:
    """Ignore example tables/headings inside Markdown fences."""
    result = []
    fence = ""
    for line in body.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if not fence:
            result.append(line)
    return result


def cells(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError("retrieval rows need leading and trailing pipes")
    parts = [x.strip() for x in line[1:-1].split("|")]
    if len(parts) != 8:
        raise ValueError("retrieval rows need exactly eight cells; no pipes inside cells")
    return parts


def history(body: str) -> list[Attempt]:
    lines = unfenced_lines(body)
    starts = [i for i, line in enumerate(lines) if line == "## Retrieval history"]
    if not starts:
        return []
    if len(starts) != 1:
        raise ValueError("duplicate Retrieval history section")
    section = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        section.append(line.strip())
    table_start = next((i for i, line in enumerate(section) if line.startswith("|")), len(section))
    table = [line for line in section[table_start:] if line]
    if len(table) < 2 or cells(table[0]) != HEADER:
        raise ValueError("missing or incorrect retrieval table header")
    if not all(re.fullmatch(r":?-{3,}:?", x) for x in cells(table[1])):
        raise ValueError("invalid retrieval table separator")
    attempts = []
    for number, line in enumerate(table[2:], 1):
        try:
            day, period, timing, method, outcome, assistance, evidence, review = cells(line)
            when = iso_date(day)
            due = iso_date(review) if review else None
            if not period or not evidence:
                raise ValueError("learning period and evidence reference are required")
            if timing not in {"same-session", "delayed"} or method not in METHODS:
                raise ValueError("invalid timing or method")
            if outcome not in {"pass", "partial", "fail"} or assistance not in {"none", "hinted", "open-notes"}:
                raise ValueError("invalid outcome or assistance")
            if attempts and when < attempts[-1].day:
                raise ValueError("attempts must be chronological")
            if due and due < when:
                raise ValueError("next review precedes attempt")
            attempts.append(Attempt(when, period, timing, method, outcome, assistance, evidence, due))
        except ValueError as exc:
            raise ValueError(f"retrieval row {number}: {exc}") from exc
    return attempts


def assess(attempts: list[Attempt], initial: str, as_of: date) -> Assessment:
    result = Assessment("learning" if initial == "learning" else "unknown")
    demonstrated_periods: dict[str, date] = {}
    latest_reconstruction: date | None = None
    for attempt in attempts:
        if attempt.day > as_of:
            break
        result.last = attempt.day
        qualifies = attempt.method in RECONSTRUCTION and attempt.assistance == "none"
        if attempt.outcome == "pass" and qualifies:
            prior = demonstrated_periods.get(attempt.period)
            delayed = (attempt.timing == "delayed" and prior is not None and prior < attempt.day
                       and latest_reconstruction is not None and latest_reconstruction < attempt.day)
            if (result.state == "retained" and attempt.timing == "delayed"
                    and prior == attempt.day and latest_reconstruction == attempt.day):
                # Another successful check today does not undo the delayed evidence,
                # but cannot extend its horizon as though another interval passed.
                continue
            result.state = "retained" if delayed else "demonstrated"
            result.first = result.first or attempt.day
            demonstrated_periods[attempt.period] = attempt.day
            latest_reconstruction = attempt.day
            result.review, result.evidence = attempt.review, attempt.evidence
        elif attempt.outcome != "pass" or attempt.assistance != "none":
            result.state = "fragile" if result.first else "learning"
            demonstrated_periods.clear()
            result.review, result.evidence = attempt.review, attempt.evidence
        # Recognition-only success neither promotes state nor renews freshness.
    return result


def make_node(meta: dict[str, object], body: str, path: str, as_of: date) -> Node:
    if not meta.get("domain") or "prerequisites" not in meta:
        raise ValueError("tracked node requires domain and explicit prerequisites")
    attempts = history(body)
    initial = meta.get("learning_state", "unknown")
    full = assess(attempts, initial, date.max)
    current = assess(attempts, initial, as_of)
    titles = [line[2:] for line in unfenced_lines(body) if line.startswith("# ")]
    node = Node(meta["learning_id"], titles[0] if titles else meta["learning_id"], path,
                meta["domain"], meta.get("projects", []), meta["prerequisites"], meta, attempts, current, as_of)
    if "learning_state" in meta:
        # Stale is a dated view of a positive evidence state, never its replacement.
        allowed = {full.state}
        if full.state in {"demonstrated", "retained"} and full.review:
            allowed.add("stale")
        if initial not in allowed:
            node.issues.append(f"learning_state {initial!r} conflicts with evidence ({full.state})")
    for key, actual in (("first_learned", full.first), ("last_retrieval", full.last), ("next_review", full.review)):
        if meta.get(key) and iso_date(meta[key]) != actual:
            node.issues.append(f"{key} conflicts with retrieval history")
    if current.state in {"demonstrated", "retained"} and current.review and as_of > current.review:
        current.state = "stale"
    return node


def discover(root: Path, as_of: date) -> Collection:
    result = Collection()
    duplicates: set[str] = set()
    seen: set[str] = set()
    def walk_error(exc: OSError) -> None:
        result.diagnostics.append(f"directory could not be read: {exc}")

    # Hidden folders and symlinks are not inputs; do not follow vault links elsewhere.
    for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_error):
        folders[:] = sorted(x for x in folders if not x.startswith(".") and not (Path(directory) / x).is_symlink())
        for filename in sorted(files):
            path = Path(directory) / filename
            if path.suffix.lower() != ".md" or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            try:
                meta, body = metadata(path.read_text(encoding="utf-8-sig"))
                if meta is None:
                    result.legacy += 1
                    continue
                if not meta["learning_id"]:
                    result.drafts += 1
                    if (any(meta.get(k) for k in ("domain", "projects", "goals", "courses", "prerequisites", "first_learned", "last_retrieval", "next_review", "retention_target"))
                            or meta.get("learning_state", "unknown") != "unknown" or history(body)):
                        raise ValueError("partially populated record has no learning_id")
                    continue
                key = meta["learning_id"]
                if key in seen:
                    duplicates.add(key)
                    result.diagnostics.append(f"{relative}: duplicate learning_id {key}")
                seen.add(key)
                node = make_node(meta, body, relative, as_of)
                if key not in duplicates:
                    result.nodes[key] = node
            except (ValueError, OSError) as exc:
                result.diagnostics.append(f"{relative}: {exc}")
    for duplicate in sorted(duplicates):
        result.diagnostics.append(f"duplicate ID excluded: {duplicate}")
        result.nodes.pop(duplicate, None)
    for node in result.nodes.values():
        for prerequisite in node.prerequisites:
            if prerequisite not in result.nodes:
                node.issues.append(f"missing prerequisite: {prerequisite}")
    # Kahn elimination finds cycles and every dependent whose ancestry hits one.
    pending = set(result.nodes)
    while pending:
        removable = {key for key in pending if not (set(result.nodes[key].prerequisites) & pending)}
        if not removable:
            break
        pending -= removable
    for key in sorted(pending):
        result.nodes[key].issues.append("cycle or dependency on a cycle")
    for node in result.nodes.values():
        result.diagnostics.extend(f"{node.path}: {issue}" for issue in node.issues)
    return result


def select(nodes: dict[str, Node], scope: str, value: str) -> tuple[set[str], set[str]]:
    primary = {key for key, node in nodes.items()
               if (node.domain == value if scope == "subject" else value in node.meta.get({"project": "projects", "goal": "goals", "course": "courses"}[scope], []))}
    selected = set(primary)
    todo = list(primary)
    while todo:
        for prerequisite in nodes[todo.pop()].prerequisites:
            if prerequisite in nodes and prerequisite not in selected:
                selected.add(prerequisite)
                todo.append(prerequisite)
    return primary, selected


def ready_nodes(nodes: dict[str, Node]) -> set[str]:
    """Readiness requires valid evidence throughout the prerequisite ancestry."""
    ready: set[str] = set()
    while True:
        additions = {key for key, node in nodes.items()
                     if key not in ready and node.ready and set(node.prerequisites) <= ready}
        if not additions:
            return ready
        ready.update(additions)


def frontier(node: Node, ready: set[str]) -> bool:
    return (not node.issues and set(node.prerequisites) <= ready
            and not (node.assessment.state == "retained" and node.id in ready))


def safe_text(value: str) -> str:
    # Escape Markdown and HTML without introducing executable Mermaid syntax.
    return "".join(c if c.isalnum() or c in " ._- /" else f"&#{ord(c)};" for c in value)


def mermaid_text(value: str) -> str:
    return "".join(c if c.isalnum() or c in " ._- /" else f"#{ord(c)};" for c in value)


def render(collection: Collection, scope: str, value: str, as_of: date) -> str:
    nodes = collection.nodes
    ready = ready_nodes(nodes)
    primary, selected = select(nodes, scope, value)
    ids = {key: f"n{i}" for i, key in enumerate(sorted(selected))}
    lines = [f"# Knowledge graph: {scope} {safe_text(value)}", "", f"As of: {as_of}", "",
             "States summarize recorded assessments, not independently verified mastery.",
             "Missing recent evidence is not proven forgetting. External nodes are required foundations.", "",
             "Retention targets are choices, not mastery or importance scores. Frontier is eligibility, not review priority.",
             "Reference records have no routine spaced-review burden; historical horizons remain visible.", "",
             "```mermaid", "flowchart TD"]
    for key in sorted(selected):
        node = nodes[key]
        label = f"{node.title} — {node.assessment.state} — {node.retention_target}"
        if key not in primary:
            label += " — external"
        if node.issues:
            label += " — evidence issue"
        elif frontier(node, ready):
            label += " — frontier"
        lines.append(f'    {ids[key]}["{mermaid_text(label)}"]:::{node.assessment.state}')
        for prerequisite in sorted(node.prerequisites):
            if prerequisite in ids:
                lines.append(f"    {ids[prerequisite]} --> {ids[key]}")
    colors = {"unknown": "#eeeeee", "learning": "#dbeafe", "demonstrated": "#ccfbf1",
              "retained": "#dcfce7", "fragile": "#ffedd5", "stale": "#f3e8ff"}
    for state, color in colors.items():
        lines.append(f"    classDef {state} fill:{color},color:#111111,stroke:#555555")
    lines += ["```", "", "| Learning ID / record | State | Retention target | Freshness | Last attempt | Recorded next review | Review policy | State evidence | Position |",
              "|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(selected):
        node = nodes[key]
        blocked = sorted(set(node.prerequisites) - ready)
        position = ("evidence issue" if node.issues else "blocked by " + ", ".join(blocked) if blocked
                    else "frontier" if frontier(node, ready) else "retained foundation")
        a = node.assessment
        freshness = node.freshness
        if node.retention_target == "reference":
            freshness += " (historical horizon; no routine review)"
        lines.append(f"| {safe_text(key)} ({safe_text(node.path)}) | {a.state} | {node.retention_target} | {freshness} | "
                     f"{a.last or '—'} | {a.review or '—'} | {node.review_policy} | {safe_text(a.evidence) or '—'} | {safe_text(position)} |")
    if not primary:
        lines += ["", "No tracked nodes match this scope."]
    lines += ["", f"Skipped untracked/legacy notes: {collection.legacy}; blank drafts: {collection.drafts}.",
              "", "## Diagnostics", ""]
    lines += [f"- {safe_text(x)}" for x in sorted(set(collection.diagnostics))] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Markdown input directory (read-only)")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--subject")
    scope.add_argument("--project")
    scope.add_argument("--goal")
    scope.add_argument("--course")
    parser.add_argument("--as-of", type=iso_date, default=date.today())
    parser.add_argument("--output", type=Path, help="create a new Markdown file; never overwrite")
    args = parser.parse_args(argv)
    # Redirected Windows consoles otherwise emit a locale code page, corrupting
    # Unicode note titles in the Markdown stream. StringIO in callers needs none.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("--root must be an existing directory")
    selected_scope = next(name for name in ("subject", "project", "goal", "course") if getattr(args, name) is not None)
    value = getattr(args, selected_scope)
    if not ID.fullmatch(value):
        parser.error("scope must be a valid domain/project/goal/course ID")
    collection = discover(root, args.as_of)
    output = render(collection, selected_scope, value, args.as_of)
    try:
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
        else:
            sys.stdout.write(output)
    except OSError as exc:
        parser.error(str(exc))
    return 1 if collection.diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
