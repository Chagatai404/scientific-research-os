"""The rules in docs/ARCHITECTURE.md, checked. A failure here names the rule that was broken; fix the code, or change
the rule in the document and here together, never one without the other."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, importers  # noqa: E402

CORE = {"store", "home"}
PURE = {"store", "learn.fsrs", "home", "install"}
DOMAIN = {"tasks", "graph", "learn.evidence", "learn.schedule", "learn.probe", "learn.tutor", "learn.policy",
          "prepare", "research", "importers", "export", "learn.fsrs", "context", "roadmap", "vault", "handouts", "automation", "director", "atlas"}
TOOLS_LAYER = {"api", "registry"} | {f"tools.{p.stem}" for p in (ROOT / "ros" / "tools").glob("*.py") if p.stem != "__init__"}
INTERFACES = {"cli", "mcp", "serve", "__main__", "runner"}
LIB_USERS = {"importers", "prepare", "handouts"}


def modules() -> dict[str, set[str]]:
    """Each module of ``ros`` (outside ``ros.lib``) and the ``ros`` modules it imports, lazy imports included."""
    out = {}
    for p in sorted((ROOT / "ros").rglob("*.py")):
        rel = p.relative_to(ROOT / "ros").with_suffix("")
        if rel.parts[0] in ("lib", "portal") or rel.name == "__init__":
            continue
        name = ".".join(rel.parts)
        pkg = name.split(".")[:-1]
        deps = set()
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom) and n.level:
                base = pkg[:len(pkg) - (n.level - 1)]
                if n.module:
                    target = ".".join(base + [n.module])
                    names = {target + "." + a.name for a in n.names}
                    deps |= {t for t in names if (ROOT / "ros" / Path(*t.split("."))).with_suffix(".py").exists()} \
                        or {target}
                else:
                    deps |= {".".join(base + [a.name]) for a in n.names}
            elif isinstance(n, ast.Import):
                deps |= {a.name[4:] for a in n.names if a.name.startswith("ros.")}
        out[name] = {d for d in deps if d and d != "__version__" and not d.startswith("__init__")}
    return out


def top(dep: str) -> str:
    return "lib" if dep.split(".")[0] == "lib" else dep


class LayeringTests(unittest.TestCase):
    def setUp(self):
        self.mods = modules()

    def test_every_module_has_a_layer(self):
        for name in self.mods:
            self.assertTrue(name in CORE | PURE | DOMAIN | TOOLS_LAYER | INTERFACES,
                            f"{name} has no layer: add it to docs/ARCHITECTURE.md and to this test")

    def test_core_and_pure_modules_import_nothing_from_ros(self):
        for name in PURE:
            self.assertEqual(self.mods.get(name, set()), set(), f"{name} must stand alone")

    def test_domain_never_reaches_up(self):
        for name in DOMAIN:
            up = {d for d in self.mods.get(name, set()) if top(d) in TOOLS_LAYER | INTERFACES or d.startswith("tools")}
            self.assertEqual(up, set(), f"{name} (domain) imports the tool table or an interface")

    def test_tools_use_only_the_table_and_the_domain(self):
        for name in TOOLS_LAYER - {"api", "registry"}:
            bad = {d for d in self.mods[name] if top(d) not in CORE | DOMAIN | {"registry", "learn"}}
            self.assertEqual(bad, set(), f"{name} imports outside the registry and the domain")
        self.assertEqual(self.mods["registry"], {"store"}, "the registry knows only the store")

    def test_interfaces_reach_the_domain_only_through_the_table(self):
        for name in INTERFACES:
            bad = {d for d in self.mods.get(name, set()) if top(d) in DOMAIN | {"learn"} or d.startswith("tools")}
            self.assertEqual(bad, set(), f"{name} calls domain code directly; go through api.call or a tool")

    def test_carried_over_engines_are_used_only_where_documented(self):
        users = {name for name, deps in self.mods.items() if any(top(d) == "lib" for d in deps)}
        self.assertEqual(users, LIB_USERS, "ros.lib is used only by importers, prepare and handouts")

    def test_no_import_cycles(self):
        graph = {n: {d for d in deps if d in self.mods} for n, deps in self.mods.items()}
        state: dict[str, int] = {}

        def visit(n, path):
            state[n] = 1
            for d in graph[n]:
                if state.get(d) == 1:
                    self.fail("import cycle: " + " -> ".join(path + [n, d]))
                if not state.get(d):
                    visit(d, path + [n])
            state[n] = 2
        for n in graph:
            if not state.get(n):
                visit(n, [])


class GuideTests(unittest.TestCase):
    def test_the_names_the_guide_relies_on_exist(self):
        """docs/ARCHITECTURE.md tells contributors where to add things; those places must exist."""
        from ros import automation, director, handouts, importers, prepare, registry, research, store, tasks, vault
        from ros.learn import evidence, policy, probe
        guide = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        for owner, names in ((store.Record, ("events", "event", "item", "node", "items_by_id", "current_items",
                                             "derived", "fold", "reading")),
                             (store, ("NODE_TYPES", "EDGE_TYPES", "event_id")), (registry, ("present", "LOCK", "tool")),
                             (policy, ("RULES", "Context")), (prepare, ("ROWS", "Row", "Gate")),
                             (importers, ("IMPORTERS",)), (tasks, ("KINDS", "open_task")),
                             (automation, ("TRIGGERS", "THEN")), (director, ("PLAYBOOKS",)),
                             (handouts, ("KINDS", "ROWS")), (vault, ("NODE_STUBS",)),
                             (research, ("STEPS", "ASSURANCE")), (evidence, ("of", "TYPES")), (probe, ("LessonView",))):
            for name in names:
                with self.subTest(name=name):
                    self.assertTrue(hasattr(owner, name), f"{name} is named in the guide but missing")
                    self.assertIn(name, guide)


class ToolContractTests(unittest.TestCase):
    def test_tools_are_named_documented_and_typed(self):
        for name, t in api.TOOLS.items():
            with self.subTest(tool=name):
                self.assertRegex(name, r"^[a-z][a-z0-9_]*$")
                self.assertTrue(t.help and t.help[0].isupper() and len(t.help) > 20)
                for pname, p in t.params.items():
                    self.assertRegex(pname, r"^[a-z][a-z0-9_]*$")
                    self.assertIn(p.type, {"string", "integer", "number", "boolean", "array", "object", "any"})
                    self.assertTrue(p.help, f"{name}.{pname} has no help")
                self.assertEqual(t.fn.__code__.co_varnames[0], "rec", "a tool's first argument is the record")
                accepted = set(t.fn.__code__.co_varnames[1:t.fn.__code__.co_argcount])
                self.assertEqual(set(t.params), accepted, "declared parameters must match the function's")

    def test_human_acts_write_and_reads_do_not_claim_to(self):
        for name, t in api.TOOLS.items():
            if t.human:
                self.assertTrue(t.writes, name)

    def test_registries_drive_their_tools(self):
        self.assertEqual(set(api.TOOLS["import"].params["kind"].enum), set(importers.IMPORTERS))

    def test_tool_modules_say_what_they_hold(self):
        for p in (ROOT / "ros" / "tools").glob("*.py"):
            if p.stem != "__init__":
                self.assertTrue(re.match(r'"""Tools for ', p.read_text(encoding="utf-8")), p.name)


if __name__ == "__main__":
    unittest.main()
