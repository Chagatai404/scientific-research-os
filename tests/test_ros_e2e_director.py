"""The whole workflow by prompting alone. A scripted agent speaks only JSON-RPC to the MCP server; a scripted person acts
only through the portal's HTTP API (the way a browser does); the runner is driven by explicit ticks. Nothing else touches
the record. What the person asked for, and the judgements they make, are all that is theirs."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import automation, home, mcp, runner, serve, tasks, vault  # noqa: E402
from ros.lib import pdf  # noqa: E402
from ros.store import Record  # noqa: E402

LECTURE = {
    "gist": "Variance is the average squared distance of a value from the mean of the distribution.",
    "recall": ("Answer each from memory first.\n\n:::question\nWhat does variance measure?\n=== answer\nSpread around the mean.\n:::\n\n"
               ":::question\nWhy squared?\n=== answer\nSo signs do not cancel.\n:::\n\n"
               ":::question\nWhat is $\\mathrm{Var}(aX+b)$?\n=== answer\n$a^2\\mathrm{Var}(X)$.\n:::\n"),
    "lecture": " ".join(["Two classes can share a mean and still differ in how widely their marks are spread."] * 20)
    + "\n\n:::definition Variance\nThe mean squared distance from the mean, $\\sigma^2=E[(X-\\mu)^2]$.\n:::\n\n"
    ":::example Scaling\nLet $Y=3X$. What is $\\mathrm{Var}(Y)$?\n=== solution\n$9\\,\\mathrm{Var}(X)$.\n:::\n",
    "derivation": " ".join(["Compare each value of Y with its mean and the shift cancels, leaving a times the deviation of X."] * 6)
    + "\n\n$$\\mathrm{Var}(aX+b)=a^2\\mathrm{Var}(X)$$",
}
FORBIDDEN_FOR_AGENTS = {"request_audits", "precheck", "bundle_tasks", "vault_sync", "export", "roadmap_tasks", "reconcile",
                        "handout_build", "handout_attach", "job_done", "vault_review"}


class Scenario(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        os.environ.pop("RESEARCH_OS_VOICE_ENVS", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        for patch in (mock.patch.object(automation, "SETTLE_SECONDS", 0), mock.patch.object(automation, "LEGACY_EVERY", 0)):
            patch.start()
            self.addCleanup(patch.stop)
        self.vault = self.tmp / "Vault"
        self.vault.mkdir()
        (self.vault / "My own note.md").write_text("# mine\n")
        home.set_settings(vault=str(self.vault), director_name="Ada")
        self.server = mcp.Server(None)  # no record exists yet: a person starting from nothing
        self.addCleanup(lambda: [r.close() for r in self.server.records.values()])
        self.calls: list[str] = []
        self.id = 0

    # ---- the agent: JSON-RPC only ------------------------------------------------------------------------------------
    def rpc(self, method, params=None):
        self.id += 1
        return self.server.handle({"jsonrpc": "2.0", "id": self.id, "method": method, "params": params or {}})

    def call(self, name, record=None, **args):
        self.calls.append(name)
        reply = self.rpc("tools/call", {"name": name, "arguments": {**args, **({"record": record} if record else {})}})
        self.assertIn("result", reply, reply)
        self.assertFalse(reply["result"]["isError"], (name, args, reply["result"]["content"]))
        return reply["result"].get("structuredContent")

    def work_all(self, by="agent:claude", **kw):
        """The agent's loop: take a task, do what the skill says, finish it; until none is left."""
        done = []
        while True:
            got = self.call("work", by=by, **kw)
            if got.get("task") is None:
                return done
            done.append(got)
            yield_ = (yield_task := got)  # noqa: F841
            self.do(got)
            self.call("finish", task=got["task"]["id"], result=self.result_for(got), by=by, record=got["use_record"])

    def result_for(self, got):
        return {"candidates": [{"title": f"Paper on {got['task'].get('facet')}", "doi": f"10.1/{got['task'].get('facet')}"}]} \
            if got["task"]["kind"] == "scout" else "done"

    do = lambda self, got: None  # noqa: E731

    # ---- the person: the portal's HTTP API --------------------------------------------------------------------------
    def portal(self):
        httpd = serve.start(self.server.record(None), 0)
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close()))
        return httpd.server_address[1]

    def person(self, port, tool, record, **args):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", f"/api/{tool}", body=json.dumps({"record": record, **args}),
                  headers={"Host": f"127.0.0.1:{port}", "X-ROS": "1", "Sec-Fetch-Site": "same-origin"})
        r = c.getresponse()
        body = json.loads(r.read())
        c.close()
        return r.status, body

    def fetch(self, port, path):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def tick(self, scan=True):
        return runner.Runner(self.server.everything).tick_once(scan=scan)

    def jobs(self):
        return runner.Runner(self.server.everything).run_jobs_once(limit=5)

    def notes(self, *parts):
        return sorted((self.vault / "Research OS").joinpath(*parts).rglob("*.md"))


class CourseByPrompting(Scenario):
    def test_teach_me_a_course(self):
        # 1. the agent is told what to do, and the person says what they want
        listed = self.rpc("prompts/list")["result"]["prompts"]
        self.assertIn("learn", {p["name"] for p in listed})
        prompt = self.rpc("prompts/get", {"name": "learn", "arguments": {"what": "STAT303"}})["result"]
        self.assertIn("STAT303", prompt["messages"][0]["content"]["text"])
        brief = self.call("brief")
        self.assertIn("record", brief)  # the record that holds what the person knows was made for them
        out = self.call("engage", intent="teach me STAT303", materials="the course syllabus")
        self.assertEqual((out["kind"], out["hub"]), ("course", "course:stat303"))
        inbox = self.vault / out["vault"]["inbox"]
        self.assertTrue(inbox.is_dir())

        # 2. the agent outlines the course; the record prepares everything else on its own
        got = self.call("work", by="agent:claude", kinds=["outline"])
        self.assertEqual((got["skill"], got["role"]), ("prepare", "librarian"))
        for key, title, req in (("mean", "Mean", None), ("variance", "Variance", "mean")):
            self.call("add_node", id=f"capability:{key}", type="capability", data={"title": title}, record="me")
            self.call("add_edge", src=f"capability:{key}", type="part-of", dst="course:stat303", record="me")
            if req:
                self.call("add_edge", src=f"capability:{key}", type="requires", dst=f"capability:{req}", record="me")
        self.call("finish", task=got["task"]["id"], result="2 capabilities", by="agent:claude", record="me")
        self.tick()
        user = self.server.record("me")
        self.assertEqual([t["capability"] for t in tasks.tasks(user, "bundle")], ["capability:mean"])
        lectures = [n for n in user.nodes(type="handout") if n["kind"] == "lecture"]
        self.assertEqual(len(lectures), 1)

        # 3. the agent writes the lecture note; the note, the PDF and the vault follow on their own
        task = self.call("work", by="agent:claude", kinds=["handout"])
        self.assertEqual(task["skill"], "prepare")
        hid = task["task"]["handout"]
        read = self.call("handout_read", handout=hid, record=task["use_record"])
        self.assertEqual(read["context"]["capabilities"][0]["title"], "Mean")
        for role, text in LECTURE.items():
            self.call("handout_write", handout=hid, section=role, text=text, by="agent:claude", record="me",
                      **({"locators": ["Wasserman ch. 3"]} if role == "lecture" else {}),
                      **({"derivation": True} if role == "derivation" else {}),
                      **({"sources": [{"key": "w", "text": "Wasserman, All of Statistics, ch. 3"}]} if role == "gist" else {}))
        self.call("finish", task=task["task"]["id"], result=hid, by="agent:claude", record="me")
        self.tick()
        note = next(p for p in self.notes("Courses") if vault.parse_note(p.read_text()).fm.get("ros_kind") == "handout")
        fm = vault.parse_note(note.read_text()).fm
        self.assertEqual((fm["handout_kind"], fm["ros_status"]), ("lecture", "draft-unreviewed"))
        self.assertIn("#node/handout:", fm["ros_portal"])
        self.assertEqual(user.node(hid)["status"], "ready")
        done = self.jobs()
        if pdf.browser():
            self.assertTrue(done and done[0]["ok"], done)
            self.assertEqual(user.node(hid)["status"], "built")
            self.assertTrue(list((self.vault / "Research OS" / "Attachments").rglob("*.pdf")))
            self.assertIn("![[Research OS/Attachments", note.read_text())
        # 4. the capability notes live under the course, with their links and their state
        caps = {p.stem: p for p in self.notes("Courses")}
        self.assertTrue({"Mean", "Variance"} <= set(caps), set(caps))
        self.assertIn("Research OS/Courses/STAT 303/Capabilities/Mean", caps["Variance"].read_text())
        self.assertEqual(vault.status(user)["broken_links"], [])

        # 5. the person works in Obsidian: a note of theirs flows back, an edit pins, a file dropped in is read in
        mean = caps["Mean"]
        mean.write_text(mean.read_text().rstrip() + "\nThe mean is the balance point; I keep forgetting this.\n")
        (inbox / "syllabus.pdf").write_bytes(b"%PDF-1.4 syllabus")
        self.tick()
        self.assertEqual(len(user.events(type="note.annotate")), 1)
        course = Record(home.home() / "projects" / "stat303")
        self.addCleanup(course.close)
        self.assertEqual([t["kind"] for t in tasks.tasks(course, "ingest")], ["ingest"])
        self.assertTrue((inbox / "syllabus.pdf").exists())
        self.assertEqual((self.vault / "My own note.md").read_text(), "# mine\n")

        # 6. the portal serves the vault's PDFs and notes (and nothing outside the folder)
        port = self.portal()
        rel = note.relative_to(self.vault).as_posix().replace(" ", "%20")
        self.assertEqual(self.fetch(port, "/vault/" + rel)[0], 200)
        self.assertEqual(self.fetch(port, "/vault/My%20own%20note.md")[0], 404)

        # 7. nothing the agent was told to leave to the system was done by hand, and doing it all again changes nothing
        self.assertTrue(FORBIDDEN_FOR_AGENTS.isdisjoint(self.calls), FORBIDDEN_FOR_AGENTS & set(self.calls))
        before = sum(len(r.events()) for r in self.server.records.values())
        self.tick()
        self.tick()
        self.assertEqual(sum(len(r.events()) for r in self.server.records.values()), before)


class ResearchByPrompting(Scenario):
    def test_investigate_a_question_and_judge_the_findings(self):
        question = "Is it true that proton showers are wider than pion showers?"
        self.call("brief")
        out = self.call("engage", intent=question)
        self.assertEqual(out["kind"], "research")
        project = out["record"]
        proj = self.server.record(project)

        # the neutral searches run, each candidate is verified, the brief is asked for: all by the agent's loop
        while True:
            got = self.call("work", by="agent:scout", kinds=["scout"])
            if got["task"] is None:
                break
            self.assertEqual(got["role"], "scout")
            self.call("finish", task=got["task"]["id"], record=got["use_record"], by="agent:scout",
                      result={"candidates": [{"title": f"Paper on {got['task']['facet']}", "doi": f"10.1/{got['task']['facet']}"}]})
        self.tick()
        verify = [t for t in tasks.tasks(proj, "verify")]
        self.assertEqual(len(verify), 3)
        while True:
            got = self.call("work", by="agent:verifier", kinds=["verify"])
            if got["task"] is None:
                break
            self.call("finish", task=got["task"]["id"], record=got["use_record"], by="agent:verifier", result={"verdict": "PASS"})
        self.tick()
        lit = self.call("work", by="agent:writer", kinds=["handout"])
        hid = lit["task"]["handout"]
        self.assertIn("proposing the experiment", lit["task"]["brief"])
        sections = {"question": question + " It matters for calibrating the detector response.",
                    "coverage": "Three neutral searches: competing models, null results and validity limits, each with reviews.",
                    "evidence": " ".join(["Each verified source reports a shower width with its locator and the regime it covers."] * 12),
                    "synthesis": " ".join(["The sources agree on the direction of the effect and differ on its size."] * 8),
                    "gaps": "No null result was found at 50 GeV; the 10 GeV regime is not covered by any verified source here.",
                    "next": "Read the calorimetry review cited by the second paper."}
        for role, text in sections.items():
            self.call("handout_write", handout=hid, section=role, text=text, by="agent:writer", record=project,
                      locators=["abstract of each source"] if role in ("evidence", "synthesis") else None,
                      sources=[{"key": "p", "text": "Paper on competing, doi 10.1/competing"}] if role == "question" else None)
        self.call("add_node", id="experiment:width", type="experiment", record=project,
                  data={"title": "Fit the width ratio at 50 GeV", "authorization": "awaiting", "ladder": ["1k events", "100k events"],
                        "budget": "2 CPU hours", "plan": "Simulate proton and pion showers and fit the lateral width"})
        self.call("finish", task=lit["task"]["id"], result=hid, by="agent:writer", record=project)
        self.tick()

        # the director is shown what to judge, with the evidence, and the agent cannot judge for them
        brief = self.call("brief", record=project)
        approve = next(i for i in brief["needs_you"] if i["kind"] == "approve")
        self.assertEqual(approve["subject"], "experiment:width")
        packet = self.call("evidence", subject="experiment:width", record=project)
        self.assertIn("2 CPU hours", packet["authorizes"])
        self.assertEqual(self.rpc("tools/call", {"name": "approve", "arguments": {"subject": "experiment:width", "decision": "approved", "by": "agent"}})["error"]["code"], -32602)
        self.assertNotIn("approve", {t["name"] for t in self.server.tools()})
        self.assertEqual(tasks.tasks(proj, "run"), [])

        # the person approves in the portal: the run is queued by itself
        port = self.portal()
        status, _ = self.person(port, "approve", project, subject="experiment:width", decision="approved", by="Ada")
        self.assertEqual(status, 200)
        self.tick()
        run = self.call("work", by="agent:executor", kinds=["run"])
        self.assertIn("every rung of its scale ladder", run["task"]["brief"])
        work_dir = proj.root / "work"
        work_dir.mkdir()
        (work_dir / "results.csv").write_text("ratio\n1.10\n")
        self.call("add_claim", key="width", text="Proton showers are about 10% wider than pion showers.", project=project,
                  author="agent:executor", assurance="internal", record=project,
                  numbers=[{"value": 1.10, "file": "results.csv", "column": "ratio"}], artifacts=["results.csv"])
        self.call("finish", task=run["task"]["id"], result="ran", by="agent:executor", record=project)
        self.tick()
        # numbers were pre-checked and audits requested without anyone asking
        self.assertEqual(self.call("claim_status", claim="claim:width", record=project)["verdicts"]["numbers"]["verdict"], "PASS")
        audits = []
        while True:
            got = self.call("work", by="agent:auditor", kinds=["audit"])
            if got["task"] is None:
                break
            audits.append(got["task"]["step"])
            checklist = {m: "ok" for m in ("implementation-bug-passing-self-review", "hallucinated-citation", "hallucinated-result",
                                           "shortcut-reliance", "bug-reframed-as-insight", "methodology-fabrication", "early-frame-lock")}
            self.call("verdict", claim="claim:width", step=got["task"]["step"], verdict="PASS", by="agent:auditor", record=project,
                      notes="read the file cold", **({"checklist": checklist} if got["task"]["step"] == "integrity" else {}))
        self.assertEqual(sorted(audits), ["integrity", "result-claim"])
        self.tick()
        findings = self.call("handout_create", kind="findings", scope=["experiment:width"], title="Width ratio findings", record=project)
        self.assertEqual(findings["context"]["claims"][0]["steps"]["numbers"]["verdict"], "PASS")

        # the evidence is complete: the person decides, and the decision lives in the vault
        brief = self.call("brief", record=project)
        decide = next(i for i in brief["needs_you"] if i["kind"] == "decide")
        self.assertEqual(decide["evidence"]["verdict"], "PASS")
        chain = self.call("chain", claim="claim:width", record=project)
        self.assertTrue(any(n["kind"] == "experiment" for n in chain["nodes"]) or chain["nodes"])
        status, body = self.person(port, "decide", project, subject="claim:width", outcome="accepted", by="Ada",
                                   rationale="The audits pass and the number matches the file.")
        self.assertEqual(status, 200, body)
        self.tick()
        decisions = self.notes("Projects")
        log = next(p for p in decisions if p.name == "Decision Log.md")
        self.assertIn("The audits pass and the number matches the file.", log.read_text())
        self.assertTrue(any("Decisions" in p.parts and "claim" not in p.name for p in decisions))
        claim_note = next(p for p in decisions if "Claims" in p.parts)
        self.assertIn("**accepted** by Ada", claim_note.read_text())

        # nothing the agent should leave to the system was done by hand; the person's three acts were theirs
        self.assertTrue(FORBIDDEN_FOR_AGENTS.isdisjoint(self.calls), FORBIDDEN_FOR_AGENTS & set(self.calls))
        self.assertEqual([e["actor"] for e in proj.events(type="approval")], ["Ada"])
        self.assertEqual([e["actor"] for e in proj.events(type="decision")], ["Ada"])
        before = sum(len(r.events()) for r in self.server.records.values())
        self.tick()
        self.assertEqual(sum(len(r.events()) for r in self.server.records.values()), before)


if __name__ == "__main__":
    unittest.main()
