"""The user-wide knowledge graph, a project's research graph, and the link between them."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, cli, context, home, importers  # noqa: E402
from ros.store import Record  # noqa: E402


class Graphs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        os.environ["ROS_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "ROS_HOME", None)
        self.addCleanup(context.release)  # the user-wide record kept open for project records
        self.user = Record(home.init("knowledge"))
        self.addCleanup(self.user.close)
        self.proj = Record(home.init("ams"))
        self.addCleanup(self.proj.close)
        # the user's knowledge: a capability under a subject
        self.user.put_node("capability:physics.energy", "capability", title="Energy accounting")
        self.user.put_node("subject:physics", "subject", title="Physics")
        self.user.put_edge("capability:physics.energy", "part-of", "subject:physics")
        # the project's research: an experiment needing that capability and one the user has no record of
        self.proj.put_node("experiment:E1", "experiment", title="Run", status="planned", authorization="awaiting")
        self.proj.put_edge("experiment:E1", "requires", "capability:physics.energy", relation="learning_dependencies")
        self.proj.put_edge("experiment:E1", "requires", "capability:physics.unknown-yet", relation="learning_dependencies")

    def test_a_projects_context_joins_its_research_to_what_the_user_knows(self):
        out = api.call("link", self.proj, user="knowledge", project="project:ams")
        self.assertEqual((out["role"], out["user"]), ("project", "knowledge"))
        ctx = api.call("context", self.proj)
        self.assertEqual(ctx["research"]["next_steps"], {"approval-required": ["experiment:E1"]})
        states = {c["capability"]: c["state"] for c in ctx["needs"]["capabilities"]}
        self.assertEqual(states, {"capability:physics.energy": "unknown", "capability:physics.unknown-yet": "untracked"})
        self.assertEqual(ctx["needs"]["summary"], {"unknown": 1, "untracked": 1})  # known but unassessed, versus not in the graph
        self.assertEqual(ctx["needs"]["capabilities"][0]["needed_by"], ["experiment:E1"])

    def test_the_user_wide_context_lists_every_linked_project(self):
        api.call("link", self.proj, user="knowledge", project="project:ams")
        ctx = api.call("context", self.user)
        self.assertEqual(ctx["role"], "user")  # linking marks the user-wide record
        self.assertEqual(ctx["knowledge"]["capabilities"], 1)
        self.assertEqual(ctx["knowledge"]["subject"], 1)
        self.assertEqual([(p["record"], p["waiting_for_you"]) for p in ctx["projects"]], [("ams", 1)])

    def test_an_unlinked_record_says_so_and_bad_links_are_refused(self):
        ctx = api.call("context", self.proj)
        self.assertEqual(ctx["role"], "unlinked")
        self.assertIn("link --user", ctx["note"])
        with self.assertRaises(ValueError):
            api.call("link", self.proj, user="ams")  # itself
        with self.assertRaises(ValueError):
            api.call("link", self.proj, user="knowledge", project="ams")  # not project:<key>
        with self.assertRaises(ValueError):
            api.call("link", self.proj, user="nonexistent")  # no such record
        api.call("link", self.proj, user="knowledge")
        with self.assertRaises(ValueError):
            api.call("link", self.user, user="ams")  # a project record is not the user-wide one

    def test_documents_become_sources_about_their_project_and_importing_twice_adds_nothing(self):
        docs = self.home / "reports"
        docs.mkdir()
        (docs / "2026-09-29_dependency_analysis.md").write_text("# Dependency analysis\n\nbody\n", encoding="utf-8")
        (docs / "notes.md").write_text("no heading here\n", encoding="utf-8")
        first = importers.documents(self.proj, docs, "project:ams")
        self.assertEqual(first["documents"], 2)
        src = self.proj.node("source:reports-2026-09-29_dependency_analysis")
        self.assertEqual((src["title"], src["date"], src["collection"]), ("Dependency analysis", "2026-09-29", "reports"))
        self.assertIsNotNone(self.proj.node("project:ams"))  # the hub exists, so `about` points at something
        self.assertEqual(self.proj.edges(src="source:reports-notes", type="about")[0]["dst"], "project:ams")
        again = importers.documents(self.proj, docs, "project:ams")
        self.assertEqual((again["nodes_written"], again["edges_written"]), (0, 0))

    def test_a_new_course_or_project_joins_the_graphs_with_its_hubs(self):
        api.call("link", self.user, user_wide=True)
        out = api.call("link", self.proj, project="course:stat303", title="STAT303 Mathematical Statistics I")
        self.assertEqual((out["role"], out["user"], out["project"]), ("project", "knowledge", "course:stat303"))
        for rec in (self.user, self.proj):  # the hub exists in both, so part-of and about point at something
            self.assertEqual(rec.node("course:stat303")["title"], "STAT303 Mathematical Statistics I")
        self.assertEqual(api.call("link", self.user)["role"], "user")  # asking again changes nothing
        other = Record(home.init("pave"))
        self.addCleanup(other.close)
        self.assertEqual(api.call("link", other)["project"], "project:pave")  # the default hub is the record's name
        self.assertEqual(self.user.node("project:pave")["title"], "Pave")

    def test_there_is_one_user_wide_record_and_a_project_is_told_when_there_is_none(self):
        with self.assertRaises(ValueError) as cm:
            api.call("link", self.proj)
        self.assertIn("--user-wide", str(cm.exception))
        api.call("link", self.user, user_wide=True)
        with self.assertRaises(ValueError) as cm:
            api.call("link", self.proj, user_wide=True)  # a second one
        self.assertIn("already the user-wide record", str(cm.exception))
        with self.assertRaises(ValueError):
            api.call("link", self.proj, project="pave")  # not project:<key> or course:<key>

    def test_ros_init_sets_a_new_record_up_and_says_why_when_it_cannot(self):
        def init(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["init", *argv, "--json"]), 0)
            return json.loads(out.getvalue())
        self.assertIn("no user-wide record yet", init("early")["setup"]["note"])
        self.assertEqual(init("me", "--user-wide")["setup"], {"role": "user"})
        self.assertEqual(init("stat303", "--kind", "course", "--title", "STAT303")["setup"],
                         {"role": "project", "user": "me", "project": "course:stat303"})
        self.assertEqual(home.config(self.home / "projects" / "stat303")["user"], "me")
        self.assertNotIn("setup", init("loose", "--no-link"))
        with contextlib.closing(Record(self.home / "projects" / "me")) as me:
            self.assertEqual(me.node("course:stat303")["title"], "STAT303")

    def test_a_records_default_plan_includes_the_capabilities_tagged_with_its_hub(self):
        api.call("link", self.user, user_wide=True)
        api.call("link", self.proj, project="course:c1")
        self.user.put_node("capability:a", "capability", title="A")
        self.user.put_edge("capability:a", "part-of", "course:c1")
        out = api.call("roadmap", self.proj)
        self.assertIn("capability:a", [s["capability"] for s in out["steps"]])  # beside what its research requires

    def test_migrate_names_the_research_documents_it_leaves_out(self):
        vault = self.home / "vault"
        (vault / "01 Projects" / "P" / "Research Records").mkdir(parents=True)
        (vault / "01 Projects" / "P" / "Research Records" / "a.md").write_text("# A\n", encoding="utf-8")
        (vault / "01 Projects" / "P" / "Research Records" / "b.md").write_text("---\nresearch_schema: 1\n---\n", encoding="utf-8")
        warnings = importers._skipped_documents(vault)
        self.assertEqual(len(warnings), 1)
        self.assertIn("1 Markdown document(s) in '01 Projects/P/Research Records'", warnings[0])  # the registry record is not counted
        self.assertIn("--kind documents", warnings[0])

    def test_a_tools_project_argument_is_not_the_record_selector(self):
        self.proj.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["-p", "ams", "claims", "--project", "stat303", "--json"])
        self.assertEqual((code, json.loads(out.getvalue())), (0, []))
        self.assertFalse((self.home / "projects" / "stat303").exists())  # it did not become a record


if __name__ == "__main__":
    unittest.main()
