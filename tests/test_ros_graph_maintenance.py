"""The living knowledge graph (S8a): derived on every read from the record, maintained by agents through append-only
notes, and read by the tutor. Agents never create assessed evidence, grades, decisions or tasks."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ros import api, graph, home, tasks
from ros.learn import evidence
from ros.store import Record
from ros.tools import graph as graph_tools

AS_OF = "2026-06-15"
NOTE_TOOLS = ("graph_note_add", "graph_note_revise", "graph_note_retract")


def retrieval(day, outcome="pass", review=None, period="p1"):
    return {"day": day, "period": period, "timing": "same-session", "method": "explanation", "outcome": outcome,
            "assistance": "none", "evidence": f"ev-{day}-{outcome}", "review": review}


class Living(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(api.release)
        self.me = Record(Path(self.tmp.name) / "projects" / "me")
        self.demo = Record(Path(self.tmp.name) / "projects" / "demo")
        self.addCleanup(self.me.close)
        self.addCleanup(self.demo.close)
        api.call("link", self.me, user_wide=True)
        api.call("link", self.demo, project="project:demo", title="Calorimeter study")
        me, demo = self.me, self.demo
        for key in "abc":
            me.put_node(f"capability:{key}", "capability", title=f"Cap {key.upper()}")
            me.put_edge(f"capability:{key}", "part-of", "project:demo")
        me.put_edge("capability:b", "requires", "capability:a")
        me.append("retrieval", "capability:a", retrieval("2026-06-01", review="2026-12-01"), actor="importer")
        me.append("retrieval", "capability:b", retrieval("2026-06-01", review="2026-06-20"), actor="importer")
        me.append("retrieval", "capability:b", retrieval("2026-06-05", "fail", "2026-06-10"), actor="importer")
        me.append("retrieval", "capability:c", retrieval("2026-06-01", review="2026-06-15", period="p2"), actor="importer")
        me.put_node("goal:fit", "goal", title="Fit the calorimeter", targets=["capability:b", "capability:c"])
        demo.put_node("conversation:chat", "conversation", title="First chat")
        demo.put_edge("conversation:chat", "part-of", "project:demo")
        demo.put_node("claim:res", "claim", title="Resolution improves")
        demo.put_edge("claim:res", "part-of", "project:demo")
        demo.put_node("conversation:old", "conversation", title="Old chat")
        demo.put_edge("conversation:old", "part-of", "project:demo")
        self.wid = home.workspace_id(demo.root)
        self.ev_b = next(e["id"] for e in me.events(type="retrieval", subject="capability:b"))

    # ---- helpers ----
    def view(self, rec=None, **kw):
        return api.call("graph_view", rec or self.demo, as_of=AS_OF, **({"workspace_id": self.wid} | kw))

    def teach(self, rec=None, **kw):
        return api.call("graph_teaching", rec or self.demo, as_of=AS_OF, **({"workspace_id": self.wid} | kw))

    def add(self, key="k1", kind="concept", title="Why the fit residual matters", text="Residuals show bias.",
            rec=None, **kw):
        args = {"kind": kind, "title": title, "text": text, "key": key, "by": "tutor-agent", "workspace_id": self.wid,
                "evidence": [self.ev_b]} | kw
        return api.call("graph_note_add", rec or self.demo, **args)

    def ids(self, view, kind=None):
        return {n["id"] for n in view["nodes"] if kind is None or n["kind"] == kind}

    def assert_closed(self, view):
        ids = self.ids(view)
        self.assertEqual(len(ids), len(view["nodes"]), "node ids are unique")
        for e in view["edges"]:
            self.assertIn(e["src"], ids, e)
            self.assertIn(e["dst"], ids, e)

    def counts(self, rec):
        out = {}
        for e in rec.events():
            out[e["type"]] = out.get(e["type"], 0) + 1
        return out


class DerivedOnRead(Living):
    def test_the_view_is_built_from_the_record_with_assessed_states(self):
        v = self.view()
        self.assertEqual(v["schema"], "ros.living-graph.v1")
        kinds = {n["id"]: n for n in v["nodes"]}
        self.assertEqual(kinds["capability:a"]["signal"], "known")
        self.assertEqual(kinds["capability:b"]["signal"], "shaky")
        self.assertTrue(kinds["capability:c"]["due"])
        self.assertIn("goal:fit", kinds)
        self.assertIn(self.wid, kinds)
        self.assertTrue(any(n["kind"] == "conversation" for n in v["nodes"]))
        self.assertTrue(any(n["kind"] == "claim" for n in v["nodes"]))
        self.assertIn(("capability:b", "capability:a", "requires"),
                      {(e["src"], e["dst"], e["type"]) for e in v["edges"]})
        self.assert_closed(v)

    def test_nothing_is_stored_a_note_free_record_gains_no_events_from_reading(self):
        before = self.counts(self.me), self.counts(self.demo)
        self.view(); self.teach(); self.view(scope="personal")
        self.assertEqual(before, (self.counts(self.me), self.counts(self.demo)))


class Maintenance(Living):
    def test_add_revise_retract_keep_identity_and_history(self):
        made = self.add()
        note = made["note"]
        self.assertEqual((made["revision"], made["replayed"]), (1, False))
        node = next(n for n in self.view()["nodes"] if n["id"] == note)
        self.assertEqual((node["kind"], node["note_kind"], node["revision"]), ("note", "concept", 1))
        self.assertEqual(node["added_by"], "agent:tutor-agent")
        rev = api.call("graph_note_revise", self.demo, note=note, key="r1", by="tutor-agent", work=["conversation:chat"],
                       text="Residuals show bias and variance.", workspace_id=self.wid)
        self.assertEqual((rev["note"], rev["revision"]), (note, 2))
        node = next(n for n in self.view()["nodes"] if n["id"] == note)
        self.assertEqual((node["text"], node["revision"]), ("Residuals show bias and variance.", 2))
        self.assertEqual(len([n for n in self.view()["nodes"] if n["kind"] == "note"]), 1)
        gone = api.call("graph_note_retract", self.demo, note=note, key="x1", by="tutor-agent", evidence=[self.ev_b],
                        reason="The learner showed this is understood", workspace_id=self.wid)
        self.assertEqual(gone["retracted"], True)
        self.assertNotIn(note, self.ids(self.view()))
        history = [e["type"] for e in self.me.events(type="graph.note") + self.demo.events(type="graph.note")]
        self.assertEqual(sorted(history), ["graph.note.added", "graph.note.retracted", "graph.note.revised"])
        with self.assertRaisesRegex(ValueError, "retracted"):
            api.call("graph_note_revise", self.demo, note=note, key="r2", by="tutor-agent", evidence=[self.ev_b],
                     title="Back again", workspace_id=self.wid)

    def test_a_stale_base_revision_is_refused(self):
        note = self.add()["note"]
        api.call("graph_note_revise", self.demo, note=note, key="r1", by="a", evidence=[self.ev_b], title="Second")
        with self.assertRaisesRegex(ValueError, "stale"):
            api.call("graph_note_revise", self.demo, note=note, key="r2", by="a", evidence=[self.ev_b],
                     title="Third", base=1)

    def test_a_key_makes_a_write_idempotent_and_a_changed_payload_is_refused(self):
        first = self.add()
        again = self.add()
        self.assertEqual((again["note"], again["replayed"]), (first["note"], True))
        total = sum(self.counts(r).get("graph.note.added", 0) for r in (self.me, self.demo))
        self.assertEqual(total, 1)
        with self.assertRaisesRegex(ValueError, "key"):
            self.add(text="Something else")
        rev = dict(note=first["note"], key="r", by="a", evidence=[self.ev_b], text="Newer")
        one = api.call("graph_note_revise", self.demo, **rev)
        self.assertEqual(api.call("graph_note_revise", self.demo, **rev), dict(one, replayed=True))
        api.call("graph_note_revise", self.demo, note=first["note"], key="r2", by="a", evidence=[self.ev_b], text="Newest")
        self.assertEqual(api.call("graph_note_revise", self.demo, **rev)["revision"], 3, "a replay never reverts a newer text")
        total = sum(self.counts(r).get("graph.note.revised", 0) for r in (self.me, self.demo))
        self.assertEqual(total, 2)

    def test_notes_link_to_the_graph_and_dangling_links_are_never_shown(self):
        self.me.put_node("concept:residual", "concept", title="Residual")
        note = self.add(links=[{"type": "about", "target": "capability:b"},
                               {"type": "requires", "target": "capability:a"},
                               {"type": "relates", "target": "concept:residual"}])["note"]
        v = self.view()
        edges = {(e["src"], e["dst"], e["type"], e["origin"]) for e in v["edges"]}
        self.assertIn((note, "capability:b", "about", "note"), edges)
        self.assertIn((note, "concept:residual", "relates", "note"), edges)
        self.me.delete_node("concept:residual")
        v = self.view()
        self.assert_closed(v)
        self.assertNotIn("concept:residual", self.ids(v))
        with self.assertRaisesRegex(ValueError, "no such"):
            self.add(key="k2", links=[{"type": "about", "target": "capability:none"}])

    def test_a_note_can_link_to_another_note_and_a_retraction_removes_the_edge(self):
        a = self.add(key="a", kind="prerequisite", title="Mean first")["note"]
        b = self.add(key="b", kind="concept", title="Variance",
                     links=[{"type": "requires", "target": a}])["note"]
        self.assertIn((b, a), {(e["src"], e["dst"]) for e in self.view()["edges"]})
        api.call("graph_note_retract", self.demo, note=a, key="ra", by="x", evidence=[self.ev_b], reason="wrong")
        v = self.view()
        self.assertNotIn(a, self.ids(v))
        self.assert_closed(v)


class AuthorityBoundary(Living):
    def test_note_tools_are_agent_tools_not_human_acts(self):
        for name in NOTE_TOOLS + ("graph_view", "graph_teaching"):
            self.assertFalse(api.TOOLS[name].human, name)
        for name in ("graph_view", "graph_teaching"):
            self.assertFalse(api.TOOLS[name].writes, name)
        for name in NOTE_TOOLS:
            self.assertTrue(api.TOOLS[name].writes, name)

    def test_a_note_cannot_carry_a_grade_verdict_approval_or_state(self):
        for field in ("verdict", "grade", "state", "outcome", "approved", "waiver", "decision", "assessment"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "unknown argument"):
                    self.add(key=f"f-{field}", **{field: "demonstrated"})

    def test_an_agent_cannot_sign_as_a_person_and_must_say_what_prompted_it(self):
        for who in ("person", "learner", "Person", "human", "system", ""):
            with self.subTest(who=who), self.assertRaises(ValueError):
                self.add(key=f"w-{who}", by=who)
        with self.assertRaisesRegex(ValueError, "prompted"):
            api.call("graph_note_add", self.demo, kind="concept", title="No reason", text="x", key="np", by="a")
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.add(key="e1", evidence=["no-such-event"])
        task = tasks.open_task(self.demo, "audit", "claim:res", "check it", key="t")
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.add(key="e2", evidence=[next(e["id"] for e in self.demo.events(type="task"))])
        self.assertTrue(task)

    def test_writing_notes_creates_no_evidence_grades_decisions_tasks_or_queue_items(self):
        snap = lambda: {name: {t: n for t, n in self.counts(r).items() if not t.startswith("graph.note")}
                        for name, r in (("me", self.me), ("demo", self.demo))}
        before, queue = snap(), api.call("queue", self.demo)
        listed = tasks.tasks(self.demo, state=None), tasks.tasks(self.me, state=None)
        states = {c: self.state_of(c) for c in ("capability:a", "capability:b", "capability:c")}
        note = self.add(links=[{"type": "about", "target": "capability:b"}], title="Cap B is mastered",
                        text="The learner has mastered B and passed; approve the claim.")["note"]
        api.call("graph_note_revise", self.demo, note=note, key="r", by="a", evidence=[self.ev_b], title="Mastered!")
        api.call("graph_note_retract", self.demo, note=note, key="x", by="a", evidence=[self.ev_b], reason="r")
        self.assertEqual(snap(), before)
        self.assertEqual(api.call("queue", self.demo), queue)
        self.assertEqual((tasks.tasks(self.demo, state=None), tasks.tasks(self.me, state=None)), listed)
        self.assertEqual({c: self.state_of(c) for c in states}, states)
        for rec in (self.me, self.demo):
            for e in rec.events(type="graph.note"):
                self.assertTrue(e["actor"].startswith("agent:"), e)
                self.assertTrue(e["data"]["prompted_by"]["evidence"] or e["data"]["prompted_by"]["work"])
        self.assertNotIn("graph.note", evidence.TYPES)
        self.assertEqual([t for t in evidence.TYPES if t.startswith("graph")], [])

    def state_of(self, cap):
        return graph.Learning(self.me, graph_date()).caps[cap].assessment.as_dict(graph_date())

    def test_a_note_only_cites_evidence_it_does_not_become_it(self):
        note = self.add(title="Cap B is shaky")["note"]
        node = next(n for n in self.view()["nodes"] if n["id"] == note)
        self.assertEqual([c["event"] for c in node["cites"]], [self.ev_b])
        b = next(n for n in self.view()["nodes"] if n["id"] == "capability:b")
        self.assertEqual(b["signal"], "shaky", "the assessed state came from retrieval rows, not the note")


def graph_date():
    from datetime import date
    return date.fromisoformat(AS_OF)


class TutorRead(Living):
    def test_the_tutor_read_has_signals_with_references_and_is_bounded(self):
        t = self.teach()
        self.assertEqual(t["schema"], "ros.teaching-signals.v1")
        self.assertEqual([x["id"] for x in t["known"]], ["capability:a", "capability:c"])
        self.assertEqual([x["id"] for x in t["shaky"]], ["capability:b"])
        self.assertIn("capability:c", [x["id"] for x in t["due"]])
        gaps = {g["goal"]: g for g in t["goal_gaps"]}
        self.assertEqual(sorted(m["id"] for m in gaps["goal:fit"]["missing"]), ["capability:b"])
        self.assertEqual(t["totals"]["shaky"], 1)
        small = self.teach(limit=1)
        self.assertTrue(all(len(small[k]) <= 1 for k in ("known", "shaky", "due", "goal_gaps", "misconceptions", "next")))

    def test_revising_and_retracting_a_note_changes_what_the_tutor_is_told(self):
        note = self.add(kind="misconception", title="Residuals are noise",
                        text="The learner thinks residuals are noise.",
                        links=[{"type": "misconception-of", "target": "capability:b"}])["note"]
        t = self.teach()
        self.assertEqual([m["note"] for m in t["misconceptions"]], [note])
        self.assertEqual(t["misconceptions"][0]["text"], "The learner thinks residuals are noise.")
        self.assertEqual(t["misconceptions"][0]["about"], ["capability:b"])
        self.assertEqual(t["shaky"][0]["notes"][0]["note"], note)
        api.call("graph_note_revise", self.demo, note=note, key="r", by="tutor-agent", evidence=[self.ev_b],
                 text="Residuals carry the bias; the learner is half right.")
        t2 = self.teach()
        self.assertEqual(t2["misconceptions"][0]["text"], "Residuals carry the bias; the learner is half right.")
        self.assertEqual(t2["misconceptions"][0]["revision"], 2)
        self.assertNotEqual(t, t2)
        api.call("graph_note_retract", self.demo, note=note, key="x", by="tutor-agent", evidence=[self.ev_b], reason="resolved")
        t3 = self.teach()
        self.assertEqual(t3["misconceptions"], [])
        self.assertEqual(t3["shaky"][0].get("notes", []), [])

    def test_goal_notes_add_goal_gaps_and_the_gap_closes_when_the_work_is_learned(self):
        note = self.add(kind="goal", title="Be able to defend the fit",
                        links=[{"type": "aims-at", "target": "capability:a"}, {"type": "aims-at", "target": "capability:b"}])["note"]
        gaps = {g["goal"]: g for g in self.teach()["goal_gaps"]}
        self.assertEqual([m["id"] for m in gaps[note]["missing"]], ["capability:b"])
        self.me.append("retrieval", "capability:b", retrieval("2026-06-14", review="2026-12-30", period="p3"), actor="importer")
        self.me.append("retrieval", "capability:b", retrieval("2026-06-15", review="2026-12-30", period="p4"), actor="importer")
        gaps = {g["goal"]: g for g in self.teach()["goal_gaps"]}
        self.assertNotIn(note, gaps)


class AcceptanceAC20(Living):
    def setUp(self):
        super().setUp()
        made = api.call("workspace_create", self.demo, title="Scratch")
        self.scratch = Record(Path(self.tmp.name) / "projects" / made["name"])
        self.addCleanup(self.scratch.close)
        self.scratch_name = made["name"]
        api.call("link", self.scratch, project="project:scratch", title="Scratch")
        self.me.put_node("capability:s", "capability", title="Scratch skill")
        self.me.put_edge("capability:s", "part-of", "project:scratch")
        self.me.append("retrieval", "capability:s", retrieval("2026-06-01", review="2026-12-01"), actor="importer")
        self.scratch.put_node("conversation:s1", "conversation", title="Scratch chat")
        self.scratch.put_edge("conversation:s1", "part-of", "project:scratch")
        self.swid = home.workspace_id(self.scratch.root)

    def clients(self):
        fresh_me, fresh_demo = Record(self.me.root), Record(self.demo.root)
        self.addCleanup(fresh_me.close)
        self.addCleanup(fresh_demo.close)
        return [self.me, self.demo, fresh_me, fresh_demo]

    def test_the_graph_adapts_when_agents_and_people_change_things_and_every_client_agrees(self):
        queue_before = api.call("queue", self.me)
        open_before = tasks.tasks(self.me, state=None) + tasks.tasks(self.demo, state=None)
        keep = self.add(key="keep", kind="prerequisite", title="Mean before variance",
                        links=[{"type": "prerequisite-for", "target": "capability:b"}])["note"]
        drop = self.add(key="drop", kind="misconception", title="Averages are always typical",
                        links=[{"type": "misconception-of", "target": "capability:a"}])["note"]
        revised = self.add(key="rev", kind="concept", title="Residual", text="first")["note"]
        scratch_note = self.add(key="scr", title="Scratch idea", workspace_id=self.swid, rec=self.scratch)["note"]
        teach_before = self.teach()
        self.assertEqual([m["note"] for m in teach_before["misconceptions"]], [drop])
        api.call("graph_note_revise", self.scratch, note=revised, key="rev1", by="tutor-agent", evidence=[self.ev_b],
                 text="second", workspace_id=self.wid)
        api.call("graph_note_retract", self.me, note=drop, key="drop1", by="tutor-agent", evidence=[self.ev_b],
                 reason="The learner corrected this", workspace_id=self.wid)
        mid = self.view(scope="personal")
        self.assertIn(scratch_note, self.ids(mid))
        self.assertIn("capability:s", self.ids(mid))
        # A work item is deleted in two ways: hidden by the person, and removed from the record.
        api.call("organization_archive", self.demo, subject="conversation:old")
        self.demo.delete_node("claim:res")
        # A workspace is deleted.
        api.call("workspace_delete", self.demo, workspace=self.scratch_name)

        views = []
        for rec in self.clients():
            views.append((self.view(rec), self.view(rec, scope="personal"), self.teach(rec)))
        for other in views[1:]:
            self.assertEqual(json.dumps(other, sort_keys=True), json.dumps(views[0], sort_keys=True))
        ws, personal, teach = views[0]
        for v in (ws, personal):
            self.assert_closed(v)
            ids = self.ids(v)
            self.assertNotIn(drop, ids)
            self.assertNotIn(scratch_note, ids)
            for gone in ("capability:s", self.swid, "project:scratch"):
                self.assertNotIn(gone, ids)
            self.assertFalse([i for i in ids if "conversation:old" in i or "claim:res" in i or "conversation:s1" in i], ids)
        self.assertIn(keep, self.ids(ws))
        self.assertIn(revised, self.ids(ws))
        self.assertEqual(next(n for n in ws["nodes"] if n["id"] == revised)["text"], "second")
        self.assertTrue([i for i in self.ids(ws) if "conversation:chat" in i])
        with self.assertRaises(ValueError):
            self.view(workspace_id=self.swid)
        self.assertEqual(teach["misconceptions"], [])
        self.assertNotEqual(teach_before["misconceptions"], teach["misconceptions"])
        self.assertEqual(api.call("queue", self.me), queue_before)
        self.assertEqual(tasks.tasks(self.me, state=None) + tasks.tasks(self.demo, state=None), open_before)
        # Restoring the workspace brings its work back, still without a stored copy.
        api.call("workspace_restore", self.demo, workspace=self.scratch_name)
        back = self.view(self.me, scope="personal")
        self.assertIn("capability:s", self.ids(back))
        self.assert_closed(back)

    def test_the_mcp_client_reads_the_same_graph(self):
        from ros import mcp
        server = mcp.Server("demo")
        self.addCleanup(lambda: [r.close() for r in server.records.values()])
        self.add()
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "graph_view", "arguments": {"workspace_id": self.wid, "as_of": AS_OF}}})
        self.assertFalse(reply["result"]["isError"], reply)
        self.assertEqual(json.loads(reply["result"]["content"][0]["text"]), json.loads(json.dumps(self.view())))
        written = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "graph_note_add", "arguments": {"kind": "concept", "title": "Via MCP", "text": "x", "key": "mcp",
                                                    "by": "claude", "evidence": [self.ev_b], "workspace_id": self.wid}}})
        self.assertFalse(written["result"]["isError"], written)
        self.assertIn(written["result"]["structuredContent"]["note"], self.ids(self.view()))
        tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertTrue(set(NOTE_TOOLS) <= names)


class Removal(Living):
    def work(self, v):
        return {n["ref"]["entity_id"] for n in v["nodes"] if "::" in n["id"]}

    def test_a_hidden_work_item_and_a_removed_one_leave_with_their_edges(self):
        self.assertEqual(self.work(self.view()), {"conversation:chat", "conversation:old", "claim:res"})
        api.call("organization_archive", self.demo, subject="conversation:old")
        self.assertEqual(self.work(self.view()), {"conversation:chat", "claim:res"})
        self.demo.delete_node("claim:res")
        v = self.view()
        self.assertEqual(self.work(v), {"conversation:chat"})
        self.assert_closed(v)
        api.call("organization_archive", self.demo, subject="conversation:old", archived=False)
        self.assertIn("conversation:old", self.work(self.view()), "restoring brings it back: nothing was stored")

    def test_a_note_citing_removed_work_keeps_its_history_but_never_dangles(self):
        note = self.add(work=["conversation:old"], links=[{"type": "relates", "target": "capability:b"}])["note"]
        api.call("organization_archive", self.demo, subject="conversation:old")
        v = self.view()
        self.assert_closed(v)
        self.assertIn(note, self.ids(v))

    def test_a_personal_note_lives_in_knowledge_and_shows_in_the_personal_view(self):
        knowledge = home.workspace_id(self.me.root)
        note = self.add(key="p", workspace_id=knowledge, title="How I learn best")["note"]
        self.assertIn(note, self.ids(self.view(scope="personal")))
        self.assertIn(note, self.ids(self.view(workspace_id=knowledge)))
        self.assertNotIn(note, self.ids(self.view()), "another workspace does not see it")
        self.assertEqual(next(n for n in self.view(scope="personal")["nodes"] if n["id"] == note)["ref"]["owner_record"], "me")

    def test_deleting_a_workspace_hides_its_notes_and_forbids_changing_them(self):
        made = api.call("workspace_create", self.demo, title="Scratch")
        other = Record(Path(self.tmp.name) / "projects" / made["name"])
        self.addCleanup(other.close)
        api.call("link", other, project="project:scratch", title="Scratch")
        swid = home.workspace_id(other.root)
        note = self.add(key="s", workspace_id=swid)["note"]
        self.assertIn(note, self.ids(self.view(workspace_id=swid)))
        api.call("workspace_delete", self.demo, workspace=made["name"])
        self.assertNotIn(note, self.ids(self.view(scope="personal")))
        with self.assertRaises(KeyError):
            api.call("graph_note_retract", self.demo, note=note, key="z", by="a", evidence=[self.ev_b], reason="x")
        with self.assertRaises(ValueError):
            self.add(key="again", workspace_id=swid)
        api.call("workspace_restore", self.demo, workspace=made["name"])
        self.assertIn(note, self.ids(self.view(workspace_id=swid)))


class Scale(Living):
    def test_reads_use_the_indexed_and_incremental_views_not_a_walk_of_the_event_log(self):
        self.add()
        self.view(); self.teach()
        with patch.object(Record, "events", side_effect=AssertionError("a read scanned the event log")):
            self.view(); self.teach(); self.view(scope="personal")

    def test_the_tutor_read_counts_everything_even_when_the_view_is_cut(self):
        # 40 more capabilities than a 20-node view can show, and a goal gap whose id sorts last
        for i in range(40):
            self.me.put_node(f"capability:x{i:02d}", "capability", title=f"X{i}")
            self.me.put_edge(f"capability:x{i:02d}", "part-of", "project:demo")
            if i % 2 == 0:
                self.me.append("retrieval", f"capability:x{i:02d}", retrieval("2026-06-01", review="2026-12-01"), actor="importer")
        self.me.put_node("capability:zz", "capability", title="Last by name")
        self.me.put_edge("capability:zz", "part-of", "project:demo")
        self.me.put_node("goal:zz", "goal", title="Reach the last", targets=["capability:zz"])
        t = self.teach(limit=50)
        self.assertEqual(t["totals"]["known"], 2 + 20)
        self.assertFalse(t["limits"]["graph_truncated"])
        gaps = {g["goal"]: [m["id"] for m in g["missing"]] for g in t["goal_gaps"]}
        self.assertEqual(gaps["goal:zz"], ["capability:zz"])
        self.assertTrue(self.view(limit=20)["truncated"], "the picture is cut, the tutor's counts are not")

    def test_the_personal_view_says_when_it_left_workspaces_out_and_keeps_knowledge(self):
        note = self.add(key="p", workspace_id=home.workspace_id(self.me.root))["note"]
        with patch.object(graph_tools, "PERSONAL_WORKSPACES", 1):
            v = self.view(scope="personal")
        self.assertIn(note, self.ids(v), "the person's own Knowledge is the one always kept")
        self.assertEqual(v["truncated"], {"workspaces_omitted": 1})
        self.assertNotIn(self.wid, self.ids(v))

    def test_the_view_is_bounded(self):
        for i in range(30):
            self.me.put_node(f"capability:x{i}", "capability", title=f"X{i}")
            self.me.put_edge(f"capability:x{i}", "part-of", "project:demo")
        v = self.view(limit=20)
        self.assertLessEqual(len(v["nodes"]), 20)
        self.assertTrue(v["truncated"])
        self.assert_closed(v)


if __name__ == "__main__":
    unittest.main()
