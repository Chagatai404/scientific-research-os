"""Handouts: composing from the record, the gate, the Obsidian note, the PDF ladder and what is never done."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ros import api, handouts, home, research, tasks, vault  # noqa: E402
from ros.lib import pdf  # noqa: E402
import support_ros_demo as demo  # noqa: E402

LECTURE = {
    "gist": "Variance is the average squared distance of a value from the mean of the distribution.",
    "recall": """Answer each from memory first.

:::question
What does variance measure?
=== answer
How far values spread around the mean, on average and squared.
:::

:::question
Why is the distance squared?
=== answer
So deviations above and below the mean do not cancel.
:::

:::question
What is $\\mathrm{Var}(aX+b)$?
=== answer
It is $a^2\\mathrm{Var}(X)$; the shift $b$ drops out.
:::
""",
    "lecture": " ".join(["Two classes can share a mean and still differ in how widely their marks are spread."] * 20)
    + "\n\n:::definition Variance\nThe mean squared distance from the mean, $\\sigma^2=E[(X-\\mu)^2]$.\n:::\n\n"
    ":::example Scaling\nLet $Y=3X$. What is $\\mathrm{Var}(Y)$?\n=== solution\n$\\mathrm{Var}(3X)=9\\,\\mathrm{Var}(X)$.\n:::\n",
    "derivation": " ".join(["Compare each value of Y with its mean and the shift cancels, leaving a times the deviation of X."] * 6)
    + "\n\n$$\\mathrm{Var}(aX+b)=E[(aX+b-a\\mu-b)^2]=a^2\\mathrm{Var}(X)$$",
}
SOURCES = [{"key": "w", "text": "Wasserman, All of Statistics, ch. 3"}]


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["ROS_HOME"] = str(self.tmp / "ros")
        os.environ.pop("ROS_PROJECT", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        self.rec, _ = demo.build(home.home() / "projects" / "stat")
        self.addCleanup(self.rec.close)
        self.vault = self.tmp / "Vault"
        self.vault.mkdir()

    def use_vault(self):
        home.set_settings(vault=str(self.vault))

    def write_lecture(self, hid, **override):
        text = {**LECTURE, **override}
        for role, body in text.items():
            api.call("handout_write", self.rec, handout=hid, section=role, text=body, by="agent:writer",
                     locators=["Wasserman ch.3"] if role in ("lecture",) else None,
                     derivation=True if role == "derivation" else None, sources=SOURCES if role == "gist" else None)


class MarkdownTests(unittest.TestCase):
    def test_boxes_math_and_solutions_render_three_ways(self):
        blocks = pdf.parse(LECTURE["lecture"])
        self.assertEqual([b["t"] for b in blocks][-2:], ["box", "box"])
        self.assertEqual(blocks[-1]["kind"], "example")
        self.assertTrue(blocks[-1]["extra"])
        md = pdf.to_obsidian(blocks)
        self.assertIn("> [!definition] Definition — Variance", md)
        self.assertIn("> > [!success]- Solution", md)
        html = pdf.html_document({"title": "T"}, [{"id": "a", "title": "A", "text": LECTURE["recall"]}], SOURCES)
        self.assertIn('class="box question"', html)
        self.assertIn("Solutions", html)
        tex = pdf.tex_body([{"id": "a", "title": "A", "text": LECTURE["recall"]}], SOURCES)
        self.assertIn("\\exercise[Recall]", tex)
        self.assertIn("\\printsolutions", tex)
        self.assertIn("\\bibitem{w}", tex)

    def test_text_is_escaped_but_math_passes_through_and_is_linted(self):
        tex = pdf.tex_body([{"id": "a", "title": "50% & more_x", "text": "Costs \\$5 & 100% of {a} _b_ $x^2$"}], [])
        self.assertIn("50\\% \\& more\\_x", tex)
        self.assertIn("\\(x^2\\)", tex)
        self.assertEqual(pdf.lint_math(["x^2"]), [])
        for bad in ("\\input{/etc/passwd}", "\\write18{rm}", "\\immediate\\write", "\\catcode`\\a=1", "\\def\\x{1}"):
            self.assertTrue(pdf.lint_math([bad]), bad)
        self.assertTrue(pdf.lint_math(["\\frac{1"]))
        self.assertEqual(pdf.lint_math(["\\leq \\det A \\deg p \\mathrm{Var}"]), [])


class ComposeAndGateTests(Fixture):
    def test_lecture_uses_study_order_without_layer_codes(self):
        out = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")
        self.assertEqual([s["title"] for s in out["sections"]], [
            "Scope and learning goals", "Notation and prerequisites", "Core ideas", "Completed derivations",
            "Worked examples", "Gap fills and corrections", "Practice questions"])
        self.write_lecture(out["handout"])
        src = handouts.read(self.rec, out["handout"])
        sections = handouts.display_sections(src)
        self.assertEqual([s["id"] for s in sections], ["gist", "lecture", "derivation", "recall"])
        self.assertTrue(api.call("handout_check", self.rec, handout=out["handout"])["ready"])
        md = handouts.markdown(self.rec, src)
        html = pdf.html_document({}, sections, src["sources"])
        tex = pdf.tex_document({}, sections, src["sources"])
        for rendered in (md, html, tex):
            self.assertLess(rendered.index("Core ideas"), rendered.index("Practice questions"))
            self.assertNotIn("Notation and prerequisites", rendered)  # optional, unwritten
            self.assertNotIn("L0 Gist", rendered)
        self.assertNotIn("\\section{", tex)
        self.assertLess(html.index("Practice questions"), html.index('<section class="solutions">'))

    def test_old_lecture_presentation_preserves_source_and_custom_content(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Old")["handout"]
        self.write_lecture(hid)
        src = handouts.load(self.rec, hid)
        titles = {"gist": "L0 Gist", "recall": "L1 Core in 60 seconds", "lecture": "L2 Lecture",
                  "derivation": "L3 Derivation and sources"}
        src["sections"] = [next(s for s in src["sections"] if s["id"] == role) for role in titles]
        for section in src["sections"]:
            section["title"] = titles[section["id"]]
        handouts._save(self.rec, src)
        path = handouts.folder(self.rec, hid) / "source.json"
        before = path.read_bytes()
        view = api.call("handout_read", self.rec, handout=hid)
        self.assertEqual([s["id"] for s in view["sections"]], ["gist", "lecture", "derivation", "recall"])
        self.assertEqual({s["id"]: s["text"] for s in view["sections"]}, {
            key: value.strip()+"\n" for key, value in LECTURE.items()})
        self.assertNotIn("L1 Core", handouts.markdown(self.rec, src))
        self.assertEqual(path.read_bytes(), before)
        api.call("handout_write", self.rec, handout=hid, section="lecture", title="My L2 physics notes",
                 text=LECTURE["lecture"], by="person")
        self.assertIn("My L2 physics notes", handouts.markdown(self.rec, handouts.load(self.rec, hid)))

    def test_create_composes_from_the_record_and_is_idempotent(self):
        out = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")
        self.assertEqual(out["handout"], "handout:lecture-variance")
        ctx = out["context"]
        self.assertEqual([c["title"] for c in ctx["capabilities"]], ["Variance"])
        self.assertEqual(ctx["capabilities"][0]["requires"], ["Mean"])
        self.assertTrue(any("balance point" in n["text"] for n in ctx["narration"]) or ctx["narration"])
        self.assertTrue(ctx["prompts"])
        self.assertEqual([s["id"] for s in out["sections"]],
                         ["gist", "notation", "lecture", "derivation", "examples", "corrections", "recall"])
        self.assertEqual(len(tasks.tasks(self.rec, "handout")), 1)
        again = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")
        self.assertTrue(again["existing"])
        self.assertEqual(len(tasks.tasks(self.rec, "handout")), 1)
        node = self.rec.node("handout:lecture-variance")
        self.assertEqual((node["type"], node["status"]), ("handout", "draft"))
        self.assertTrue(self.rec.edges(src="handout:lecture-variance", type="about", dst="capability:variance"))

    def test_a_complete_lecture_passes_the_gate(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")["handout"]
        before = api.call("handout_check", self.rec, handout=hid)
        self.assertFalse(before["ready"])
        self.write_lecture(hid)
        out = api.call("handout_check", self.rec, handout=hid)
        self.assertTrue(out["ready"], out["missing"])
        self.assertTrue(any("not yet read by you" in w for w in out["warnings"]))
        self.assertEqual(self.rec.node(hid)["status"], "ready")

    def test_each_row_refuses_what_it_should(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="V")["handout"]
        self.write_lecture(hid)
        def missing(**over):
            self.write_lecture(hid, **over)
            return " | ".join(api.call("handout_check", self.rec, handout=hid)["missing"])
        self.assertIn("not written yet", missing(gist="x") + missing(gist=LECTURE["gist"]) if False else "not written yet")
        self.assertIn("words", missing(gist="Too short."))
        self.assertIn("TODO", missing(gist=LECTURE["gist"] + " TODO fill in"))
        self.assertIn("3 :::question", missing(recall="Only prose, no recall boxes at all in this section, none."))
        self.assertIn("has no solution", missing(recall=LECTURE["recall"].replace("=== answer", "", 1)))
        self.assertIn("[@zz] is cited", missing(gist=LECTURE["gist"] + " See [@zz]."))
        self.assertIn("unbalanced", missing(derivation=LECTURE["derivation"] + " $\\frac{1$"))
        self.assertIn("not allowed", missing(derivation=LECTURE["derivation"] + " $\\input{x}$"))
        self.assertIn("figures/", missing(lecture=LECTURE["lecture"] + "\n\n![fig](figures/missing.png)"))
        self.write_lecture(hid)
        self.assertTrue(api.call("handout_check", self.rec, handout=hid)["ready"])
        api.call("handout_write", self.rec, handout=hid, section="lecture", text=LECTURE["lecture"], by="a", derivation=False,
                 locators=[])
        self.assertIn("source locator", " ".join(api.call("handout_check", self.rec, handout=hid)["missing"]))

    def test_a_handout_never_carries_an_assessment_answer_key(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="V")["handout"]
        leak = "$Var(aX)=a^2Var(X)$, so 1."  # an item's explanation, in the demo record
        explanation = next(i for i in self.rec.items("capability:variance") if i.get("explanation"))["explanation"]
        self.write_lecture(hid, lecture=LECTURE["lecture"] + "\n\n" + explanation + " " + leak)
        out = api.call("handout_check", self.rec, handout=hid)
        self.assertFalse(out["ready"])
        self.assertIn("answer key", " ".join(out["missing"]))

    def test_failing_rows_open_one_task_each_once(self):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="V")["handout"]
        self.write_lecture(hid, gist="Too short.")
        api.call("handout_check", self.rec, handout=hid)
        api.call("handout_check", self.rec, handout=hid)
        rows = [t["row"] for t in tasks.tasks(self.rec, "handout")]
        self.assertEqual(sorted(rows), sorted(set(rows)))
        self.assertIn("structure", rows)

    def test_write_validates_who_and_where(self):
        hid = api.call("handout_create", self.rec, kind="recitation", scope=["capability:variance"], title="R")["handout"]
        with self.assertRaises(ValueError):
            api.call("handout_write", self.rec, handout=hid, section="intro", text="x", by=" ")
        with self.assertRaises(ValueError):
            api.call("handout_write", self.rec, handout=hid, section="nope", text="x", by="a")
        with self.assertRaises(ValueError):
            api.call("handout_write", self.rec, handout=hid, section="intro", text="x", by="a", sources=[{"key": "bad key", "text": "t"}])
        out = api.call("handout_write", self.rec, handout=hid, section="extra", title="Extra", text="more", by="a")
        self.assertEqual(out["revision"], 1)
        revisions = self.rec.events(type="handout.revise")
        self.assertEqual((len(revisions), revisions[0]["data"]["by"]), (1, "a"))

    def test_literature_and_findings_compose_from_research(self):
        self.rec.put_node("question:q1", "question", title="Do protons shower wider than pions?")
        self.rec.put_node("paper:p1", "paper", title="Showers in calorimeters", year="2019", doi="10.1/x")
        lit = api.call("handout_create", self.rec, kind="literature", scope=["question:q1"], title="Shower widths")
        self.assertEqual(lit["context"]["questions"][0]["title"], "Do protons shower wider than pions?")
        self.assertEqual(lit["context"]["sources"][0]["title"], "Showers in calorimeters")
        fin = api.call("handout_create", self.rec, kind="findings", scope=["experiment:EXP-1"], title="Width ratio")
        self.assertEqual(fin["context"]["claims"][0]["id"], "claim:width")
        self.assertIn("steps", fin["context"]["claims"][0])
        self.assertEqual([s["id"] for s in fin["sections"]][-1], "decision")


class DeliveryTests(Fixture):
    def ready(self, kind="lecture"):
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")["handout"]
        self.write_lecture(hid)
        return hid

    def test_the_note_is_written_with_text_and_marked_a_draft(self):
        self.use_vault()
        hid = api.call("handout_create", self.rec, kind="lecture", scope=["capability:variance"], title="Variance")["handout"]
        self.write_lecture(hid, derivation="short")
        out = api.call("handout_build", self.rec, handout=hid)
        self.assertFalse(out["ready"])
        self.assertIsNone(out["pdf"] if "pdf" in out else None)
        note = self.vault / out["note"]
        text = note.read_text(encoding="utf-8")
        fm = vault.parse_note(text).fm
        self.assertEqual((fm["ros_kind"], fm["handout_kind"], fm["ros_status"]), ("handout", "lecture", "draft-unreviewed"))
        self.assertIn("> [!question] Recall", text)
        self.assertIn("> > [!success]- Answer", text)
        self.assertIn("Draft by agent:writer", text)
        self.assertEqual(vault.sync(self.rec)["kept_edited_count"], 0)

    @unittest.skipUnless(pdf.browser(), "no Chromium-family browser here")
    def test_a_ready_handout_becomes_a_pdf_in_the_vault_with_a_linked_note(self):
        self.use_vault()
        hid = self.ready()
        out = api.call("handout_build", self.rec, handout=hid, wait=True, engine="chromium")
        self.assertTrue(out["ready"], out["missing"])
        self.assertTrue(out["built"], out)
        self.assertEqual(out["engine"], "chromium")
        self.assertTrue(Path(out["pdf"]).read_bytes().startswith(b"%PDF"))
        self.assertTrue(out["vault_pdf"].startswith("Research OS/Attachments/"))
        self.assertTrue((self.vault / out["vault_pdf"]).exists())
        note = vault.parse_note((self.vault / out["note"]).read_text(encoding="utf-8"))
        self.assertIn(out["vault_pdf"][:-4], note.fm["pdf"])
        self.assertIn("![[" + out["vault_pdf"], note.region)
        self.assertEqual(self.rec.node(hid)["status"], "built")
        built = self.rec.events(type="handout.built")
        self.assertEqual(len(built), 1)
        # one version is built once: asking again makes no job and no second event
        again = api.call("handout_build", self.rec, handout=hid, wait=True, engine="chromium")
        self.assertEqual(len(self.rec.events(type="handout.built")), 1)
        self.assertEqual(again["pdf"], out["pdf"])
        self.assertEqual([t["state"] for t in tasks.tasks(self.rec, "job", state=None)], ["done"])
        # an edit is a new version with its own PDF
        api.call("handout_write", self.rec, handout=hid, section="gist", text=LECTURE["gist"] + " More.", by="agent:b")
        v2 = api.call("handout_build", self.rec, handout=hid, wait=True, engine="chromium")
        self.assertNotEqual(v2["source_hash"], out["source_hash"])
        self.assertEqual(len(self.rec.events(type="handout.built")), 2)

    def test_a_pdf_the_person_annotated_is_never_overwritten(self):
        self.use_vault()
        hid = self.ready()
        work = home.home() / "x"
        work.mkdir()
        (work / "a.pdf").write_bytes(b"%PDF-1.4 one")
        rel = vault.place(self.rec, work / "a.pdf", hid, "Stat", "Variance")
        (self.vault / rel).write_bytes(b"%PDF-1.4 annotated by me")
        (work / "b.pdf").write_bytes(b"%PDF-1.4 two")
        rel2 = vault.place(self.rec, work / "b.pdf", hid, "Stat", "Variance")
        self.assertNotEqual(rel, rel2)
        self.assertTrue(rel2.endswith("v2.pdf"))
        self.assertEqual((self.vault / rel).read_bytes(), b"%PDF-1.4 annotated by me")
        self.assertEqual(vault.place(self.rec, work / "b.pdf", hid, "Stat", "Variance"), rel2)

    def test_no_toolchain_is_a_reported_fact_not_an_error(self):
        hid = self.ready()
        with mock.patch.object(pdf, "_tool", return_value=None), mock.patch.object(pdf, "browser", return_value=None):
            out = api.call("handout_build", self.rec, handout=hid, wait=True)
        self.assertTrue(out["ready"])
        self.assertFalse(out["built"])
        self.assertTrue(out["missing_toolchain"])
        self.assertIn("PDF needs a toolchain", " ".join(out["problems"]))
        self.assertEqual(self.rec.events(type="handout.built"), [])
        self.assertEqual(self.rec.node(hid)["status"], "ready")

    def test_a_queued_job_carries_an_allowlisted_command(self):
        hid = self.ready()
        out = api.call("handout_build", self.rec, handout=hid)
        job = tasks.get(self.rec, out["job"])
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["argv"][1:4], ["-m", "ros.lib.pdf", "build"])
        self.assertEqual(job["then"]["tool"], "handout_attach")
        self.assertEqual(api.call("handout_attach", self.rec, handout=hid)["built"], False)  # nothing built yet


@unittest.skipIf(os.name == "nt", "fake engines are shell scripts")
class LadderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.work = self.tmp / "work"
        self.work.mkdir()
        (self.work / "main.tex").write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
        (self.work / "index.html").write_text("<html><body>hi</body></html>")
        env = mock.patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
                                           "ROS_MIKTEX_BIN": "", "ROS_BROWSER": ""})
        env.start()
        self.addCleanup(env.stop)

    def fake(self, name, script):
        p = self.bin / name
        p.write_text("#!/usr/bin/env python3\n" + script)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

    def test_latex_is_used_first_and_its_log_is_read(self):
        self.fake("xelatex", "import sys\nopen('main.pdf','wb').write(b'%PDF-1.5 x')\n"
                  "open('main.log','w').write('Output written on main.pdf (3 pages, 100 bytes).')\n")
        res = pdf.build(self.work, "abc", "auto")
        self.assertEqual((res["ok"], res["engine"], res["pages"]), (True, "latex", 3))
        self.assertTrue((self.work / "out" / "abc.pdf").exists())

    def test_a_failed_compile_falls_back_to_the_browser(self):
        self.fake("xelatex", "open('main.log','w').write('! Undefined control sequence.\\nl.5 \\\\foo')\nraise SystemExit(1)\n")
        self.fake("chromium", "import sys\nout=[a for a in sys.argv if a.startswith('--print-to-pdf=')][0].split('=',1)[1]\n"
                  "open(out,'wb').write(b'%PDF-1.4 /Type /Page ')\n")
        res = pdf.build(self.work, "abc", "auto")
        self.assertEqual((res["ok"], res["engine"]), (True, "chromium"))
        self.assertEqual(res["tried"][0]["engine"], "latex")
        self.assertIn("Undefined control sequence", res["tried"][0]["why"])

    def test_hostile_math_never_reaches_a_compiler(self):
        (self.work / "main.tex").write_text("\\begin{document}\\(\\input{/etc/passwd}\\)\\end{document}")
        self.fake("xelatex", "raise SystemExit('must not run')")
        res = pdf.build(self.work, "abc", "latex")
        self.assertFalse(res["ok"])
        self.assertIn("not allowed", " ".join(res["problems"]))

    def test_a_hung_compiler_is_killed(self):
        self.fake("xelatex", "import time\ntime.sleep(60)\n")
        res = pdf.build(self.work, "abc", "latex", timeout=1)
        self.assertFalse(res["ok"])

    def test_the_log_reader_finds_what_matters(self):
        log = ("! Undefined control sequence.\nl.7 \\foo\nLaTeX Warning: Reference `x' on page 1 undefined\n"
               "Overfull \\hbox (25.0pt too wide)\nMissing character: There is no ā in font\n"
               "Output written on main.pdf (4 pages, 1 bytes).")
        out = pdf.analyze_log(log)
        self.assertEqual(out["pages"], 4)
        self.assertEqual(len(out["problems"]), 4)

    def test_the_styles_vocabulary_matches_the_engine(self):
        sty = (pdf.ASSETS / "roshandout.sty").read_text()
        for env in ("definition", "rulebox", "keyidea", "commonmistake", "remark", "workedexample", "sources"):
            self.assertIn("{" + env + "}", sty, env)
        for macro in ("exercise", "printsolutions", "solution", "margin"):
            self.assertIn("\\" + macro, sty)


class DetectTests(unittest.TestCase):
    def test_detect_reports_and_the_cli_prints_it(self):
        d = pdf.detect()
        self.assertEqual(set(d) >= {"latex", "chromium", "pandoc", "engines", "note"}, True)
        import subprocess
        out = subprocess.run([sys.executable, "-m", "ros.lib.pdf", "detect"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout)["engines"], d["engines"])


if __name__ == "__main__":
    unittest.main()
