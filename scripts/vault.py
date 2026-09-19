from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import os
import time
import urllib.parse
import webbrowser

from common import load_config, expand, safe_filename

def vault_root(cfg: dict) -> Path:
    root = expand(cfg["vault"]["path"])
    if not root.exists():
        raise SystemExit(f"Vault path does not exist: {root}")
    return root

def render_template(text: str, title: str) -> str:
    now = dt.datetime.now()
    return (
        text.replace("{{title}}", title)
            .replace("{{date}}", now.strftime("%Y-%m-%d"))
            .replace("{{time}}", now.strftime("%H:%M"))
    )

class Lock:
    def __init__(self, path: Path, timeout: float = 3.0):
        self.path = path
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() - start > self.timeout:
                    raise SystemExit(f"Timed out waiting for lock: {self.path}")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

def new_note(args, cfg):
    root = vault_root(cfg)
    template_dir = root / cfg["vault"]["templates_dir"]
    template = template_dir / args.template
    if not template.exists():
        raise SystemExit(f"Template not found: {template}")

    dest = root / args.dest
    dest.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    filename = f"{date} {safe_filename(args.title)}.md"
    note = dest / filename
    if note.exists() and not args.force:
        raise SystemExit(f"Note already exists: {note}")

    text = render_template(template.read_text(encoding="utf-8"), args.title)
    note.write_text(text, encoding="utf-8")
    print(note.relative_to(root).as_posix())

def append_note(args, cfg):
    root = vault_root(cfg)
    note = root / args.note
    if not note.exists():
        raise SystemExit(f"Note not found: {note}")
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"\n### {stamp} — {args.speaker}\n\n{args.text.rstrip()}\n"
    lock = note.with_suffix(note.suffix + ".lock")
    with Lock(lock):
        with note.open("a", encoding="utf-8") as f:
            f.write(block)
    print(note.relative_to(root).as_posix())

def open_note(args, cfg):
    root = vault_root(cfg)
    note = root / args.note
    if not note.exists():
        raise SystemExit(f"Note not found: {note}")
    vault_name = root.name
    rel = note.relative_to(root).as_posix()
    uri = (
        "obsidian://open?vault="
        + urllib.parse.quote(vault_name)
        + "&file="
        + urllib.parse.quote(rel)
    )
    webbrowser.open(uri)
    print(uri)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new")
    p.add_argument("--template", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("append")
    p.add_argument("--note", required=True)
    p.add_argument("--speaker", required=True)
    p.add_argument("--text", required=True)

    p = sub.add_parser("open")
    p.add_argument("--note", required=True)

    args = ap.parse_args()
    cfg = load_config()

    if args.cmd == "new":
        new_note(args, cfg)
    elif args.cmd == "append":
        append_note(args, cfg)
    elif args.cmd == "open":
        open_note(args, cfg)

if __name__ == "__main__":
    main()
