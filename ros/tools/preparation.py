"""Tools for prepared lessons: bundles, their plans and files, the readiness gate, the tasks it opens, and local voice
and animation renders.

Each tool is declared with ``@tool``; see ``ros.api`` and ``docs/ARCHITECTURE.md``."""
from __future__ import annotations

import base64

from .. import prepare
from ..api import P, tool


@tool("bundles", "Prepared bundles with their goal and whether each is ready.")
def bundles(rec):
    return prepare.bundles(rec)


@tool("bundle_create", "Create a lesson bundle with its goal as the only node.", writes=True,
      bundle=P("string", "bundle id", True), title=P("string", "title", True),
      goal=P("string", "the goal node, e.g. capability:x", True), lang=P("string", "narration language (en, tr)"))
def bundle_create(rec, bundle, title, goal, lang="en"):
    return prepare.create(rec, bundle, title, goal, lang)


@tool("bundle_plan", "Read a bundle's plan, or replace it with plan=... (validated; voids the last gate verdict).",
      writes=True, bundle=P("string", "bundle id", True), plan=P("object", "the whole new plan"))
def bundle_plan(rec, bundle, plan=None):
    if plan is not None:
        prepare.save_plan(rec, bundle, plan)
    return prepare.load_plan(rec, bundle)


@tool("bundle_file", "Write one file into a bundle (text, or base64 for binary), e.g. a visual or its RESULT note.",
      writes=True, bundle=P("string", "bundle id", True), path=P("string", "path inside the bundle", True),
      text=P("string", "text content"), base64=P("string", "binary content, base64"))
def bundle_file(rec, bundle, path, text=None, base64=None):
    d = prepare.bundle_dir(rec, bundle)
    target = (d / path).resolve()
    if d.resolve() not in target.parents:
        raise ValueError("the path must stay inside the bundle")
    if (text is None) == (base64 is None):
        raise ValueError("give exactly one of text or base64")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8") if text is not None else _b64(base64)
    target.write_bytes(data)
    (d / "manifest.json").unlink(missing_ok=True)
    return {"path": path, "bytes": len(data)}


def _b64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


@tool("bundle_check", "Run the readiness gate: every row with what is missing, and ready true or false.", writes=True,
      bundle=P("string", "bundle id", True))
def bundle_check(rec, bundle):
    return prepare.check(rec, bundle)


@tool("bundle_tasks", "Open one task per missing piece of a bundle for agents to make (and clip searches).",
      writes=True, bundle=P("string", "bundle id", True), clips=P("boolean", "also ask video scouts for clips"))
def bundle_tasks(rec, bundle, clips=False):
    return {"tasks": prepare.open_tasks(rec, bundle, clips)}


@tool("bundle_voice", "Speak every narration segment without audio with a local engine.", writes=True,
      bundle=P("string", "bundle id", True), provider=P("string", "kokoro (default), piper or chatterbox"))
def bundle_voice(rec, bundle, provider="kokoro"):
    return prepare.render_voice(rec, bundle, provider)


@tool("bundle_animate", "Render a node's Manim animation from its spec and attach it.", writes=True,
      bundle=P("string", "bundle id", True), node=P("string", "node id", True),
      spec=P("string", "animation spec path inside the bundle", True))
def bundle_animate(rec, bundle, node, spec):
    return prepare.render_animation(rec, bundle, node, spec)
