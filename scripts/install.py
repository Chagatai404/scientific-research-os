from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import datetime as dt

from common import ROOT, load_config, expand, parse_frontmatter

COMPUTE_SKILLS = {"geant4", "ml-experiment", "qml-experiment", "design-experiment",
                  "research-session", "research-review"}
COMPUTE_AGENTS = {
    "simulation-reviewer": ("GEANT4_PROTOCOL.md",),
    "ml-reviewer": ("ML_PROTOCOL.md",),
    "qml-reviewer": ("ML_PROTOCOL.md", "QML_PROTOCOL.md"),
}

# Canonical v0.8 inventory; helpers arrive in their authorized slices.
V08_REFERENCES = (
    "V0.8_IMPLEMENTATION.md", "LITERATURE_RELIABILITY_PROTOCOL.md",
    "AUTHENTICATED_ACCESS_PROTOCOL.md", "ORCHESTRATION_PROTOCOL.md",
    "RESEARCHER_OWNERSHIP_PROTOCOL.md", "DEFENSE_PROTOCOL.md",
)
V08_AGENT_REFERENCES = {
    "literature-scout": ("LITERATURE_RELIABILITY_PROTOCOL.md", "AUTHENTICATED_ACCESS_PROTOCOL.md"),
    "source-verifier": ("LITERATURE_RELIABILITY_PROTOCOL.md", "AUTHENTICATED_ACCESS_PROTOCOL.md"),
    "adversarial-reviewer": ("LITERATURE_RELIABILITY_PROTOCOL.md",),
}
# v0.9: the verification protocol travels with every role that audits a quantitative claim.
V09_AGENT_REFERENCES = {role: ("VERIFICATION_PROTOCOL.md",) for role in (
    "mathematics-reviewer", "statistics-reviewer", "physics-reviewer", "adversarial-reviewer",
    "ml-reviewer", "simulation-reviewer", "qml-reviewer", "chemistry-reviewer", "biology-reviewer", "walkthrough-verifier")}
# v0.9.5: the domain protocol travels with the reviewer for that domain.
DOMAIN_AGENT_REFERENCES = {"chemistry-reviewer": ("CHEMISTRY_PROTOCOL.md",), "biology-reviewer": ("BIOLOGY_PROTOCOL.md",),
                           "walkthrough-verifier": ("CODE_LEARNING_PROTOCOL.md",)}


# Standard-library helpers the graph-first workflows call from an installed skill
# directory (`python scripts/<helper>.py`); they import each other by module name.
GRAPH_SKILLS = {"tutor", "course-study", "science-visualize", "research-session", "research-review", "defend-research", "code-walkthrough"}

# Skills renamed between releases. The old directory is moved aside (never deleted) so that a host does not
# see two skills for one capability; it is recognized as ours only if it carries our shared reference.
RENAMED_SKILLS = {"visualize": "science-visualize"}
GRAPH_HELPERS = ("html_sessions.py", "common.py", "knowledge.py", "ontology.py", "migrate_learning.py", "research.py", "visuals.py", "tutor_contract.py", "tutor_plan.py", "bootstrap.py",
                 "vault_health.py", "computational_manifest.py", "validate_evidence.py", "excalidraw_schematic.py",
                 "retention.py", "math_notes.py", "visual_intent.py", "knowledge_maps.py", "paper_library.py", "library_index.py", "terms.py", "teaching_lint.py", "code_walkthrough.py", "resources.py", "diagram_spec.py", "animate.py", "fsrs_schedule.py", "notebook_coverage.py", "notebook_trace.py", "speech_text.py", "voice.py", "voice_adapter.py",
                 "literature_check.py", "paper_access.py", "tasks.py", "tutor_session.py", "defense.py",
                 "context_kernel.py", "learning_advice.py", "learning_preferences.py", "plan_evidence.py", "scientific_verify.py", "chembio_verify.py", "structure_verify.py", "rich_text.py", "board_script.py", "session_plan.py", "pedagogy_contract.py", "pedagogy_budget.py", "tutor_session.py", "handout.py", "visual_assets.py", "tutor_gate.py", "supervision.py",
                 # tasks.py gates reconciliation on the library inventory receipt that scout.py produces.
                 "scout.py",
                 # Optional Obsidian adapters: detection, vault search, and generated cards/canvas (all degrade to built-in routes).
                 "obsidian_plugins.py", "vault_search.py", "plugin_exports.py")


# Every substantive workflow writes HTML sessions, and `html_sessions.py context` loads the
# research and knowledge graphs in-process, so each skill carries these helpers.
SESSION_HELPERS = ("html_sessions.py", "common.py", "research.py", "knowledge.py", "ontology.py",
                   "validate_evidence.py", "computational_manifest.py",
                   # The context kernel gates every session; this is its complete import closure.
                   "context_kernel.py", "learning_advice.py", "learning_preferences.py", "plan_evidence.py", "tutor_plan.py", "migrate_learning.py", "paper_library.py", "library_index.py", "terms.py", "resources.py", "visuals.py",
                   # Stdlib-only verification engine: every review workflow can execute its checks.
                   "scientific_verify.py", "chembio_verify.py", "structure_verify.py",
                   # The shared scientific inline grammar html_sessions renders with.
                   "rich_text.py",
                   # A board widget's lecture script is checked by validate_state with the same rules the page uses.
                   "board_script.py",
                   # A session plan (probe tree, lecture segments, handout) is checked with the same board rules.
                   "session_plan.py", "pedagogy_contract.py", "pedagogy_budget.py", "tutor_session.py",
                   # A planned session's study handout (LaTeX body to PDF in the library, vault note, plan status); its template travels in assets/handout.
                   "handout.py",
                   # `voice.py board` records a board's sentences (the session protocol names it); it starts the engine through voice_adapter.py and says text with speech_text.py.
                   "voice.py", "voice_adapter.py", "speech_text.py",
                   # `html_sessions.py place` / `attach-visual` put registered figures into a lesson.
                   "visual_assets.py", "excalidraw_schematic.py",
                   # Concept-first gates for tutoring sessions (prerequisites, probe contracts, evidence proposals).
                   "tutor_gate.py", "tutor_contract.py",
                   # html_sessions validates a session's supervision record and renews its lease while waiting.
                   "supervision.py",
                   # The resume brief names which optional Obsidian adapters the vault has; visual_assets shares the detection.
                   "obsidian_plugins.py")


def copy_dir(src: Path, dst: Path, dry: bool) -> None:
    print(f"{'[dry] ' if dry else ''}{src} -> {dst}")
    if dry:
        return
    # Overlay known files, preserve extra user files, and back up changed files.
    dst.mkdir(parents=True, exist_ok=True)
    for source in sorted(src.rglob('*')):
        if source.is_file():
            copy_file(source, dst / source.relative_to(src), False)


def copy_file(src: Path, dst: Path, dry: bool) -> None:
    print(f"{'[dry] ' if dry else ''}{src} -> {dst}")
    if dry:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.read_bytes() != src.read_bytes():
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = dst.parent / '.research-os-install-backups' / stamp / dst.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, backup)
    shutil.copy2(src, dst)


def write_installed_text(dst: Path, content: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8")
    if dst.exists() and dst.read_bytes() != payload:
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = dst.parent / '.research-os-install-backups' / stamp / dst.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, backup)
    dst.write_bytes(payload)


def codex_agent_toml(meta: dict[str, str], body: str) -> str:
    body = body.strip().replace('"""', r'\"\"\"')
    return (
        f'name = "{meta["name"]}"\n'
        f'description = "{meta["description"].replace(chr(34), chr(39))}"\n'
        f'developer_instructions = """\n{body}\n"""\n'
    )


def retire_renamed_skills(base: Path, dry: bool) -> None:
    """Move a previously installed skill that has been renamed into ``.research-os-retired``.

    Only a directory that is provably an earlier Research OS install is touched: a SKILL.md whose name is the
    old name and a shipped ``references/SOURCE_POLICY.md``. Anything else is left alone and reported.
    """

    for old, new in RENAMED_SKILLS.items():
        legacy = base / old
        if not legacy.is_dir():
            continue
        text = (legacy / "SKILL.md").read_text(encoding="utf-8") if (legacy / "SKILL.md").is_file() else ""
        ours = f"name: {old}\n" in text and (legacy / "references" / "SOURCE_POLICY.md").is_file()
        if not ours:
            print(f"{legacy} is not a Research OS install; left in place (it may shadow {new})")
            continue
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = base / ".research-os-retired" / stamp / old
        print(f"{'[dry] ' if dry else ''}retire renamed skill {legacy} -> {target} (replaced by {new})")
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(target))


def install_skills(base: Path, dry: bool) -> None:
    """Install each skill together with the shared Research OS references.

    SKILL.md files use paths such as ``references/SOURCE_POLICY.md`` relative
    to the installed skill directory.  Therefore every installed skill needs
    a local copy of the canonical shared references.
    """

    shared_references = ROOT / "references"
    retire_renamed_skills(base, dry)

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
        # HTML sessions are mandatory for every substantive workflow.
        for helper in SESSION_HELPERS:
            copy_file(ROOT / "scripts" / helper, destination / "scripts" / helper, dry)
        copy_dir(ROOT / "assets/html-runtime", destination / "assets/html-runtime", dry)
        copy_dir(ROOT / "assets/handout", destination / "assets/handout", dry)      # the LaTeX template and style that handout.py builds with
        # Startup checks the actual host files, not only its (possibly unchanged) version label.
        for name in ("main.js", "manifest.json", "styles.css"):
            copy_file(ROOT / "extensions/obsidian-html" / name,
                      destination / "extensions/obsidian-html" / name, dry)
        if skill.name in GRAPH_SKILLS:
            for helper in GRAPH_HELPERS:
                copy_file(ROOT / "scripts" / helper, destination / "scripts" / helper, dry)


def install_agents_claude(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        out = base / p.name
        print(f"{'[dry] ' if dry else ''}{p} -> {out}")
        if not dry:
            write_installed_text(out, p.read_text(encoding="utf-8") + agent_policy(p.stem))


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
    v08_policy = ""
    for name in ("ORCHESTRATION_PROTOCOL.md", *V08_AGENT_REFERENCES.get(role, ()), *V09_AGENT_REFERENCES.get(role, ()), *DOMAIN_AGENT_REFERENCES.get(role, ())):
        v08_policy += "\n" + (ROOT / "references" / name).read_text(encoding="utf-8")
    if role in COMPUTE_AGENTS:
        for name in ("COMPUTATIONAL_PROTOCOL.md", "SOURCE_POLICY.md", *COMPUTE_AGENTS[role]):
            compute_policy += "\n" + (ROOT / "references" / name).read_text(encoding="utf-8")
    if role in {"literature-scout", "source-verifier", "adversarial-reviewer"}:
        evidence = (ROOT / "references" / "EVIDENCE_FORMAT.md").read_text(encoding="utf-8")
        evidence_policy = "\n" + evidence.split("## Storage and tooling", 1)[0]
    if role == "literature-scout":
        evidence_policy += "\n" + (ROOT / "references" / "PAPER_LIBRARY.md").read_text(encoding="utf-8")
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
        + v08_policy
    )


def install_agents_codex(base: Path, dry: bool) -> None:
    for p in sorted((ROOT / "agents").glob("*.md")):
        meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        out = base / f'{meta["name"]}.toml'
        print(f"{'[dry] ' if dry else ''}{p} -> {out}")
        if not dry:
            write_installed_text(out, codex_agent_toml(meta, body + agent_policy(meta["name"])))


def install_obsidian(cfg: dict, dry: bool) -> None:
    vault = expand(cfg["vault"]["path"])
    dst = vault / cfg["vault"]["templates_dir"]
    for p in sorted((ROOT / "assets" / "obsidian").glob("*.md")):
        copy_file(p, dst / p.name, dry)


def install_html_companion(cfg: dict, dry: bool) -> None:
    """Stage the desktop companion without changing the user's enabled plugins."""
    vault = expand(cfg["vault"]["path"])
    plugin = ROOT / "extensions/obsidian-html"
    destination = vault / ".obsidian/plugins/research-os-html"
    for name in ("main.js", "manifest.json", "styles.css"):
        source = plugin / name
        target = destination / name
        # Never silently overwrite a locally modified plugin installation.
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f"Existing companion differs; back it up before updating: {target}")
        copy_file(source, target, dry)
    for name in ('voice.py', 'voice_adapter.py', 'speech_text.py'):
        copy_file(ROOT / 'scripts' / name, destination / 'voice' / name, dry)
    from html_sessions import install_runtime
    if dry:
        print(f"[dry] shared HTML runtime -> {vault / '.research-os/runtime'}")
    else:
        install_runtime(vault)


def skill_status(base: Path) -> dict[str, str]:
    """Compare installed skills with the repository by content, never by modification time.

    The installer rewrites a file only when its bytes differ, so an unchanged skill keeps its old date and is
    still current. Values: ``current``, ``drifted`` (SKILL.md or a shared reference/helper differs),
    ``missing``, or ``legacy`` (an old name that a rename has replaced).
    """

    result: dict[str, str] = {}
    for skill in sorted((ROOT / "skills").iterdir()):
        if not (skill / "SKILL.md").is_file():
            continue
        installed = base / skill.name
        if not (installed / "SKILL.md").is_file():
            result[skill.name] = "missing"
            continue
        pairs = [(p, installed / p.relative_to(skill)) for p in skill.rglob('*') if p.is_file()]
        for source, destination in ((ROOT / 'references', installed / 'references'),
                                    (ROOT / 'assets/html-runtime', installed / 'assets/html-runtime'),
                                    (ROOT / 'assets/handout', installed / 'assets/handout')):
            pairs += [(p, destination / p.relative_to(source)) for p in source.rglob('*') if p.is_file()]
        helpers = set(SESSION_HELPERS)
        if skill.name in GRAPH_SKILLS:
            helpers.update(GRAPH_HELPERS)
        if skill.name in COMPUTE_SKILLS:
            helpers.update(('scientific_tools.py', 'computational_manifest.py'))
            source = ROOT / 'extensions/scientific-tools'
            pairs += [(p, installed / 'extensions/scientific-tools' / p.relative_to(source)) for p in source.rglob('*') if p.is_file()]
        pairs += [(ROOT / 'scripts' / name, installed / 'scripts' / name) for name in helpers]
        pairs += [(ROOT / 'extensions/obsidian-html' / name, installed / 'extensions/obsidian-html' / name)
                  for name in ('main.js', 'manifest.json', 'styles.css')]
        def matches(src, dst):
            if not dst.is_file():
                return False
            a, b = src.read_bytes(), dst.read_bytes()
            if src.suffix in {'.md', '.py', '.js', '.css', '.json', '.toml', '.txt', '.tex', '.sty'}:
                a, b = a.replace(b'\r\n', b'\n'), b.replace(b'\r\n', b'\n')
            return a == b
        drifted = any(not matches(src, dst) for src, dst in pairs)
        result[skill.name] = "drifted" if drifted else "current"
    for old in RENAMED_SKILLS:
        if (base / old).is_dir():
            result[old] = "legacy"
    return result


def print_status(cfg: dict, target: str) -> bool:
    clean = True
    for name, key in (("claude", "claude_skills"), ("codex", "codex_skills")):
        if target not in ("all", name):
            continue
        base = expand(cfg["install"][key])
        print(f"{name}: {base}")
        for skill, state in skill_status(base).items():
            clean &= state == "current"
            print(f"  {state:8} {skill}")
    return clean


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="report installed-vs-repository drift by content and exit")
    ap.add_argument("--target", choices=["all", "claude", "codex"], default="all")
    ap.add_argument("--obsidian", action="store_true")
    ap.add_argument("--html-companion", action="store_true", help="stage companion plugin/runtime; enable manually in Obsidian")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    ins = cfg["install"]

    if args.status:
        raise SystemExit(0 if print_status(cfg, args.target) else 1)

    if args.target in ("all", "claude"):
        install_skills(expand(ins["claude_skills"]), args.dry_run)
        install_agents_claude(expand(ins["claude_agents"]), args.dry_run)

    if args.target in ("all", "codex"):
        install_skills(expand(ins["codex_skills"]), args.dry_run)
        install_agents_codex(expand(ins["codex_agents"]), args.dry_run)

    if args.obsidian:
        install_obsidian(cfg, args.dry_run)
    if args.html_companion:
        install_html_companion(cfg, args.dry_run)


if __name__ == "__main__":
    main()
