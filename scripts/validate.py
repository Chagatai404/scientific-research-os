from __future__ import annotations

from pathlib import Path
import re
import sys

from common import ROOT, parse_frontmatter

errors = []

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
    if name in agent_names:
        errors.append(f"Duplicate agent name: {name}")
    agent_names.add(name)

required = [
    ROOT / "references" / "SOURCE_POLICY.md",
    ROOT / "references" / "RESEARCH_PROTOCOL.md",
    ROOT / "references" / "AGENT_POLICY.md",
    ROOT / "references" / "LEARNING_PROTOCOL.md",
    ROOT / "assets" / "obsidian" / "00_Tutor_Session.md",
]
for p in required:
    if not p.exists():
        errors.append(f"Missing required file: {p}")

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

if errors:
    print("Validation failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

print(
    f"OK: {len(skill_names)} skills, {len(agent_names)} agents, "
    f"{len(list((ROOT/'assets'/'obsidian').glob('*.md')))} Obsidian templates."
)
