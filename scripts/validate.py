from __future__ import annotations

from pathlib import Path
from datetime import date
import re
import sys

from common import ROOT, parse_frontmatter
from scientific_tools import load_profiles

errors = []
try:
    tool_profiles = load_profiles(ROOT / "extensions" / "scientific-tools")
    for tool in ("geant4", "pytorch", "sklearn", "pennylane", "qiskit", "root-scikit-hep"):
        if tool not in tool_profiles:
            errors.append(f"Missing required tool pack: {tool}")
except ValueError as exc:
    errors.append(str(exc))

skill_names = set()
reference_pattern = re.compile(r"`?references/([A-Za-z0-9_.-]+)`?")

for d in sorted((ROOT / "skills").iterdir()):
    if not d.is_dir():
        continue

    p = d / "SKILL.md"
    if not p.exists():
        errors.append(f"Missing SKILL.md: {d}")
        continue

    text = p.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)

    for key in ("name", "description"):
        if not meta.get(key):
            errors.append(f"{p}: missing {key}")

    name = meta.get("name", "")
    if name != d.name:
        errors.append(f"{p}: skill name must match directory")
    if name and not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        errors.append(f"{p}: invalid skill name {name!r}")
    if name in skill_names:
        errors.append(f"Duplicate skill name: {name}")
    skill_names.add(name)

    if len(meta.get("description", "")) > 1024:
        errors.append(f"{p}: description too long")

    # Skills are installed with ROOT/references copied into
    # <installed-skill>/references.  Any referenced shared document must
    # therefore exist in the canonical references directory.
    for reference_name in reference_pattern.findall(text):
        reference_path = ROOT / "references" / reference_name
        if not reference_path.is_file():
            errors.append(
                f"{p}: references missing shared document "
                f"references/{reference_name}"
            )

agent_names = set()
for p in sorted((ROOT / "agents").glob("*.md")):
    meta, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
    for key in ("name", "description"):
        if not meta.get(key):
            errors.append(f"{p}: missing {key}")
    name = meta.get("name", "")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or name != p.stem:
        errors.append(f"{p}: invalid agent name or filename mismatch")
    if meta.get("mode") not in {"read-only", "controlled-write"}:
        errors.append(f"{p}: agent mode must be read-only or controlled-write")
    if name in {"simulation-reviewer", "ml-reviewer", "qml-reviewer"} and meta.get("mode") != "read-only":
        errors.append(f"{p}: computational reviewer mode must be read-only")
    if name in agent_names:
        errors.append(f"Duplicate agent name: {name}")
    agent_names.add(name)

required = [
    ROOT / "references" / "V0.5_IMPLEMENTATION.md",
    ROOT / "references" / "COMPUTATIONAL_PROTOCOL.md",
    ROOT / "references" / "GEANT4_PROTOCOL.md",
    ROOT / "references" / "ML_PROTOCOL.md",
    ROOT / "references" / "QML_PROTOCOL.md",
    ROOT / "scripts" / "computational_manifest.py",
    ROOT / "scripts" / "scientific_tools.py",
    ROOT / "extensions" / "scientific-tools" / "README.md",
    ROOT / "skills" / "geant4" / "SKILL.md",
    ROOT / "skills" / "ml-experiment" / "SKILL.md",
    ROOT / "skills" / "qml-experiment" / "SKILL.md",
    ROOT / "agents" / "simulation-reviewer.md",
    ROOT / "agents" / "ml-reviewer.md",
    ROOT / "agents" / "qml-reviewer.md",
    ROOT / "references" / "V0.4.5_IMPLEMENTATION.md",
    ROOT / "references" / "COURSE_LEARNING_PROTOCOL.md",
    ROOT / "skills" / "course-study" / "SKILL.md",
    ROOT / "assets" / "obsidian" / "14_Learning_Goal.md",
    ROOT / "assets" / "obsidian" / "15_Course.md",
    ROOT / "assets" / "obsidian" / "16_Course_Session.md",
    ROOT / "references" / "LATEX_TRANSCRIPTION_PROTOCOL.md",
    ROOT / "skills" / "notes-to-latex" / "SKILL.md",
    ROOT / "references" / "SOURCE_POLICY.md",
    ROOT / "references" / "RESEARCH_PROTOCOL.md",
    ROOT / "references" / "AGENT_POLICY.md",
    ROOT / "references" / "LEARNING_PROTOCOL.md",
    ROOT / "references" / "TUTOR_PLANNING.md",
    ROOT / "references" / "VISUALIZATION_PROTOCOL.md",
    ROOT / "skills" / "visualize" / "SKILL.md",
    ROOT / "assets" / "obsidian" / "00_Tutor_Session.md",
    ROOT / "assets" / "obsidian" / "13_Knowledge_Graph.md",
    ROOT / "scripts" / "knowledge.py",
    ROOT / "scripts" / "tutor_plan.py",
    ROOT / "scripts" / "validate_evidence.py",
    ROOT / "references" / "EVIDENCE_FORMAT.md",
]
for p in required:
    if not p.exists():
        errors.append(f"Missing required file: {p}")

# Check installer-owned source references without writing outputs or executing probes.
from install import COMPUTE_AGENTS, COMPUTE_SKILLS
for skill in COMPUTE_SKILLS:
    if not (ROOT / "skills" / skill / "SKILL.md").is_file():
        errors.append(f"Installer references missing compute skill: {skill}")
for role, names in COMPUTE_AGENTS.items():
    if not (ROOT / "agents" / f"{role}.md").is_file():
        errors.append(f"Installer references missing compute agent: {role}")
    for name in names:
        if not (ROOT / "references" / name).is_file():
            errors.append(f"Installer references missing protocol: {name}")
for name in ("pytorch", "sklearn", "pennylane", "qiskit", "root", "scikit-hep", "root-scikit-hep"):
    if (ROOT / "skills" / name).exists():
        errors.append(f"Framework pack must not be a global skill: {name}")

canonical_pattern = re.compile(r"`([A-Z0-9_]+_(?:PROTOCOL|POLICY)\.md)`")
for directory in ("references", "skills", "agents", "extensions/scientific-tools"):
    for p in (ROOT / directory).rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        for name in set(reference_pattern.findall(text) + canonical_pattern.findall(text)):
            if not (ROOT / "references" / name).is_file():
                errors.append(f"{p}: missing canonical reference {name}")

# Check named template links in canonical instructions and template documentation.
template_pattern = re.compile(r"\b[0-9]{2}_[A-Za-z0-9_]+\.md\b")
documents = [ROOT / "README.md"]
for directory in ("skills", "references", "assets/obsidian"):
    documents.extend((ROOT / directory).rglob("*.md"))
for p in documents:
    for name in template_pattern.findall(p.read_text(encoding="utf-8")):
        if not (ROOT / "assets" / "obsidian" / name).is_file():
            errors.append(f"{p}: missing template {name}")

# knowledge.py owns learning/ontology validation; do not duplicate its rules.
from knowledge import discover

for directory in (ROOT / "examples" / "learning", ROOT / "examples" / "ontology", ROOT / "assets" / "obsidian"):
    if not directory.is_dir():
        errors.append(f"Missing learning input directory: {directory}")
        continue
    collection = discover(directory, date.max)
    errors.extend(f"{directory}: {issue}" for issue in collection.diagnostics)

# The connected example must stay valid under every canonical parser it demonstrates.
import research
import visuals

connected = ROOT / "examples" / "connected-research"
if not connected.is_dir():
    errors.append(f"Missing example: {connected}")
else:
    errors.extend(f"{connected}: {d.severity} {d.code} {d.path} {d.message}"
                  for d in research.validate(connected).diagnostics if d.severity == "ERROR")
    errors.extend(f"{connected}: {issue}" for issue in discover(connected, date.max).diagnostics)
    errors.extend(f"{connected}: {issue}" for issue in visuals.discover(connected)[1])
    errors.extend(f"{connected}: {issue}" for issue in visuals.broken_embeds(connected))

suspicious = [
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"sk-[A-Za-z0-9_-]{20,}",
]
for p in ROOT.rglob("*"):
    if not p.is_file() or ".git" in p.parts:
        continue
    if p.suffix.lower() not in {".md", ".py", ".toml", ".txt", ""}:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pat in suspicious:
        if re.search(pat, text):
            errors.append(f"Possible credential-like token in {p}")

from validate_evidence import load_board, validate as validate_atom

board, evidence_errors = load_board(ROOT / "examples" / "evidence")
errors.extend(str(e) for e in evidence_errors)
for claim_id, atom in board.items():
    errors.extend(f"{claim_id}: {e}" for e in validate_atom(atom, board))

if errors:
    print("Validation failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(
    f"OK: {len(skill_names)} skills, {len(agent_names)} agents, "
    f"{len(list((ROOT/'assets'/'obsidian').glob('[0-9][0-9]_*.md')))} Obsidian templates."
)
