"""The Obsidian vault as the place knowledge and decisions live, kept in step with the record without anyone running a
command. Everything Research OS writes goes under ``<vault>/<vault_root>/`` (default ``Research OS/``); nothing outside
it is touched, and a file is deleted only when it is one Research OS generated and nobody has edited.

    Research OS/Home.md                      the map of content: courses, projects, today, bases
    Research OS/Inbox/                       drop anything here; every course and project has its own Inbox/
    Research OS/Courses/<Course>/            course note, Capabilities/, Lessons/, Handouts/, Decisions/
    Research OS/Projects/<Project>/          project note, Questions/, Experiments/, Claims/, Papers/, Handouts/ ...
    Research OS/Knowledge/                   the user-wide record: capabilities by domain
    Research OS/Reviews/YYYY-MM-DD.md        the daily review note
    Research OS/Bases/*.base                 Obsidian Bases views over the properties below
    Research OS/Attachments/<hub>/*.pdf      handout PDFs

A note is ``frontmatter + generated region + "My notes"``. The frontmatter keys Research OS owns carry a hash of what it
wrote (``ros_hash``). The rules, each a branch of ``scan`` and ``sync`` (see ``references/VAULT.md``):

* the generated region and owned keys match their hash: they are updated freely when the record changes;
* text after the region ("My notes") is never touched, and flows back to the record as a ``note.annotate`` event;
* an edit inside the generated region or an owned key pins the note (``user-edited``) until the person lets the record
  update it; the edit is kept in the event and re-appended under "My notes" if they do;
* a generated note the person deletes is not recreated (``note.dismiss``); structural notes are;
* a new file the person drops in an ``Inbox/`` (or anywhere under the root) is never moved or edited: it becomes a
  ``source`` node, and a PDF or image opens an ``ingest`` task (``inbox.found``).

The manifest (``$ROS_HOME/vault/<id>.sqlite``) lives outside the vault. It remembers each file's stat, hashes, id and
links, so a scan stats the files under the root and reads only those that changed, and a lookup by id or title is an
indexed query. It is derived: lose it and the next scan rebuilds it from the ``ros_id`` in each note's frontmatter.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Callable
from urllib.parse import quote

from . import context, graph, home, research, tasks
from .export import MARK as V11_MARK, lesson_log
from .store import Record, canonical, event_id

BEGIN = "<!-- ros:begin (generated from the record; edits here pause updates) -->"
BEGIN_PREFIX = "<!-- ros:begin"
END = "<!-- ros:end -->"
MY_NOTES = "## My notes"
SCAFFOLD_HASH = hashlib.sha256(MY_NOTES.encode()).hexdigest()[:16]
EVENTS = ("note.dismiss", "note.release", "lesson.close", "decision", "verdict", "retrieval", "grade", "approval",
          "inbox.found", "handout.built", "handout.revise")
# Frontmatter keys Research OS owns; the hash covers these and the generated region. Anything else is the person's.
OWNED = ("ros_id", "ros_record", "ros_kind", "ros_portal", "title", "aliases", "state", "next_review", "up",
         "prerequisites", "unlocks", "pdf", "legacy", "outcome", "by", "date", "subject", "verdict", "ownership",
         "assurance", "started", "closed", "status", "authorization", "handout_kind", "project", "capabilities",
         "lecture", "sources")
FILES = {".md": "note", ".pdf": "pdf", ".canvas": "canvas", ".base": "base", ".png": "image", ".jpg": "image",
         ".jpeg": "image", ".gif": "image", ".svg": "image", ".webp": "image"}
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
SHOWN = 50  # how many names a report lists; the counts are always whole


# ---- names, links, frontmatter ------------------------------------------------------------------------------------
def safe_name(title: str | None, limit: int = 120) -> str:
    """A file name that works in Obsidian and on Windows: no ``[]#^|:\\/*?"<>``, no reserved device names."""
    name = re.sub(r'[\[\]#^|:\\/*?"<>]', " ", str(title or ""))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "Untitled"
    if name.lower() in RESERVED:
        name = "_" + name
    return name[:limit].rstrip(" .") or "Untitled"


def wikilink(path: str, title: str | None = None) -> str:
    """A path-qualified wikilink, so two notes with the same title never resolve to each other."""
    target = path[:-3] if path.endswith(".md") else path
    return f"[[{target}|{title}]]" if title else f"[[{target}]]"


_WORDS = {"true", "false", "null", "yes", "no", "on", "off", "~"}
_BARE = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _scalar_out(value) -> str:
    s = str(value)
    if _DATE.match(s) or (_BARE.match(s) and s.lower() not in _WORDS):
        return s
    return json.dumps(s, ensure_ascii=False)


def emit_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar_out(v) for v in value) + "]"
    return _scalar_out(value)


def _scalar_in(text: str) -> str:
    s = text.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return re.sub(r"\s+#.*\Z", "", s)


def _inline_list(text: str) -> list[str]:
    body = text.strip()[1:]
    body = body[:body.rindex("]")] if "]" in body else body
    items, cur, quote_ch = [], "", ""
    for ch in body:
        if quote_ch:
            cur += ch
            if ch == quote_ch and not cur.endswith("\\" + ch):
                quote_ch = ""
        elif ch in "\"'":
            quote_ch = ch
            cur += ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    return [_scalar_in(i) for i in items if i.strip()]


def parse_block(block: str) -> tuple[dict, dict]:
    """The values (strings, or lists of strings) and the raw lines of each key in a frontmatter block. Nested maps are
    kept as raw lines only, so they survive a rewrite untouched."""
    lines, values, raw, i = block.splitlines(), {}, {}, 0
    while i < len(lines):
        m = re.match(r"([A-Za-z_][\w-]*):[ \t]*(.*)\Z", lines[i])
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(lines) and (lines[j][:1] in (" ", "\t") or lines[j].startswith("- ") or lines[j] == "-"):
            j += 1
        cont = [c for c in lines[i + 1:j] if c.strip()]
        raw[key] = lines[i:j]
        if rest.startswith("["):
            values[key] = _inline_list(rest)
        elif rest == "" and cont and all(c.strip().startswith("-") for c in cont):
            values[key] = [_scalar_in(c.strip()[1:]) for c in cont]
        elif rest in ("|", ">", "|-", ">-"):
            values[key] = " ".join(c.strip() for c in cont)
        elif rest == "" and cont:
            values[key] = ""
        else:
            values[key] = _scalar_in(rest)
        i = j
    return values, raw


@dataclass
class Parsed:
    fm: dict
    raw: dict
    region: str | None
    user: str
    has_fm: bool


def parse_note(text: str) -> Parsed:
    m = re.match(r"---[ \t]*\r?\n(.*?)(?:\r?\n)?---[ \t]*(?:\r?\n|\Z)", text, re.S)
    fm, raw = parse_block(m.group(1)) if m else ({}, {})
    rest = text[m.end():] if m else text
    region, user = None, rest
    b = re.search(r"^" + re.escape(BEGIN_PREFIX) + r"[^\n]*\n", rest, re.M)
    e = rest.find(END, b.end()) if b else -1
    if b and e != -1:
        region = rest[b.end():e].strip("\n")
        user = rest[e + len(END):].lstrip("\n")
    return Parsed(fm, raw, region, user, bool(m))


def _as_list(value) -> list[str]:
    return [] if value in (None, "") else list(value) if isinstance(value, list) else [str(value)]


def gen_hash(fm: dict, region: str | None) -> str:
    """The hash of what Research OS wrote: its owned keys, its own tags and the generated region."""
    own = {k: ([str(x) for x in v] if isinstance(v, list) else str(v)) for k, v in fm.items()
           if k in OWNED and v not in ("", [], None)}
    tags = sorted(t for t in _as_list(fm.get("tags")) if t.startswith("ros/"))
    return hashlib.sha256(canonical([own, tags, (region or "").strip()])).hexdigest()[:16]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _short(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


@dataclass
class Note:
    """What a note type produces: owned properties (strings or lists of strings), tags and the generated body."""
    id: str
    kind: str
    folder: str
    title: str
    props: dict
    body: str
    tags: tuple = ()
    structural: bool = False
    status: str = "generated"


def render_note(note: Note, user_text: str | None = None, user_tags: list[str] = (), raw_extra: list[str] = ()) -> str:
    props = {k: ([str(x) for x in v] if isinstance(v, list) else str(v)) for k, v in note.props.items()}
    tags = [*dict.fromkeys(note.tags), *[t for t in user_tags if t not in note.tags]]
    fm = {**props, "tags": tags}
    h = gen_hash(fm, note.body)
    lines = ["---"]
    for k in ("ros_id", "ros_record", "ros_kind", "ros_portal"):
        if k in props:
            lines.append(f"{k}: {emit_value(props[k])}")
    lines += [f"ros_hash: {h}", f"ros_status: {note.status}"]
    lines += [f"{k}: {emit_value(v)}" for k, v in props.items() if not k.startswith("ros_") and v not in ("", [], None)]
    lines.append(f"tags: {emit_value(tags)}")
    lines += list(raw_extra)
    lines += ["---", BEGIN, note.body.strip("\n"), END, ""]
    lines.append(MY_NOTES + "\n" if user_text is None else user_text.rstrip("\n") + "\n")
    return "\n".join(lines)


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".ros-{os.getpid()}-{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ---- the manifest -------------------------------------------------------------------------------------------------
class Manifest:
    """The derived index of the vault: one row per file Research OS knows (written or found), the hubs whose folders
    receive inbox files, the links each note makes, and a cursor per record."""
    SCHEMA = "3"

    def __init__(self, vault: Path):
        d = home.home() / "vault"
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / (hashlib.sha256(str(vault.resolve()).encode()).hexdigest()[:10] + ".sqlite")
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        if self.db.execute("SELECT name FROM sqlite_master WHERE name='kv'").fetchone() is None or \
                self.kv("schema") != self.SCHEMA:
            self.db.executescript("""
                DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS hubs; DROP TABLE IF EXISTS links;
                DROP TABLE IF EXISTS kv;
                CREATE TABLE kv(k TEXT PRIMARY KEY, v TEXT);
                CREATE TABLE files(path TEXT PRIMARY KEY, lpath TEXT UNIQUE, key TEXT UNIQUE, ros_id TEXT,
                    record TEXT, kind TEXT, title TEXT, tags TEXT, status TEXT, mtime_ns INTEGER, size INTEGER,
                    sha TEXT, gen_hash TEXT, user_hash TEXT, applied TEXT, extra TEXT);
                CREATE INDEX files_id ON files(ros_id);
                CREATE INDEX files_title ON files(title COLLATE NOCASE);
                CREATE INDEX files_kind ON files(kind, record);
                CREATE TABLE hubs(prefix TEXT PRIMARY KEY, record TEXT, hub TEXT);
                CREATE TABLE links(src TEXT, target TEXT, embed INTEGER);
                CREATE INDEX links_src ON links(src);
                CREATE INDEX links_target ON links(target);""")
            self.db.execute("INSERT INTO kv VALUES('schema', ?)", (self.SCHEMA,))
            self.db.commit()

    def kv(self, k):
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def set_kv(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))

    def cursor(self, record: str):
        v = self.kv("cursor:" + record)
        return json.loads(v) if v else None

    def set_cursor(self, record: str, cursor: dict):
        self.set_kv("cursor:" + record, json.dumps(cursor))

    def by_path(self, path: str):
        return self.db.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()

    def by_key(self, key: str):
        return self.db.execute("SELECT * FROM files WHERE key=?", (key,)).fetchone()

    def under(self, prefix: str):
        return self.db.execute("SELECT * FROM files WHERE path LIKE ? ESCAPE '\\'",
                               (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%",)).fetchall()

    def upsert(self, **row):
        row.setdefault("lpath", row["path"].lower())
        old = self.by_path(row["path"])
        if row.get("key"):  # a key lives at one path: a moved note takes its row with it
            self.db.execute("DELETE FROM files WHERE key=? AND path!=?", (row["key"], row["path"]))
        merged = {**(dict(old) if old else {}), **row}
        cols = ("path", "lpath", "key", "ros_id", "record", "kind", "title", "tags", "status", "mtime_ns", "size",
                "sha", "gen_hash", "user_hash", "applied", "extra")
        self.db.execute(f"INSERT OR REPLACE INTO files({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        [merged.get(c) for c in cols])

    def delete(self, path: str):
        self.db.execute("DELETE FROM files WHERE path=?", (path,))
        self.db.execute("DELETE FROM links WHERE src=?", (path,))

    def reserve(self, key: str, record: str, ros_id: str, kind: str, folder: str, title: str, ext: str = ".md") -> str:
        """The path a note lives at: the one it has, or a new one from its title, with a short suffix on a collision.
        Reserved in the manifest so every link to it resolves before it is written."""
        row = self.by_key(key)
        if row:
            return row["path"]
        name = safe_name(title)
        path = f"{folder}/{name}{ext}"
        if self.db.execute("SELECT 1 FROM files WHERE lpath=?", (path.lower(),)).fetchone():
            path = f"{folder}/{name[:100]} {hashlib.sha256(key.encode()).hexdigest()[:4]}{ext}"
        self.upsert(path=path, key=key, ros_id=ros_id, record=record, kind=kind, title=title, status="planned")
        return path

    def set_links(self, src: str, targets: list[tuple[str, int]]):
        self.db.execute("DELETE FROM links WHERE src=?", (src,))
        self.db.executemany("INSERT INTO links VALUES(?,?,?)", [(src, t, e) for t, e in targets])

    def set_hub(self, prefix: str, record: str, hub: str):
        self.db.execute("INSERT OR REPLACE INTO hubs VALUES(?,?,?)", (prefix, record, hub))

    def hub_for(self, rel: str):
        best = None
        for h in self.db.execute("SELECT * FROM hubs"):
            if rel.startswith(h["prefix"] + "/") and (best is None or len(h["prefix"]) > len(best["prefix"])):
                best = h
        return best


@contextmanager
def opened(vault: Path, dry_run: bool = False):
    mf = Manifest(vault)
    try:
        yield mf
        mf.db.rollback() if dry_run else mf.db.commit()
    except BaseException:
        mf.db.rollback()
        raise
    finally:
        mf.db.close()


# ---- settings and the context of one sync -------------------------------------------------------------------------
def vault_path() -> Path:
    st = home.settings()
    if not st.get("vault"):
        found = home.detect_vaults()
        raise ValueError("no Obsidian vault is set: run `ros vault_set --path <your vault>`"
                         + (f" (found: {', '.join(v['path'] for v in found[:3])})" if found else ""))
    vault = Path(st["vault"]).expanduser()
    if not vault.is_dir():
        raise ValueError(f"the vault folder {vault} does not exist: run `ros vault_set --path <your vault>`")
    return vault


def configured() -> bool:
    try:
        vault_path()
        return True
    except ValueError:
        return False


def set_vault(path: str | None = None, root: str | None = None) -> dict:
    """Choose the vault (and the folder inside it) and say what the first sync would create."""
    found = home.detect_vaults()
    if path is None and root is None and not home.settings().get("vault"):
        if len(found) == 1:
            path = found[0]["path"]
        else:
            return {"vault": None, "detected": found, "note": "pass --path <your vault>" + (
                " (more than one vault was found)" if found else " (no Obsidian vault was found)")}
    fields = {}
    if path is not None:
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"{p} is not a folder")
        fields["vault"] = str(p)
    if root is not None:
        fields["vault_root"] = root
    st = home.set_settings(**fields)
    return {"vault": st["vault"], "vault_root": st["vault_root"], "detected": found}


class Ctx:
    """Everything one pass needs: the record, where it writes, the manifest and the lazily built learning state."""

    def __init__(self, rec: Record, mf: Manifest, vault: Path, as_of: date | None = None, dry: bool = False):
        self.rec, self.mf, self.vault, self.dry = rec, mf, vault, dry
        st = home.settings()
        self.root_name = st["vault_root"]
        self.port = st["portal_port"]
        self.as_of = as_of or date.today()
        self.record = rec.root.name
        self.cfg = home.config(rec.root)
        self.role = self.cfg.get("role") or "unlinked"
        self.is_user = self.role == "user"
        self.hub_id = None if self.is_user else (self.cfg.get("project") or f"project:{self.record}")
        node = (rec.node(self.hub_id) or {}) if self.hub_id else {}
        self.hub_title = "Knowledge" if self.is_user else (node.get("title") or self.record)
        top = "Knowledge" if self.is_user else ("Courses" if self.hub_id.startswith("course:") else "Projects")
        self.hub_folder = top if self.is_user else f"{top}/{safe_name(self.hub_title)}"
        self._learning: graph.Learning | None = None
        self.cap_ids: list[str] | None = None
        self.state: dict = rec.fold("vault.state", ("note.dismiss", "note.release"), dict, _state_step)

    # paths are relative to the vault, with forward slashes
    def rel(self, folder: str, name: str = "") -> str:
        return "/".join(p for p in (self.root_name, folder, name) if p)

    def key(self, ros_id: str) -> str:
        return f"{self.record}|{ros_id}"

    def portal(self, node_id: str) -> str:
        return f"http://127.0.0.1:{self.port}/#node/{quote(node_id, safe=':')}?r={quote(self.record)}"

    def obsidian(self, rel: str) -> str:
        return f"obsidian://open?vault={quote(self.vault.name)}&file={quote(rel[:-3] if rel.endswith('.md') else rel)}"

    def learning(self) -> graph.Learning:
        if self._learning is None:
            self._learning = graph.Learning(self.rec, self.as_of, within=self.cap_ids)
        return self._learning

    def link(self, ros_id: str, title: str | None = None, record: str | None = None) -> str:
        """A wikilink to a note by its record id, or its title as plain text when it has no note (yet)."""
        row = self.mf.by_key(f"{record or self.record}|{ros_id}")
        label = title or (row["title"] if row else ros_id.split(":", 1)[-1])
        return wikilink(row["path"], label) if row else label


def _state_step(out: dict, e: dict) -> None:
    out[e["subject"]] = {"state": "dismissed" if e["type"] == "note.dismiss" else "released", "event": e["id"],
                         "action": e["data"].get("action")}


# ---- the note types -----------------------------------------------------------------------------------------------
@dataclass
class Stub:
    """A note that will exist: its record id, kind, folder and title (enough to reserve and link to its path) and the
    function that builds its properties, tags and body."""
    id: str
    kind: str
    folder: str
    title: str
    build: Callable[["Ctx", "Stub"], tuple[dict, list, str]]
    structural: bool = False


def _props(ctx: Ctx, stub: Stub, **more) -> dict:
    return {"ros_id": stub.id, "ros_record": ctx.record, "ros_kind": stub.kind, "ros_portal": ctx.portal(stub.id),
            "title": stub.title, **more}


def _up(ctx: Ctx) -> str:
    return ctx.link("moc:knowledge" if ctx.is_user else ctx.hub_id, ctx.hub_title)


def _group(ctx: Ctx, nid: str) -> str:
    for e in ctx.rec.edges(src=nid, type="part-of"):
        node = ctx.rec.node(e["dst"])
        return (node or {}).get("title") or e["dst"].split(":", 1)[-1]
    return "General"


def _cap_stub(ctx: Ctx, nid: str) -> Stub | None:
    n = ctx.rec.node(nid)
    if not n or n["type"] != "capability":
        return None
    folder = ctx.rel(f"{ctx.hub_folder}/Capabilities" if not ctx.is_user
                     else f"Knowledge/Capabilities/{safe_name(_group(ctx, nid))}")
    return Stub(nid, "capability", folder, n.get("title") or nid.split(":", 1)[-1], _build_cap)


def _build_cap(ctx: Ctx, stub: Stub):
    nid, learning = stub.id, ctx.learning()
    if nid not in learning.caps:
        raise KeyError(nid)
    v = learning.view(nid)
    structure = graph.structure(ctx.rec)
    req = [ctx.link(p) for p in v["prerequisites"]]
    unlocks = [ctx.link(d) for d in structure.dependents(nid)][:60]
    if v["ready"]:
        head = "ready to learn" if v["state"] in ("unknown", "learning") else "ready"
    else:
        head = "needs " + ", ".join(ctx.link(b) for b in v["blocked_by"])
    body = [f"# {stub.title}", "", f"> [!info] State", f"> **{v['state']}** · next review "
            f"{v['next_review'] or '—'} · {head}", "", "## Requires", "", *([f"- {x}" for x in req] or ["Nothing."]),
            "", "## Unlocks", "", *([f"- {x}" for x in unlocks] or ["Nothing yet."]), ""]
    prompts = [i for i in ctx.rec.items(nid) if not i.get("defence")][:5]
    if prompts:
        body += ["## Self-test", "", "Try to answer before you open the portal; it checks your answer and schedules "
                 "your review.", ""]
        for it in prompts:
            body.append(f"> [!question] {it['prompt'].strip()}")
            for i, o in enumerate(it.get("options") or []):
                body.append(f"> {chr(97 + i)}. {o}")
            body.append("")
    body += [f"[Open in the portal]({ctx.portal(nid)})"]
    props = _props(ctx, stub, aliases=[nid.split(":", 1)[-1]], state=v["state"], next_review=v["next_review"] or "",
                   up=_up(ctx), prerequisites=req, unlocks=unlocks[:20])
    if (ctx.rec.node(nid) or {}).get("path"):
        props["legacy"] = (ctx.rec.node(nid) or {}).get("path")
    return props, ["ros/capability", f"state/{v['state']}", *([f"course/{safe_name(ctx.hub_title).lower().replace(' ', '-')}"]
                                                             if not ctx.is_user else [])], "\n".join(body)


GENERIC = {"question": "Questions", "hypothesis": "Hypotheses", "experiment": "Experiments", "paper": "Papers"}


def _generic_stub(ctx: Ctx, nid: str) -> Stub | None:
    n = ctx.rec.node(nid)
    if not n or n["type"] not in GENERIC:
        return None
    title = n.get("title") or n.get("text") or nid.split(":", 1)[-1]
    return Stub(nid, n["type"], ctx.rel(f"{ctx.hub_folder}/{GENERIC[n['type']]}"), str(title)[:80], _build_generic)


def _build_generic(ctx: Ctx, stub: Stub):
    n = ctx.rec.node(stub.id) or {}
    status = n.get("authorization") or n.get("status") or ""
    body = [f"# {stub.title}", ""]
    if n.get("text") and n.get("text") != stub.title:
        body += [str(n["text"]), ""]
    facts = {k: v for k, v in n.items() if k not in ("id", "type", "title", "text", "path") and isinstance(
        v, (str, int, float, bool)) and v != ""}
    if facts:
        body += ["| Field | Value |", "|---|---|", *[f"| {k} | {str(v).replace('|', '/')} |" for k, v in sorted(facts.items())], ""]
    out = [e for e in ctx.rec.edges(src=stub.id) if e["type"] != "part-of"][:40]
    inc = [e for e in ctx.rec.edges(dst=stub.id) if e["type"] != "part-of"][:40]
    if out or inc:
        body += ["## Related", ""]
        body += [f"- {e['type']} → {ctx.link(e['dst'])}" for e in out]
        body += [f"- {ctx.link(e['src'])} → {e['type']} this" for e in inc]
        body.append("")
    body.append(f"[Open in the portal]({ctx.portal(stub.id)})")
    props = _props(ctx, stub, up=_up(ctx), status=str(status))
    return props, [f"ros/{stub.kind}"], "\n".join(body)


def _claim_stub(ctx: Ctx, nid: str) -> Stub | None:
    n = ctx.rec.node(nid)
    if not n or n["type"] != "claim":
        return None
    return Stub(nid, "claim", ctx.rel(f"{ctx.hub_folder}/Claims"), (n.get("text") or nid.split(":", 1)[-1])[:80],
                _build_claim)


def _build_claim(ctx: Ctx, stub: Stub):
    st = research.status(ctx.rec, stub.id)
    n = ctx.rec.node(stub.id) or {}
    body = [f"# {n.get('text') or stub.id}", "", f"> [!info] {st['verdict']}", f"> Ownership **{st['ownership']}** · "
            f"assurance **{st['assurance']}** ({'met' if st['assurance_met'] else 'not met'})", "",
            "## Audit chain", "", "| Step | Verdict | By | Notes |", "|---|---|---|---|"]
    for step in st["required"]:
        v = st["verdicts"].get(step)
        body.append(f"| {step} | {v['verdict'] if v else 'waiting'} | {v['by'] if v else '—'} | "
                    f"{(v.get('notes') or '').replace('|', '/').replace(chr(10), ' ') if v else ''} |")
    if n.get("artifacts") or n.get("citations") or n.get("numbers"):
        body += ["", "## Evidence", ""]
        body += [f"- file `{a}`" for a in n.get("artifacts", [])] + [f"- cites {c}" for c in n.get("citations", [])]
        body += [f"- number {x.get('value')} in `{x.get('file')}`" for x in n.get("numbers", [])]
    sup = graph.support(ctx.rec, stub.id)
    for rel, rows in sup.items():
        if rows:
            body += ["", f"## {rel.capitalize()}", ""] + [f"- {ctx.link(r['id'])}" for r in rows]
    decisions = ctx.rec.events(type="decision", subject=stub.id)
    if decisions:
        d = decisions[-1]
        body += ["", "## Decision", "", f"**{d['data'].get('outcome')}** by {d['actor']} on {d['ts'][:10]}: "
                 f"{d['data'].get('rationale', '')}"]
    body += ["", f"[Open in the portal]({ctx.portal(stub.id)})"]
    return _props(ctx, stub, up=_up(ctx), verdict=st["verdict"], ownership=st["ownership"],
                  assurance=st["assurance"]), ["ros/claim", f"verdict/{st['verdict'].lower()}"], "\n".join(body)


def _lesson_stubs(ctx: Ctx, only: set[str] | None = None) -> list[Stub]:
    out = []
    for e in ctx.rec.events(type="lesson.close"):
        lid = e["subject"]
        if (only is not None and lid not in only) or lid.startswith("bundle:"):
            continue
        node = ctx.rec.node(lid) or {}
        started = next(iter(ctx.rec.events(type="lesson.start", subject=lid, limit=1)), None)
        day = (started or e)["ts"][:10]
        title = node.get("title") or (started or {}).get("data", {}).get("title") or lid.split(":", 1)[-1]
        out.append(Stub(lid, "lesson", ctx.rel(f"{ctx.hub_folder}/Lessons"), f"{day} {title}", _build_lesson))
    return out


def _build_lesson(ctx: Ctx, stub: Stub):
    closed = (ctx.rec.events(type="lesson.close", subject=stub.id) or [{"ts": ""}])[-1]["ts"]
    taught = sorted({e["subject"] for e in ctx.rec.events(lesson=stub.id) if e["type"] == "teach"})
    props = _props(ctx, stub, up=_up(ctx), started=stub.title[:10], closed=closed[:10],
                   capabilities=[ctx.link(c) for c in taught][:40])
    return props, ["ros/lesson"], lesson_log(ctx.rec, stub.id).rstrip() + f"\n\n[Open in the portal]({ctx.portal(stub.id)})"


def _decision_stubs(ctx: Ctx, only: set[str] | None = None) -> list[Stub]:
    out = []
    for e in ctx.rec.events(type="decision"):
        rid = "decision:" + e["id"][:12]
        if only is not None and rid not in only:
            continue
        key = e["subject"].split(":", 1)[-1]
        out.append(Stub(rid, "decision", ctx.rel(f"{ctx.hub_folder}/Decisions"), f"{e['ts'][:10]} {key}",
                        lambda c, s, e=e: _build_decision(c, s, e)))
    return out


def _build_decision(ctx: Ctx, stub: Stub, e: dict):
    d = e["data"]
    props = _props(ctx, stub, up=_up(ctx), outcome=str(d.get("outcome")), by=e["actor"], date=e["ts"][:10],
                   subject=ctx.link(e["subject"]))
    body = [f"# Decision: {e['subject'].split(':', 1)[-1]}", "", f"**{d.get('outcome')}** by {e['actor']} on "
            f"{e['ts'][:10]}.", "", d.get("rationale", ""), "", f"Subject: {ctx.link(e['subject'])}", "",
            f"[Open in the portal]({ctx.portal(e['subject'])})"]
    return props, ["ros/decision", f"decision/{d.get('outcome')}"], "\n".join(body)


def _decision_log_stub(ctx: Ctx) -> Stub:
    return Stub("decision-log:" + (ctx.hub_id or "knowledge"), "decision-log", ctx.rel(ctx.hub_folder),
                "Decision Log", _build_decision_log, structural=True)


def _build_decision_log(ctx: Ctx, stub: Stub):
    rows = ["| Date | Subject | Outcome | By | Why |", "|---|---|---|---|---|"]
    for e in reversed(ctx.rec.events(type="decision")):
        d = e["data"]
        rows.append(f"| {e['ts'][:10]} | {ctx.link(e['subject'])} | {d.get('outcome')} | {e['actor']} | "
                    f"{str(d.get('rationale', '')).replace('|', '/').replace(chr(10), ' ')[:140]} |")
    body = ["# Decision Log", "", "Every decision you made, newest first. The reason is the one you wrote.", "",
            *(rows if len(rows) > 2 else ["No decisions yet."])]
    return _props(ctx, stub, up=_up(ctx)), ["ros/decision-log"], "\n".join(body)


def _hub_stub(ctx: Ctx) -> Stub:
    if ctx.is_user:
        return Stub("moc:knowledge", "moc", ctx.rel("Knowledge"), "Knowledge", _build_moc, structural=True)
    return Stub(ctx.hub_id, ctx.hub_id.split(":")[0], ctx.rel(ctx.hub_folder), ctx.hub_title, _build_moc,
                structural=True)


def _build_moc(ctx: Ctx, stub: Stub):
    rec = ctx.rec
    body = [f"# {ctx.hub_title}", "", f"[Open in the portal]({ctx.portal(stub.id)}) · drop files into "
            f"`{ctx.rel(ctx.hub_folder, 'Inbox')}` and they are read in automatically.", ""]
    props = _props(ctx, stub, up=wikilink(ctx.rel("Home"), "Home"))
    states: dict[str, int] = {}
    caps = rec.nodes(type="capability")
    if caps:
        learning = ctx.learning() if ctx.cap_ids is None else graph.Learning(rec, ctx.as_of)
        rows = []
        for key in learning.order(learning.caps):
            v = learning.view(key)
            states[v["state"]] = states.get(v["state"], 0) + 1
            if len(rows) < 400:
                rows.append(f"| {ctx.link(key)} | {v['state']} | {v['next_review'] or '—'} |")
        body += [f"## Capabilities ({len(learning.caps)})", "", " · ".join(f"{k} {n}" for k, n in sorted(states.items())),
                 "", "| Capability | State | Next review |", "|---|---|---|", *rows]
        if len(learning.caps) > 400:
            body.append(f"\nand {len(learning.caps) - 400} more: see the Knowledge base view.")
        body.append("")
    sections = (("Lessons", "lesson"), ("Questions", "question"), ("Hypotheses", "hypothesis"),
                ("Experiments", "experiment"), ("Claims", "claim"), ("Papers", "paper"), ("Handouts", "handout"))
    for title, ntype in sections:
        if ntype == "lesson":
            ids = [e["subject"] for e in rec.events(type="lesson.close") if not e["subject"].startswith("bundle:")]
        else:
            ids = [n["id"] for n in rec.nodes(type=ntype)]
        if ids:
            body += [f"## {title} ({len(ids)})", "", *[f"- {ctx.link(i)}" for i in ids[:100]], ""]
    srcs = rec.nodes(type="source")
    if srcs:
        body += [f"## Sources ({len(srcs)})", ""]
        for s in srcs[:60]:
            where = s.get("vault_path") or ""
            body.append(f"- {wikilink(where, s.get('title')) if where.endswith('.md') else s.get('title') or s['id']}"
                        + (f" — {s['path']}" if s.get("path") and not where else ""))
        body.append("")
    body.append(f"See also: {ctx.link('decision-log:' + (ctx.hub_id or 'knowledge'), 'Decision Log')}")
    if ctx.is_user:
        goals = rec.nodes(type="goal")
        if goals:
            body += ["", "## Goals", "", *[f"- {g.get('title') or g['id']}" + (f" (by {g['deadline']})" if g.get("deadline")
                                                                                else "") for g in goals]]
    if not ctx.is_user:
        ctx.mf.set_hub(ctx.rel(ctx.hub_folder), ctx.record, ctx.hub_id)
        if not ctx.dry:
            (ctx.vault / ctx.rel(ctx.hub_folder, "Inbox")).mkdir(parents=True, exist_ok=True)
    return props, [f"ros/{stub.kind}"], "\n".join(body)


def _home_stub(ctx: Ctx) -> Stub:
    return Stub("home", "home", ctx.root_name, "Home", _build_home, structural=True)


def _build_home(ctx: Ctx, stub: Stub):
    rec = ctx.rec
    hubs = _hub_records(rec) if ctx.is_user else {}
    body = ["# Research OS", "", f"[Open the portal](http://127.0.0.1:{ctx.port}/) · drop anything into "
            f"`{ctx.rel('Inbox')}`: it is read in and linked automatically.", ""]
    for title, kind in (("Courses", "course"), ("Projects", "project")):
        rows = []
        for n in rec.nodes(type=kind):
            record = hubs.get(n["id"]) or (None if ctx.is_user else ctx.record)
            rows.append("- " + (ctx.link(n["id"], n.get("title"), record) if record else (n.get("title") or n["id"])))
        if not ctx.is_user and not rows and ctx.hub_id and ctx.hub_id.startswith(kind + ":"):
            rows.append("- " + ctx.link(ctx.hub_id, ctx.hub_title))  # a record not linked to a user-wide one
        if rows:
            body += [f"## {title}", "", *rows, ""]
    body += ["## Knowledge", "", f"- {ctx.link('moc:knowledge', 'Knowledge', ctx.record)}",
             f"- Reviews: `{ctx.rel('Reviews')}` (one note a day)", "- Views: " + ", ".join(
                 wikilink(ctx.rel("Bases", n), n[:-5]) for n in sorted(BASES)), ""]
    ctx.mf.set_hub(ctx.rel("Inbox"), ctx.record, "")
    if not ctx.dry:
        (ctx.vault / ctx.rel("Inbox")).mkdir(parents=True, exist_ok=True)
    return _props(ctx, stub), ["ros/home"], "\n".join(body)


def _hub_records(user_rec: Record) -> dict[str, str]:
    """Hub id -> the record that holds it, for every record linked to this user-wide one."""
    out = {}
    for name in home.projects():
        cfg = home.config(home.home() / "projects" / name)
        if cfg.get("role") == "project" and cfg.get("user") == user_rec.root.name and cfg.get("project"):
            out[cfg["project"]] = name
    return out


NODE_STUBS = {"capability": _cap_stub, "claim": _claim_stub, **{t: _generic_stub for t in GENERIC}}


def _stubs(ctx: Ctx, ids: set[str] | None, structural: bool = True) -> list[Stub]:
    """The notes to write: every one (``ids`` None) or only those whose ids are named."""
    out: list[Stub] = []
    if ids is None:
        for t, make in NODE_STUBS.items():
            out += [s for n in ctx.rec.nodes(type=t) if (s := make(ctx, n["id"]))]
    else:
        for nid in ids:
            make = NODE_STUBS.get(nid.split(":", 1)[0])
            if make and (s := make(ctx, nid)):
                out.append(s)
    out += _lesson_stubs(ctx, None if ids is None else ids)
    out += _decision_stubs(ctx, None if ids is None else ids)
    if structural:
        out += [_hub_stub(ctx), _decision_log_stub(ctx)]
        if ctx.is_user:
            out.append(_home_stub(ctx))
    return out


SYNC_EVENTS = ("lesson.close", "decision", "verdict", "retrieval", "grade", "approval", "note.release",
               "note.dismiss")


def _affected(ctx: Ctx, ch: dict) -> set[str]:
    """The record ids whose notes may have changed, from the tails of the logs."""
    rec, ids = ctx.rec, set(ch["nodes"]) | set(ch["edges"])
    for nid in list(ids):  # a changed edge also changes the notes at its ends and their neighbours' lists
        if nid.startswith("capability:"):
            ids |= set(graph.structure(rec).prerequisites(nid)) | set(graph.structure(rec).dependents(nid))
    for e in ch["events"]:
        t, subject = e["type"], e["subject"]
        if t == "lesson.close":
            ids.add(subject)
        elif t == "decision":
            ids.add("decision:" + e["id"][:12])
            ids.add(subject)
        elif t in ("verdict", "approval"):
            ids.add(subject)
        elif t == "retrieval":
            ids.add(subject)
        elif t == "grade":
            ids |= set(c for c in ((rec.item(subject) or {}).get("concepts") or []) if c.startswith("capability:"))
        elif t in ("note.release", "note.dismiss"):
            ids.add(subject)
    return ids


# ---- emitting one note --------------------------------------------------------------------------------------------
def _emit(ctx: Ctx, stub: Stub, report: dict, dry_run: bool) -> None:
    mf = ctx.mf
    key = ctx.key(stub.id)
    row = mf.by_key(key)
    path = row["path"] if row else mf.reserve(key, ctx.record, stub.id, stub.kind, stub.folder, stub.title)
    row = mf.by_key(key)
    state = ctx.state.get(stub.id)
    released = bool(state and state["state"] == "released" and state["event"] != row["applied"])
    if row["status"] == "dismissed" and not stub.structural and not released:
        report["dismissed"].append(path)
        return
    if row["status"] == "user-edited" and not released:
        report["kept_edited"].append(path)
        return
    props, tags, body = stub.build(ctx, stub)
    note = Note(stub.id, stub.kind, stub.folder, stub.title, props, body, tuple(tags), stub.structural,
                "draft-unreviewed" if (props.get("ros_kind") == "handout") else "generated")
    target = ctx.vault / path
    fm = {**props, "tags": list(tags)}
    h = gen_hash(fm, body)
    if row["gen_hash"] == h and target.exists() and not released and row["status"] in ("generated", "reviewed"):
        report["unchanged"] += 1
        _links(mf, path, body)
        return
    existing = parse_note(target.read_text(encoding="utf-8", errors="replace")) if target.exists() else None
    user_text = existing.user if existing and existing.has_fm else None
    user_tags = [t for t in _as_list(existing.fm.get("tags")) if not t.startswith("ros/")] if existing else []
    extra = [ln for k, lines in (existing.raw if existing else {}).items()
             if k not in OWNED and not k.startswith("ros_") and k != "tags" for ln in lines]
    if released and existing and existing.region is not None and existing.region.strip() != body.strip():
        kept = f"\n\n### Kept from your edit ({date.today().isoformat()})\n\n{existing.region.strip()}\n"
        user_text = (user_text or MY_NOTES + "\n").rstrip("\n") + kept
    existed = target.exists()
    report["updated" if existed else "created"].append(path)
    if dry_run:
        return
    text = render_note(note, user_text, user_tags, extra)
    data = text.encode("utf-8")
    _atomic(target, data)
    st = target.stat()
    mf.upsert(path=path, key=key, ros_id=stub.id, record=ctx.record, kind=stub.kind, title=stub.title,
              tags=json.dumps(list(tags)), status="generated",
              mtime_ns=st.st_mtime_ns, size=st.st_size, sha=_sha(data), gen_hash=h,
              user_hash=_short(parse_note(text).user), applied=(state or {}).get("event") if released else row["applied"],
              extra=json.dumps({"pdf": props.get("pdf") or "", "structural": stub.structural}))
    _links(mf, path, body, props)


WIKILINK = re.compile(r"(!?)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def _links(mf: Manifest, path: str, body: str, props: dict | None = None) -> None:
    text = body + " " + " ".join(v for x in (props or {}).values() for v in (x if isinstance(x, list) else [x])
                                 if isinstance(v, str))
    found = sorted({(m.group(2).strip(), 1 if m.group(1) else 0) for m in WIKILINK.finditer(text)})
    mf.set_links(path, found)


# ---- scan: what the person did in the vault -----------------------------------------------------------------------
def _walk(base: Path):
    stack = [base]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        yield e
                except OSError:
                    continue


def scan(ctx: Ctx, apply: bool = True) -> dict:
    """Compare the files under the root with the manifest. With ``apply`` it records what the person did (events,
    source nodes, ingest tasks) and updates the manifest; without it, only reports. Cost: one stat per file, a read
    only for files whose size or time changed."""
    mf, rec = ctx.mf, ctx.rec
    base_rel = ctx.root_name
    base = ctx.vault / base_rel
    out = {"annotate": [], "edited": [], "found": [], "moved": [], "missing": [], "dismissed": [], "reviewed": [],
           "v11": [], "files": 0}
    if not base.is_dir():
        return out
    rows = {r["path"]: r for r in mf.under(base_rel)}
    seen: set[str] = set()
    for e in _walk(base):
        rel = Path(e.path).relative_to(ctx.vault).as_posix()
        seen.add(rel)
        out["files"] += 1
        kind = FILES.get(Path(e.name).suffix.lower())
        if kind is None:
            continue
        st = e.stat()
        row = rows.get(rel)
        if row and row["mtime_ns"] == st.st_mtime_ns and row["size"] == st.st_size:
            continue
        if row and row["record"] not in (None, "", ctx.record):
            continue  # another record's note: its own scan handles it
        _look(ctx, rel, Path(e.path), kind, st, row, out, apply)
    for rel, row in rows.items():
        if rel in seen or row["record"] not in (None, "", ctx.record) or row["status"] in ("planned", "dismissed"):
            continue
        _gone(ctx, rel, row, out, apply)
    return out


def _mine(ctx: Ctx, rel: str) -> bool:
    """Whether a file nobody wrote belongs to this record: the hub whose folder holds it, else the user-wide record."""
    hub = ctx.mf.hub_for(rel)
    return hub["record"] == ctx.record if hub is not None else ctx.is_user


def _look(ctx: Ctx, rel: str, abs_path: Path, kind: str, st, row, out: dict, apply: bool) -> None:
    mf, rec = ctx.mf, ctx.rec
    data = abs_path.read_bytes()
    sha = _sha(data)
    base = dict(path=rel, mtime_ns=st.st_mtime_ns, size=st.st_size, sha=sha)
    if kind != "note":
        if row and row["key"]:  # a file we placed (a handout PDF, a canvas, a base)
            if sha != row["sha"] and row["status"] != "user-edited":
                out["edited"].append(rel)
                if apply:
                    mf.upsert(**base, status="user-edited")
            elif apply:
                mf.upsert(**base)
            return
        if row and row["sha"] == sha:
            if apply:
                mf.upsert(**base)
            return
        if not _mine(ctx, rel):
            return
        if kind in ("pdf", "image"):
            _found(ctx, rel, kind, sha, st.st_size, out, apply)
            if apply:
                mf.upsert(**base, record=ctx.record, kind=kind, status="foreign", title=Path(rel).stem)
        elif apply:
            mf.upsert(**base, record=ctx.record, kind=kind, status="foreign", title=Path(rel).stem)
        return
    p = parse_note(data.decode("utf-8", errors="replace"))
    rid, rrec = p.fm.get("ros_id"), p.fm.get("ros_record")
    if rid and rrec:
        if rrec != ctx.record:
            return
        key = f"{rrec}|{rid}"
        old = mf.by_key(key)
        if old and old["path"] != rel:
            out["moved"].append(f"{old['path']} -> {rel}")
        h = gen_hash(p.fm, p.region)
        edited = p.region is None or h != p.fm.get("ros_hash")
        status = "user-edited" if edited else ("reviewed" if p.fm.get("ros_status") == "reviewed" else "generated")
        uh = _short(p.user)
        prev = old or row
        if edited and (not prev or prev["status"] != "user-edited" or prev["sha"] != sha):
            out["edited"].append(rel)
        if uh != SCAFFOLD_HASH and (not prev or prev["user_hash"] != uh):
            out["annotate"].append(rel)
        if status == "reviewed" and (not prev or prev["status"] != "reviewed"):
            out["reviewed"].append(rel)
        if apply:
            if uh != SCAFFOLD_HASH and (not prev or prev["user_hash"] != uh):
                _annotate(ctx, rid, rel, sha, p.user, "my-notes", prev["sha"] if prev else None)
            if edited and (not prev or prev["status"] != "user-edited" or prev["sha"] != sha):
                _annotate(ctx, rid, rel, sha, p.region or "", "region-edit", prev["sha"] if prev else None)
            if status == "reviewed" and (not prev or prev["status"] != "reviewed"):
                rec.append("note.reviewed", rid, {"path": rel, "sha": sha}, actor="vault",
                           id=event_id("note.reviewed", f"{key}|{sha}"))
            mf.upsert(**base, key=key, ros_id=rid, record=rrec, kind=p.fm.get("ros_kind") or "note",
                      title=p.fm.get("title") or Path(rel).stem, tags=json.dumps(_as_list(p.fm.get("tags"))),
                      status=status, gen_hash=p.fm.get("ros_hash") if edited else h, user_hash=uh,
                      applied=prev["applied"] if prev else None, extra=(prev["extra"] if prev else None))
            _links(mf, rel, (p.region or "") + "\n" + p.user, p.fm)
        return
    if V11_MARK in p.fm and (Path(rel).parts[1:2] == (ctx.record,) or (Path(rel).parts[1:2] != () and _mine(ctx, rel))):  # a note the version 1.1 export wrote: replaced by the new layout when it is unedited
        out["v11"].append(rel)
        if apply:
            mf.upsert(**base, record=ctx.record, kind="v1.1", status="v1.1", title=Path(rel).stem)
        return
    if not _mine(ctx, rel):
        return
    if row and row["sha"] == sha:
        if apply:
            mf.upsert(**base)
        return
    title = p.fm.get("title") or (re.search(r"^#\s+(.+)$", p.user or data.decode("utf-8", "replace"), re.M) or [None, Path(rel).stem])[1]
    _found(ctx, rel, "note", sha, st.st_size, out, apply, title=str(title).strip())
    if apply:
        mf.upsert(**base, record=ctx.record, kind="note", status="foreign", title=str(title).strip())
        _links(mf, rel, p.user, p.fm)


def _annotate(ctx: Ctx, rid: str, rel: str, sha: str, text: str, kind: str, prev: str | None) -> None:
    ctx.rec.append("note.annotate", rid, {"path": rel, "sha": sha, "prev_sha": prev, "kind": kind,
                                          "text": text[:20000], "truncated": len(text) > 20000}, actor="vault",
                   id=event_id("note.annotate", f"{ctx.key(rid)}|{kind}|{sha}"))


def _found(ctx: Ctx, rel: str, kind: str, sha: str, size: int, out: dict, apply: bool, title: str | None = None) -> None:
    """A file the person added: attribute it to the hub whose folder holds it, and read it in."""
    mf, rec = ctx.mf, ctx.rec
    hub = mf.hub_for(rel)
    if hub is not None and hub["record"] != ctx.record:
        return  # another record's folder: that record reads it in
    if hub is None and not ctx.is_user:
        return  # a file outside every hub belongs to the user-wide record
    hub_id = (hub["hub"] if hub else "") or None
    out["found"].append(rel)
    if not apply:
        return
    nid = "source:vault-" + hashlib.sha256(rel.encode()).hexdigest()[:10]
    node = {"id": nid, "type": "source", "title": title or Path(rel).stem, "kind": "note" if kind == "note" else "file",
            "vault_path": rel, "path": str(ctx.vault / rel), "sha": sha, "origin": "inbox"}
    if rec.node(nid) != node:
        rec.put_nodes([node])
    if hub_id and rec.node(hub_id) and not rec.edges(src=nid, type="about", dst=hub_id):
        rec.put_edge(nid, "about", hub_id)
    rec.append("inbox.found", rel, {"path": rel, "sha": sha, "size": size, "kind": kind, "hub": hub_id, "source": nid},
               actor="vault", id=event_id("inbox.found", f"{ctx.record}|{rel}|{sha}"))
    if kind != "note":
        tasks.open_task(rec, "ingest", nid, f"A new {kind} arrived in the vault at {rel}: read it, say what it is "
                        "(paper, syllabus, slides, textbook, problem set, handwritten notes) and link it to what it "
                        "is about.", data={"path": str(ctx.vault / rel), "vault_path": rel, "hub": hub_id,
                                           "file_kind": kind}, key=sha)


def _gone(ctx: Ctx, rel: str, row, out: dict, apply: bool) -> None:
    extra = json.loads(row["extra"] or "{}")
    if row["status"] in ("foreign", "v1.1") or not row["key"]:
        if apply:
            ctx.mf.delete(rel)
        return
    if extra.get("structural") or row["kind"] in ("pdf", "base", "canvas"):
        out["missing"].append(rel)  # regenerated (or placed again) the next time it is written
        if apply:
            ctx.mf.upsert(path=rel, status="planned", gen_hash=None, sha=None, mtime_ns=None, size=None)
        return
    out["dismissed"].append(rel)
    if apply:
        ctx.rec.append("note.dismiss", row["ros_id"], {"path": rel}, actor="vault",
                       id=event_id("note.dismiss", f"{row['key']}|{row['sha']}"))
        ctx.mf.upsert(path=rel, status="dismissed")


# ---- static files: bases and canvases -----------------------------------------------------------------------------
BASES = {
    "Knowledge.base": ("ros/capability", "Capabilities", ["file.name", "state", "next_review", "up"], "next_review"),
    "Research.base": ("ros/claim", "Claims", ["file.name", "verdict", "ownership", "assurance", "up"], "verdict"),
    "Handouts.base": ("ros/handout", "Handouts", ["file.name", "handout_kind", "status", "pdf", "up"], "file.name"),
    "Inbox.base": ("ros/lesson", "Lessons", ["file.name", "started", "closed", "up"], "started"),
    "Reviews.base": ("ros/decision", "Decisions", ["file.name", "outcome", "by", "date", "subject"], "date"),
}


def _base_text(tag: str, name: str, columns: list[str], sort: str) -> str:
    return "\n".join(["filters:", "  and:", f'    - file.hasTag("{tag}")', "views:", "  - type: table",
                      f"    name: {name}", "    order:", *[f"      - {c}" for c in columns], "    sort:",
                      f"      - property: {sort}", "        direction: ASC", ""])


def _static(ctx: Ctx, rid: str, kind: str, rel: str, text: str, report: dict, dry_run: bool, once: bool = False) -> None:
    mf = ctx.mf
    key = ctx.key(rid)
    row = mf.by_key(key)
    data = text.encode("utf-8")
    sha = _sha(data)
    target = ctx.vault / rel
    if row and row["status"] == "user-edited":
        return
    if row and target.exists() and (once or row["sha"] == sha):
        return
    if target.exists() and not row:  # someone else's file at this name: leave it
        return
    (report["updated"] if row and row["status"] != "planned" else report["created"]).append(rel)
    if dry_run:
        return
    _atomic(target, data)
    st = target.stat()
    mf.upsert(path=rel, key=key, ros_id=rid, record=ctx.record, kind=kind, title=Path(rel).stem, status="generated",
              mtime_ns=st.st_mtime_ns, size=st.st_size, sha=sha, gen_hash=sha, user_hash=None,
              extra=json.dumps({"structural": True}))


def _structure(ctx: Ctx, report: dict, dry_run: bool) -> None:
    for name, (tag, view, cols, sort) in BASES.items():
        _static(ctx, "base:" + name, "base", ctx.rel("Bases", name), _base_text(tag, view, cols, sort), report, dry_run)


def _canvas(ctx: Ctx, report: dict, dry_run: bool) -> None:
    """A prerequisite map (course) or research lanes (project), seeded once and then yours."""
    rows = ctx.mf.db.execute("SELECT * FROM files WHERE record=? AND kind IN ('capability','question','hypothesis',"
                             "'experiment','claim','paper') AND status IN ('generated','reviewed','user-edited') "
                             "LIMIT 200", (ctx.record,)).fetchall()
    if not rows or ctx.is_user:
        return
    lanes = ["question", "hypothesis", "experiment", "claim", "paper", "capability"]
    layer: dict[str, int] = {}
    if any(r["kind"] == "capability" for r in rows):
        s = graph.structure(ctx.rec)
        for r in rows:
            if r["kind"] == "capability":
                layer[r["ros_id"]] = len(s.ancestors([r["ros_id"]]))
    nodes, edges, counts, ids = [], [], {}, {}
    for r in rows:
        col = layer.get(r["ros_id"]) if r["kind"] == "capability" else lanes.index(r["kind"])
        row_n = counts.get((r["kind"], col), 0)
        counts[(r["kind"], col)] = row_n + 1
        y, x = row_n * 90, (col or 0) * 340
        cid = hashlib.sha256(r["ros_id"].encode()).hexdigest()[:16]
        ids[r["ros_id"]] = cid
        nodes.append({"id": cid, "type": "file", "file": r["path"], "x": x, "y": y, "width": 300, "height": 70})
    for e in ctx.rec.edges(type="requires"):
        if e["src"] in ids and e["dst"] in ids:
            edges.append({"id": hashlib.sha256((e["src"] + e["dst"]).encode()).hexdigest()[:16], "fromNode": ids[e["dst"]],
                          "fromSide": "right", "toNode": ids[e["src"]], "toSide": "left"})
    rel = ctx.rel(ctx.hub_folder, f"{safe_name(ctx.hub_title)}.canvas")
    _static(ctx, "canvas:" + (ctx.hub_id or "knowledge"), "canvas", rel,
            json.dumps({"nodes": nodes, "edges": edges}, indent=1), report, dry_run, once=True)


# ---- sync ---------------------------------------------------------------------------------------------------------
def sync(rec: Record, dry_run: bool = False, full: bool = False, as_of: date | None = None) -> dict:
    """Bring the vault in step with this record: first what the person did there (scan), then the notes the record
    changed. Incremental after the first pass: the cost follows the change. ``dry_run`` writes nothing and says what
    would be."""
    vault = vault_path()
    report = {"vault": str(vault), "folder": home.settings()["vault_root"], "dry_run": dry_run, "created": [],
              "updated": [], "unchanged": 0, "kept_edited": [], "dismissed": [], "annotations": 0, "found": 0,
              "v1_1_replaced": 0, "kind": "full"}
    with opened(vault, dry_run) as mf:
        ctx = Ctx(rec, mf, vault, as_of, dry_run)
        if not dry_run:
            (vault / ctx.root_name).mkdir(parents=True, exist_ok=True)
        found = scan(ctx, apply=not dry_run)
        report["annotations"], report["found"] = len(found["annotate"]), len(found["found"])
        ch = rec.since(mf.cursor(ctx.record), types=SYNC_EVENTS)
        ids = None if (ch["full"] or full or found["missing"]) else _affected(ctx, ch)
        report["kind"] = "full" if ids is None else "incremental"
        touch = ids is None or bool(ch["nodes"] or ch["edges"] or ch["events"] or found["found"])
        stubs = _stubs(ctx, ids, structural=touch) if (ids is None or ids or touch) else []
        ctx.cap_ids = None if ids is None else [s.id for s in stubs if s.kind == "capability"]
        for s in stubs:  # reserve every path first, so a link to a note written later still resolves
            mf.reserve(ctx.key(s.id), ctx.record, s.id, s.kind, s.folder, s.title)
        for s in sorted(stubs, key=lambda s: (s.structural, s.id)):
            try:
                _emit(ctx, s, report, dry_run)
            except KeyError:  # a node deleted since the list was made
                continue
        if not ctx.is_user and touch:
            _emit_home(ctx, report, dry_run)
        elif ctx.is_user:
            _structure(ctx, report, dry_run)
        _canvas(ctx, report, dry_run)
        if not dry_run:
            report["v1_1_replaced"] = _drop_v11(ctx, vault)
            mf.set_cursor(ctx.record, ch["cursor"])
    for k in ("created", "updated", "kept_edited", "dismissed"):
        report[k + "_count"] = len(report[k])
        report[k] = report[k][:SHOWN]
    return report


def _emit_home(ctx: Ctx, report: dict, dry_run: bool) -> None:
    """``Home.md`` is the user-wide record's note; a project that syncs first still gets a Home to point at."""
    urec = None
    if ctx.cfg.get("user"):
        try:
            urec = context.user_record(ctx.cfg)
        except (ValueError, KeyError):
            pass
    hctx = Ctx(urec, ctx.mf, ctx.vault, ctx.as_of, dry_run) if urec is not None else ctx
    stub = _home_stub(hctx)
    ctx.mf.reserve(hctx.key(stub.id), hctx.record, stub.id, stub.kind, stub.folder, stub.title)
    _emit(hctx, stub, report, dry_run)
    _structure(hctx, report, dry_run)  # the bases Home links to


def _drop_v11(ctx: Ctx, vault: Path) -> int:
    """Version 1.1's exported notes sit under the root without ids. Unedited ones (their hash still matches what was
    written) are replaced by the new layout; edited ones are left."""
    n = 0
    for r in ctx.mf.db.execute("SELECT path FROM files WHERE status='v1.1'").fetchall():
        p = vault / r["path"]
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            ctx.mf.delete(r["path"])
            continue
        m = re.match(rf"---\n{V11_MARK}: ([0-9a-f]{{16}})\n---\n(.*)\Z", text, re.S)
        if m and hashlib.sha256(m.group(2).rstrip().encode("utf-8")).hexdigest()[:16] == m.group(1):
            p.unlink()
            ctx.mf.delete(r["path"])
            n += 1
            for d in (p.parent, p.parent.parent):  # tidy folders the old export emptied
                try:
                    d.rmdir()
                except OSError:
                    break
    return n


# ---- placing files, finding notes ---------------------------------------------------------------------------------
def put_note(rec: Record, stub: Stub, dry_run: bool = False) -> dict:
    """Write one note on behalf of another module (a handout): same ownership, hashing and flow-back as any note."""
    vault = vault_path()
    report = {"created": [], "updated": [], "unchanged": 0, "kept_edited": [], "dismissed": []}
    with opened(vault, dry_run) as mf:
        ctx = Ctx(rec, mf, vault)
        mf.reserve(ctx.key(stub.id), ctx.record, stub.id, stub.kind, stub.folder, stub.title)
        _emit(ctx, stub, report, dry_run)
        row = mf.by_key(ctx.key(stub.id))
        return {"path": row["path"], **report}


def place(rec: Record, src: Path, rid: str, hub_slug: str, title: str) -> str:
    """Copy a file (a handout PDF) into ``Attachments/<hub>/``. A copy the person changed since (an annotation plugin)
    is kept and the new one is saved beside it as ``v2``, ``v3``. Returns the path relative to the vault."""
    vault = vault_path()
    data = Path(src).read_bytes()
    sha = _sha(data)
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault)
        key = ctx.key("file:" + rid)
        row = mf.by_key(key)
        folder = ctx.rel("Attachments", safe_name(hub_slug))
        if row and row["status"] != "planned" and (vault / row["path"]).exists():
            if row["sha"] == sha:
                return row["path"]
            on_disk = _sha((vault / row["path"]).read_bytes())
            if on_disk == row["sha"]:  # untouched by the person: replace in place
                _atomic(vault / row["path"], data)
                st = (vault / row["path"]).stat()
                mf.upsert(path=row["path"], mtime_ns=st.st_mtime_ns, size=st.st_size, sha=sha, gen_hash=sha)
                return row["path"]
            version = 2
            while mf.db.execute("SELECT 1 FROM files WHERE lpath=?", (f"{folder}/{safe_name(title)} v{version}.pdf".lower(),)).fetchone():
                version += 1
            title = f"{title} v{version}"
            mf.db.execute("UPDATE files SET key=NULL WHERE key=?", (key,))
        rel = mf.reserve(key, ctx.record, "file:" + rid, "pdf", folder, title, ".pdf")
        _atomic(vault / rel, data)
        st = (vault / rel).stat()
        mf.upsert(path=rel, key=key, status="generated", mtime_ns=st.st_mtime_ns, size=st.st_size, sha=sha,
                  gen_hash=sha, extra=json.dumps({"structural": False}))
        return rel


def locate(rec: Record, rid: str) -> dict | None:
    """Where a note (and its PDF) is, by record id: path, absolute path, Obsidian link, portal link."""
    vault = vault_path()
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault)
        row = mf.by_key(ctx.key(rid))
        if not row:
            return None
        out = {"id": rid, "path": row["path"], "absolute": str(vault / row["path"]),
               "obsidian": ctx.obsidian(row["path"]), "portal": ctx.portal(rid), "status": row["status"]}
        pdf = json.loads(row["extra"] or "{}").get("pdf")
        if pdf:
            out["pdf"] = pdf
        return out


def find(rec: Record, q: str | None = None, kind: str | None = None, id: str | None = None, tag: str | None = None,
         limit: int = 20) -> list[dict]:
    """Search the manifest (indexed): notes of this record by title text, kind, record id or tag."""
    vault = vault_path()
    sql, args = "SELECT * FROM files WHERE key IS NOT NULL AND record=?", [rec.root.name]
    if q:
        sql += " AND title LIKE ? ESCAPE '\\'"
        args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if id:
        sql += " AND ros_id=?"
        args.append(id)
    if tag:
        sql += " AND tags LIKE ?"
        args.append(f'%"{tag}"%')
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault)
        rows = mf.db.execute(sql + " ORDER BY title LIMIT ?", (*args, max(1, min(int(limit), 200)))).fetchall()
        return [{"id": r["ros_id"], "title": r["title"], "kind": r["kind"], "path": r["path"], "status": r["status"],
                 "obsidian": ctx.obsidian(r["path"]), "portal": ctx.portal(r["ros_id"])} for r in rows]


# ---- status and resolving drift -----------------------------------------------------------------------------------
def status(rec: Record, deep: bool = False) -> dict:
    """What is out of step, without changing anything: notes the person edited, deleted or added, links that do not
    resolve, attachments nothing links to. ``deep`` also counts every file under the root."""
    vault = vault_path()
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault)
        found = scan(ctx, apply=False)
        counts = {r[0]: r[1] for r in mf.db.execute(
            "SELECT status, COUNT(*) FROM files WHERE record=? GROUP BY status", (ctx.record,))}
        broken = _broken_links(ctx)
        orphans = [r["path"] for r in mf.db.execute(
            "SELECT path FROM files WHERE record=? AND kind IN ('pdf','image') AND key IS NOT NULL AND status!='planned'",
            (ctx.record,)) if not mf.db.execute("SELECT 1 FROM links WHERE target IN (?,?,?) LIMIT 1", (
                r["path"], r["path"][:-4], Path(r["path"]).name)).fetchone()]
        out = {"vault": str(vault), "folder": ctx.root_name, "notes": counts, "pending": {
            "edited": found["edited"][:SHOWN], "my_notes_changed": found["annotate"][:SHOWN],
            "deleted": found["dismissed"][:SHOWN], "added": found["found"][:SHOWN], "moved": found["moved"][:SHOWN],
            "regenerate": found["missing"][:SHOWN]},
            "pinned": [r["path"] for r in mf.db.execute("SELECT path FROM files WHERE record=? AND status='user-edited'",
                                                        (ctx.record,))][:SHOWN],
            "dismissed": [r["path"] for r in mf.db.execute("SELECT path FROM files WHERE record=? AND status='dismissed'",
                                                           (ctx.record,))][:SHOWN],
            "broken_links": broken[:SHOWN], "orphan_attachments": orphans[:SHOWN],
            "in_sync": not any(found[k] for k in ("edited", "annotate", "dismissed", "found", "moved", "missing"))
            and not broken}
        if deep:
            out["files_under_root"] = found["files"]
        return out


def _broken_links(ctx: Ctx) -> list[dict]:
    mf, out = ctx.mf, []
    targets = [r[0] for r in mf.db.execute(
        "SELECT DISTINCT l.target FROM links l JOIN files f ON f.path=l.src WHERE f.record=?", (ctx.record,))]
    for t in targets:
        cand = t if t.lower().endswith((".md", ".pdf", ".png", ".svg", ".canvas", ".base")) else t + ".md"
        if mf.db.execute("SELECT 1 FROM files WHERE lpath IN (?,?)", (t.lower(), cand.lower())).fetchone() \
                or (ctx.vault / cand).exists() or (ctx.vault / t).exists() \
                or mf.db.execute("SELECT 1 FROM files WHERE title=? COLLATE NOCASE", (Path(t).stem,)).fetchone():
            continue
        src = mf.db.execute("SELECT src FROM links WHERE target=? LIMIT 3", (t,)).fetchall()
        out.append({"link": t, "from": [s[0] for s in src]})
    return out


def resolve(rec: Record, target: str, action: str) -> dict:
    """Act on drift: ``update`` lets the record rewrite a note the person edited (their edit is kept under "My notes"),
    ``restore`` brings back a deleted one, ``reviewed`` marks an agent-written note as read and accepted."""
    if action not in ("update", "restore", "reviewed"):
        raise ValueError("action is update, restore or reviewed")
    vault = vault_path()
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault)
        row = mf.by_key(ctx.key(target)) or mf.by_path(target)
        if not row or row["record"] != ctx.record or not row["key"]:
            raise KeyError(f"no note {target}")
        rid = row["ros_id"]
        if action == "reviewed":
            p = vault / row["path"]
            text = p.read_text(encoding="utf-8")
            if re.search(r"^ros_status: \w[\w-]*$", text, re.M):
                text = re.sub(r"^ros_status: \w[\w-]*$", "ros_status: reviewed", text, count=1, flags=re.M)
                _atomic(p, text.encode("utf-8"))
            st = p.stat()
            mf.upsert(path=row["path"], status="reviewed", mtime_ns=st.st_mtime_ns, size=st.st_size,
                      sha=_sha(text.encode("utf-8")))
            rec.append("note.reviewed", rid, {"path": row["path"], "sha": _sha(text.encode())}, actor="vault",
                       id=event_id("note.reviewed", f"{row['key']}|{_sha(text.encode())}"))
            return {"id": rid, "path": row["path"], "status": "reviewed"}
        if action == "update" and row["status"] != "user-edited":
            raise ValueError(f"{row['path']} is not pinned: it follows the record already")
        if action == "restore" and row["status"] != "dismissed":
            raise ValueError(f"{row['path']} was not deleted")
        rec.append("note.release", rid, {"path": row["path"], "action": action}, actor="vault")
    sync(rec)
    return {"id": rid, "path": row["path"], "released": action}


# ---- the daily review note ----------------------------------------------------------------------------------------
def review_note(rec: Record, day: date | None = None) -> dict:
    """Today's review note: what is due, what was learned, decided and added. Written once a day, and again if the
    day's facts change; the record, not the note, is the source."""
    day = day or date.today()
    vault = vault_path()
    with opened(vault) as mf:
        ctx = Ctx(rec, mf, vault, day)
        iso = day.isoformat()
        sid = f"review:{iso}"
        title = iso if ctx.is_user else f"{iso} {ctx.record}"
        stub = Stub(sid, "review", ctx.rel("Reviews"), title, lambda c, s: _build_review(c, s, iso))
        mf.reserve(ctx.key(sid), ctx.record, sid, "review", stub.folder, title)
        report = {"created": [], "updated": [], "unchanged": 0, "kept_edited": [], "dismissed": []}
        _emit(ctx, stub, report, False)
        return {"path": mf.by_key(ctx.key(sid))["path"], **{k: report[k] for k in ("created", "updated")}}


def _build_review(ctx: Ctx, stub: Stub, iso: str):
    rec = ctx.rec
    since = iso + "T00:00:00Z"
    learning = graph.Learning(rec, ctx.as_of)
    due = learning.due()
    learned = [e for e in rec.events(type="lesson.close", since=since) if not e["subject"].startswith("bundle:")]
    decided = rec.events(type="decision", since=since)
    found = rec.events(type="inbox.found", since=since)
    notes = rec.events(type="note.annotate", since=since)
    done = [t for t in tasks.tasks(rec, state="done") if (t.get("done") or "") >= since and t["kind"] != "job"]
    body = [f"# Review {iso}", "", f"[Open the portal]({ctx.portal('review')})", "",
            f"## Due now ({len(due)})", "", *([f"- {ctx.link(d['id'])} — due {d['next_review']}" for d in due[:30]]
                                              or ["Nothing is due."]), ""]
    for head, rows in (("Learned today", [f"- {ctx.link(e['subject'])}" for e in learned]),
                       ("Decided today", [f"- {ctx.link(e['subject'])}: **{e['data'].get('outcome')}** — "
                                          f"{e['data'].get('rationale', '')[:120]}" for e in decided]),
                       ("New in the vault", [f"- `{e['data'].get('path')}`" for e in found]),
                       ("Your notes that flowed back", [f"- `{e['data'].get('path')}`" for e in notes]),
                       ("Agents finished", [f"- {t['kind']}: {t.get('brief', '')[:100]}" for t in done[:20]])):
        if rows:
            body += [f"## {head}", "", *rows, ""]
    return _props(ctx, stub, date=iso), ["ros/review"], "\n".join(body)
