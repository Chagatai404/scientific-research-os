from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from common import ROOT, load_config, expand, parse_frontmatter

COMPUTE_SKILLS = {"geant4", "ml-experiment", "qml-experiment", "design-experiment",
                  "research-session", "research-review"}
COMPUTE_AGENTS = {
    "simulation-reviewer": ("GEANT4_PROTOCOL.md",),
    "ml-reviewer": ("ML_PROTOCOL.md",),
    "qml-reviewer": ("ML_PROTOCOL.md", "QML_PROTOCOL.md"),
}


# Standard-library helpers the graph-first workflows call from an installed skill
# directory (`python scripts/<helper>.py`); they import each other by module name.
GRAPH_SKILLS = {"tutor", "course-study", "visualize", "research-session", "research-review"}
GRAPH_HELPERS = ("knowledge.py", "ontology.py", "migrate_learning.py", "research.py", "visuals.py", "tutor_contract.py", "bootstrap.py",
                 "vault_health.py", "computational_manifest.py", "validate_evidence.py", "excalidraw_schematic.py")


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
        if skill.name in COMPUTE_SKILLS:
            for helper in ("scientific_tools.py", "computational_manifest.py"):
                copy_file(ROOT / "scripts" / helper, destination / "scripts" / helper, dry)
            copy_dir(ROOT / "extensions/scientific-tools",
                     destination / "extensions/scientific-tools", dry)
        if skill.name in {"research-session", "research-review"}:
            copy_file(ROOT / "scripts" / "validate_evidence.py",
                      destination / "scripts" / "validate_evidence.py", dry)
        if skill.name in GRAPH_SKILLS:
            for helper in GRAPH_HELPERS:
                copy_file(ROOT / "scripts" / helper, destination / "scripts" / helper, dry)


def install_agents_claude(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        out = base / p.name
        print(f"{'[dry] ' if dry else ''}{p} -> {out}")
        if not dry:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(p.read_text(encoding="utf-8") + agent_policy(p.stem), encoding="utf-8")


def agent_policy(role: str) -> str:
    """Bundle canonical boundaries so standalone agents need no relative lookup."""
    research = (ROOT / "references" / "RESEARCH_PROTOCOL.md").read_text(encoding="utf-8")
    triage_and_gate = research.split("## Blocker / relevance triage\n", 1)[1].split(
        "## Scientific invariants\n", 1
    )[0]
    source_policy = ""
    if role in {"literature-scout", "source-verifier", "visualizer"}:
        source_policy = "\n" + (ROOT / "references" / "SOURCE_POLICY.md").read_text(encoding="utf-8")
    visualization_policy = ""
    evidence_policy = ""
    compute_policy = ""
    if role in COMPUTE_AGENTS:
        for name in ("COMPUTATIONAL_PROTOCOL.md", "SOURCE_POLICY.md", *COMPUTE_AGENTS[role]):
            compute_policy += "\n" + (ROOT / "references" / name).read_text(encoding="utf-8")
    if role in {"literature-scout", "source-verifier", "adversarial-reviewer"}:
        evidence = (ROOT / "references" / "EVIDENCE_FORMAT.md").read_text(encoding="utf-8")
        evidence_policy = "\n" + evidence.split("## Storage and tooling", 1)[0]
    if role == "visualizer":
        visualization_policy = "\n" + (ROOT / "references" / "VISUALIZATION_PROTOCOL.md").read_text(encoding="utf-8")
    return (
        "\n\n# Shared Research OS policy (generated from canonical references)\n\n"
        + (ROOT / "references" / "AGENT_POLICY.md").read_text(encoding="utf-8")
        + "\n## Blocker / relevance triage\n" + triage_and_gate
        + source_policy
        + visualization_policy
        + evidence_policy
        + compute_policy
    )


def install_agents_codex(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        out = base / f'{meta["name"]}.toml'
        print(f"{'[dry] ' if dry else ''}{p} -> {out}")
        if not dry:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(codex_agent_toml(meta, body + agent_policy(meta["name"])), encoding="utf-8")


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
