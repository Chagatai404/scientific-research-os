"""Views written out of the record: Markdown lesson logs (math stays as LaTeX, so any Markdown viewer with KaTeX
renders it) and a read-only snapshot. The Obsidian notes are ``ros.vault``. A view is regenerated from events each
time; editing it changes nothing."""
from __future__ import annotations

from pathlib import Path
import re

from .store import Record

VERDICT_MARK = {"correct": "✓ correct", "partially-correct": "◐ partly correct", "incorrect": "✗ not yet",
                "pending": "… waiting for the tutor"}


def lesson_log(rec: Record, lesson: str) -> str:
    """The lesson as it happened: what was taught, each question with the answer given and the verdict, hints shown,
    questions asked and their answers."""
    node = rec.node(lesson) or {}
    events = rec.events(lesson=lesson)
    title = node.get("title") or next((e["data"].get("title") for e in events if e["type"] == "lesson.start"
                                       and e["data"].get("title")), None) or lesson
    grades = {e["data"].get("attempt"): e for e in events if e["type"] == "grade"}
    replies = {e["subject"]: e for e in rec.events(type="answer")}
    lines = [f"# {title}", ""]
    n = 0
    for e in events:
        t, d = e["type"], e["data"]
        if t == "lesson.start":
            lines += [f"*Started {e['ts'][:16].replace('T', ' ')} UTC*", ""]
        elif t == "teach":
            cap = (rec.node(e["subject"]) or {}).get("title", e["subject"].split(":", 1)[-1])
            lines += [f"## {cap}", "", f"*Taught: {d.get('mode', 'explain').replace('-', ' ')}*", ""]
            if d.get("content"):
                lines += [d["content"], ""]
        elif t == "attempt":
            n += 1
            item = rec.item(e["subject"]) or {}
            lines += [f"**Q{n}.** {item.get('prompt', '')}", ""]
            if item.get("kind") == "choice":
                lines += [f"{chr(97 + i)}. {o}" for i, o in enumerate(item.get("options", []))] + [""]
            g = grades.get(e["id"])
            verdict = g["data"]["verdict"] if g else "pending"
            lines += [f"> Answer: {_show(item, d.get('response'))}", ">", f"> {VERDICT_MARK.get(verdict, verdict)}"]
            if g and g["data"].get("feedback"):
                lines += [">", f"> {g['data']['feedback']}"]
            if g and verdict != "correct" and item.get("explanation"):
                lines += [">", f"> *Why:* {item['explanation']}"]
            lines.append("")
        elif t == "hint":
            item = rec.item(e["subject"]) or {}
            hints = item.get("hints") or []
            if d.get("index", 0) < len(hints):
                lines += [f"*Hint:* {hints[d.get('index', 0)]}", ""]
        elif t == "ask":
            text = d.get("text") or d.get("response") or f"Explain it another way ({d.get('mode')})"
            lines += [f"**You asked:** {text}", ""]
            r = replies.get(e["id"])
            if r:
                lines += [f"**Tutor:** {r['data'].get('text', '')}", ""]
        elif t == "lesson.close":
            lines += ["---", "", f"*Closed {e['ts'][:16].replace('T', ' ')} UTC.* {d.get('summary', '')}".rstrip(), ""]
    return "\n".join(lines).rstrip() + "\n"


def write_lesson_log(rec: Record, lesson: str) -> Path:
    path = rec.root / "logs" / (lesson.split(":", 1)[-1] + ".md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lesson_log(rec, lesson), encoding="utf-8", newline="\n")
    return path


def _show(item: dict, response) -> str:
    if item.get("kind") == "choice":
        try:
            i = int(response)
            return f"{chr(97 + i)}. {item['options'][i]}"
        except (TypeError, ValueError, IndexError):
            pass
    return str(response)


# ---- the mark version 1.1's Obsidian export wrote -------------------------------------------------------------------
MARK = "ros_export"  # notes carrying it are replaced by ``vault`` when unedited; the writer is now ``ros.vault``


# ---- a read-only snapshot -------------------------------------------------------------------------------------------
def static(rec: Record, out: Path | str, as_of=None) -> Path:
    """One self-contained HTML file: capabilities, claims, answers and lesson logs, marked read-only. Math is shown as
    its LaTeX source; nothing is loaded from anywhere."""
    from datetime import date
    from html import escape
    from . import graph, research
    learning = graph.Learning(rec, as_of or date.today())
    css = (Path(__file__).resolve().parent / "portal" / "app.css").read_text(encoding="utf-8")
    css = re.sub(r"@font-face\s*{[^}]*}", "", css)

    def table(head, rows):
        return ("<div class='table-wrap'><table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in head)
                + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>"
                                                    for r in rows) + "</tbody></table></div>")

    caps = [learning.view(k) for k in learning.order(learning.caps)]
    parts = [f"<h1>{escape(rec.root.name)}</h1>",
             "<p class='card'><strong>Read-only snapshot.</strong> Nothing here saves; open the portal "
             "(<code>ros serve</code>) to learn or decide.</p>",
             "<h2>Capabilities</h2>", table(["Capability", "State", "Next review"],
                                            [[c["title"], c["state"], c["next_review"] or "—"] for c in caps])]
    claims = research.claims(rec)
    if claims:
        parts += ["<h2>Claims</h2>", table(["Claim", "Verdict", "Ownership"],
                                           [[c["text"] or c["id"], c["verdict"], c["ownership"]] for c in claims])]
    hist = graph.history(rec)
    if hist:
        parts += ["<h2>Answers</h2>", table(["When", "Question", "Answer", "Grade"],
                                            [[h["ts"][:16].replace("T", " "), h["prompt"] or "", h["response"],
                                              h["grade"] or "waiting"] for h in hist])]
    for n in rec.nodes(type="lesson"):
        if n["id"].startswith("lesson:") and rec.events(type="lesson.start", subject=n["id"]):
            parts += [f"<h2>{escape(n.get('title') or n['id'])}</h2>",
                      f"<pre class='card' style='white-space:pre-wrap'>{escape(lesson_log(rec, n['id']))}</pre>"]
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            "content='width=device-width, initial-scale=1'><meta http-equiv='Content-Security-Policy' "
            "content=\"default-src 'none'; style-src 'unsafe-inline'\"><title>" + escape(rec.root.name)
            + " (read-only)</title><style>" + css + "body{display:block}</style></head><body><main>"
            + "".join(parts) + "</main></body></html>\n")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8", newline="\n")
    return out
