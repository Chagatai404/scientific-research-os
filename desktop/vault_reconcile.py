"""Reversible local vault navigation cleanup; never deletes authored content.

This maintenance interface has no cloud access. Import/indexing is performed by
the canonical source API separately; generated projections are not originals.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import unquote, urlsplit


BEGIN = "<!-- research-os:navigation:begin -->"
END = "<!-- research-os:navigation:end -->"
EXCLUDED = {".obsidian", ".git", ".ros", "node_modules", "__pycache__"}
SECRET = re.compile(r"(^\.env|credential|secret|token|password|^id_(rsa|ed25519)|\.(pem|key|pfx|p12)$)", re.I)
CONTENT = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".excalidraw", ".canvas"}


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def without_navigation(text: str) -> str:
    """Return authored text, retaining ambiguous markers conservatively."""
    if text.count(BEGIN) == text.count(END) == 1:
        start, end = text.index(BEGIN), text.index(END)
        if start < end:
            return text[:start] + text[end + len(END):]
    return text


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def confined(root: Path, relative: str, *, exists=False) -> Path:
    """Reject traversal and links, including links at intermediate components."""
    posix = PurePosixPath(relative)
    if not relative or "\\" in relative or ":" in relative or posix.is_absolute() or any(p in (".", "..") for p in posix.parts):
        raise ValueError("Expected a safe vault-relative path")
    target = root
    for part in posix.parts:
        target = target / part
        if linked(target):
            raise ValueError("Vault symlinks are not migration targets")
    resolved = target.resolve(strict=exists)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Migration target leaves its root")
    return target


def files(vault: Path):
    for directory, dirs, names in os.walk(vault, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in EXCLUDED
                         and not SECRET.search(d) and not linked(base / d))
        for name in sorted(names):
            path = base / name
            if name.startswith(".") or SECRET.search(name) or linked(path):
                continue
            yield path


def inventory(vault: Path, generated="Research OS") -> dict:
    vault = vault.resolve(strict=True)
    if not vault.is_dir() or vault == Path(vault.anchor):
        raise ValueError("Select a specific existing vault")
    rows = []
    for path in files(vault):
        rel = path.relative_to(vault).as_posix()
        data = path.read_bytes()
        generated_file = rel == generated or rel.startswith(generated.rstrip("/") + "/")
        category = ("generated" if generated_file else "archive" if rel.startswith("99 Archive/")
                    else "template" if rel.startswith("90 Templates/") else "original")
        if category == "original" and path.suffix.lower() == ".md":
            text = data.decode("utf-8", errors="replace")
            if BEGIN in text and not without_navigation(text).strip():
                category = "managed_navigation"
        rows.append({"path": rel, "size": len(data), "sha256": digest(data), "category": category,
                     "eligible": category == "original" and path.suffix.lower() in CONTENT,
                     "format": path.suffix.lower() or "none"})
    return {"schema": "ros.vault-inventory.v1", "vault": str(vault), "files": rows,
            "counts": dict(Counter(row["category"] for row in rows)),
            "eligible": sum(row["eligible"] for row in rows)}


def wiki_targets(text: str):
    for match in re.finditer(r"!?\[\[([^\]\n]+)\]\]", text):
        value = match[1].split("|", 1)[0].split("#", 1)[0].strip()
        if value:
            yield value.replace("\\", "/")


def markdown_targets(text: str):
    """Local inline links/images; remote and file-system links stay external."""
    for match in re.finditer(r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+[\"'][^\n]*?[\"'])?\s*\)", text):
        value = unquote(match[1] or match[2]).split("#", 1)[0]
        if value and not urlsplit(value).scheme and not value.startswith(("/", "\\")):
            yield value.replace("\\", "/")


def links(vault: Path) -> dict:
    """Read-only link diagnostic, including aliased short Obsidian names."""
    paths = list(files(vault))
    aliases = set()
    text_by_path = {}
    for path in paths:
        rel = path.relative_to(vault).as_posix()
        aliases.update((rel.casefold(), str(PurePosixPath(rel).with_suffix("")).casefold(), path.name.casefold(), path.stem.casefold()))
        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8", errors="replace")
            text_by_path[rel] = text
            # This only extends diagnostics; it is not a general YAML parser.
            fm = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.S)
            if fm:
                alias = re.search(r"^aliases:\s*\[(.*?)\]", fm[1], re.M)
                if alias:
                    aliases.update(x.strip(" \"'").casefold() for x in alias[1].split(",") if x.strip(" \"'"))
    unresolved = []
    total = 0
    for rel, text in text_by_path.items():
        for target in wiki_targets(text):
            total += 1
            sibling = str(PurePosixPath(rel).parent / target).casefold()
            if target.casefold() not in aliases and sibling not in aliases:
                unresolved.append({"file": rel, "target": target})
        for target in markdown_targets(text):
            total += 1
            local = (vault / PurePosixPath(rel).parent / target).resolve()
            if not local.is_relative_to(vault.resolve()) or not local.is_file():
                unresolved.append({"file": rel, "target": target})
    return {"local_links": total, "unresolved": unresolved, "unresolved_count": len(unresolved)}


def managed(text: str, body: str) -> str:
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Navigation ownership markers are ambiguous")
    block = BEGIN + "\n" + body.rstrip() + "\n" + END
    if BEGIN in text:
        return text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    return text.rstrip() + "\n\n" + block + "\n"


def wikilink(path: str, label: str | None = None) -> str:
    target = str(PurePosixPath(path).with_suffix("")) if path.lower().endswith(".md") else path
    # Brackets/pipes cannot be encoded losslessly in an Obsidian wikilink.
    if any(c in target for c in "[]|\n\r"):
        return f"`{PurePosixPath(path).name.replace('`', '')}`"
    return f"[[{target}|{label or PurePosixPath(path).stem}]]"


def plan(vault: Path, generated="Research OS") -> dict:
    snap = inventory(vault, generated)
    vault = Path(snap["vault"])
    rows = {row["path"]: row for row in snap["files"]}
    changes = []

    def write(relative, body):
        path = confined(vault, relative)
        original = path.read_bytes() if path.exists() else None
        current = original.decode("utf-8") if original is not None else ""
        output = managed(current, body).encode("utf-8")
        if output != original:
            changes.append({"action": "write", "path": relative,
                            "before": digest(original) if original is not None else None,
                            "after": digest(output), "text": output.decode("utf-8")})

    project_dirs = sorted({PurePosixPath(rel).parts[1] for rel in rows
                           if rel.startswith("01 Projects/") and len(PurePosixPath(rel).parts) > 2})
    project_links = []
    for folder in project_dirs:
        prefix = f"01 Projects/{folder}/"
        local = [rel for rel, row in rows.items() if rel.startswith(prefix) and row["category"] == "original"
                 and PurePosixPath(rel).suffix.lower() in CONTENT and not rel.endswith("/Material Index.md")]
        if not local:
            continue
        index = prefix + "Material Index.md"
        notes = [p for p in local if p.lower().endswith(".md")]
        attachments = [p for p in local if not p.lower().endswith(".md")]
        body = f"# {folder}: material index\n\nOriginal notes and material in this project. Study progress and research decisions remain in Research OS.\n\n"
        body += "## Notes\n\n" + "\n".join("- " + wikilink(p) for p in notes)
        if attachments:
            body += "\n\n## Original attachments\n\n" + "\n".join("- " + wikilink(p, PurePosixPath(p).name) for p in attachments)
        write(index, body)
        project_links.append("- " + wikilink(index, folder))
    home_body = "## Organized projects and courses\n\n" + "\n".join(project_links)
    for section, title in (("02 Knowledge", "Concepts"), ("03 Sources", "Sources"), ("04 Decisions", "Decisions")):
        local = [rel for rel in rows if rel.startswith(section + "/") and rel.endswith(".md")]
        if local:
            index = section + "/Material Index.md"
            write(index, f"# {title}\n\n" + "\n".join("- " + wikilink(p) for p in local if p != index))
            home_body += "\n- " + wikilink(index, title)
    home_body += "\n\nGenerated app projections remain under Research OS; authored notes above are the canonical vault material."
    write("Home.md", home_body)

    # The current vault contains this proven empty leftover. No nonempty or
    # ambiguous note is inferred to be useless. Never archive a linked empty note.
    empty = "Handouts/STAT303 Handout Packet.pdf.md"
    if empty in rows and rows[empty]["size"] == 0:
        references = False
        for path in files(vault):
            if path.suffix.lower() == ".md" and path.relative_to(vault).as_posix() != empty:
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(PurePosixPath(t).name.casefold() in ("stat303 handout packet.pdf", "stat303 handout packet.pdf.md")
                       for t in (*wiki_targets(text), *markdown_targets(text))):
                    references = True
        if not references:
            dest = "99 Archive/Research OS cleanup/STAT303 Handout Packet.pdf.md"
            if not confined(vault, dest).exists():
                changes.append({"action": "archive", "path": empty, "destination": dest,
                                "before": rows[empty]["sha256"], "after": rows[empty]["sha256"],
                                "reason": "Unlinked, zero-byte placeholder; original preserved in archive"})
    return {"schema": "ros.vault-reconcile.v1", "inventory": snap, "before_links": links(vault), "changes": changes}


def atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ros-nav-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(proposal: dict, backup: Path) -> dict:
    if proposal.get("schema") != "ros.vault-reconcile.v1":
        raise ValueError("Unsupported reconciliation plan")
    vault = Path(proposal["inventory"]["vault"]).resolve(strict=True)
    backup = backup.resolve()
    if backup == vault or backup.is_relative_to(vault) or vault.is_relative_to(backup):
        raise ValueError("Backup must be separate from the vault")
    backup.mkdir(parents=True, exist_ok=False)
    result = {"schema": "ros.vault-reconcile-result.v1", "vault": str(vault), "backup": str(backup),
              "applied": [], "pending": None, "conflicts": [], "backup_files": 0,
              "before_links": proposal["before_links"]}
    # Snapshot each original user-content file, including generated projections;
    # backup is verified before the first source modification.
    for row in proposal["inventory"]["files"]:
        path = confined(vault, row["path"], exists=True)
        data = path.read_bytes()
        if digest(data) != row["sha256"]:
            raise ValueError("Vault changed since inventory; rebuild the plan before migration")
        dst = confined(backup, "files/" + row["path"])
        atomic(dst, data)
        if digest(dst.read_bytes()) != row["sha256"]:
            raise OSError("Backup verification failed")
        result["backup_files"] += 1
    atomic(backup / "plan.json", json.dumps(proposal, ensure_ascii=False, indent=2).encode("utf-8"))
    atomic(backup / "result.json", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
    for change in proposal["changes"]:
        src = confined(vault, change["path"])
        before = digest(src.read_bytes()) if src.exists() else None
        if before != change["before"]:
            result["conflicts"].append({"path": change["path"], "reason": "Changed during migration"})
            continue
        if change["action"] not in ("write", "archive"):
            raise ValueError("Unsupported migration action")
        if change["action"] == "write" and digest(change["text"].encode("utf-8")) != change["after"]:
            raise ValueError("Plan content hash mismatch")
        # Persist intent BEFORE the first mutation. A process interruption after
        # atomic replacement or rename can then be distinguished by exact hashes
        # from an interruption before mutation; both are safely recoverable.
        result["pending"] = {k: v for k, v in change.items() if k != "text"}
        atomic(backup / "result.json", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        if change["action"] == "archive":
            dst = confined(vault, change["destination"])
            if dst.exists():
                result["conflicts"].append({"path": change["path"], "reason": "Archive destination already exists"})
                result["pending"] = None
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        elif change["action"] == "write":
            data = change["text"].encode("utf-8")
            atomic(src, data)
        result["applied"].append({k: v for k, v in change.items() if k != "text"})
        result["pending"] = None
        atomic(backup / "result.json", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
    result["after_links"] = links(vault)
    atomic(backup / "result.json", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
    return result


def rollback(backup: Path) -> dict:
    backup = backup.resolve(strict=True)
    result = json.loads((backup / "result.json").read_text(encoding="utf-8"))
    vault = Path(result["vault"]).resolve(strict=True)
    restored, conflicts = [], []
    pending = result.get("pending")
    changes = result["applied"] + ([pending] if pending else [])
    for change in reversed(changes):
        current_rel = change.get("destination", change["path"])
        current = confined(vault, current_rel)
        original = confined(vault, change["path"])
        if change is pending:
            # Journal was durable but the source write/rename had not happened.
            # In that case the exact original state needs no restoration.
            untouched = ((not original.exists() and change["before"] is None) or
                         (original.is_file() and digest(original.read_bytes()) == change["before"]))
            if untouched and (change["action"] != "archive" or not current.exists()):
                continue
        if not current.exists() or digest(current.read_bytes()) != change["after"]:
            conflicts.append(change["path"])
            continue
        if change["action"] == "archive" and original.exists():
            conflicts.append(change["path"])
            continue
        if change["before"] is None:
            current.unlink()  # only a generated index with the exact recorded hash
        else:
            data = confined(backup, "files/" + change["path"], exists=True).read_bytes()
            if digest(data) != change["before"]:
                raise ValueError("Backup hash mismatch")
            atomic(original, data)
            if current != original:
                current.unlink()
        restored.append(change["path"])
    return {"restored": restored, "conflicts": conflicts}


def summary(result: dict) -> dict:
    """Safe public counts, without note text or private link target names."""
    if "inventory" in result:
        snap = result["inventory"]
        return {"files": len(snap["files"]), "eligible_originals": snap["eligible"], "categories": snap["counts"],
                "planned_changes": len(result["changes"]), "unresolved_before": result["before_links"]["unresolved_count"]}
    return {"backup": result["backup"], "backup_files": result["backup_files"], "applied": len(result["applied"]),
            "conflicts": len(result["conflicts"]), "unresolved_before": result["before_links"]["unresolved_count"],
            "unresolved_after": result["after_links"]["unresolved_count"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--generated", default="Research OS")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    if args.rollback:
        print(json.dumps(rollback(args.rollback)))
        return
    if not args.vault:
        parser.error("--vault is required")
    proposal = plan(args.vault, args.generated)
    if args.apply:
        if not args.backup:
            parser.error("--apply requires --backup")
        print(json.dumps(summary(apply(proposal, args.backup)), ensure_ascii=True))
    else:
        print(json.dumps(summary(proposal), ensure_ascii=True))


if __name__ == "__main__":
    main()
