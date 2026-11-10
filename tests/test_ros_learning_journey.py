"""The adaptive learning journey on a synthetic, generic course (nothing here is specific to one subject):
prior evidence before probing, prerequisites, wrong/helped/correct paths, durable drafts and answers, delayed review on
controlled dates, honest media choice and graph notes for agents."""
from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ros import api, graph, home, prepare  # noqa: E402
from ros.learn import evidence, policy, probe, schedule, tutor  # noqa: E402
from ros.store import Record  # noqa: E402

TODAY = date.today()
A, B, C = "capability:basics", "capability:method", "capability:synthesis"
COURSE = "course:generic"


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def stamp(offset: int, hour: int = 10) -> str:
    return f"{day(offset)}T{hour:02d}:00:00Z"


def retrieval(when, outcome="pass", review=None, method="explanation", period="p1"):
    return {"day": when, "period": period, "timing": "same-session", "method": method, "outcome": outcome,
            "assistance": "none", "evidence": f"ev-{when}-{outcome}", "review": review}


class Course(unittest.TestCase):
    """basics <- method <- synthesis, each with a numeric ladder of four levels (item d has answer d)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"ROS_HOME": self.tmp.name, "ROS_NO_VAULT": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(api.release)
        self.rec = Record(Path(self.tmp.name) / "rec")
        self.addCleanup(self.rec.close)
        rec = self.rec
        rec.put_node(COURSE, "course", title="A generic course")
        for cap, title in ((A, "Basics"), (B, "Method"), (C, "Synthesis")):
            rec.put_node(cap, "capability", title=title)
            rec.put_edge(cap, "part-of", COURSE)
        rec.put_edge(B, "requires", A)
        rec.put_edge(C, "requires", B)
        self.items = {cap: {d: rec.put_item({"kind": "numeric", "prompt": f"{cap} level {d}", "answer": d,
                                             "concepts": [cap], "difficulty": d, "hints": ["look again"],
                                             "explanation": "because", "feedback_wrong": "you added instead of multiplying"})
                            for d in range(1, 5)} for cap in (A, B, C)}

    def reopen(self):
        """A restarted process: a new Record on the same directory."""
        self.rec.close()
        api.release()
        self.rec = Record(Path(self.tmp.name) / "rec")
        self.addCleanup(self.rec.close)
        return self.rec

    def known(self, cap, review_in=120):
        self.rec.append("retrieval", cap, retrieval(day(-30), review=day(review_in)), actor="importer")

    def start(self, scope=COURSE, **kw):
        return api.call("start", self.rec, scope=scope, **kw)

    def answer(self, lesson, cap, level, response=None, **kw):
        item = self.items[cap][level]
        return api.call("answer", self.rec, lesson=lesson, item=item, response=level if response is None else response, **kw)

    def item_cap(self, item_id):
        return next(c for c in (self.rec.item(item_id) or {}).get("concepts", []))

    def drive(self, lesson, right=lambda cap, level: True, limit=30):
        """Run the lesson: answer each question from ``right``; teach on request. Returns the steps taken."""
        steps = []
        for _ in range(limit):
            step = api.call("next", self.rec, lesson=lesson)
            steps.append(step)
            if step["action"] in ("close", "wait"):
                break
            if step["action"] == "teach":
                api.call("teach", self.rec, lesson=lesson, capability=step["capability"], mode=step.get("mode", "explain"))
                continue
            cap = self.item_cap(step["item"])
            level = self.rec.item(step["item"])["difficulty"]
            api.call("answer", self.rec, lesson=lesson, item=step["item"],
                     response=level if right(cap, level) else level + 100)
        return steps


class PriorEvidenceTests(Course):
    def test_known_material_is_not_probed_and_the_reason_names_the_evidence(self):
        self.known(A)
        started = self.start()
        prior = {c["id"]: c for c in started["prior"]["capabilities"]}
        self.assertEqual((prior[A]["signal"], prior[A]["action"]), ("known", "skip"))
        self.assertIn("demonstrated", prior[A]["reason"])
        self.assertIn(day(120), prior[A]["reason"])  # its review date stands
        self.assertEqual(prior[B]["signal"], "new")
        self.assertEqual(started["next"]["capability"], B)  # the first question is about the uncertain part
        steps = self.drive(started["lesson"])
        asked = {self.item_cap(s["item"]) for s in steps if s.get("item")}
        self.assertNotIn(A, asked)
        self.assertTrue(asked >= {B})

    def test_everything_known_closes_without_asking_and_says_why(self):
        for cap in (A, B, C):
            self.known(cap)
        started = self.start()
        self.assertEqual(started["next"]["action"], "close")
        self.assertIn("earlier evidence already shows this", started["next"]["reason"])
        self.assertEqual(started["prior"]["counts"]["known"], 3)

    def test_reading_teaching_and_confidence_alone_are_never_mastery(self):
        lesson0 = "lesson:old"
        self.rec.put_node(lesson0, "lesson", title="old", scope=B)
        tutor.teach(self.rec, lesson0, B, "explain")
        tutor.hint(self.rec, lesson0, self.items[B][1])  # reading the explanation is help, not evidence
        tutor.answer(self.rec, lesson0, self.items[B][2], tutor.DONT_KNOW, confidence=5, at=stamp(-3))
        prior = api.call("prior_evidence", self.rec, scope=B)
        entry = {c["id"]: c for c in prior["capabilities"]}[B]
        self.assertNotEqual(entry["signal"], "known")
        self.assertNotEqual(entry["action"], "skip")
        # a capability that was only taught is still uncertain and gets a probe
        self.assertEqual({c["id"]: c for c in api.call("prior_evidence", self.rec, scope=C)["capabilities"]}[C]["action"], "probe")

    def test_shaky_is_taught_not_reprobed_and_earlier_answers_bound_practice(self):
        self.known(A)
        lesson0 = "lesson:old"
        self.rec.put_node(lesson0, "lesson", title="old", scope=B)
        tutor.answer(self.rec, lesson0, self.items[B][1], 1, at=stamp(0, 1))     # right, unaided
        tutor.answer(self.rec, lesson0, self.items[B][3], 99, at=stamp(0, 2))    # wrong at level 3
        started = self.start(scope=B)
        entry = {c["id"]: c for c in started["prior"]["capabilities"]}[B]
        self.assertEqual((entry["signal"], entry["action"]), ("shaky", "teach"))
        step = started["next"]
        self.assertEqual((step["action"], step["capability"]), ("teach", B))
        self.assertIn("rather than asking again", step["reason"])
        lesson = started["lesson"]
        api.call("teach", self.rec, lesson=lesson, capability=B)
        nxt = api.call("next", self.rec, lesson=lesson)
        self.assertEqual(nxt["action"], "practice")
        self.assertEqual(self.rec.item(nxt["item"])["difficulty"], 3)  # starts at the earlier miss, not at level 1
        self.assertEqual(self.rec.events(type="journey.plan", subject=lesson)[0]["data"]["caps"][B]["floor"], 1)

    def test_graph_teaching_signals_count_when_this_record_has_none(self):
        teaching = {"schema": "ros.teaching-signals.v1", "known": [{"id": C, "state": "retained", "next_review": day(90)}],
                    "shaky": [{"id": B, "state": "fragile", "next_review": day(-1)}], "misconceptions": [
                        {"note": "note:m1", "title": "Adds instead of multiplies", "about": [B]}]}
        started = self.start(teaching=teaching)
        prior = {c["id"]: c for c in started["prior"]["capabilities"]}
        self.assertEqual((prior[C]["action"], prior[C]["signal"]), ("skip", "known"))
        self.assertEqual((prior[B]["action"], prior[B]["signal"]), ("teach", "shaky"))
        with self.assertRaises(ValueError):
            self.start(teaching={"schema": "other"})

    def test_prior_plan_is_fixed_when_the_lesson_starts(self):
        started = self.start(scope=B)
        lesson = started["lesson"]
        before = probe.LessonView(self.rec, lesson).prior
        self.drive(lesson)
        self.assertEqual(probe.LessonView(self.rec, lesson).prior, before)
        self.assertEqual(len(self.rec.events(type="journey.plan", subject=lesson)), 1)


class AdaptationTests(Course):
    def shaky_lesson(self):
        """A lesson on B whose earlier answers put the edge at level 3, with B already taught."""
        if not evidence.of(self.rec).cap_answers.get(B):
            self.known(A)
        old = f"lesson:old{len(self.rec.nodes(type='lesson'))}"
        self.rec.put_node(old, "lesson", title="old", scope=B)
        if not evidence.of(self.rec).cap_answers.get(B):
            tutor.answer(self.rec, old, self.items[B][1], 1, at=stamp(0, 1))
            tutor.answer(self.rec, old, self.items[B][3], 99, at=stamp(0, 2))
        started = self.start(scope=B)
        api.call("teach", self.rec, lesson=started["lesson"], capability=B)
        return started["lesson"]

    def test_wrong_helped_and_correct_lead_to_different_justified_steps(self):
        lesson = self.shaky_lesson()
        first = api.call("next", self.rec, lesson=lesson)
        item3 = first["item"]
        self.assertEqual(self.rec.item(item3)["difficulty"], 3)
        # wrong: another try with a hint on offer
        wrong = api.call("answer", self.rec, lesson=lesson, item=item3, response=77)["next"]
        self.assertEqual(wrong["action"], "retry")
        self.assertTrue(wrong["offer_hint"])
        self.assertEqual(wrong["after"]["outcome"], "wrong")
        self.assertTrue(wrong["reason"].startswith("missed"))

        # helped: right only with a hint is not counted; a fresh unaided question follows
        other = self.shaky_lesson()
        api.call("hint", self.rec, lesson=other, item=item3)
        helped = api.call("answer", self.rec, lesson=other, item=item3, response=3)["next"]
        self.assertEqual((helped["action"], helped["after"]["outcome"]), ("practice", "helped"))
        self.assertTrue(helped["unaided"])
        self.assertNotEqual(helped["item"], item3)
        self.assertIn("only with help", helped["reason"])

        # correct without help: one level up
        third = self.shaky_lesson()
        correct = api.call("answer", self.rec, lesson=third, item=item3, response=3)["next"]
        self.assertEqual((correct["action"], correct["after"]["outcome"]), ("practice", "correct"))
        self.assertEqual(self.rec.item(correct["item"])["difficulty"], 4)
        self.assertIn("one level up", correct["reason"])

        # "I do not know" is a miss, named as such, never a guess
        fourth = self.shaky_lesson()
        unknown = api.call("answer", self.rec, lesson=fourth, item=item3, dont_know=True)["next"]
        self.assertEqual(unknown["action"], "retry")
        self.assertEqual(unknown["after"]["outcome"], "dont_know")

        reasons = {wrong["reason"], helped["reason"], correct["reason"], unknown["reason"]}
        self.assertEqual(len(reasons), 4)

    def test_a_miss_on_the_easiest_question_checks_the_prerequisite_even_if_it_was_known(self):
        self.known(A)
        started = self.start(scope=B)
        lesson = started["lesson"]
        self.assertEqual(self.rec.item(started["next"]["item"])["difficulty"], 2)
        miss = self.answer(lesson, B, 2, response=50)["next"]
        self.assertEqual(self.rec.item(miss["item"])["difficulty"], 1)
        repair = self.answer(lesson, B, 1, response=50)["next"]
        self.assertEqual((repair["action"], repair["capability"], repair["repair_for"]), ("probe", A, B))
        self.assertIn("even if earlier evidence called it known", repair["reason"])
        # the prerequisite holds: back to teaching the capability whose edge was found
        back = api.call("answer", self.rec, lesson=lesson, item=repair["item"],
                        response=self.rec.item(repair["item"])["difficulty"])["next"]
        self.assertEqual((back["action"], back["capability"]), ("teach", B))

    def test_three_misses_in_a_row_stop_and_say_the_work_continues_later(self):
        lesson = self.shaky_lesson()
        step = api.call("next", self.rec, lesson=lesson)
        for _ in range(3):
            step = api.call("answer", self.rec, lesson=lesson, item=step["item"], response=88)["next"]
            if step["action"] == "close":
                break
        self.assertEqual(step["action"], "close")
        self.assertIn("misses in a row", step["reason"])

    def test_transfer_follows_known_material_from_a_prepared_lesson(self):
        self.known(A)
        close = self.rec.put_item({"kind": "free", "prompt": "Explain it in your own words.",
                                   "rubric": {"criteria": ["states the idea"]}, "concepts": [A]})
        transfer = self.rec.put_item({"kind": "free", "prompt": "Use it in a new setting.", "concepts": [A]})
        prepare.create(self.rec, "gen-1", "Basics", A)
        plan = prepare.load_plan(self.rec, "gen-1")
        plan["items"] = {"probe": [], "close": [close], "transfer": [transfer], "review": []}
        prepare.save_plan(self.rec, "gen-1", plan)
        lesson = "lesson:prepared"
        self.rec.put_node(lesson, "lesson", title="prepared", scope=A, bundle="gen-1")
        tutor.record_plan(self.rec, lesson, policy.prior_plan(self.rec, A))
        step = policy.decide(self.rec, lesson, A)
        self.assertEqual((step["action"], step["item"]), ("recall", close))  # known: not probed, but recalled
        tutor.answer(self.rec, lesson, close, "my words")
        self.assertEqual(policy.decide(self.rec, lesson, A)["item"], transfer)


class DelayedReviewTests(Course):
    def test_review_dates_come_from_graded_answers_and_the_review_is_scheduled_on_that_day(self):
        lesson = "lesson:r1"
        self.rec.put_node(lesson, "lesson", title="r1", scope=B)
        first = TODAY - timedelta(days=60)
        tutor.answer(self.rec, lesson, self.items[B][1], 1, at=f"{first.isoformat()}T09:00:00Z")
        card = next(c for c in schedule.schedule(self.rec, TODAY) if c["id"] == self.items[B][1])
        due = date.fromisoformat(card["due"])
        # nothing is due the day before; the day it falls due the policy puts it first, with the date in the reason
        tutor.record_plan(self.rec, lesson, policy.prior_plan(self.rec, B, due - timedelta(days=1)))
        self.assertNotEqual(policy.decide(self.rec, lesson, B, due - timedelta(days=1))["action"], "review")
        lesson2 = "lesson:r2"
        self.rec.put_node(lesson2, "lesson", title="r2", scope=B)
        tutor.record_plan(self.rec, lesson2, policy.prior_plan(self.rec, B, due))
        step = policy.decide(self.rec, lesson2, B, due)
        self.assertEqual((step["action"], step["item"]), ("review", self.items[B][1]))
        self.assertIn(f"due for review since {due.isoformat()}", step["reason"])
        # a correct review on that day pushes the next date out
        tutor.answer(self.rec, lesson2, self.items[B][1], 1, at=f"{due.isoformat()}T09:00:00Z")
        later = next(c for c in schedule.schedule(self.rec, due) if c["id"] == self.items[B][1])
        self.assertGreater(date.fromisoformat(later["due"]), due)
        self.assertEqual(later["reviews"], 2)

    def test_a_known_capability_that_falls_due_is_checked_again_not_skipped(self):
        self.rec.append("retrieval", A, retrieval(day(-90), review=day(-2)), actor="importer")
        entry = {c["id"]: c for c in api.call("prior_evidence", self.rec, scope=A)["capabilities"]}[A]
        self.assertEqual((entry["signal"], entry["action"]), ("due", "probe"))
        self.assertIn(day(-2), entry["reason"])

    def test_dates_and_answers_survive_a_restart_and_regrading_changes_nothing(self):
        started = self.start(scope=B)
        lesson, item = started["lesson"], started["next"]["item"]
        first = api.call("answer", self.rec, lesson=lesson, item=item, response=2, key="client-a-1")
        due_before = [c["due"] for c in schedule.schedule(self.rec, TODAY)]
        count = len(self.rec.events())
        self.reopen()
        again = api.call("answer", self.rec, lesson=lesson, item=item, response=2, key="client-a-1")
        other = api.call("answer", self.rec, lesson=lesson, item=item, response=999, key="client-a-1")  # a client's retry
        self.assertTrue(again["duplicate"] and other["duplicate"])
        self.assertEqual(again["attempt"], first["attempt"])
        self.assertEqual(other["verdict"], first["verdict"])
        self.assertEqual(len(self.rec.events(type="attempt")), 1)
        self.assertEqual(len(self.rec.events(type="grade")), 1)
        self.assertEqual([c["due"] for c in schedule.schedule(self.rec, TODAY)], due_before)
        self.assertEqual(len(self.rec.events()), count)
        state = api.call("lesson_state", self.rec, lesson=lesson)
        self.assertEqual([a["attempt"] for a in state["answers"]], [first["attempt"]])
        self.assertEqual({r["id"] for r in state["reviews"]}, {A, B})

    def test_a_tutor_grade_sent_twice_is_one_grade_and_one_closed_task(self):
        free = self.rec.put_item({"kind": "free", "prompt": "Explain.", "rubric": {"criteria": ["x"]}, "concepts": [B]})
        lesson = self.start(scope=B)["lesson"]
        sent = api.call("answer", self.rec, lesson=lesson, item=free, response="because", key="k")
        again = api.call("answer", self.rec, lesson=lesson, item=free, response="because", key="k")
        self.assertEqual(sent["task"], again["task"])
        for _ in range(2):
            api.call("grade", self.rec, attempt=sent["attempt"], verdict="correct", feedback="good", by="tutor")
        self.reopen()
        api.call("grade", self.rec, attempt=sent["attempt"], verdict="correct", feedback="good", by="tutor")
        self.assertEqual(len(self.rec.events(type="grade", subject=free)), 1)
        self.assertEqual(len([t for t in api.call("tasks", self.rec, kind="grade") if t["ref"] == sent["attempt"]]), 0)

    def test_two_processes_with_stale_indexes_write_one_attempt_and_one_grade_for_one_key(self):
        started = self.start(scope=B)
        lesson, item, key = started["lesson"], started["next"]["item"], started["next"]["answer_key"]
        other = Record(Path(self.tmp.name) / "rec")  # a second client's own handle, opened before the first writes
        self.addCleanup(other.close)
        other.events()
        first = tutor.answer(self.rec, lesson, item, 2, key=key)
        second = tutor.answer(other, lesson, item, 77, key=key)
        third = tutor.answer(other, lesson, item, tutor.DONT_KNOW, key=key, confidence=5)
        self.assertTrue(second["duplicate"] and third["duplicate"])
        self.assertEqual({second["attempt"], third["attempt"]}, {first["attempt"]})
        fresh = Record(Path(self.tmp.name) / "rec")
        self.addCleanup(fresh.close)
        self.assertEqual(len(fresh.events(type="attempt", subject=item)), 1)
        self.assertEqual(len(fresh.events(type="grade", subject=item)), 1)
        self.assertEqual(len(fresh.events(type="confidence")), 0)  # the loser's confidence is not attached to the winner

    def test_an_answer_whose_writer_stopped_before_grading_is_finished_once_on_retry(self):
        started = self.start(scope=B)
        lesson, item, key = started["lesson"], started["next"]["item"], started["next"]["answer_key"]
        attempt_id = "att-" + tutor._digest(lesson, item, key)
        self.rec.append_once(tutor.make_event("attempt", item, {"lesson": lesson, "response": 2}, actor="learner", id=attempt_id))
        self.assertEqual(len(self.rec.events(type="grade", subject=item)), 0)  # the writer died here
        retry = tutor.answer(self.rec, lesson, item, 2, key=key)
        self.assertEqual((retry["verdict"], retry["duplicate"]), ("correct", True))
        tutor.answer(self.rec, lesson, item, 2, key=key)
        self.assertEqual(len(self.rec.events(type="grade", subject=item)), 1)


class DraftTests(Course):
    def test_a_draft_follows_the_learner_between_clients_and_restarts(self):
        started = self.start(scope=B)
        lesson, item = started["lesson"], started["next"]["item"]
        saved = api.call("draft_save", self.rec, lesson=lesson, item=item, text="I think it is", client="app")
        self.assertTrue(saved["saved"])
        same = api.call("draft_save", self.rec, lesson=lesson, item=item, text="I think it is", client="terminal")
        self.assertFalse(same["saved"])
        self.reopen()
        self.assertEqual(api.call("draft_get", self.rec, lesson=lesson, item=item)["draft"]["text"], "I think it is")
        self.assertEqual(api.call("next", self.rec, lesson=lesson)["draft"]["text"], "I think it is")
        # another client writes meanwhile: the stale one is told, and nothing is lost
        api.call("draft_save", self.rec, lesson=lesson, item=item, text="I think it is two", client="terminal",
                 base=saved["draft"]["id"])
        clash = api.call("draft_save", self.rec, lesson=lesson, item=item, text="three", client="app", base=saved["draft"]["id"])
        self.assertTrue(clash["conflict"])
        self.assertEqual(clash["other"]["text"], "I think it is two")
        # sending the answer ends the draft; a draft is never evidence
        before = len(self.rec.events(type="grade"))
        api.call("answer", self.rec, lesson=lesson, item=item, response=2)
        self.assertIsNone(api.call("draft_get", self.rec, lesson=lesson, item=item)["draft"])
        self.assertEqual(len(self.rec.events(type="grade")), before + 1)
        self.assertEqual(len(self.rec.events(type="draft")), 3)

    def test_every_client_shown_a_question_gets_one_answer_key_so_two_clients_write_one_answer(self):
        started = self.start(scope=B)
        lesson, shown = started["lesson"], started["next"]
        self.assertEqual(api.call("next", self.rec, lesson=lesson)["answer_key"], shown["answer_key"])
        first = api.call("answer", self.rec, lesson=lesson, item=shown["item"], response=2, key=shown["answer_key"])
        second = api.call("answer", self.rec, lesson=lesson, item=shown["item"], response=77, key=shown["answer_key"])
        self.assertTrue(second["duplicate"])
        self.assertEqual((second["attempt"], second["verdict"]), (first["attempt"], first["verdict"]))
        self.assertEqual(len(self.rec.events(type="attempt")), 1)
        after = api.call("next", self.rec, lesson=lesson)
        if after.get("item") == shown["item"]:  # asked again (a retry): a new presentation, a new key
            self.assertNotEqual(after["answer_key"], shown["answer_key"])


class MediaTests(Course):
    def node_dir(self):
        prepare.create(self.rec, "m-1", "Method", B)
        return prepare.bundle_dir(self.rec, "m-1")

    def test_medium_follows_the_learning_goal_and_the_reason_is_recorded(self):
        text = api.call("medium_choose", self.rec, goal="a definition", nature="definition")
        visual = api.call("medium_choose", self.rec, goal="how two quantities relate", nature="relationship")
        motion = api.call("medium_choose", self.rec, goal="how an estimate settles", nature="convergence")
        code = api.call("medium_choose", self.rec, goal="sample-to-sample variation", nature="sampling")
        self.assertEqual([x["chosen"] for x in (text, visual, motion, code)], ["text", "static-visual", "animation", "code"])
        for x in (text, visual, motion, code):
            self.assertTrue(x["text_first"] and not x["blocks_teaching"])
            self.assertTrue(x["reason"])
        self.assertEqual(api.call("medium_choose", self.rec, goal="g", nature="sampling", requested="simpler")["chosen"], "text")
        with self.assertRaises(ValueError):
            api.call("medium_choose", self.rec, goal="g", nature="vibes")

    def test_a_missing_engine_falls_back_and_says_so_without_blocking(self):
        d = self.node_dir()
        plan = prepare.load_plan(self.rec, "m-1")
        node = plan["nodes"][0]
        node.update(dynamic=True, segments=[{"id": "s1", "role": "establish", "text": "Words that explain it."}],
                    visuals=[{"path": "visuals/f.svg"}])
        prepare.save_plan(self.rec, "m-1", plan)
        (d / "visuals").mkdir()
        (d / "visuals" / "f.svg").write_text("<svg/>")
        with patch.object(prepare, "engines", return_value={
                "voice": {"state": "unavailable", "note": "no voice engine"},
                "animation": {"state": "unavailable", "note": "no animation renderer found"},
                "renderer": {"state": "available", "note": ""}}):
            chosen = prepare.choose_medium("Method", None, None, node, d, probe_engines=True)
        self.assertEqual(chosen["chosen"], "animation")
        self.assertEqual(chosen["delivered"], "static-visual")  # the figure exists, the animation cannot be made
        self.assertIn("no animation renderer found", " ".join(chosen["notes"]))
        self.assertFalse(chosen["blocks_teaching"])
        self.assertEqual(chosen["readiness"]["animation"]["state"], "not-rendered")
        self.assertEqual(chosen["readiness"]["narration-audio"]["state"], "not-spoken")
        self.assertEqual(chosen["readiness"]["text"]["state"], "ready")

    def test_a_bundle_with_words_and_questions_is_taught_while_media_are_missing(self):
        probe_items = list(self.items[B].values())[:3]
        close = self.rec.put_item({"kind": "free", "prompt": "Explain it.", "rubric": {"criteria": ["x"]}, "concepts": [B]})
        transfer = self.rec.put_item({"kind": "free", "prompt": "Apply it elsewhere.", "concepts": [B]})
        check = self.rec.put_item({"kind": "choice", "prompt": "Pick", "options": ["a", "b"], "answer": 1, "concepts": [B]})
        prepare.create(self.rec, "m-2", "Method", B)
        plan = prepare.load_plan(self.rec, "m-2")
        plan["nodes"][0]["segments"] = [{"id": "s1", "role": "establish", "text": "The method is a repeated step.",
                                         "claims": [{"text": "definition", "derivation": True}]}]
        plan["nodes"][0]["items"] = {"check": [check]}
        plan["items"] = {"probe": probe_items, "close": [close], "transfer": [transfer], "review": []}
        prepare.save_plan(self.rec, "m-2", plan)
        self.assertFalse(prepare.check(self.rec, "m-2")["ready"])  # the full gate still wants voice and a figure
        readiness = api.call("bundle_readiness", self.rec, bundle="m-2")
        self.assertTrue(readiness["teachable"] and not readiness["ready"])
        listed = {b["id"]: b for b in api.call("bundles", self.rec)}
        self.assertEqual((listed["m-2"]["ready"], listed["m-2"]["teachable"]), (False, True))
        today = api.call("today", self.rec)
        self.assertEqual((today["next_lesson"]["bundle"], today["next_lesson"]["teachable"]), ("m-2", True))
        started = api.call("start", self.rec, bundle="m-2")
        self.assertTrue(started["readiness"]["teachable"] and not started["readiness"]["ready"])
        self.assertTrue(any("voice" in m or "visual" in m for m in started["readiness"]["missing_media"]))
        self.assertIn(started["next"]["action"], ("probe", "teach"))
        # a bundle whose words are missing is still refused
        prepare.create(self.rec, "m-3", "Empty", B)
        with self.assertRaises(ValueError) as caught:
            api.call("start", self.rec, bundle="m-3")
        self.assertIn("not ready", str(caught.exception))

    def test_code_examples_report_what_was_and_was_not_executed(self):
        d = self.node_dir()
        (d / "sim.py").write_text("print(1)\n", encoding="utf-8")
        shown = api.call("bundle_code", self.rec, bundle="m-1", node=B, path="sim.py")
        self.assertEqual((shown["state"], shown["executed"], shown["verified_by_research_os"]), ("not-run", False, False))
        run = {"ran_at": "2026-01-02T03:04:05Z", "runtime": "python 3.12", "exit_code": 0, "ran_by": "tutor-agent"}
        proven = api.call("bundle_code", self.rec, bundle="m-1", node=B, path="sim.py", execution=run)
        self.assertEqual((proven["state"], proven["executed"]), ("run-recorded", True))
        self.assertIn("not re-run by Research OS", proven["note"])
        self.assertFalse(proven["verified_by_research_os"])
        (d / "sim.py").write_text("print(2)\n", encoding="utf-8")  # edited after the recorded run
        node = prepare.load_plan(self.rec, "m-1")["nodes"][0]
        self.assertEqual(prepare.media_readiness(d, node, check_engines=False)["code"]["examples"][0]["state"], "changed")
        with self.assertRaises(ValueError):
            api.call("bundle_code", self.rec, bundle="m-1", node=B, path="sim.py", execution={"exit_code": 0})

    def test_prepared_reading_shows_each_sections_readiness_and_recorded_code(self):
        prepare.create(self.rec, "rd", "Reading", A)
        plan = prepare.load_plan(self.rec, "rd")
        plan["nodes"] = [{"id": "n1", "title": "One", "segments": [{"text": "Words."}], "code": [{"path": "x.py", "language": "python"}]}]
        (prepare.bundle_dir(self.rec, "rd") / "plan.json").write_text(__import__("json").dumps(plan), encoding="utf-8")
        self.rec.put_node("lesson:rd", "lesson", title="Reading", bundle="rd")
        section = api.call("workspace_lesson_material", self.rec, lesson="lesson:rd")["sections"][0]
        self.assertEqual(section["readiness"]["text"]["state"], "ready")
        self.assertEqual(section["readiness"]["static-visual"]["state"], "not-planned")
        self.assertEqual(section["code"], [{"path": "x.py", "language": "python"}])
        self.assertEqual(section["readiness"]["code"]["state"], "missing", "a recorded example whose file is absent is not ready")

    def test_engine_readiness_is_honest_and_never_blocks(self):
        out = api.call("learning_readiness", self.rec)
        self.assertFalse(out["blocks_teaching"])
        self.assertEqual(set(out["engines"]), {"voice", "animation", "renderer", "code"})
        self.assertEqual(out["engines"]["code"]["state"], "recorded-only")

    def test_the_chosen_medium_is_logged_with_its_reason_when_teaching(self):
        self.known(A)
        self.rec.put_node(B, "capability", title="Method", nature="relationship")
        started = self.start(scope=B)
        step = started["next"]
        while step["action"] != "teach":
            level = self.rec.item(step["item"])["difficulty"]
            step = api.call("answer", self.rec, lesson=started["lesson"], item=step["item"],
                            response=999 if level == 2 else level)["next"]
        self.assertEqual(step["medium"]["chosen"], "static-visual")
        self.assertEqual(step["medium"]["delivered"], "text")  # nothing is prepared, so the tutor explains in words
        logged = [e for e in self.rec.events(type="policy", subject=started["lesson"]) if e["data"].get("medium")]
        self.assertTrue(logged and logged[-1]["data"]["medium_reason"])


class WorkspaceAndGraphTests(Course):
    def test_a_lesson_is_stamped_with_a_valid_workspace_and_creates_none(self):
        before = sorted(p.name for p in Path(self.tmp.name).iterdir())
        own = self.start(scope=B)
        self.assertEqual(own["workspace_id"], home.workspace_id(self.rec.root))
        self.assertEqual(self.rec.node(own["lesson"])["workspace_id"], own["workspace_id"])
        again = self.start(scope=B, workspace_id=own["workspace_id"])
        self.assertEqual(again["workspace_id"], own["workspace_id"])
        with self.assertRaises(ValueError):  # a made-up workspace is refused, not stamped, and nothing is created
            self.start(scope=B, workspace_id="ws:knowledge:course:made-up")
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), before)
        self.assertEqual(api.call("lesson_state", self.rec, lesson=own["lesson"])["workspace_id"], own["workspace_id"])

    def linked(self):
        me = Record(Path(self.tmp.name) / "projects" / "me")
        proj = Record(Path(self.tmp.name) / "projects" / "proj")
        self.addCleanup(me.close)
        self.addCleanup(proj.close)
        api.call("link", me, user_wide=True)
        api.call("link", proj, project="project:generic", title="Generic study")
        return me, proj, home.workspace_id(proj.root)

    def test_a_lesson_in_a_linked_project_is_stamped_with_that_workspace(self):
        _, proj, wid = self.linked()
        proj.put_node(B, "capability", title="Method")
        started = api.call("start", proj, scope=B, workspace_id=wid)
        self.assertEqual(started["workspace_id"], wid)
        self.assertEqual(proj.node(started["lesson"])["workspace_id"], wid)

    def test_a_linked_record_shows_what_the_workspace_graph_already_knows(self):
        me, proj, wid = self.linked()
        for rec in (me, proj):
            rec.put_node(B, "capability", title="Method")
        me.put_edge(B, "part-of", "project:generic")
        me.append("retrieval", B, retrieval(day(-20), review=day(100)), actor="importer")
        started = api.call("start", proj, scope=B, workspace_id=wid)
        entry = {c["id"]: c for c in started["prior"]["capabilities"]}[B]
        self.assertEqual((entry["signal"], entry["action"]), ("known", "skip"))
        self.assertEqual(started["next"]["action"], "close")  # nothing to ask: the person already shows it elsewhere

    def test_close_hands_the_agent_graph_notes_and_writes_none_itself(self):
        choice = self.rec.put_item({"kind": "choice", "prompt": "Pick", "options": ["adds", "multiplies"], "answer": 1,
                                    "option_feedback": ["That adds the terms; the rule multiplies them.", None],
                                    "concepts": [B], "difficulty": 1})
        started = self.start(scope=B)
        lesson = started["lesson"]
        api.call("answer", self.rec, lesson=lesson, item=choice, response=0)
        nodes_before = len(self.rec.nodes())
        closed = api.call("close", self.rec, lesson=lesson, summary="done")
        notes = closed["graph_notes"]
        self.assertEqual((notes["for"], notes["call"]), ("agent", "graph_note_add"))
        mis = [n for n in notes["notes"] if n["kind"] == "misconception"]
        self.assertEqual(len(mis), 1)
        self.assertIn(mis[0]["kind"], graph.NOTE_KINDS)
        self.assertTrue(all(link["type"] in graph.NOTE_LINKS for link in mis[0]["links"]))
        self.assertEqual(mis[0]["links"][0]["target"], B)
        again = api.call("close", self.rec, lesson=lesson, summary="done")["graph_notes"]["notes"]
        self.assertEqual([n["key"] for n in again], [n["key"] for n in notes["notes"]])  # stable keys: written once
        self.assertEqual(len(self.rec.nodes()), nodes_before)  # the lesson itself writes no graph note
        for name in ("graph_note_add", "graph_note_revise", "graph_note_retract"):
            self.assertFalse(api.TOOLS[name].human)
        # a lesson the person closed in the app still hands the notes to whichever agent reads its state
        self.assertEqual([n["key"] for n in api.call("lesson_state", self.rec, lesson=lesson)["graph_notes"]["notes"]],
                         [n["key"] for n in notes["notes"]])

    def test_suggested_notes_are_accepted_by_the_real_graph_note_tool(self):
        _, proj, wid = self.linked()
        proj.put_node(B, "capability", title="Method")
        choice = proj.put_item({"kind": "choice", "prompt": "Pick", "options": ["adds", "multiplies"], "answer": 1,
                                "option_feedback": ["That adds the terms; the rule multiplies them.", None],
                                "concepts": [B], "difficulty": 1})
        lesson = api.call("start", proj, scope=B, workspace_id=wid)["lesson"]
        api.call("answer", proj, lesson=lesson, item=choice, response=0)
        notes = api.call("close", proj, lesson=lesson, summary="done")["graph_notes"]["notes"]
        self.assertTrue(notes)
        for note in notes:
            written = api.call("graph_note_add", proj, by="tutor-agent", workspace_id=wid, **note)
            again = api.call("graph_note_add", proj, by="tutor-agent", workspace_id=wid, **note)
            self.assertEqual((again["note"], again["replayed"]), (written["note"], True))  # the stable key: a no-op


class ToolContractTests(unittest.TestCase):
    def test_new_tools_are_declared_without_a_human_act(self):
        for name in ("prior_evidence", "draft_save", "draft_get", "lesson_state", "learning_readiness", "medium_choose",
                     "bundle_readiness", "bundle_code"):
            self.assertIn(name, api.TOOLS)
            self.assertFalse(api.TOOLS[name].human, name)
        self.assertTrue(api.TOOLS["draft_save"].writes and api.TOOLS["bundle_code"].writes)
        self.assertFalse(api.TOOLS["lesson_state"].writes or api.TOOLS["prior_evidence"].writes)


if __name__ == "__main__":
    unittest.main()
