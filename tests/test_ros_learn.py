"""The learning engine: FSRS parity, answer checking, bracketing, and the policy driving whole lessons."""
from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import tasks  # noqa: E402
from ros.learn import policy, probe, schedule, tutor  # noqa: E402
from ros.store import Record  # noqa: E402

CAP = "capability:var"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rec = Record(Path(self._tmp.name) / "rec")
        self.addCleanup(self.rec.close)

    def ladder(self, cap=CAP, n=5):
        """Numeric items of difficulty 1..n; item d's answer is d."""
        self.rec.put_node(cap, "capability", title=cap)
        return {d: self.rec.put_item({"kind": "numeric", "prompt": f"{cap} level {d}", "answer": d,
                                      "concepts": [cap], "difficulty": d, "hints": ["h1"], "explanation": "e"})
                for d in range(1, n + 1)}


class ScheduleTests(Fixture):
    def test_golden_values(self):
        golden = json.loads((ROOT / "tests" / "fixtures" / "fsrs-golden.json").read_text(encoding="utf-8"))
        for case in golden["cases"]:
            p, card, d0 = tuple(case["parameters"]), schedule.Card(), date(2026, 1, 1)
            for r in case["reviews"]:
                card = schedule.review(card, r["rating"], d0 + timedelta(days=r["day"]), p)
                self.assertAlmostEqual(card.stability, r["stability"], places=3)
                self.assertAlmostEqual(card.difficulty, r["difficulty"], places=3)
                self.assertEqual(schedule.interval_days(card.stability, case["desired_retention"], p), r["interval"])

    def test_grades_become_reviews_of_item_and_capability_and_help_lowers_rating(self):
        items = self.ladder()
        tutor.answer(self.rec, "L1", items[1], 1)
        tutor.hint(self.rec, "L1", items[2])
        tutor.answer(self.rec, "L1", items[2], 2)
        revs = schedule.reviews(self.rec, date(2100, 1, 1))
        self.assertEqual([r for _, r in revs[items[1]]], [schedule.GOOD])
        self.assertEqual([r for _, r in revs[items[2]]], [schedule.HARD])
        self.assertEqual(len(revs[CAP]), 2)
        self.assertTrue(schedule.due(self.rec, date.today() + timedelta(days=400)))


class TutorTests(Fixture):
    def test_checking(self):
        choice = {"kind": "choice", "options": ["a", "B"], "answer": 1}
        self.assertEqual([tutor.check(choice, r) for r in (1, "1", "b", "a", "zzz")],
                         ["correct", "correct", "correct", "incorrect", "incorrect"])
        num = {"kind": "numeric", "answer": 0.5, "tolerance": 0.01}
        self.assertEqual([tutor.check(num, r) for r in ("0,505", 0.52, "x", "nan")],
                         ["correct", "incorrect", "incorrect", "incorrect"])
        self.assertIsNone(tutor.check({"kind": "free"}, "anything"))

    def test_free_answer_opens_a_grade_task_until_graded(self):
        h = self.rec.put_item({"kind": "free", "prompt": "Why?", "concepts": [CAP]})
        out = tutor.answer(self.rec, "L1", h, "because")
        self.assertEqual(out["verdict"], "pending")
        self.assertEqual([t["id"] for t in tasks.tasks(self.rec, kind="grade")], [out["task"]])
        tasks.claim(self.rec, out["task"], "agent-a")
        with self.assertRaises(ValueError):
            tasks.claim(self.rec, out["task"], "agent-b")
        tutor.grade(self.rec, out["attempt"], "partially-correct", "close", by="agent-a")
        self.assertEqual(tasks.tasks(self.rec, kind="grade"), [])
        self.assertEqual(probe.outcomes(self.rec, "L1")[0]["verdict"], "partially-correct")

    def test_dont_know_is_a_miss_without_a_grader(self):
        h = self.rec.put_item({"kind": "free", "prompt": "Why?", "explanation": "Because."})
        out = tutor.answer(self.rec, "L", h, tutor.DONT_KNOW)
        self.assertEqual((out["verdict"], out["explanation"]), ("incorrect", "Because."))
        self.assertEqual(tasks.tasks(self.rec, kind="grade"), [])

    def test_hints_then_reveal(self):
        h = self.rec.put_item({"kind": "free", "prompt": "P", "hints": ["one", "two"], "explanation": "E"})
        self.assertEqual([tutor.hint(self.rec, "L", h).get("hint") for _ in range(2)], ["one", "two"])
        self.assertEqual(tutor.hint(self.rec, "L", h)["explanation"], "E")

    def test_ask_and_reply(self):
        out = tutor.ask(self.rec, "L", "Why squares?")
        tutor.reply(self.rec, out["ask"], "Because signs cancel.")
        self.assertEqual(tasks.tasks(self.rec, kind="answer"), [])
        self.assertEqual(self.rec.events(type="answer")[0]["subject"], out["ask"])


class BracketTests(Fixture):
    def test_binary_search_finds_the_edge(self):
        items = self.ladder(n=9)
        for skill in (0, 3, 6, 9):
            lesson = f"L{skill}"
            for _ in range(10):
                b = probe.bracket(probe.LessonView(self.rec, lesson), CAP, budget=10)
                if b["done"]:
                    break
                d = next(k for k, v in items.items() if v == b["next"])
                tutor.answer(self.rec, lesson, b["next"], d if d <= skill else -1)
            with self.subTest(skill=skill):
                self.assertEqual(b["floor"], skill or None)
                self.assertEqual(b["ceiling"], skill + 1 if skill < 9 else None)
                self.assertLessEqual(b["asked"], 4)


class PolicyTests(Fixture):
    def run_lesson(self, skill, lesson="L", budget=12):
        """A learner who answers everything at or below ``skill`` and learns one level each time they are taught."""
        items = self.ladder()
        trace = []
        for _ in range(40):
            d = policy.decide(self.rec, lesson, CAP, budget=budget)
            trace.append(d["action"])
            if d["action"] in ("close", "wait"):
                return trace, d
            if d["action"] == "teach":
                tutor.teach(self.rec, lesson, d["capability"] or CAP, d["mode"])
                skill += 1
                continue
            level = next(k for k, v in items.items() if v == d["item"])
            tutor.answer(self.rec, lesson, d["item"], level if level <= skill else -1)
        self.fail(f"lesson did not end: {trace}")

    def test_probe_then_teach_then_practice_then_close(self):
        trace, last = self.run_lesson(skill=2)
        self.assertEqual(trace[0], "probe")
        self.assertIn("teach", trace)
        self.assertIn("practice", trace)
        self.assertLess(trace.index("teach"), trace.index("practice"))
        self.assertEqual(last["action"], "close")

    def test_three_misses_stop_the_lesson(self):
        items = self.ladder()
        tutor.teach(self.rec, "L", CAP)
        for d in (1, 2, 3):
            tutor.answer(self.rec, "L", items[d], -1)
        out = policy.decide(self.rec, "L", CAP)
        self.assertEqual(out["action"], "close")
        self.assertIn("misses", out["reason"])

    def test_after_teaching_a_miss_is_retried_then_shown_worked(self):
        items = self.ladder()
        tutor.teach(self.rec, "L", CAP)
        tutor.answer(self.rec, "L", items[1], -1)
        self.assertEqual(policy.decide(self.rec, "L", CAP)["action"], "retry")
        tutor.answer(self.rec, "L", items[1], -1)
        d = policy.decide(self.rec, "L", CAP)
        self.assertEqual((d["action"], d["mode"]), ("teach", "worked-example"))

    def test_learner_request_sets_the_teaching_mode(self):
        items = self.ladder()
        tutor.answer(self.rec, "L", items[3], -1)
        self.rec.append("ask", "L", {"lesson": "L", "mode": "visual"})
        for _ in range(4):
            d = policy.decide(self.rec, "L", CAP)
            if d["action"] == "teach":
                break
            tutor.answer(self.rec, "L", d["item"], -1)
        self.assertEqual((d["action"], d["mode"]), ("teach", "visual"))

    def test_due_reviews_come_first(self):
        items = self.ladder()
        self.rec.append("grade", items[4], {"verdict": "correct"}, ts="2026-01-01T00:00:00Z")
        d = policy.decide(self.rec, "L", CAP, as_of=date(2026, 6, 1))
        self.assertEqual((d["action"], d["item"]), ("review", items[4]))

    def test_ungraded_free_answers_wait(self):
        self.rec.put_node(CAP, "capability")
        h = self.rec.put_item({"kind": "free", "prompt": "Why?", "concepts": [CAP]})
        d = policy.decide(self.rec, "L", CAP)
        tutor.answer(self.rec, "L", d["item"], "because")
        self.assertEqual(policy.decide(self.rec, "L", CAP)["action"], "wait")
        self.assertEqual(h, d["item"])


if __name__ == "__main__":
    unittest.main()
