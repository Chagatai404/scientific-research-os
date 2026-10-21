"""The record: an append-only event log, immutable content-addressed items, a typed graph, and a rebuildable index.

Layout under one record root (the caller always passes the root; nothing here picks a location)::

    events.jsonl            one fact per line: id, ts, actor, type, subject, data[, source]
    items/<sha256>.json     an immutable question; its name is the hash of its canonical content
    graph/nodes.jsonl       node versions, last write wins by id; {"deleted": true} is a tombstone
    graph/edges.jsonl       edge versions keyed by (src, type, dst), same rules
    index.sqlite            cache built from the files above; safe to delete at any time

Rules that keep it robust:

* Files are only ever appended to. One call writes whole lines, then flushes and fsyncs, under a short OS file lock.
* Readers skip a truncated last line or an unparsable line and report it; they never crash on a damaged tail.
* The index remembers how many bytes of each file it has consumed and a hash of the last few kilobytes before that
  point. If they changed (the file was rewritten or truncated) or the schema version moved, the index is dropped and
  rebuilt from scratch. Reads first check whether the files grew, so another process's appends are always seen.
* Event ids are unique. Importers derive them from their source (``event_id(source, key)``), so importing twice adds
  nothing. Imported events keep their original timestamps, so the log is not in time order; queries sort by ``ts``.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

SCHEMA_VERSION = 2
# How much of each log's consumed end is hashed to notice a rewrite: constant work, however long the log grows.
PREFIX_WINDOW = 4096
MAX_PROBLEMS = 200
ITEM_KINDS = {"choice", "numeric", "free"}
# Node ids are "<type>:<key>", so a concept and a capability can share a key without colliding.
NODE_TYPES = {"domain", "subject", "concept", "capability", "course", "goal", "project", "block", "paper", "question",
              "hypothesis", "claim", "experiment", "decision", "code-symbol", "source", "lesson"}
EDGE_TYPES = {"requires", "teaches", "tests", "supports", "invalidates", "implements", "cites", "supersedes",
              "part-of", "about", "applied-in", "addresses", "decides", "relates"}
# Item fields that carry no content and are left out of the hash.
ITEM_UNHASHED = {"id", "meta"}


def canonical(obj) -> bytes:
    """Canonical JSON bytes: sorted keys, no whitespace, UTF-8. The basis of every content hash."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def item_hash(item: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in item.items() if k not in ITEM_UNHASHED})).hexdigest()


def event_id(source: str, key: str) -> str:
    """A deterministic id for an imported fact, so re-importing the same source is a no-op."""
    return "imp-" + hashlib.sha256(f"{source}\x00{key}".encode("utf-8")).hexdigest()[:24]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_item(item: dict) -> list[str]:
    """Problems that keep an item out of the record. Checked when it is written, never during a lesson."""
    problems = []
    kind = item.get("kind")
    if kind not in ITEM_KINDS:
        problems.append(f"kind must be one of {sorted(ITEM_KINDS)}, got {kind!r}")
    if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
        problems.append("prompt must be non-empty text")
    if kind == "choice":
        options = item.get("options")
        if not isinstance(options, list) or len(options) < 2:
            problems.append("a choice item needs at least two options")
        elif item.get("answer") not in range(len(options)):
            problems.append("a choice item's answer must be the index of one option")
    if kind == "numeric":
        if not isinstance(item.get("answer"), (int, float)) or isinstance(item.get("answer"), bool):
            problems.append("a numeric item's answer must be a number")
        tol = item.get("tolerance", 0)
        if not isinstance(tol, (int, float)) or tol < 0:
            problems.append("tolerance must be a non-negative number")
    if kind == "free" and "answer" in item:
        problems.append("a free item has a hidden rubric, not an answer")
    if "concepts" in item and not (isinstance(item["concepts"], list) and all(isinstance(c, str) for c in item["concepts"])):
        problems.append("concepts must be a list of node ids")
    sup = item.get("supersedes")
    if sup is not None and not (isinstance(sup, str) and len(sup) == 64):
        problems.append("supersedes must be the hash of another item")
    return problems


@dataclass
class ReadResult:
    records: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    end: int = 0  # bytes consumed: the end of the last complete line


def read_jsonl(path: Path, start: int = 0) -> ReadResult:
    """Read complete JSON lines from byte ``start``. A final line without its newline is left unread (it may be a
    write in progress or a torn write); a line that does not parse is skipped and reported."""
    out = ReadResult(end=start)
    if not path.exists():
        return out
    with path.open("rb") as f:
        f.seek(start)
        data = f.read()
    pos = 0
    while True:
        nl = data.find(b"\n", pos)
        if nl == -1:
            if pos < len(data):
                out.problems.append(f"{path.name}: incomplete last line at byte {start + pos} left unread")
            break
        line = data[pos:nl].strip()
        if line:
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    raise ValueError("not an object")
                out.records.append(rec)
            except ValueError as exc:
                out.problems.append(f"{path.name}: unreadable line at byte {start + pos} skipped ({exc})")
        pos = nl + 1
    out.end = start + pos
    return out


@contextmanager
def _file_lock(path: Path):
    """An exclusive OS lock held only while lines are appended. Not a lease: it dies with the process."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fh:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _append_lines(path: Path, records: list[dict]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(canonical(r) + b"\n" for r in records)
    with path.open("a+b") as f:
        # Under the lock, a last line without its newline is a crashed write. Close it off so the new lines stay
        # whole; the fragment becomes one unreadable line that readers report and skip.
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                payload = b"\n" + payload
        f.seek(0, os.SEEK_END)
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())


_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE events(seq INTEGER PRIMARY KEY, id TEXT UNIQUE, ts TEXT, actor TEXT, type TEXT, subject TEXT,
                    lesson TEXT, data TEXT, source TEXT);
CREATE INDEX events_type ON events(type, ts);
CREATE INDEX events_subject ON events(subject, ts);
CREATE INDEX events_lesson ON events(lesson, ts);
CREATE TABLE nodes(id TEXT PRIMARY KEY, type TEXT, data TEXT);
CREATE INDEX nodes_type ON nodes(type);
CREATE TABLE edges(src TEXT, type TEXT, dst TEXT, data TEXT, PRIMARY KEY(src, type, dst));
CREATE INDEX edges_dst ON edges(dst, type);
CREATE TABLE items(id TEXT PRIMARY KEY, kind TEXT, difficulty REAL, supersedes TEXT, data TEXT);
CREATE TABLE item_concepts(item TEXT, concept TEXT, PRIMARY KEY(item, concept));
CREATE INDEX item_concepts_concept ON item_concepts(concept);
"""


class Record:
    """One project's or course's record. All writes go through here; all reads go through the index."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.events_path = self.root / "events.jsonl"
        self.items_dir = self.root / "items"
        self.nodes_path = self.root / "graph" / "nodes.jsonl"
        self.edges_path = self.root / "graph" / "edges.jsonl"
        self.index_path = self.root / "index.sqlite"
        self.lock_path = self.root / ".write.lock"
        self.problems: list[str] = []
        self._db: sqlite3.Connection | None = None
        self._seen: tuple = ((), "")  # log sizes and items stamp the index has consumed, kept in memory for sync()
        self._generation = 0  # bumped whenever the index changes; derived views are cached per generation
        self._derived: dict[str, tuple[int, object]] = {}
        self._folds: dict[str, list] = {}  # name -> [index epoch, last seq folded, state]
        self._held = 0  # inside reading(): already synced, nested reads skip the check

    # ---- writing -------------------------------------------------------------------------------------------
    def append(self, type: str, subject: str, data: dict | None = None, *, actor: str = "system",
               ts: str | None = None, id: str | None = None, source: str | None = None) -> dict:
        ev = make_event(type, subject, data, actor=actor, ts=ts, id=id, source=source)
        self.append_many([ev])
        return ev

    def append_many(self, events: list[dict]) -> int:
        """Append events whose ids are not yet in the record. Returns how many were written."""
        for ev in events:
            missing = {"id", "ts", "actor", "type", "subject", "data"} - ev.keys()
            if missing:
                raise ValueError(f"event lacks {sorted(missing)}: {ev!r}")
        with _file_lock(self.lock_path):
            db = self.index()
            seen: set[str] = set()
            fresh = []
            for ev in events:
                if ev["id"] in seen or db.execute("SELECT 1 FROM events WHERE id=?", (ev["id"],)).fetchone():
                    continue
                seen.add(ev["id"])
                fresh.append(ev)
            _append_lines(self.events_path, fresh)
            self.refresh()
        return len(fresh)

    def put_item(self, item: dict) -> str:
        """Store an immutable item and return its hash. Writing the same content again is a no-op."""
        problems = validate_item(item)
        if problems:
            raise ValueError("; ".join(problems))
        h = item_hash(item)
        path = self.items_dir / f"{h}.json"
        if not path.exists():
            self.items_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            tmp.write_bytes(canonical({**item, "id": h}))
            os.replace(tmp, path)
        db = self.index()
        with db:
            self._index_item(h, {**item, "id": h})
        self._generation += 1
        return h

    def put_node(self, id: str, type: str, **data) -> None:
        self.put_nodes([{"id": id, "type": type, **data}])

    def put_nodes(self, nodes: list[dict]) -> None:
        for n in nodes:
            if n.get("type") not in NODE_TYPES and not n.get("deleted"):
                raise ValueError(f"unknown node type {n.get('type')!r} for {n.get('id')!r}")
        with _file_lock(self.lock_path):
            _append_lines(self.nodes_path, nodes)
            self.refresh()

    def put_edge(self, src: str, type: str, dst: str, **data) -> None:
        self.put_edges([{"src": src, "type": type, "dst": dst, **data}])

    def put_edges(self, edges: list[dict]) -> None:
        for e in edges:
            if e.get("type") not in EDGE_TYPES:
                raise ValueError(f"unknown edge type {e.get('type')!r}")
        with _file_lock(self.lock_path):
            _append_lines(self.edges_path, edges)
            self.refresh()

    def delete_node(self, id: str) -> None:
        self.put_nodes([{"id": id, "deleted": True}])

    def delete_edge(self, src: str, type: str, dst: str) -> None:
        self.put_edges([{"src": src, "type": type, "dst": dst, "deleted": True}])

    # ---- index ---------------------------------------------------------------------------------------------
    def index(self) -> sqlite3.Connection:
        if self._db is None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.index_path, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self.refresh()
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def rebuild(self) -> None:
        """Drop the index and build it again from the files."""
        self.close()
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = Path(str(self.index_path) + suffix)
            if p.exists():
                p.unlink()
        self.index()

    def refresh(self) -> None:
        """Bring the index up to date with the files, incrementally when their consumed prefixes are unchanged."""
        db = self._db
        if db is None:
            self.index()
            return
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone():
            db.executescript(_SCHEMA)
            db.execute("INSERT INTO meta VALUES('schema', ?)", (str(SCHEMA_VERSION),))
            db.execute("INSERT INTO meta VALUES('epoch', ?)", (uuid.uuid4().hex,))  # new on every rebuild
            db.commit()
        if self._meta("schema") != str(SCHEMA_VERSION) or not all(
                self._prefix_ok(name, path) for name, path in self._logs()):
            self.close()
            self.index_path.unlink()
            self.index()
            return
        found: list[str] = []
        self._generation += 1
        with db:
            self._consume("events", self.events_path, self._index_event, found)
            self._consume("nodes", self.nodes_path, self._index_node, found)
            self._consume("edges", self.edges_path, self._index_edge, found)
            self._index_items(found)
            # A damaged line is kept on the list for good; an unfinished last line only while it is unfinished.
            lasting = [p for p in found if "incomplete last line" not in p]
            if lasting:
                kept = json.loads(self._meta("problems") or "[]")
                self._set_meta("problems", json.dumps((kept + lasting)[-MAX_PROBLEMS:], ensure_ascii=False))
        self.problems = json.loads(self._meta("problems") or "[]") + [p for p in found if p not in self.problems
                                                                        and "incomplete last line" in p]
        self._seen = (tuple(int(self._meta(f"{name}.end") or 0) for name, _ in self._logs()),
                      self._meta("items.stamp") or "")

    def sync(self) -> None:
        """Refresh only if a log grew or the items folder changed since the index last read them. Costs four
        stat calls and no query, so every read can afford it; inside ``reading()`` it is done once."""
        if self._db is None:
            self.index()
            return
        if self._held:
            return
        sizes = tuple(path.stat().st_size if path.exists() else 0 for _, path in self._logs())
        if sizes != self._seen[0] or self._items_stamp() != self._seen[1]:
            if all(size == int(self._meta(f"{name}.end") or 0) or self._only_torn_tail(name, path, size)
                   for (name, path), size in zip(self._logs(), sizes)) \
                    and self._items_stamp() == (self._meta("items.stamp") or ""):
                self._seen = (sizes, self._items_stamp())
                return
            self.refresh()

    @contextmanager
    def reading(self):
        """One consistent view for a whole operation: sync once, then every read inside uses the index as it is.
        The record's own writes still update the index as they happen."""
        self.sync()
        self._held += 1
        try:
            yield self
        finally:
            self._held -= 1

    def derived(self, name: str, build):
        """``build(self)``, computed once per state of the index and reused until anything is written or read in
        from the files. For views derived from the whole record (the answer log, every item by id)."""
        self.sync()
        hit = self._derived.get(name)
        if hit and hit[0] == self._generation:
            return hit[1]
        value = build(self)
        self._derived[name] = (self._generation, value)
        return value

    def fold(self, name: str, types: tuple[str, ...], init, step):
        """An incremental view: ``step(state, event)`` is applied to each event of ``types`` in the order the record
        received them, starting from ``init()``. Later calls apply only events added since, so the cost of a write
        does not grow with the history. Rebuilding the index starts the view again from ``init()``."""
        self.sync()
        epoch = self._meta("epoch")
        cur = self._folds.get(name)
        if cur is None or cur[0] != epoch:
            cur = [epoch, 0, init()]
        rows = self.index().execute(
            f"SELECT * FROM events WHERE seq>? AND type IN ({','.join('?' * len(types))}) ORDER BY seq",
            (cur[1], *types))
        for r in rows:
            ev = _event_row(r)
            ev["_seq"] = r["seq"]  # the order the record received it, for views that need a tiebreak
            step(cur[2], ev)
            cur[1] = r["seq"]
        self._folds[name] = cur
        return cur[2]

    def _only_torn_tail(self, name: str, path: Path, size: int) -> bool:
        """A file larger than what was consumed only by an unfinished last line needs no refresh."""
        end = int(self._meta(f"{name}.end") or 0)
        if size < end or size - end > 1 << 16:
            return False
        with path.open("rb") as f:
            f.seek(end)
            return b"\n" not in f.read()

    def _logs(self):
        return (("events", self.events_path), ("nodes", self.nodes_path), ("edges", self.edges_path))

    def _meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO meta VALUES(?, ?)", (key, value))

    @staticmethod
    def _hash_prefix(path: Path, end: int) -> str:
        """The hash of the window of bytes just before ``end``: enough to notice a rewrite or truncation."""
        start = max(0, end - PREFIX_WINDOW)
        with path.open("rb") as f:
            f.seek(start)
            return hashlib.sha256(f.read(end - start)).hexdigest()

    def _prefix_ok(self, name: str, path: Path) -> bool:
        end = int(self._meta(f"{name}.end") or 0)
        if end == 0:
            return True
        if not path.exists() or path.stat().st_size < end:
            return False
        return self._hash_prefix(path, end) == self._meta(f"{name}.hash")

    def _consume(self, name: str, path: Path, handle, found: list[str]) -> None:
        start = int(self._meta(f"{name}.end") or 0)
        res = read_jsonl(path, start)
        for rec in res.records:
            handle(rec)
        found.extend(res.problems)
        if res.end != start:
            self._set_meta(f"{name}.end", str(res.end))
            self._set_meta(f"{name}.hash", self._hash_prefix(path, res.end))

    def _index_event(self, ev: dict) -> None:
        data = ev.get("data") or {}
        subject = ev.get("subject")
        lesson = data.get("lesson") if isinstance(data, dict) else None
        if lesson is None and isinstance(subject, str) and subject.startswith("lesson:"):
            lesson = subject
        self._db.execute(
            "INSERT OR IGNORE INTO events(id, ts, actor, type, subject, lesson, data, source) VALUES(?,?,?,?,?,?,?,?)",
            (ev.get("id"), ev.get("ts"), ev.get("actor"), ev.get("type"), subject, lesson,
             json.dumps(data, ensure_ascii=False), ev.get("source")))

    def _index_node(self, n: dict) -> None:
        if n.get("deleted"):
            self._db.execute("DELETE FROM nodes WHERE id=?", (n["id"],))
            return
        data = {k: v for k, v in n.items() if k not in ("id", "type")}
        self._db.execute("INSERT OR REPLACE INTO nodes VALUES(?,?,?)",
                         (n["id"], n["type"], json.dumps(data, ensure_ascii=False)))

    def _index_edge(self, e: dict) -> None:
        if e.get("deleted"):
            self._db.execute("DELETE FROM edges WHERE src=? AND type=? AND dst=?", (e["src"], e["type"], e["dst"]))
            return
        data = {k: v for k, v in e.items() if k not in ("src", "type", "dst")}
        self._db.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?)",
                         (e["src"], e["type"], e["dst"], json.dumps(data, ensure_ascii=False)))

    def _items_stamp(self) -> str:
        try:
            st = self.items_dir.stat()
        except OSError:
            return ""
        return f"{st.st_mtime_ns}:{st.st_nlink}"

    def _index_items(self, found: list[str]) -> None:
        """Index item files written by another process. Skipped unless the folder changed since the last scan."""
        stamp = self._items_stamp()
        if not stamp or stamp == self._meta("items.stamp"):
            return
        known = {r[0] for r in self._db.execute("SELECT id FROM items")}
        for path in self.items_dir.glob("*.json"):
            h = path.stem
            if h in known:
                continue
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                found.append(f"items/{path.name}: unreadable ({exc})")
                continue
            if item_hash(item) != h:
                found.append(f"items/{path.name}: content does not match its hash; left out")
                continue
            self._index_item(h, item)
        self._set_meta("items.stamp", stamp)

    def _index_item(self, h: str, item: dict) -> None:
        self._db.execute("INSERT OR IGNORE INTO items VALUES(?,?,?,?,?)",
                         (h, item.get("kind"), item.get("difficulty"), item.get("supersedes"),
                          json.dumps(item, ensure_ascii=False)))
        for c in item.get("concepts") or []:
            self._db.execute("INSERT OR IGNORE INTO item_concepts VALUES(?,?)", (h, c))

    # ---- reading -------------------------------------------------------------------------------------------
    def events(self, type: str | None = None, subject: str | None = None, since: str | None = None,
               lesson: str | None = None, types: tuple[str, ...] | list[str] | None = None,
               limit: int | None = None) -> list[dict]:
        """Events in time order. ``type`` matches a type and its dotted subtypes ("lesson" matches "lesson.start");
        ``types`` matches any of several exact types; ``lesson`` keeps one lesson's events (indexed); ``limit`` keeps
        the newest ``limit`` of them (still returned oldest first)."""
        self.sync()
        sql, args = "SELECT * FROM events WHERE 1=1", []
        if type is not None:
            sql += " AND (type=? OR type LIKE ?)"
            args += [type, type + ".%"]
        if types is not None:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            args += list(types)
        if lesson is not None:
            sql += " AND lesson=?"
            args.append(lesson)
        if subject is not None:
            sql += " AND subject=?"
            args.append(subject)
        if since is not None:
            sql += " AND ts>=?"
            args.append(since)
        if limit is not None:
            rows = self.index().execute(sql + " ORDER BY ts DESC, seq DESC LIMIT ?", (*args, int(limit))).fetchall()
            return [_event_row(r) for r in reversed(rows)]
        sql += " ORDER BY ts, seq"
        return [_event_row(r) for r in self.index().execute(sql, args)]

    def event(self, id: str) -> dict | None:
        self.sync()
        row = self.index().execute("SELECT * FROM events WHERE id=?", (id,)).fetchone()
        return _event_row(row) if row else None

    def item(self, h: str) -> dict | None:
        self.sync()
        row = self.index().execute("SELECT data FROM items WHERE id=?", (h,)).fetchone()
        return json.loads(row[0]) if row else None

    def items(self, concept: str | None = None) -> list[dict]:
        self.sync()
        if concept is None:
            rows = self.index().execute("SELECT data FROM items ORDER BY difficulty, id")
        else:
            rows = self.index().execute(
                "SELECT i.data FROM items i JOIN item_concepts c ON c.item=i.id WHERE c.concept=? "
                "ORDER BY i.difficulty, i.id", (concept,))
        return [json.loads(r[0]) for r in rows]

    def items_by_id(self) -> dict[str, dict]:
        """Every item by hash, read in one query and cached until the index changes."""
        return self.derived("items_by_id", lambda r: {row[0]: json.loads(row[1]) for row in
                                                       r.index().execute("SELECT id, data FROM items")})

    def current_items(self) -> dict[str, str]:
        """Each item's newest version (following ``supersedes``), for every item, cached until the index changes."""
        def build(r):
            newer = {}
            for h, it in sorted(r.items_by_id().items()):
                if it.get("supersedes") and it["supersedes"] not in newer:
                    newer[it["supersedes"]] = h
            out = {}
            for h in r.items_by_id():
                seen, cur = {h}, h
                while cur in newer and newer[cur] not in seen:
                    cur = newer[cur]
                    seen.add(cur)
                out[h] = cur
            return out
        return self.derived("current_items", build)

    def current_item(self, h: str) -> str:
        """Follow ``supersedes`` forward to the newest version of an item."""
        self.sync()
        db = self.index()
        seen = {h}
        while True:
            row = db.execute("SELECT id FROM items WHERE supersedes=? ORDER BY id LIMIT 1", (h,)).fetchone()
            if not row or row[0] in seen:
                return h
            h = row[0]
            seen.add(h)

    def node(self, id: str) -> dict | None:
        self.sync()
        row = self.index().execute("SELECT * FROM nodes WHERE id=?", (id,)).fetchone()
        return _node_row(row) if row else None

    def nodes(self, type: str | None = None) -> list[dict]:
        self.sync()
        if type is None:
            rows = self.index().execute("SELECT * FROM nodes ORDER BY id")
        else:
            rows = self.index().execute("SELECT * FROM nodes WHERE type=? ORDER BY id", (type,))
        return [_node_row(r) for r in rows]

    def edges(self, src: str | None = None, type: str | None = None, dst: str | None = None) -> list[dict]:
        self.sync()
        sql, args = "SELECT * FROM edges WHERE 1=1", []
        for col, val in (("src", src), ("type", type), ("dst", dst)):
            if val is not None:
                sql += f" AND {col}=?"
                args.append(val)
        sql += " ORDER BY src, type, dst"
        return [{"src": r["src"], "type": r["type"], "dst": r["dst"], **json.loads(r["data"])}
                for r in self.index().execute(sql, args)]


def make_event(type: str, subject: str, data: dict | None = None, *, actor: str = "system", ts: str | None = None,
               id: str | None = None, source: str | None = None) -> dict:
    ev = {"id": id or uuid.uuid4().hex, "ts": ts or now(), "actor": actor, "type": type, "subject": subject,
          "data": data or {}}
    if source:
        ev["source"] = source
    return ev


def _event_row(r: sqlite3.Row) -> dict:
    ev = {"id": r["id"], "ts": r["ts"], "actor": r["actor"], "type": r["type"], "subject": r["subject"],
          "data": json.loads(r["data"])}
    if r["source"]:
        ev["source"] = r["source"]
    return ev


def _node_row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "type": r["type"], **json.loads(r["data"])}
