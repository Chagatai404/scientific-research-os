"""Release contracts for canonical stage order and the documented learning example.

These checks protect structure and deployment, not the quality of AI judgments.
"""
from datetime import date
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import knowledge


class ReleaseContracts(unittest.TestCase):
    def test_research_stage_order_keeps_preparation_review_and_approval_separate(self):
        text = (ROOT / "references/RESEARCH_PROTOCOL.md").read_text(encoding="utf-8")
        stages = text.split("## Stages\n", 1)[1].split("\n## ", 1)[0]
        matches = re.findall(r"^(\d+)\. \*\*(.*?)\.\*\*", stages, re.M)
        numbers = [int(number) for number, _ in matches]
        self.assertEqual(numbers, list(range(1, len(matches) + 1)))
        names = [name for _, name in matches]
        expected = [
            "Inspect knowledge and retention", "Discover literature independently",
            "Verify sources independently", "Prepare and sanity-check the lesson evidence",
            "Learn with prepared evidence", "Reconcile repository/model", "Synthesize",
            "Specialist validation", "Adversarial review", "Triage and resolve blockers",
            "Plan", "Human approval", "Build", "Experiment", "Validate results",
            "Attack results", "Research decision", "Learn again", "Persist and repeat",
        ]
        positions = [names.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(names), len(set(names)))

    def test_learning_protocol_and_parser_agree_on_state_vocabulary(self):
        text = (ROOT / "references/LEARNING_PROTOCOL.md").read_text(encoding="utf-8")
        states = set(re.findall(r"^\| `([a-z]+)` \|", text, re.M))
        self.assertEqual(states, knowledge.STATES)
        self.assertNotIn("frontier", states)

    def test_documented_example_subject_project_and_staleness(self):
        root = ROOT / "examples/learning"
        before = {p.name: p.read_bytes() for p in root.glob("*.md")}
        collection = knowledge.discover(root, date(2026, 9, 29))
        self.assertFalse(collection.diagnostics)
        self.assertEqual(collection.legacy, 2)  # README and legacy note
        self.assertEqual(set(collection.nodes), {
            "probability.density", "probability.gamma-density", "demo.shower-profile"})
        primary, selected = knowledge.select(collection.nodes, "project", "demo")
        self.assertEqual(primary, {"probability.gamma-density", "demo.shower-profile"})
        self.assertEqual(selected, set(collection.nodes))
        ready = knowledge.ready_nodes(collection.nodes)
        self.assertEqual(ready, {"probability.density"})
        self.assertTrue(knowledge.frontier(collection.nodes["probability.gamma-density"], ready))
        self.assertFalse(knowledge.frontier(collection.nodes["demo.shower-profile"], ready))
        subject, _ = knowledge.select(collection.nodes, "subject", "probability")
        self.assertEqual(subject, {"probability.density", "probability.gamma-density"})
        later = knowledge.discover(root, date(2026, 10, 6))
        self.assertEqual(later.nodes["probability.density"].assessment.state, "stale")
        self.assertFalse(knowledge.ready_nodes(later.nodes))
        self.assertFalse(knowledge.frontier(later.nodes["probability.gamma-density"], set()))
        self.assertEqual(before, {p.name: p.read_bytes() for p in root.glob("*.md")})

    def test_example_cli_is_reproducible_without_site_packages(self):
        command = [sys.executable, "-S", "-B", str(ROOT / "scripts/knowledge.py"),
                   "--root", str(ROOT / "examples/learning"), "--project", "demo",
                   "--as-of", "2026-09-29"]
        results = [subprocess.run(command, capture_output=True) for _ in range(2)]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertIn(b"external", results[0].stdout)
        self.assertIn(b"blocked by probability.gamma-density", results[0].stdout)

    def test_course_contract_routes_routine_study_to_learning(self):
        text = (ROOT / "references/COURSE_LEARNING_PROTOCOL.md").read_text(encoding="utf-8")
        for required in ("LEARNING_PROTOCOL.md", "Do not invoke the full", "explicit transition",
                         "Do not require literature-scout or source-verifier", "one",
                         "Obsidian", "assigned textbook", "courses:"):
            self.assertIn(required, text)
        skill = (ROOT / "skills/course-study/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/COURSE_LEARNING_PROTOCOL.md", skill)

    def test_transcription_fidelity_and_ambiguity_contract(self):
        from common import parse_frontmatter
        skill = (ROOT / "skills/notes-to-latex/SKILL.md").read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(skill)
        self.assertEqual(meta["name"], "notes-to-latex")
        self.assertTrue(meta["description"])
        self.assertIn("references/LATEX_TRANSCRIPTION_PROTOCOL.md", skill)
        text = (ROOT / "references/LATEX_TRANSCRIPTION_PROTOCOL.md").read_text(encoding="utf-8")
        for required in ("**faithful:**", "**clean:**", "**polished:**", "**faithful-clean**",
                         "% UNCERTAIN", "[illegible]", "Figure placeholder", "Do not silently replace",
                         "transcription, formatting, interpretation and correction", "I did not modify",
                         "report substantive corrections separately", "without claiming a compilation"):
            self.assertIn(required, text)
        validator = (ROOT / "scripts/validate.py").read_text(encoding="utf-8")
        self.assertIn('"LATEX_TRANSCRIPTION_PROTOCOL.md"', validator)

if __name__ == "__main__":
    unittest.main()
