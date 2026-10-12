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
from install import COMPUTE_AGENTS, COMPUTE_SKILLS, GRAPH_HELPERS, V08_REFERENCES, V08_AGENT_REFERENCES, V09_AGENT_REFERENCES
for name in V08_REFERENCES:
    if not (ROOT / 'references' / name).is_file():
        errors.append(f'Missing v0.8 design reference: {name}')
for role, names in V08_AGENT_REFERENCES.items():
    if not (ROOT / 'agents' / f'{role}.md').is_file():
        errors.append(f'Missing v0.8 contract role: {role}')
    for name in names:
        if name not in V08_REFERENCES:
            errors.append(f'Unknown v0.8 agent reference: {name}')
for role, names in V09_AGENT_REFERENCES.items():
    if not (ROOT / 'agents' / f'{role}.md').is_file():
        errors.append(f'Missing v0.9 verification role: {role}')
    for name in names:
        if not (ROOT / 'references' / name).is_file():
            errors.append(f'Missing v0.9 agent reference: {name}')
for helper in GRAPH_HELPERS:
    if not (ROOT / 'scripts' / helper).is_file():
        errors.append(f'Installer references missing graph helper: {helper}')
for name in ('V0.7_IMPLEMENTATION.md', 'KNOWLEDGE_MODEL.md', 'TUTOR_PLANNING.md',
             'RETENTION_PROTOCOL.md', 'MATH_RENDERING.md', 'KNOWLEDGE_MAPS.md', 'PAPER_LIBRARY.md'):
    if not (ROOT / 'references' / name).is_file():
        errors.append(f'Missing v0.7 reference: {name}')

import math_notes
for p in (ROOT / 'assets/obsidian').glob('*.md'):
    errors.extend(f'{p}: {issue}' for issue in math_notes.issues(p.read_text(encoding='utf-8')))
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
    if p.suffix.lower() not in {".md", ".py", ".toml", ".txt", ".json", ".yaml", ".yml", ".ini", ""}:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pat in suspicious:
        if re.search(pat, text):
            errors.append(f"Possible credential-like token in {p}")

from validate_evidence import load_board, validate as validate_atom
import literature_check
import paper_access
import tasks
import tutor_session
import defense
import runpy

try:
    tutor_example = ROOT / 'examples/tutoring'
    tutor_records = discover(tutor_example, date(2026, 10, 2))
    errors.extend(f'{tutor_example}: {issue}' for issue in tutor_records.diagnostics)
    lesson_report = tutor_session.replay(paper_access.read_json(tutor_example / 'session.json'))
    if lesson_report['branches'] or lesson_report['budget']['used'] != 4 or len(lesson_report['assessed_answers']) != 4:
        raise ValueError('synthetic lesson return/budget invalid')
    if len(tutor_records.nodes) != 4:
        raise ValueError('synthetic literacy profiles missing')
except (OSError, ValueError, TypeError, KeyError, UnicodeError):
    errors.append('Invalid tutoring example: bounded lesson and schema-3 canonical ledgers required')

try:
    defense_example = ROOT / 'examples/defense'
    defense_demo = runpy.run_path(str(defense_example / 'demo.py'))
    defense_report = defense.project(defense_example, defense_demo['declaration'](defense_example), date(2026, 10, 8))
    defense_gaps = defense.ownership(defense_example, defense_demo['ownership_declaration'](defense_example), date(2026, 10, 8))
    expected = [('SUPPORTED', 'DEFENSIBLE'), ('SUPPORTED', 'INCOMPLETE'),
                ('OVERSTATED', 'DEFENSIBLE'), ('UNCERTAIN', 'DEFENSIBLE'), ('UNCERTAIN', 'UNKNOWN')]
    if [(row['scientific_support']['state'], row['personal_defensibility']) for row in defense_report['claims']] != expected:
        raise ValueError('synthetic defense axes invalid')
    if defense_gaps['ownership'][0]['state'] != 'OPEN_UNKNOWN':
        raise ValueError('synthetic ownership gap invalid')
    if not (ROOT / 'skills/defend-research/SKILL.md').is_file():
        raise ValueError('defense skill missing')
except (OSError, ValueError, TypeError, KeyError, UnicodeError):
    errors.append('Invalid defense example: five claim cases and selective ownership required')

try:
    task_example = ROOT / 'examples/tasks'
    declaration = runpy.run_path(str(task_example / 'demo.py'))['declaration'](task_example)
    task_report = tasks.plan(task_example, declaration)
    if len(task_report['tasks']) != 4 or sum(row['state'] == 'READY' for row in task_report['tasks']) != 3:
        raise ValueError('synthetic independent task frontier invalid')
except (OSError, ValueError, TypeError, KeyError, UnicodeError):
    errors.append('Invalid task example: bounded schema-1 DAG required')

try:
    paper_access.request_data(paper_access.read_json(ROOT / 'examples/access/request.json'))
except (OSError, ValueError, TypeError, UnicodeError):
    errors.append('Invalid access example: sanitized schema-1 request required')

literature_root = ROOT / 'examples' / 'literature'
try:
    literature_report = literature_check.check(literature_root, literature_check.read_json(literature_root / 'literature.json'))
    errors.extend(str(d) for d in literature_report['diagnostics'] if d['severity'] == 'ERROR')
except (OSError, ValueError) as exc:
    errors.append(f'Invalid literature example: {exc}')

board, evidence_errors = load_board(ROOT / "examples" / "evidence")
errors.extend(str(e) for e in evidence_errors)
for claim_id, atom in board.items():
    errors.extend(f"{claim_id}: {e}" for e in validate_atom(atom, board))

# HTML-native sessions: known historical fixture is an explicitly reported archive.
import html_sessions
html_archives = {"examples/connected-research/tutor-sessions/2026-09-25 gamma shape.md"}
errors.extend(html_sessions.validate_sessions(ROOT, exceptions=html_archives))
for archive in sorted(html_archives):
    print(f"INFO HTML archival exception: {archive} (historical compatibility fixture)")

if errors:
    print("Validation failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(
    f"OK: {len(skill_names)} skills, {len(agent_names)} agents, "
    f"{len(list((ROOT/'assets'/'obsidian').glob('[0-9][0-9]_*.md')))} Obsidian templates."
)
