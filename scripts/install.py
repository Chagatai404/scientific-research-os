from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from common import ROOT, load_config, expand, parse_frontmatter


def copy_dir(src: Path, dst: Path, dry: bool) -> None:
    print(f"{'[dry] ' if dry else ''}{src} -> {dst}")
    if dry:
        return
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def copy_file(src: Path, dst: Path, dry: bool) -> None:
    print(f"{'[dry] ' if dry else ''}{src} -> {dst}")
    if dry:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def codex_agent_toml(meta: dict[str, str], body: str) -> str:
    body = body.strip().replace('"""', r'\"\"\"')
    return (
        f'name = "{meta["name"]}"\n'
        f'description = "{meta["description"].replace(chr(34), chr(39))}"\n'
        f'developer_instructions = """\n{body}\n"""\n'
    )


def install_skills(base: Path, dry: bool) -> None:
    """Install each skill together with the shared Research OS references.

    SKILL.md files use paths such as ``references/SOURCE_POLICY.md`` relative
    to the installed skill directory.  Therefore every installed skill needs
    a local copy of the canonical shared references.
    """

    shared_references = ROOT / "references"

    for skill in sorted((ROOT / "skills").iterdir()):
        if not skill.is_dir() or not (skill / "SKILL.md").exists():
            continue

        destination = base / skill.name
        copy_dir(skill, destination, dry)
        copy_dir(shared_references, destination / "references", dry)


def install_agents_claude(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        copy_file(p, base / p.name, dry)


def install_agents_codex(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        out = base / f'{meta["name"]}.toml'
        print(f"{'[dry] ' if dry else ''}{p} -> {out}")
        if not dry:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(codex_agent_toml(meta, body), encoding="utf-8")


def install_obsidian(cfg: dict, dry: bool) -> None:
    vault = expand(cfg["vault"]["path"])
    dst = vault / cfg["vault"]["templates_dir"]
    for p in sorted((ROOT / "assets" / "obsidian").glob("*.md")):
        copy_file(p, dst / p.name, dry)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["all", "claude", "codex"], default="all")
    ap.add_argument("--obsidian", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    ins = cfg["install"]

    if args.target in ("all", "claude"):
        install_skills(expand(ins["claude_skills"]), args.dry_run)
        install_agents_claude(expand(ins["claude_agents"]), args.dry_run)

    if args.target in ("all", "codex"):
        install_skills(expand(ins["codex_skills"]), args.dry_run)
        install_agents_codex(expand(ins["codex_agents"]), args.dry_run)

    if args.obsidian:
        install_obsidian(cfg, args.dry_run)


if __name__ == "__main__":
    main()
