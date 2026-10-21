"""Views written out of the record: Markdown lesson logs (math stays as LaTeX, so any Markdown viewer with KaTeX
renders it) and curated Obsidian notes. A view is regenerated from events each time; editing it changes nothing."""
from __future__ import annotations

from pathlib import Path

from .store import Record

VERDICT_MARK = {"correct": "✓ correct", "partially-correct": "◐ partly correct", "incorrect": "✗ not yet",
                "pending": "… waiting for the tutor"}


def lesson_log(rec: Record, lesson: str) -> str:
    """The lesson as it happened: what was taught, each question with the answer given and the verdict, hints shown,
    questions asked and their answers."""
    node = rec.node(lesson) or {}
    events = [e for e in rec.events() if e["subject"] == lesson or e["data"].get("lesson") == lesson]
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
