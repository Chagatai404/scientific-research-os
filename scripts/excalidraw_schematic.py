#!/usr/bin/env python3
"""Write a simple Excalidraw schematic (``.excalidraw.md``) for an Obsidian vault.

Standard library only. The output follows the Obsidian Excalidraw plugin's
uncompressed ``parsed`` format, so it opens in the Excalidraw view. It draws
boxes in labelled rows with arrows between them. It is a **schematic of
intent**: no quantitative content, never a data plot (see the visualization
protocol). It never overwrites an existing file.

Spec (JSON)::

    {
      "title": "Plan name",
      "note": "optional one-line caveat; defaults to a schematic disclaimer",
      "rows": [
        {"label": "Fri", "nodes": [{"id": "a", "text": "Step one\\nline two", "kind": "step"}]}
      ],
      "edges": [["a", "b"], ["a", "c", "gate"]]
    }

``kind`` is ``step`` (default), ``gate`` or ``done``; an edge's optional third
item ``gate`` colours it as a decision path.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from pathlib import Path

KINDS = {
    "step": ("#e7f0fa", "#1f4e79"),
    "gate": ("#fff3cd", "#b8860b"),
    "done": ("#e6f4ea", "#2e7d32"),
}
BOX_W, BOX_H, GAP_X, GAP_Y, MARGIN_X, TOP = 250, 78, 70, 62, 40, 110
DEFAULT_NOTE = "SCHEMATIC of intent, not quantitative, not to scale."
HEADER = (
    "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== "
    "You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. "
    "For more info check in plugin settings under 'Saving'"
)


class SpecError(ValueError):
    pass


def _rid(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(8))


def _base(rng, id_, kind, x, y, w, h, **extra):
    element = {
        "id": id_, "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": {"type": 3},
        "seed": rng.randint(1, 2**31 - 1), "version": 1, "versionNonce": rng.randint(1, 2**31 - 1),
        "isDeleted": False, "boundElements": None, "updated": 1759400000000, "link": None, "locked": False,
    }
    element.update(extra)
    return element


def validate_spec(spec: dict) -> None:
    if not isinstance(spec, dict) or not isinstance(spec.get("rows"), list) or not spec["rows"]:
        raise SpecError("spec needs a non-empty 'rows' list")
    for key, default in [('box_width', BOX_W), ('box_height', BOX_H)]:
        value = spec.get(key, default)
        if type(value) is not int or not default <= value <= 1000:
            raise SpecError(f'{key} must be an integer from {default} to 1000')
    seen = set()
    for row in spec["rows"]:
        for node in row.get("nodes", []):
            nid = node.get("id")
            if not nid or not node.get("text"):
                raise SpecError("every node needs an 'id' and 'text'")
            if nid in seen:
                raise SpecError(f"duplicate node id: {nid}")
            if node.get("kind", "step") not in KINDS:
                raise SpecError(f"unknown kind for {nid}: {node.get('kind')}")
            seen.add(nid)
    for edge in spec.get("edges", []):
        if len(edge) < 2 or edge[0] not in seen or edge[1] not in seen:
            raise SpecError(f"edge refers to an unknown node: {edge}")
        if len(edge) > 2 and edge[2] != "gate":
            raise SpecError(f"unknown edge kind: {edge[2]}")
    labels = spec.get('edge_labels', [])
    if not isinstance(labels, list) or (labels and len(labels) != len(spec.get('edges', []))) or any(not isinstance(x, str) for x in labels):
        raise SpecError('edge_labels must be strings matching edges')


def build(spec: dict, seed: int = 7) -> tuple[list[dict], list[tuple[str, str]]]:
    validate_spec(spec)
    rng = random.Random(seed)
    elements: list[dict] = []
    texts: list[tuple[str, str]] = []
    box_w, box_h = spec.get('box_width', BOX_W), spec.get('box_height', BOX_H)

    def free_text(x, y, text, size, color="#1e1e1e"):
        tid = _rid(rng)
        lines = text.split("\n")
        elements.append(_base(
            rng, tid, "text", x, y, max(len(line) for line in lines) * size * 0.55, len(lines) * size * 1.3,
            text=text, originalText=text, fontSize=size, fontFamily=1, textAlign="left", verticalAlign="top",
            containerId=None, lineHeight=1.25, strokeColor=color, roundness=None, autoResize=True))
        texts.append((text, tid))

    free_text(MARGIN_X, 10, spec.get("title", "Schematic"), 26)
    free_text(MARGIN_X, 48, spec.get("note", DEFAULT_NOTE), 14, "#c0504d")
    geometry: dict[str, tuple[float, float, float, float]] = {}
    for r, row in enumerate(spec["rows"]):
        y = TOP + r * (box_h + GAP_Y)
        if row.get("label"):
            free_text(MARGIN_X, y - 14, row["label"], 16, "#555555")
        for c, node in enumerate(row.get("nodes", [])):
            x = MARGIN_X + c * (box_w + GAP_X)
            bg, stroke = KINDS[node.get("kind", "step")]
            rect_id, text_id = _rid(rng), _rid(rng)
            lines = node["text"].split("\n")
            elements.append(_base(rng, rect_id, "rectangle", x, y + 20, box_w, box_h, backgroundColor=bg,
                                  strokeColor=stroke, boundElements=[{"id": text_id, "type": "text"}]))
            elements.append(_base(
                rng, text_id, "text", x + 10, y + 20 + box_h / 2 - len(lines) * 11, box_w - 20, len(lines) * 22,
                text=node["text"], originalText=node["text"], fontSize=16, fontFamily=1, textAlign="center",
                verticalAlign="middle", containerId=rect_id, lineHeight=1.25, roundness=None, autoResize=True))
            texts.append((node["text"], text_id))
            geometry[node["id"]] = (x, y + 20, box_w, box_h)
    for index, edge in enumerate(spec.get("edges", [])):
        (ax, ay, aw, ah), (bx, by, bw, bh) = geometry[edge[0]], geometry[edge[1]]
        if abs(ay - by) < 5:
            sx, sy, ex, ey = (ax + aw, ay + ah / 2, bx, by + bh / 2) if bx > ax else (ax, ay + ah / 2, bx + bw, by + bh / 2)
        elif by > ay:
            sx, sy, ex, ey = ax + aw / 2, ay + ah, bx + bw / 2, by
        else:
            sx, sy, ex, ey = ax + aw / 2, ay, bx + bw / 2, by + bh
        colour = "#b8860b" if len(edge) > 2 else "#1e1e1e"
        elements.append(_base(
            rng, _rid(rng), "arrow", sx, sy, ex - sx, ey - sy, strokeColor=colour, points=[[0, 0], [ex - sx, ey - sy]],
            startBinding=None, endBinding=None, startArrowhead=None, endArrowhead="arrow", lastCommittedPoint=None,
            roundness={"type": 2}))
        if spec.get('edge_labels'):
            free_text((sx + ex) / 2, (sy + ey) / 2, spec['edge_labels'][index], 12, colour)
    return elements, texts


def render(spec: dict, seed: int = 7) -> str:
    elements, texts = build(spec, seed)
    drawing = {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": elements,
               "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"}, "files": {}}
    lines = ["---", "", "excalidraw-plugin: parsed", "tags: [excalidraw]", "", "---", HEADER, "", "",
             "# Excalidraw Data", "", "## Text Elements"]
    for text, tid in texts:
        lines += [f"{text} ^{tid}", ""]
    lines += ["%%", "## Drawing", "```json", json.dumps(drawing), "```", "%%", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--spec", required=True, help="JSON spec file")
    parser.add_argument("--out", required=True, help="new .excalidraw.md file to create (never overwritten)")
    parser.add_argument("--seed", type=int, default=7, help="seed for element ids (deterministic output)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if not out.name.endswith(".excalidraw.md"):
        print("error: output must end with .excalidraw.md", file=sys.stderr)
        return 2
    if out.exists():
        print(f"error: {out} already exists; choose a new name", file=sys.stderr)
        return 2
    if not out.parent.is_dir():
        print(f"error: directory does not exist: {out.parent}", file=sys.stderr)
        return 2
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        content = render(spec, args.seed)
    except (OSError, json.JSONDecodeError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
