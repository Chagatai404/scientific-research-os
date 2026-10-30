"""The map follows the record: what agents add (a code change, a claim), what the person decides and what they delete show up on
the next read, and a live view of one workspace also watches the records its map spans."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api
from ros.store import Record


class LiveMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"}); env.start(); self.addCleanup(env.stop)
        self.me = Record(Path(self.tmp.name) / "projects" / "me"); self.addCleanup(self.me.close)
        self.rec = Record(Path(self.tmp.name) / "projects" / "demo"); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        api.call("link", self.me, user_wide=True)
        api.call("link", self.rec, project="project:demo")
        self.rec.put_node("project:demo", "project", title="Calorimeter study")

    def nodes(self, rec=None):
        return {n["id"]: n for n in api.call("workspace_map", rec or self.rec)["nodes"]}

    def test_agent_work_and_decisions_appear_and_a_deleted_item_disappears(self):
        self.rec.put_node("claim:resolution", "claim", title="Energy resolution improves with the new fit")
        self.rec.put_edge("claim:resolution", "part-of", "project:demo")
        self.assertNotIn("change:abc", self.nodes())
        # A Code session's change, as workbench.record writes it.
        self.rec.put_node("change:abc", "change", title="Add residual plots to the fit", files=["fit.py"])
        self.rec.put_edge("change:abc", "part-of", "project:demo")
        before = self.nodes()
        self.assertEqual((before["change:abc"]["parent"], before["change:abc"]["category"]), ("project:demo", "research"))
        self.assertNotIn("decision", before["claim:resolution"])
        self.rec.append("decision", "claim:resolution", {"outcome": "revise", "rationale": "Needs the 2017 test beam"}, actor="person")
        decided = self.nodes()["claim:resolution"]
        self.assertEqual(decided["decision"], "revise"); self.assertTrue(decided["tip"].startswith("Decided: revise."))
        api.call("organization_archive", self.rec, subject="claim:resolution")
        self.assertNotIn("claim:resolution", self.nodes(), "a deleted item leaves the map")
        # Knowledge's map spans its projects: the change shows there too.
        self.assertIn("change:abc", self.nodes(self.me))

    def test_a_live_view_watches_the_records_its_map_spans(self):
        watched = api.call("workspace_watched", self.me)
        self.assertIn(str(self.rec.events_path), watched); self.assertIn(str(self.rec.nodes_path), watched)
        self.assertIn(str(self.me.events_path), api.call("workspace_watched", self.rec))
        made = api.call("workspace_create", self.rec, title="Scratch")
        other = Record(Path(self.tmp.name) / "projects" / made["name"])
        try:
            api.call("link", other, project="project:scratch")
        finally:
            other.close()
        self.assertTrue(any(made["name"] in f for f in api.call("workspace_watched", self.me)))
        api.call("workspace_delete", self.rec, workspace=made["name"])
        self.assertFalse(any(made["name"] in f for f in api.call("workspace_watched", self.me)), "a deleted workspace is not watched")


    def test_after_deleting_a_linked_workspace_knowledge_can_restore_its_sessions_and_never_falls_back_to_another_record(self):
        from ros import home, serve
        self.rec.put_node("conversation:asked", "conversation", title="Asked in the project")
        api.call("organization_archive", self.rec, subject="conversation:asked")
        gone = api.call("workspace_organization", self.me)["archived"]
        self.assertEqual([(a["id"], a["record"]) for a in gone], [("conversation:asked", "demo")], "Knowledge lists it, with its owner")
        api.call("organization_archive", self.rec, subject="conversation:asked", archived=False)
        repo = Path(self.tmp.name) / "code"; repo.mkdir()
        home.set_config(self.rec.root, repo=str(repo))
        self.me.put_node("project:demo", "project", title="Calorimeter study")
        pool = serve.Pool(self.me); self.addCleanup(pool.close)
        pool.get("demo")
        api.call("workspace_delete", self.me, workspace="demo")
        self.assertNotIn("project:demo", [f["id"] for f in api.call("workspace_organization", self.me)["folders"]])
        self.assertNotIn("project:demo", self.nodes(self.me), "a deleted workspace's hub leaves Knowledge's map")
        self.assertEqual([r.root.name for r in pool.all()], ["me"], "background workers skip a deleted workspace")
        with self.assertRaisesRegex(ValueError, "is deleted"):
            home.resolve("demo")
        with self.assertRaisesRegex(ValueError, "is deleted"):
            home.resolve(cwd=repo)


if __name__ == "__main__":
    unittest.main()
