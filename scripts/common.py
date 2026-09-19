from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def load_config() -> dict:
    path = ROOT / "research-os.toml"
    if not path.exists():
        raise SystemExit(
            "Missing research-os.toml. Copy research-os.example.toml to "
            "research-os.toml and edit local paths."
        )
    with path.open("rb") as f:
        return tomllib.load(f)

def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5:]
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data, body

def safe_filename(title: str) -> str:
    title = re.sub(r'[<>:"/\\|?*]', "-", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title.rstrip(". ")
