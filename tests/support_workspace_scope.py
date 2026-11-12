"""Synthetic multi-workspace fixture and loopback server for scope tests; no personal data, no providers.

Two courses and one project (plus an empty project), each with its own sessions, sources and handouts.
`algebra` is a split course (empty dedicated record, history in Knowledge); `optics` and
`survey` exist only as hubs inside the Knowledge record. Every hub carries a source that
is called "Notes" with the same relative path, so equal names must never cross over.
"""
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ROS_NO_VAULT"] = "1"
from ros import home, serve
from ros.store import Record

HUBS = (("course", "algebra", "Linear Algebra"), ("course", "optics", "Optics"), ("project", "survey", "Field Survey"))


def build(base):
    """Create the records under ``base``; returns the open Knowledge record."""
    os.environ["ROS_HOME"] = str(base)
    projects = Path(base) / "projects"
    knowledge = Record(projects / "knowledge")
    knowledge.root.mkdir(parents=True, exist_ok=True)
    home.set_config(knowledge.root, role="user")
    dedicated = Record(projects / "algebra-course")
    dedicated.root.mkdir(parents=True, exist_ok=True)
    home.set_config(dedicated.root, role="project", user="knowledge", project="course:algebra")
    for kind, key, title in HUBS:
        hub = f"{kind}:{key}"
        knowledge.put_node(hub, kind, title=title)
        if key == "algebra":
            dedicated.put_node(hub, kind, title=title)
            dedicated.append("workspace.renamed", "workspace", {"title": title}, actor="person")
        knowledge.put_node(f"conversation:{key}", "conversation", title=f"{title} discussion", hub=hub, hub_record="knowledge")
        knowledge.put_node(f"lesson:{key}", "lesson", title=f"{title} first lesson")
        knowledge.put_edge(f"lesson:{key}", "part-of", hub)
        knowledge.put_node(f"source:{key}-notes", "source", title="Notes", path=f"vault/{key}/Notes.md", source_hash=f"hash-{key}")
        knowledge.put_edge(f"source:{key}-notes", "part-of", hub)
        knowledge.put_node(f"handout:{key}-lecture", "handout", title=f"{title} lecture", kind="lecture", source_hash=f"lecture-{key}")
        knowledge.put_edge(f"handout:{key}-lecture", "part-of", hub)
        knowledge.append("source.registered", f"connection:{key}", {"root": f"unused-{key}", "kind": "folder", "label": f"{title} files", "localOnly": True})
        knowledge.append("organization.moved", f"connection:{key}", {"parent": hub})
        knowledge.append("library.added", f"material:{key}", {"source": f"connection:{key}", "path": "Week 1/Notes.pdf", "title": "Notes", "format": "pdf"})
        knowledge.append("library.state", f"material:{key}", {"state": "ready", "indexed": False})
    # One file kept in two places inside algebra: shown once, with the other place as an alternate.
    knowledge.put_node("source:algebra-copy", "source", title="Notes (copy)", path="folder/Notes.md", source_hash="hash-algebra")
    knowledge.put_edge("source:algebra-copy", "part-of", "course:algebra")
    # A project with no work yet: the empty state.
    knowledge.put_node("project:blank", "project", title="Blank Project")
    # An unrelated record that never joins any workspace.
    knowledge.put_node("lesson:unrelated", "lesson", title="Unrelated lesson")
    dedicated.close()
    return knowledge


if __name__ == "__main__":
    rec = build(Path(sys.argv[1]))
    server = serve._bind(rec, 0)
    print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}/", "pairing": server.pairing}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        rec.close()
