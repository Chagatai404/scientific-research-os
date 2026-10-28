"""Research OS v1 core: one record per project or course, one writer, many views. Standard library only.

The record is plain files (``events.jsonl``, ``items/<sha256>.json``, ``graph/nodes.jsonl`` and ``graph/edges.jsonl``);
``index.sqlite`` is a cache rebuilt from them and can always be deleted. See ``docs/plans/v1.0-overhaul-architecture.md``.
"""
from __future__ import annotations

__version__ = "1.3.0"
