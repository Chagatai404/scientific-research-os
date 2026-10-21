"""The v1 graph queries agree with the old runtime on the same history, and the research queries read the graph."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "tests"))

from ros.lib import knowledge  # noqa: E402
from ros import graph, importers  # noqa: E402
from ros.store import Record  # noqa: E402

DATES = [date(2026, 9, 1), date(2026, 9, 29), date(2026, 10, 2), date(2026, 10, 20), date(2027, 6, 1)]
SCOPES = {"subject": "subject", "domain": "domain", "concept": "concept", "project": "project", "block": "block",
          "goal": "goal", "course": "course"}


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rec = Record(Path(self._tmp.name) / "rec")
        self.addCleanup(self.rec.close)


class LearningParityTests(Fixture):
    def scopes(self, collection):
        """Every scope value the old runtime can be queried by in this collection."""
        out = {("capability", key) for key in collection.nodes}
        for n in collection.nodes.values():
            out.add(("subject", n.domain))
            out |= {("project", p) for p in n.projects} | {("goal", g) for g in n.meta.get("goals", [])}
            out |= {("course", c) for c in n.meta.get("courses", [])}
            if n.meta["learning_schema"] in (2, 3):
                out |= {("subject", s) for s in n.subjects} | {("domain", d) for d in n.domains}
                out |= {("block", b) for b in n.blocks} | {("concept", n.meta["concept"])}
        return sorted((s, v) for s, v in out if v)

    def check(self, source: Path):
        report = importers.learning_records(self.rec, source)
        self.assertGreater(report["capabilities"], 0)
        for as_of in DATES:
            old = knowledge.discover(source, as_of)
            new = graph.Learning(self.rec, as_of)
            self.assertEqual(set(new.caps), {f"capability:{k}" for k in old.nodes})
            self.assertEqual(new.ready, {f"capability:{k}" for k in knowledge.ready_nodes(old.nodes)}, as_of)
            for scope, value in self.scopes(old):
                with self.subTest(source=source.name, as_of=as_of, scope=scope, value=value):
                    q = knowledge.query(old, scope, value, dependencies=True)
                    primary, closure = new.select(f"{scope}:{value}")
                    self.assertEqual(sorted(closure), sorted(f"capability:{n['id']}" for n in q["nodes"]))
                    for n in q["nodes"]:
                        v = new.view(f"capability:{n['id']}")
                        self.assertEqual(v["state"], n["state"])
                        self.assertEqual(v["ready"], n["ready"])
                        self.assertEqual(v["frontier"], n["frontier"])
                        self.assertEqual(v["blocked_by"], [f"capability:{b}" for b in n["blocked_by"]])
                        self.assertEqual(v["next_review"], n["next_review"])
                        self.assertEqual(v["last_retrieval"], n["last_retrieval"])
                        self.assertEqual(v["evidence"], n["evidence"])
                        self.assertEqual(v["freshness"], n["freshness"])
                        self.assertEqual(v["diagnostics"], n["diagnostics"])
                        if "mastery" in n:
                            for s, dims in n["mastery"].items():
                                for d, a in dims.items():
                                    self.assertEqual(v["mastery"][s][d]["state"], a["state"], (s, d))
                                    self.assertEqual(v["mastery"][s][d]["next_review"], a["next_review"], (s, d))

    def test_examples_learning(self):
        self.check(ROOT / "examples" / "learning")

    def test_examples_ontology(self):
        self.check(ROOT / "examples" / "ontology")

    def test_synthetic_vault_covers_every_state_and_issue(self):
        import test_knowledge as tk
        src = Path(self._tmp.name) / "vault"
        retained = tk.attempt() + tk.attempt(day="2026-09-29", timing="delayed", method="transfer")
        notes = {
            "unknown": tk.record("unknown"),
            "learning": tk.record("learning", rows=tk.attempt(outcome="fail")),
            "demonstrated": tk.record("demonstrated", prerequisites=["retained"], rows=tk.attempt()),
            "retained": tk.record("retained", rows=retained),
            "fragile": tk.record("fragile", rows=retained + tk.attempt(day="2026-09-29", outcome="partial")),
            "hinted": tk.record("hinted", rows=tk.attempt(assistance="hinted")),
            "orphan": tk.record("orphan", prerequisites=["nowhere"], rows=tk.attempt()),
            "cycle-a": tk.record("cycle-a", prerequisites=["cycle-b"], rows=tk.attempt()),
            "cycle-b": tk.record("cycle-b", prerequisites=["cycle-a"], rows=tk.attempt()),
            "after-cycle": tk.record("after-cycle", prerequisites=["cycle-a"]),
            "liar": tk.record("liar", rows=tk.attempt(outcome="fail"), state="retained"),
            "top": tk.record("top", domain="physics", projects=["demo"], prerequisites=["demonstrated", "fragile"]),
        }
        for name, text in notes.items():
            (src / f"{name}.md").parent.mkdir(parents=True, exist_ok=True)
            (src / f"{name}.md").write_text(text, encoding="utf-8")
        self.check(src)
        states = {c.assessment.state for c in graph.Learning(self.rec, date(2026, 9, 29)).caps.values()}
        self.assertTrue({"unknown", "learning", "demonstrated", "retained", "fragile"} <= states)

    def test_reimport_is_a_noop_and_follows_edits(self):
        src = Path(self._tmp.name) / "vault"
        shutil.copytree(ROOT / "examples" / "learning", src)
        first = importers.learning_records(self.rec, src)
        self.assertGreater(first["events_added"] + first["nodes_written"], 0)
        size = (self.rec.root / "graph" / "nodes.jsonl").stat().st_size
        again = importers.learning_records(self.rec, src)
        self.assertEqual((again["nodes_written"], again["edges_written"], again["events_added"]), (0, 0, 0))
        self.assertEqual((self.rec.root / "graph" / "nodes.jsonl").stat().st_size, size)
        # Dropping a prerequisite in the note removes the edge on the next import.
        gamma = src / "gamma.md"
        gamma.write_text(gamma.read_text(encoding="utf-8").replace('prerequisites: ["probability.density"]',
                                                                   "prerequisites: []"), encoding="utf-8")
        importers.learning_records(self.rec, src)
        self.assertEqual(self.rec.edges(src="capability:probability.gamma-density", type="requires"), [])
        self.rec.rebuild()
        self.assertEqual(self.rec.edges(src="capability:probability.gamma-density", type="requires"), [])

    def test_due_skips_reference_targets_and_sorts_oldest_first(self):
        for key, target in (("a", "core"), ("b", "reference"), ("c", "working")):
            self.rec.put_node(f"capability:{key}", "capability", retention_target=target)
        for key, review in (("a", "2026-10-05"), ("b", "2026-10-01"), ("c", "2026-10-03")):
            self.rec.append("retrieval", f"capability:{key}",
                            {"day": "2026-09-28", "period": "p", "timing": "same-session", "method": "explanation",
                             "outcome": "pass", "assistance": "none", "evidence": "e", "review": review})
        due = graph.Learning(self.rec, date(2026, 10, 5)).due()
        self.assertEqual([d["id"] for d in due], ["capability:c", "capability:a"])


class ResearchTests(Fixture):
    def test_support_and_invalidation(self):
        self.rec.put_node("claim:C1", "claim", text="Width scales with energy")
        self.rec.put_node("experiment:E1", "experiment", status="completed")
        self.rec.put_edge("experiment:E1", "supports", "claim:C1", verdict="supported")
        self.rec.put_edge("paper:P1", "invalidates", "claim:C1")
        got = graph.support(self.rec, "claim:C1")
        self.assertEqual([(s["id"], s["verdict"], s["node"]["status"]) for s in got["supports"]],
                         [("experiment:E1", "supported", "completed")])
        self.assertEqual([(s["id"], s["node"]) for s in got["invalidates"]], [("paper:P1", None)])

    def test_code_links_with_graphify_symbols(self):
        repo = Path(self._tmp.name) / "repo"
        g = repo / "graph.json"
        g.parent.mkdir()
        g.write_text(json.dumps({"nodes": [
            {"id": "n1", "label": "fit_width", "source_file": str(repo / "src" / "a.py").replace("/", "\\")},
            {"id": "n2", "label": "Model", "source_file": str(repo / "src" / "a.py")},
            {"id": "n3", "label": "orphan"}]}), encoding="utf-8")
        self.assertEqual(graph.import_graphify(self.rec, g, repo_root=repo), 2)
        self.rec.put_edge("code-symbol:src/a.py", "implements", "experiment:E1")
        links = graph.code_links(self.rec, "experiment:E1")
        self.assertEqual(links[0]["path"], "src/a.py")
        self.assertIn("Model", links[0]["symbols"])
        bad = repo / "broken.json"
        bad.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            graph.import_graphify(self.rec, bad)


if __name__ == "__main__":
    unittest.main()
