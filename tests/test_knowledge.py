"""Behavioral checks for learning evidence and read-only graph generation."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import knowledge as k

AS_OF = date(2026, 9, 29)
TABLE = "## Retrieval history\n\n| " + " | ".join(k.HEADER) + " |\n|" + "---|" * 8 + "\n"


def attempt(day="2026-09-28", timing="same-session", method="explanation", outcome="pass",
            assistance="none", review="2026-10-05", period="intro"):
    return f"| {day} | {period} | {timing} | {method} | {outcome} | {assistance} | [[Lesson#Attempt]] | {review} |\n"


def record(key="foundation", domain="math", prerequisites=(), projects=(), rows="", state=None, extra="", title=None):
    summary = f"learning_state: {state}\n" if state else ""
    return (f"---\nlearning_schema: 1\nlearning_id: {key}\ndomain: {domain}\n"
            f"prerequisites: {json.dumps(list(prerequisites))}\nprojects: {json.dumps(list(projects))}\n"
            f"{summary}{extra}---\n# {title or key}\n\n{TABLE}{rows}")


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def node(self, text, as_of=AS_OF):
        meta, body = k.metadata(text)
        return k.make_node(meta, body, "node.md", as_of)

    def test_six_states_derived_from_evidence(self):
        demonstrated = attempt()
        retained = demonstrated + attempt(day="2026-09-29", timing="delayed", method="transfer")
        cases = {
            "unknown": ("", AS_OF),
            "learning": (attempt(outcome="fail"), AS_OF),
            "demonstrated": (demonstrated, AS_OF),
            "retained": (retained, AS_OF),
            "fragile": (retained + attempt(day="2026-09-29", outcome="partial"), AS_OF),
            "stale": (retained, date(2026, 10, 6)),
        }
        for expected, (rows, as_of) in cases.items():
            with self.subTest(state=expected):
                node = self.node(record(rows=rows, state=expected), as_of)
                self.assertEqual(node.assessment.state, expected)
                self.assertFalse(node.issues)

    def test_labels_never_substitute_for_evidence(self):
        for state in ("demonstrated", "retained", "fragile", "stale"):
            node = self.node(record(state=state))
            self.assertEqual(node.assessment.state, "unknown")
            self.assertTrue(node.issues)
            self.assertFalse(node.ready)
        self.assertEqual(self.node(record(state="learning")).assessment.state, "learning")

    def test_mcq_recall_prediction_and_assistance_do_not_establish_mastery(self):
        for method in ("mcq", "recall", "prediction"):
            node = self.node(record(rows=attempt(method=method)))
            self.assertEqual(node.assessment.state, "unknown")
        for assistance in ("hinted", "open-notes"):
            node = self.node(record(rows=attempt(assistance=assistance)))
            self.assertEqual(node.assessment.state, "learning")

    def test_delayed_requires_prior_demonstration_and_later_date(self):
        cases = [attempt(timing="delayed"),
                 attempt() + attempt(timing="delayed"),
                 attempt() + attempt(day="2026-09-29", timing="delayed", period="new-chat")]
        for rows in cases:
            self.assertEqual(self.node(record(rows=rows)).assessment.state, "demonstrated")

    def test_failure_retry_and_later_retention(self):
        rows = attempt() + attempt(day="2026-09-29", timing="delayed", outcome="fail")
        self.assertEqual(self.node(record(rows=rows)).assessment.state, "fragile")
        rows += attempt(day="2026-09-29", timing="delayed")
        self.assertEqual(self.node(record(rows=rows)).assessment.state, "demonstrated")
        rows += attempt(day="2026-09-30", timing="delayed")
        self.assertEqual(self.node(record(rows=rows), date(2026, 9, 30)).assessment.state, "retained")

    def test_same_day_reteaching_cannot_be_called_delayed_retention(self):
        rows = attempt() + attempt(day="2026-09-29") + attempt(day="2026-09-29", timing="delayed")
        self.assertEqual(self.node(record(rows=rows)).assessment.state, "demonstrated")

    def test_extra_same_day_check_preserves_retention_without_extending_horizon(self):
        rows = attempt() + attempt(day="2026-09-29", timing="delayed", review="2026-10-05")
        rows += attempt(day="2026-09-29", timing="delayed", review="2026-11-01")
        node = self.node(record(rows=rows, state="retained"))
        self.assertEqual(node.assessment.state, "retained")
        self.assertEqual(node.assessment.review, date(2026, 10, 5))
        self.assertFalse(node.issues)

    def test_old_period_label_cannot_bypass_same_day_reteaching(self):
        rows = attempt() + attempt(day="2026-09-29", period="reinforcement")
        rows += attempt(day="2026-09-29", timing="delayed", period="intro")
        self.assertEqual(self.node(record(rows=rows)).assessment.state, "demonstrated")

    def test_mcq_success_does_not_extend_retention_horizon(self):
        rows = attempt(review="2026-09-29") + attempt(day="2026-09-29", timing="delayed", review="2026-09-30")
        rows += attempt(day="2026-10-01", timing="delayed", method="mcq", review="2026-11-01")
        node = self.node(record(rows=rows), date(2026, 10, 1))
        self.assertEqual(node.assessment.state, "stale")
        self.assertEqual(node.assessment.review, date(2026, 9, 30))
        self.assertEqual(node.assessment.last, date(2026, 10, 1))

    def test_staleness_unknown_horizon_and_failure_are_distinct(self):
        node = self.node(record(rows=attempt(review="")))
        self.assertEqual(node.assessment.state, "demonstrated")
        self.assertEqual(node.freshness, "unknown")
        self.assertFalse(node.ready)
        rows = attempt() + attempt(day="2026-09-29", outcome="fail", review="2026-09-30")
        fragile = self.node(record(rows=rows), date(2026, 10, 5))
        self.assertEqual(fragile.assessment.state, "fragile")
        self.assertEqual(fragile.freshness, "overdue")
        self.assertEqual(self.node(record(rows=attempt(review="2026-09-29"))).assessment.state, "demonstrated")

    def test_as_of_ignores_future_attempts_but_validates_full_summary(self):
        rows = attempt() + attempt(day="2026-09-30", timing="delayed")
        node = self.node(record(rows=rows, state="retained"))
        self.assertFalse(node.issues)
        self.assertEqual(node.assessment.state, "demonstrated")
        self.assertEqual(node.assessment.last, date(2026, 9, 28))

    def test_summary_date_conflicts_block_readiness(self):
        for key in ("first_learned", "last_retrieval", "next_review"):
            node = self.node(record(rows=attempt(), extra=f'{key}: "2026-09-01"\n'))
            self.assertTrue(node.issues)
            self.assertFalse(node.ready)

    def test_scopes_prerequisite_closure_frontier_and_edge_direction(self):
        self.put("base.md", record("base", domain="math", rows=attempt()))
        self.put("target.md", record("target", domain="physics", prerequisites=["base"], projects=["experiment"]))
        self.put("later.md", record("later", domain="physics", prerequisites=["target"], projects=["experiment"]))
        self.put("unrelated.md", record("unrelated", domain="biology"))
        collection = k.discover(self.root, AS_OF)
        self.assertFalse(collection.diagnostics)
        for scope, value in (("subject", "physics"), ("project", "experiment")):
            primary, selected = k.select(collection.nodes, scope, value)
            self.assertEqual(primary, {"target", "later"})
            self.assertEqual(selected, {"base", "target", "later"})
            rendered = k.render(collection, scope, value, AS_OF)
            self.assertIn("n0 --> n2", rendered)  # base -> target, sorted IDs
            self.assertIn("external", rendered)
        ready = k.ready_nodes(collection.nodes)
        self.assertTrue(k.frontier(collection.nodes["target"], ready))
        self.assertFalse(k.frontier(collection.nodes["later"], ready))
        self.assertTrue(k.frontier(collection.nodes["base"], ready))

    def test_retained_foundation_is_not_frontier(self):
        rows = attempt() + attempt(day="2026-09-29", timing="delayed")
        self.put("base.md", record(rows=rows))
        c = k.discover(self.root, AS_OF)
        self.assertFalse(k.frontier(c.nodes["foundation"], k.ready_nodes(c.nodes)))

    def test_fragile_stale_and_unknown_freshness_block_descendants(self):
        histories = [attempt(review=""), attempt(review="2026-09-28"),
                     attempt() + attempt(day="2026-09-29", outcome="partial")]
        for rows in histories:
            self.put("base.md", record("base", rows=rows))
            self.put("mid.md", record("mid", prerequisites=["base"], rows=attempt()))
            self.put("target.md", record("target", prerequisites=["mid"]))
            c = k.discover(self.root, AS_OF)
            self.assertFalse(k.frontier(c.nodes["target"], k.ready_nodes(c.nodes)))

    def test_missing_prerequisites_cycles_and_duplicates(self):
        self.put("a.md", record("a", prerequisites=["b"], rows=attempt()))
        self.put("b.md", record("b", prerequisites=["a"], rows=attempt()))
        self.put("c.md", record("c", prerequisites=["a"]))
        self.put("missing.md", record("missing", prerequisites=["absent"]))
        self.put("duplicate1.md", record("duplicate"))
        self.put("duplicate2.md", record("duplicate"))
        c = k.discover(self.root, AS_OF)
        self.assertNotIn("duplicate", c.nodes)
        self.assertFalse(k.ready_nodes(c.nodes))
        for key in ("a", "b", "c", "missing"):
            self.assertTrue(c.nodes[key].issues)
            self.assertFalse(k.frontier(c.nodes[key], set()))
        self.assertTrue(any("duplicate" in x for x in c.diagnostics))

    def test_legacy_drafts_and_template_collection(self):
        self.put("legacy.md", '---\ntype: concept\nstatus: solid\nproject: experiment\n---\n# Existing\n')
        self.put("pointer.md", '---\nlearning_ref: foundation\n---\n# Concept\n')
        self.put("draft.md", (ROOT / "assets/obsidian/03_Quizbook_Topic.md").read_text(encoding="utf-8"))
        c = k.discover(self.root, AS_OF)
        self.assertEqual((c.legacy, c.drafts, c.nodes, c.diagnostics), (2, 1, {}, []))
        templates = k.discover(ROOT / "assets/obsidian", AS_OF)
        self.assertEqual(templates.drafts, 1)
        self.assertFalse(templates.nodes)
        self.assertFalse(templates.diagnostics)

    def test_duplicate_with_malformed_history_excludes_other_copy(self):
        self.put("a.md", record(rows=attempt().replace("| pass |", "| oops |")))
        self.put("b.md", record(rows=attempt()))
        c = k.discover(self.root, AS_OF)
        self.assertFalse(c.nodes)
        self.assertTrue(any("duplicate" in x for x in c.diagnostics))

    def test_malformed_metadata_is_diagnosed_without_crashing(self):
        source = record()
        cases = [source.replace("learning_schema: 1", "learning_schema: 2"),
                 source.replace("prerequisites: []\n", ""),
                 source.replace("prerequisites: []", "prerequisites:\n  - base"),
                 source.replace("projects: []", 'projects: ["UPPER"]'),
                 source.replace("domain: math", "domain: math\ndomain: physics"),
                 source.replace("domain: math", "domain: math # comment"),
                 source.replace("learning_id: foundation", "learning_id: bad id"),
                 source.replace("domain: math", " domain: math"),
                 source.replace("---\n#", "#"),
                 record(state="solid"), record(extra="first_learned: 2026-02-30\n"),
                 source.replace("learning_schema: 1\n", ""),
                 source.replace("learning_id: foundation", 'learning_id: ""')]
        for i, text in enumerate(cases):
            self.put(f"invalid{i}.md", text)
        c = k.discover(self.root, AS_OF)
        self.assertFalse(c.nodes)
        self.assertEqual(len(c.diagnostics), len(cases))

    def test_malformed_history_is_not_silently_ignored(self):
        source = record(rows=attempt())
        cases = [source.replace("| Outcome |", "| Score |"),
                 source.replace("| pass |", "| great |"),
                 source.replace("[[Lesson#Attempt]]", ""),
                 source.replace("[[Lesson#Attempt]]", "[[Lesson|label]]"),
                 source.replace("| same-session |", "| later |"),
                 source.replace("2026-10-05", "2026-09-01"),
                 source.replace("| 2026-09-28 |", "2026-09-28 |"),
                 source + "\n" + TABLE,
                 record(rows=attempt(day="2026-09-29") + attempt())]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.node(text)

    def test_unrelated_yaml_and_fenced_examples_do_not_become_evidence(self):
        text = record(extra="tags:\n  - learning/quiz\n")
        text += "\n## Examples\n```markdown\n" + TABLE + attempt() + "```\n"
        self.assertEqual(self.node(text).assessment.state, "unknown")
        self.assertEqual(self.node(text.replace("\n", "\r\n")).assessment.state, "unknown")

    def test_determinism_escaping_and_input_preservation(self):
        path = self.put("z.md", record("z", title='Quote " ] --> Evil <script> | `click`'))
        self.put("a.md", record("a", prerequisites=["z"]))
        before = {p.name: p.read_bytes() for p in self.root.glob("*.md")}
        first = k.render(k.discover(self.root, AS_OF), "subject", "math", AS_OF)
        content = path.read_text(encoding="utf-8")
        path.unlink()
        path.write_text(content, encoding="utf-8")
        second = k.render(k.discover(self.root, AS_OF), "subject", "math", AS_OF)
        self.assertEqual(first, second)
        self.assertNotIn('<script>', first)
        self.assertNotIn('] --> Evil', first)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.glob("*.md")})

    def test_cli_output_exit_status_and_overwrite_protection(self):
        source = self.put("node.md", record())
        output = self.root / "view.md"
        args = ["--root", str(self.root), "--subject", "math", "--as-of", "2026-09-29"]
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(k.main(args), 0)
        self.assertIn("frontier", stdout.getvalue())
        self.assertEqual(k.main(args + ["--output", str(output)]), 0)
        before = source.read_bytes()
        for destination in (source, output):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                k.main(args + ["--output", str(destination)])
            self.assertEqual(error.exception.code, 2)
        self.assertEqual(source.read_bytes(), before)
        self.put("bad.md", record("bad", prerequisites=["absent"]))
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(k.main(args), 1)
        self.assertIn("missing prerequisite", stdout.getvalue())

    def test_cli_subprocess_runs_without_configuration(self):
        self.put("node.md", record(projects=["experiment"], title="Probability Γ — yoğunluk"))
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/knowledge.py"),
                                 "--root", str(self.root), "--project", "experiment",
                                 "--as-of", "2026-09-29"], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Probability Γ", result.stdout)
        self.assertIn("yoğunluk", result.stdout)

    def test_empty_selection_and_invalid_cli_arguments(self):
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(k.main(["--root", str(self.root), "--subject", "math"]), 0)
        self.assertIn("No tracked nodes", stdout.getvalue())
        for extra in (["--as-of", "not-a-date"], ["--project", "another"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                k.main(["--root", str(self.root), "--subject", "math"] + extra)
            self.assertEqual(error.exception.code, 2)

    def test_retention_targets_are_optional_validated_and_separate(self):
        rows = attempt(review="2026-09-28")
        old = self.node(record(rows=rows))
        self.assertEqual(old.retention_target, "unspecified")
        for target in k.RETENTION_TARGETS:
            node = self.node(record(rows=rows, extra=f"retention_target: {target}\n"))
            self.assertEqual(node.retention_target, target)
            self.assertEqual(node.assessment, old.assessment)
            self.assertEqual(node.attempts, old.attempts)
            self.assertEqual(node.ready, old.ready)
        for value in ('unimportant', 'unspecified', '""', '[]', 'CORE'):
            with self.assertRaises(ValueError):
                self.node(record(extra=f"retention_target: {value}\n"))

    def test_reference_policy_preserves_failure_and_historical_horizon(self):
        for rows, state in ((attempt(review=""), "demonstrated"),
                            (attempt(review="2026-09-28"), "stale"),
                            (attempt() + attempt(day="2026-09-29", outcome="fail"), "fragile")):
            self.put("reference.md", record(rows=rows, extra="retention_target: reference\n"))
            c = k.discover(self.root, AS_OF)
            self.assertEqual(c.nodes["foundation"].assessment.state, state)
            view = k.render(c, "subject", "math", AS_OF)
            self.assertIn("Retention target", view)
            self.assertIn("no routine spaced review", view)
            self.assertIn("historical horizon; no routine review", view)
            self.assertFalse(c.nodes["foundation"].ready)


    def test_goal_membership_closure_multiple_goals_and_old_records(self):
        self.put("base.md", record("base", rows=attempt()))
        self.put("target.md", record("target", prerequisites=["base"], projects=["demo"],
                                     extra='goals: ["goal-a", "goal-b"]\nretention_target: working\n'))
        self.put("other.md", record("other", projects=["demo"]))
        c = k.discover(self.root, AS_OF)
        self.assertFalse(c.diagnostics)
        for goal in ("goal-a", "goal-b"):
            self.assertEqual(k.select(c.nodes, "goal", goal), ({"target"}, {"base", "target"}))
            first = k.render(c, "goal", goal, AS_OF)
            self.assertEqual(first, k.render(k.discover(self.root, AS_OF), "goal", goal, AS_OF))
            self.assertIn("external", first)
            self.assertIn("n0 --> n1", first)
            self.assertIn("working", first)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(k.main(["--root", str(self.root), "--goal", goal,
                                         "--as-of", AS_OF.isoformat()]), 0)
            self.assertEqual(first, out.getvalue())
        self.assertEqual(k.select(c.nodes, "goal", "absent"), (set(), set()))

    def test_invalid_goal_membership_and_partial_drafts_are_diagnosed(self):
        for value in ('"goal"', '["UPPER"]', '["a", "a"]', '{}', '[1]', 'null'):
            with self.assertRaises(ValueError):
                self.node(record(extra=f"goals: {value}\n"))
        self.put("draft.md", '---\nlearning_schema: 1\nlearning_id: ""\ngoals: ["a"]\n---\n')
        self.assertTrue(k.discover(self.root, AS_OF).diagnostics)


    def test_course_context_reuses_one_node_and_cross_course_prerequisites(self):
        self.put("base.md", record("base", rows=attempt(), extra='courses: ["foundation-course"]\n'))
        self.put("target.md", record("target", prerequisites=["base"], projects=["demo"],
                                     extra='courses: ["stat-xxx", "math-yyy"]\ngoals: ["long-term"]\n'))
        self.put("other.md", record("other"))
        c = k.discover(self.root, AS_OF)
        self.assertFalse(c.diagnostics)
        for scope, value in (("course", "stat-xxx"), ("course", "math-yyy"),
                             ("project", "demo"), ("goal", "long-term")):
            self.assertEqual(k.select(c.nodes, scope, value), ({"target"}, {"base", "target"}))
        self.assertIn("target", k.select(c.nodes, "subject", "math")[0])
        self.assertEqual(len(c.nodes), 3)
        args = ["--root", str(self.root), "--course", "stat-xxx", "--as-of", AS_OF.isoformat()]
        outputs = []
        for _ in range(2):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(k.main(args), 0)
            outputs.append(out.getvalue())
        self.assertEqual(*outputs)
        self.assertIn("n0 --> n1", outputs[0])
        self.assertIn("external", outputs[0])
        self.assertTrue(k.frontier(c.nodes["target"], k.ready_nodes(c.nodes)))
        self.assertEqual(k.select(c.nodes, "course", "missing"), (set(), set()))

    def test_invalid_course_membership(self):
        for value in ('"course"', '["UPPER"]', '["a", "a"]', '{}', '[1]', 'null'):
            with self.assertRaises(ValueError):
                self.node(record(extra=f"courses: {value}\n"))
        self.put("draft.md", '---\nlearning_schema: 1\nlearning_id: ""\ncourses: ["a"]\n---\n')
        self.assertTrue(k.discover(self.root, AS_OF).diagnostics)



if __name__ == "__main__":
    unittest.main()
