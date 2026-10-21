"""Path confinement shared by the library helpers."""
from __future__ import annotations

from pathlib import Path


def confined(root: Path, relative: str) -> Path:
    """``root / relative``, refused unless it is a plain relative path that stays inside ``root`` without symlinks."""
    if any(part in {'', '.', '..'} for part in relative.split('/')) or '\\' in relative or ':' in relative:
        raise ValueError('expected a root-relative path')
    path = root / relative
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root):
        raise ValueError('paths must stay inside root without symlinks')
    return path
