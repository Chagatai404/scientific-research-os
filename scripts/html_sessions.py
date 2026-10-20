"""HTML-primary sessions, exact Markdown bridges, and reversible migration.

Structured JSON owns content. HTML and Markdown are deterministic projections;
browser interaction is pending review and cannot confer learning credit.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import base64
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time
import urllib.parse
import uuid

from common import load_config, parse_frontmatter
import rich_text

SCHEMA_VERSION = 1
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10000
# A standalone export embeds each recorded narration it can; a recording over the per-file or the total limit stays out and that card uses the browser voice.
MAX_EXPORT_AUDIO = 3 * 1024 * 1024
MAX_EXPORT_AUDIO_TOTAL = 12 * 1024 * 1024
AUDIO_TYPES = {".wav": "audio/wav", ".ogg": "audio/ogg", ".mp3": "audio/mpeg"}
BRIDGE_MARKER = "\n<!-- research-os:html-session -->\n"
RUNTIME = Path(__file__).resolve().parents[1] / "assets" / "html-runtime"


class Lock:
    """Filesystem lock shared with the host's session update protocol."""
    def __init__(self, path, timeout=3.0):
        self.path, self.timeout = path, timeout

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() - start > self.timeout:
                    raise ValueError(f"Session is being updated: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *args):
        os.close(self.fd)
        self.path.unlink(missing_ok=True)


def install_runtime(root):
    destination = _path(root, ".research-os/runtime")
    if not RUNTIME.is_dir():
        raise ValueError("Bundled HTML runtime missing")
    copies = []
    for source in RUNTIME.rglob("*"):
        if source.is_file():
            target = _path(root, Path(".research-os/runtime") / source.relative_to(RUNTIME))
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError(f"Runtime resource conflict: {target}; update explicitly after backup")
            copies.append((source, target))
    destination.mkdir(parents=True, exist_ok=True)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _path(root, relative):
    root = Path(root).resolve()
    lexical = root / relative
    for part in (lexical, *lexical.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Symlink session paths are unsupported")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Session path must stay within the vault")
    return path


def resource_id(resource):
    """A resource's identity. v0.8 sessions may omit `id` on an image; the Obsidian host has always used the path then, so every reader here does too."""
    return resource.get("id") or resource["path"]


def paths(root, relative_md):
    md = _path(root, relative_md)
    if md.suffix.lower() != ".md":
        raise ValueError("Session compatibility path must end in .md")
    return md, md.with_suffix(".html"), md.with_suffix(".state.json")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _approved_module(root, path, resource):
    registry = _path(root, '.research-os/runtime/extensions/trusted-modules.json')
    approved = json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else {}
    relative = path.relative_to(Path(root).resolve()).as_posix()
    digest = _hash(path.read_bytes())
    if resource.get('sha256') != digest or approved.get(relative) != digest:
        raise ValueError('Local module requires a matching independently approved SHA-256 trust entry')


PLAN_VERDICTS = ('correct', 'wrong', 'pending')


def validate_interaction(event, question_ids, plan_ids=frozenset()):
    if not isinstance(event, dict) or set(event) - {'event_id','type','question_id','response','created_at','status','origin'}:
        raise ValueError('Unknown interaction event field')
    if isinstance(event, dict) and event.get('type') == 'plan-answer':
        # An answer to a question in the session plan, judged on the page against the plan's own key: a pacing decision, never evidence of learning.
        response = event.get('response')
        if (event.get('question_id') not in plan_ids or not isinstance(response, dict) or set(response) - {'answer', 'verdict', 'tree'}
                or response.get('verdict') not in PLAN_VERDICTS or response.get('tree') not in ('probe', 'check')
                or not isinstance(response.get('answer'), (str, int, float)) or isinstance(response.get('answer'), bool)):
            raise ValueError('A plan answer names a plan question, an answer, a verdict and the tree it belongs to')
    if 'origin' in event:
        # Where in the lesson an open question was asked, so the learner can return there; a section anchor and its title.
        origin = event['origin']
        if (event.get('type') not in ('open-question', 'explanation-request') or not isinstance(origin, dict) or set(origin) - {'section', 'title'}
                or not isinstance(origin.get('section'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', origin['section'])
                or not isinstance(origin.get('title'), str) or len(origin['title']) > 200):
            raise ValueError('Invalid question origin')
    if not isinstance(event.get('event_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', event['event_id']):
        raise ValueError('Invalid interaction event ID')
    if event.get('created_at') is not None:
        try:
            dt.datetime.fromisoformat(event['created_at'].replace('Z','+00:00'))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid interaction timestamp') from None
    if event.get('type') == 'explanation-request':
        # A request for another explanation: one of the known modes, tied to no question, and never evidence of anything.
        if not (isinstance(event.get('response'), str) and event['response'] in ADAPT_MODES) or event.get('question_id') is not None:
            raise ValueError('An explanation request names one known mode and no question')
    elif event.get('type') in {'open-question','checkpoint'}:
        if not isinstance(event.get('response'), str) or not event['response'].strip():
            raise ValueError('Question/checkpoint requires bounded nonempty text')
    elif event.get('type') in {'plan-answer', 'pedagogy-help'}:
        pass                                    # checked above against the plan's question ids
    else:
        if event.get('question_id') not in question_ids:
            raise ValueError('Unknown interaction question')
    def bounded(value, depth=0):
        if depth > 4:
            raise ValueError('Response nesting limit exceeded')
        if value is None or isinstance(value, (str,bool)):
            return
        if isinstance(value,(int,float)) and math.isfinite(value):
            return
        if isinstance(value,list) and len(value) <= 100:
            for item in value: bounded(item,depth+1)
            return
        if isinstance(value,dict) and len(value) <= 100:
            for key,item in value.items():
                if key in {'__proto__','constructor','prototype'}: raise ValueError('Invalid response key')
                bounded(item,depth+1)
            return
        raise ValueError('Invalid bounded response')
    bounded(event.get('response'))
    if len(json.dumps(event,ensure_ascii=False,allow_nan=False)) > 16384:
        raise ValueError('Interaction event exceeds limit')


REVIEW_VERDICTS = ("correct", "partially-correct", "incorrect", "reviewed")
# What a learner can ask for instead of moving on. A request is a request: it never counts as demonstrated understanding.
ADAPT_MODES = {"simpler": "Explain more simply", "more-rigorous": "Explain more rigorously", "derivation": "Show the derivation",
               "visual": "Explain visually", "analogy": "Give an intuitive analogy", "worked-example": "Show a worked example",
               "physical-interpretation": "Explain the physical interpretation", "implementation": "Explain how to implement it",
               "prerequisites": "Review the prerequisites"}
QUESTION_KINDS = {"mcq", "multi", "numeric", "matching", "ordering", "free-response"}


def _validate_reviews(reviews):
    """Tutor verdicts on actual responses: shown beside the question, never ledger credit."""
    if not isinstance(reviews, list) or len(reviews) > 200:
        raise ValueError("Invalid question reviews")
    for review in reviews:
        if not isinstance(review, dict) or set(review) - {"response_event_id", "verdict", "feedback", "reviewed_at", "criteria_met", "reviewed_by", "rationale", "covers"}:
            raise ValueError("Invalid question review")
        # Optional structured review: which declared criteria the answer met, and who judged it.
        if "criteria_met" in review and not (isinstance(review["criteria_met"], list) and 0 < len(review["criteria_met"]) <= 20
                                             and all(type(x) is bool for x in review["criteria_met"])):
            raise ValueError("criteria_met is a list of true/false, one per declared criterion")
        if "criteria_met" in review and review.get("verdict") == "correct" and not all(review["criteria_met"]):
            raise ValueError("A correct verdict requires every declared criterion to be met")
        if "covers" in review and not (isinstance(review["covers"], list) and len(review["covers"]) <= 200 and all(
                isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", x) for x in review["covers"])):
            raise ValueError("covers lists the earlier submissions this review supersedes")
        for key, limit in (("reviewed_by", 200), ("rationale", 2000)):
            if key in review and not (isinstance(review[key], str) and 0 < len(review[key].strip()) <= limit):
                raise ValueError(f"Review {key} must be bounded text")
        if review.get("verdict") not in REVIEW_VERDICTS:
            raise ValueError("Unsupported review verdict")
        if not isinstance(review.get("feedback", ""), str) or len(review.get("feedback", "")) > 32000:
            raise ValueError("Review feedback must be bounded text")
        if review.get("response_event_id") is not None and not (isinstance(review["response_event_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", review["response_event_id"])):
            raise ValueError("Invalid reviewed response identity")
        try:
            dt.datetime.fromisoformat(str(review.get("reviewed_at")).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid review timestamp") from None


PLAN_LECTURE_WIDGET = "plan-lecture"   # the id under which the staged lecture reports its position to the host (``board-position``); no declared widget may use it
# What a tutor's verdict on a written answer means for choosing the lecture (a pacing decision, never a grade): a partly correct answer leaves a gap, so it
# plays a repair segment and does not satisfy an extension; ``reviewed`` carries no judgement and changes nothing.
PLAN_REVIEW_RESULT = {"correct": "correct", "partially-correct": "wrong", "incorrect": "wrong"}


def _validate_plan_reviews(reviews, plan, events):
    """The tutor's verdicts on written answers in a staged session. Each names the plan question and the learner's answer event it is about; it is pending
    tutor feedback exactly like a question review, never evidence, and it never replaces the learner's answer (which stays an event)."""
    if not isinstance(reviews, list) or len(reviews) > 200:
        raise ValueError("Invalid plan reviews")
    questions = {q["id"]: q for tree in ("probe", "check") for q in ((plan or {}).get(tree) or {}).get("questions", [])}
    answers = {e["event_id"]: e for e in events if isinstance(e, dict) and e.get("type") == "plan-answer"}
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("question_id"), str) or review["question_id"] not in questions:
            raise ValueError("A plan review names a question of the session plan")
        answer = answers.get(review.get("response_event_id"))
        if answer is None or answer.get("question_id") != review["question_id"]:
            raise ValueError("A plan review names the learner's answer to that question")
        _validate_reviews([{k: v for k, v in review.items() if k != "question_id"}])
        criteria = questions[review["question_id"]].get("criteria") or []
        if "criteria_met" in review and len(review["criteria_met"]) != len(criteria):
            raise ValueError("criteria_met has one true/false for each of the question's %d criteria" % len(criteria))


def active_plan_reviews(events, reviews):
    """Only a review of the latest actual attempt may pace current instruction.

    Retain superseded reviews in storage. Contradictory criterion records cannot
    establish a correct pacing result even in unvalidated projections.
    """
    latest = {e['question_id']: e['event_id'] for e in events if e.get('type') == 'plan-answer'}
    selected = {}
    for review in reviews:
        if latest.get(review['question_id']) == review['response_event_id']:
            selected[review['question_id']] = review
    return [r for r in selected.values() if not (
        r['verdict'] == 'correct' and 'criteria_met' in r and not all(r['criteria_met']))]


def reviewed_results(results, reviews, events=None):
    """The results the lecture is chosen from: the page's probe results (question id -> correct/wrong/pending) with each written answer's pending result
    replaced by the tutor's latest verdict on it (see ``PLAN_REVIEW_RESULT``). Choice and numeric results are never touched. Mirrors Stages.reviewedResults."""
    latest = {r["question_id"]: r for r in (active_plan_reviews(events, reviews) if events is not None else reviews)}
    return {q: (PLAN_REVIEW_RESULT.get(latest[q]["verdict"], v) if v == "pending" and q in latest else v) for q, v in results.items()}


def _checkpoints(events, prefix):
    return [e["response"][len(prefix):] for e in events if e.get("type") == "checkpoint" and isinstance(e.get("response"), str) and e["response"].startswith(prefix)]


def recorded_lecture_path(events):
    """The segments the lecture was started with (the page freezes the path in a ``lecture-path:`` checkpoint at its first step), or ``None`` before it starts."""
    paths = _checkpoints(events, "lecture-path:")
    return [s for s in paths[-1].split(",") if s] if paths else None


def plan_lecture(state):
    """What the staged lecture plays now: ``{results, path, started}``. Once the lecture has started the path is the one it started with; before that it
    follows the probe results with the tutor's reviews applied, so a verdict on a written answer can still change a lecture that has not begun."""
    import session_plan
    plan, events = state["plan"], state["events"]
    results = reviewed_results(session_plan.replay(plan, "probe", events)["results"], state.get("plan_reviews", []), events)
    recorded = recorded_lecture_path(events)
    known = {s["id"] for s in plan["segments"]}
    return {"results": results, "started": recorded is not None,
            "path": [s for s in recorded if s in known] if recorded is not None else session_plan.lecture_path(plan, results)}


def session_adaptation(state):
    """Attempt-bound teaching advice; never a canonical mastery projection.

    Uses existing replay/repair rules. Advice does not switch stages, rewrite
    questions, reroute a started lecture or expand the assessment budget.
    """
    import session_plan
    base = {'adaptation_schema': 1, 'evidence': False}
    plan, events = state.get('plan'), state['events']
    if not plan:
        return dict(base, action='prepare_lesson', stage='handout', reason='A prepared lesson is not available yet.')
    active = active_plan_reviews(events, state.get('plan_reviews', []))
    by_question = {r['question_id']: r for r in active}
    lecture = plan_lecture(state)
    pending, gaps = [], []
    for tree in ('probe', 'check'):
        replayed = session_plan.replay(plan, tree, events)
        for answer in replayed['trail']:
            review = by_question.get(answer['id'])
            if answer['verdict'] == 'pending' and (review is None or review['verdict'] == 'reviewed'):
                pending.append(answer['id'])
            if review and review['verdict'] in {'incorrect', 'partially-correct'}:
                gaps.append((tree, answer['id'], review))
    if gaps:
        tree, question, review = gaps[-1]
        repairs = [s['id'] for s in plan['segments'] if s['role'] == 'repair'
                   and question in s['plays_if']['wrong']]
        available = [r for r in repairs if r in lecture['path']]
        return dict(base, action='review_repair' if available else 'request_repair', stage='lecture' if available else 'handout',
                    reason='The latest reviewed attempt has an unresolved gap. ' + (
                        'The prepared lecture includes its repair.' if available else
                        'Ask the tutor for a focused repair; the current lecture path stays intact.'),
                    question_id=question, response_event_id=review['response_event_id'], tree=tree,
                    verdict=review['verdict'], repair_segments=available, lecture_started=lecture['started'],
                    pending_review=len(pending))
    if pending:
        return dict(base, action='await_review', stage='handout', pending_review=len(pending),
                    reason='Written reasoning awaits a substantive review. You can keep studying; no learning credit is inferred.')
    stage = session_plan.stage_of(plan, events)
    return dict(base, action='continue', stage=stage,
                reason='Continue the prepared lesson. Local results and reading pace study; they do not establish mastery.',
                pending_review=0)


def answered_plan_changes(old, new, events):
    """Protect what answered questions actually asked/judged, even on rerouting.

    Explicit pacing reroutes may change only next/on_correct/on_wrong and an
    option's next. Prompt, criteria, keys, assumptions and solutions retain their
    meaning; use a new question ID for a changed assessment.
    """
    def questions(plan):
        if not isinstance(plan, dict):
            return {}
        return {(tree, q['id']): q for tree in ('probe', 'check')
                for q in (plan.get(tree) or {}).get('questions', [])}
    def semantics(question):
        if question is None:
            return None
        value = {k: v for k, v in question.items() if k not in {'next', 'on_correct', 'on_wrong'}}
        if isinstance(value.get('options'), list):
            value['options'] = [{k: v for k, v in option.items() if k != 'next'} for option in value['options']]
        return value
    before, after = questions(old), questions(new)
    answered = {(e.get('response', {}).get('tree'), e.get('question_id')) for e in events
                if e.get('type') == 'plan-answer' and isinstance(e.get('response'), dict)}
    import pedagogy_contract
    return pedagogy_contract.revision_problems(old, new, events) + [f'{tree}/{qid}: answered question semantics changed; preserve it and add a new question ID'
            for tree, qid in sorted(answered) if semantics(before.get((tree, qid))) != semantics(after.get((tree, qid)))]


def plan_revision_problems(old, new, events):
    """Why replacing the plan ``old`` by ``new`` would move a learner who has already answered: the questions answered must be judged the same and lead where
    they led (which also keeps a finished tree finished, so the stage never moves backwards), and the segments the lecture was started with must still exist.
    Empty when it is safe."""
    import session_plan
    problems = []
    for tree in ("probe", "check"):
        before, after = session_plan.replay(old, tree, events), session_plan.replay(new, tree, events)
        route = lambda r: [(t["id"], t["verdict"], t["next"]) for t in r["trail"]]
        if route(before) != route(after):
            problems.append(f"{tree}: the revised plan would send the answers already given somewhere else (a changed kind, option or route on an answered question)")
    gone = [s for s in recorded_lecture_path(events) or [] if s not in {seg["id"] for seg in new["segments"]}]
    if gone:
        problems.append("the lecture has started with segments the revised plan drops: " + ", ".join(gone))
    return problems


def review_plan_answer(root, relative_md, question_id, verdict, feedback="", reviewed_by=None, rationale=None, criteria_met=None,
                       revised_plan=None, allow_reroute=False, response_event_id=None):
    """Record the tutor's verdict on the learner's latest written answer to a plan question, and optionally replace the plan in the same save.

    A written answer never blocked the learner; this is how the agent's reading of it comes back. It is pending tutor feedback, exactly like ``review_response``
    for an ordinary question: the learner's answer stays as it was, nothing awards mastery or evidence, and the list is append-only (a later review of the same
    answer supersedes the earlier one on the page). Only a ``pending`` answer is reviewed here; a choice or number was judged on the page against the plan's key.
    The result says what the lecture would now play and whether it has started. A revised plan is refused (and the review with it) when it would move the
    learner (``plan_revision_problems``) unless ``allow_reroute``."""
    import session_plan
    if verdict not in REVIEW_VERDICTS:
        raise ValueError("Verdict must be one of: " + ", ".join(REVIEW_VERDICTS))
    if not isinstance(feedback, str) or len(feedback) > 32000:
        raise ValueError("Feedback must be bounded text")
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        plan = state.get("plan")
        if not plan:
            raise ValueError("This session has no plan; ordinary questions are reviewed with `review`")
        question = next((q for tree in ("probe", "check") for q in (plan.get(tree) or {}).get("questions", []) if q["id"] == question_id), None)
        if question is None:
            raise ValueError(f"Unknown plan question {question_id!r}")
        answered = [e for e in state["events"] if e.get("type") == "plan-answer" and e.get("question_id") == question_id]
        answer = next((e for e in reversed(answered) if response_event_id in (None, e["event_id"])), None)
        if answer is None:
            raise ValueError("No learner answer to review; never invent an answer" if response_event_id is None else "Unknown answer to review")
        if answer["response"].get("verdict") != "pending":
            raise ValueError("That answer was judged on the page against the plan's key; only a written answer awaits the tutor")
        review = {"question_id": question_id, "response_event_id": answer["event_id"], "verdict": verdict, "feedback": feedback.strip(), "reviewed_at": _now()}
        declared = question.get("criteria") or []
        if criteria_met is not None:
            if len(criteria_met) != len(declared):
                raise ValueError("This question declares %d criteria; state for each whether it was met (criteria_met)" % len(declared))
            review["criteria_met"] = criteria_met
        if reviewed_by:
            review["reviewed_by"] = reviewed_by
        if rationale:
            review["rationale"] = rationale
        before = plan_lecture(state)
        if revised_plan is not None:
            _ensure_context(state)
            session_plan.check(revised_plan)
            changed_answers = answered_plan_changes(plan, revised_plan, state['events'])
            if changed_answers:
                raise ValueError('The revised plan would move the learner; nothing was saved: ' + '; '.join(changed_answers))
            problems = plan_revision_problems(plan, revised_plan, state["events"])
            if problems and not allow_reroute:
                raise ValueError("The revised plan would move the learner; nothing was saved: " + "; ".join(problems))
            state["plan"] = revised_plan
        reviews = state.setdefault("plan_reviews", [])
        same = lambda r: {k: v for k, v in r.items() if k != "reviewed_at"}
        if not reviews or same(reviews[-1]) != same(review):
            reviews.append(review)
        _validate_plan_reviews(reviews, state["plan"], state["events"])
        import learning_advice
        learning_advice.refresh_in_state(root, relative_md, state, require_usable=revised_plan is not None)
        state["updated_at"] = _now()
        saved = _save(root, relative_md, state)
    after = plan_lecture(saved)
    return {"session": str(relative_md), "question_id": question_id, "verdict": verdict, "stage": session_plan.stage_of(saved["plan"], saved["events"]),
            "lecture_started": after["started"], "lecture_path_before": before["path"], "lecture_path": after["path"], "plan_revised": revised_plan is not None,
            "pending": pending_activity(saved), "adaptation": session_adaptation(saved)}


def _validate_context(context):
    """Optional binding to a context receipt; absent in historical sessions, never required to read one."""
    if not isinstance(context, dict):
        raise ValueError("Invalid session context")
    if "preferences" in context:
        import learning_preferences
        learning_preferences.validate(context["preferences"])
    if context.get("waived") is True:
        if set(context) - {"waived", "reason", "bound_at", "preferences"} or not isinstance(context.get("reason"), str) or not context["reason"].strip():
            raise ValueError("A context waiver needs a reason")
        return
    if "advice" in context:
        import learning_advice
        learning_advice.validate(context["advice"])
    if set(context) - {"binding", "request", "bound_at", "refreshed_at", "advice", "preferences"} or not isinstance(context.get("binding"), dict) \
            or not isinstance(context.get("request"), dict):
        raise ValueError("Invalid session context binding")
    binding = context["binding"]
    if not isinstance(binding.get("receipt_id"), str) or binding.get("outcome") not in {"ready", "degraded"} \
            or not isinstance(binding.get("sources"), list) or not isinstance(binding.get("workflow"), str):
        raise ValueError("Invalid session context binding")


NAVIGATION_KINDS = ("prerequisite", "earlier", "first-taught", "related", "application", "evidence", "paper")


def _validate_navigation(items):
    """Where a learner can go from here. Targets are note references the host resolves and may refuse; never URLs."""
    if not isinstance(items, list) or len(items) > 64:
        raise ValueError("Invalid session navigation")
    for item in items:
        if (not isinstance(item, dict) or set(item) - {"kind", "label", "target", "note"} or item.get("kind") not in NAVIGATION_KINDS
                or not isinstance(item.get("label"), str) or not 0 < len(item["label"].strip()) <= 200
                or not rich_text.valid_note_target(item.get("target"))
                or ("note" in item and not (isinstance(item["note"], str) and len(item["note"]) <= 300))):
            raise ValueError("Invalid session navigation entry")


BOARD_AUDIO_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._/-]{0,200}\.(?:wav|ogg|mp3)\Z")


def _validate_board_audio(audio, step_id):
    """A board widget's recordings: one per step, each a vault-relative file with its length, the silence to wait after it and the hash of the sentence it
    was made for. Nothing here is a URL; the page gets addresses only from the builder, and only for entries whose sentence has not changed since."""
    if not isinstance(audio, dict) or len(audio) > 200:
        raise ValueError("Invalid board audio")
    for key, entry in audio.items():
        if (not isinstance(key, str) or not step_id.fullmatch(key) or not isinstance(entry, dict) or set(entry) != {"file", "seconds", "pause", "say_sha256"}
                or not isinstance(entry["file"], str) or not BOARD_AUDIO_PATH.match(entry["file"]) or any(p in {"", ".", ".."} for p in entry["file"].split("/"))
                or not _plain_number(entry["seconds"], 0.1, 600) or not _plain_number(entry["pause"], 0, 5)
                or not isinstance(entry["say_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["say_sha256"])):
            raise ValueError("Invalid board audio entry")


def _plain_number(value, low, high):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and low <= value <= high


def validate_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported HTML session schema")
    for key in ("session_id", "type", "title", "source_markdown"):
        if not isinstance(state.get(key), str):
            raise ValueError(f"Invalid {key}")
    if not state["session_id"] or len(state["session_id"]) > 256:
        raise ValueError("Invalid session identity")
    if not isinstance(state.get("metadata"), dict):
        raise ValueError("Invalid metadata")
    for key in ("questions", "events", "open_questions"):
        if not isinstance(state.get(key), list):
            raise ValueError(f"Invalid {key}")
    for widget in state.get("widgets", []):
        if not isinstance(widget, dict) or widget.get("kind") not in {"sampling", "vector", "board"} or not isinstance(widget.get("id"), str):
            raise ValueError("Unsupported session widget")
        if widget["id"] == PLAN_LECTURE_WIDGET:
            raise ValueError(f"The widget id {PLAN_LECTURE_WIDGET!r} is reserved for the lecture of a staged session")
        if widget["kind"] == "board":
            import board_script  # a lecture is untrusted data written by an agent; the page re-checks it with the same rules
            board_script.check(widget.get("script"))
            if "audio" in widget:
                _validate_board_audio(widget["audio"], board_script.ID)
    plan_ids = frozenset()
    if "plan" in state:
        import session_plan  # the plan an agent wrote before the session; the page runs it, so it is checked with the same rules
        session_plan.check(state["plan"])
        import pedagogy_source_comparison
        for entry in (state['plan'].get('pedagogy') or {}).get('comparisons', []):
            problems = pedagogy_source_comparison.validate(entry,state['plan'],state)
            if problems:
                raise ValueError('; '.join(problems))
        plan_ids = frozenset(q["id"] for tree in ("probe", "check") for q in (state["plan"].get(tree) or {}).get("questions", []))
    if "video_records" in state:
        _validate_video_records(state["video_records"])
    if "context" in state:
        _validate_context(state["context"])
    if state.get("placement") not in (None, "explicit"):
        raise ValueError("Unsupported placement mode")
    if "navigation" in state:
        _validate_navigation(state["navigation"])
    # Tutoring declarations are checked in depth by tutor_gate (validate / check); here only their shape and size are bounded.
    if "teaching" in state and not (isinstance(state["teaching"], list) and len(state["teaching"]) <= 64 and all(isinstance(b, dict) for b in state["teaching"])):
        raise ValueError("Invalid teaching declarations")
    if "tutoring" in state and not isinstance(state["tutoring"], dict):
        raise ValueError("Invalid tutoring declaration")
    if "supervision" in state:
        import supervision  # imports this module, so it is loaded on demand
        supervision.validate_record(state["supervision"])
    if "explanation_requests" in state:
        requests = state["explanation_requests"]
        if (not isinstance(requests, list) or len(requests) > 200 or any(
                not isinstance(r, dict) or not (isinstance(r.get("mode"), str) and r["mode"] in ADAPT_MODES) or r.get("status") not in ("open", "answered")
                or not isinstance(r.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", r["id"]) for r in requests)):
            raise ValueError("Invalid explanation requests")
    if not isinstance(state.get("resources", []), list):
        raise ValueError("Invalid session resources")
    for resource in state.get("resources", []):
        if not isinstance(resource, dict) or resource.get("kind") not in {"module", "image"} or not isinstance(resource.get("path"), str):
            raise ValueError("Invalid local session resource")
        value = resource["path"]
        if re.search(r"[:\\\\%?#]", value) or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Unsafe local session resource path")
        suffix = Path(value).suffix.lower()
        if resource["kind"] == "image" and suffix not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            raise ValueError("Unsupported session image")
        if resource.get("visual_id") is not None and not (isinstance(resource["visual_id"], str) and re.fullmatch(r"VIS-[A-Za-z0-9][A-Za-z0-9._-]*", resource["visual_id"])):
            raise ValueError("Invalid visual identity")
        if resource.get("visual_class") is not None and resource["visual_class"] not in VISUAL_CLASSES:
            raise ValueError("Unsupported visual class")
        if resource.get("verification_outcome") is not None and not (isinstance(resource["verification_outcome"], str) and re.fullmatch(r"[a-z-]{1,40}", resource["verification_outcome"])):
            raise ValueError("Invalid verification outcome")
        if resource["kind"] == "module" and suffix != ".js":
            raise ValueError("Unsupported session module")
    if len(state["events"]) > MAX_EVENTS or len(_json(state)) > MAX_STATE_BYTES:
        raise ValueError("Session state exceeds limits")
    ids = set()
    for q in state["questions"]:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q["id"] or len(q["id"]) > 128 or q["id"] in ids:
            raise ValueError("Invalid or duplicate question identity")
        ids.add(q["id"])
        _validate_reviews(q.get("reviews", []))
    event_ids = set()
    import pedagogy_contract
    previous_events = []
    for event in state["events"]:
        validate_interaction(event, ids, plan_ids)
        pedagogy_contract.validate_event(event, dict(state, events=previous_events), historical=True)
        previous_events.append(event)
        if not isinstance(event, dict) or event.get("type") not in {"response", "hint", "solution", "confidence", "checkpoint", "reset", "open-question", "explanation-request", "plan-answer", "pedagogy-help"}:
            raise ValueError("Unsupported interaction event")
        if not isinstance(event.get("event_id"), str) or event["event_id"] in event_ids:
            raise ValueError("Invalid or duplicate event identity")
        event_ids.add(event["event_id"])
        if event.get("type") not in {"open-question", "checkpoint", "explanation-request", "plan-answer", "pedagogy-help"} and event.get("question_id") not in ids:
            raise ValueError("Unknown interaction question")
        if event.get("status") not in (None, "pending-review"):
            raise ValueError("Browser evidence must remain pending review")
        if any(k in event for k in ("mastery", "retained", "credit", "reviewed_by")):
            raise ValueError("Browser event cannot award learning evidence")
        if len(json.dumps(event, ensure_ascii=False)) > 20000:
            raise ValueError("Interaction event exceeds limit")
    if "plan_reviews" in state:
        _validate_plan_reviews(state["plan_reviews"], state.get("plan"), state["events"])
    return state


_INTERNAL_TOKEN = r'(?:block|content|chunk|segment|item|unit|node|slice|stage|step|part|section|module|lesson|topic|question|q)'
_INTERNAL_PAIR = re.compile(r'\b' + _INTERNAL_TOKEN + r'\s*[-_#:.]?\s*\d+\b', re.I)
_ID_LIKE = re.compile(r'[A-Z]{1,6}-\d+(?:\.\d+)*|[0-9a-fA-F]{12,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def prose_lines(lines):
    """(index, is_heading, text) of lesson prose: not frontmatter and not inside a code fence."""
    start = 0
    if lines and lines[0].strip() == '---':
        closing = next((n for n in range(1, len(lines)) if lines[n].strip() == '---'), None)
        start = 0 if closing is None else closing + 1
    fenced = False
    for number in range(start, len(lines)):
        line = lines[number]
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if not fenced:
            heading = re.match(r'#{1,6}\s+(.*?)\s*#*\s*$', line)
            yield number, bool(heading), heading[1] if heading else line


_PLACEHOLDER = re.compile(r'<[^<>]*>|\[[^\[\]]*\]|\{\{[^{}]*\}\}')


def heading_is_placeholder(text):
    """An unfilled template slot such as "[Name the concept this part teaches]"."""
    return bool(_PLACEHOLDER.fullmatch(text.strip()))


def heading_is_internal(text):
    """A heading that names a workflow position or an identifier ("Block 9 - Content 3", "RQ-004", "Q3"), not what is studied."""
    text = text.strip()
    if _ID_LIKE.fullmatch(text) or text.lower() in {'untitled', 'tbd', 'todo'}:
        return True
    rest = _INTERNAL_PAIR.sub(' ', text)
    return rest != text and not re.findall(r'[^\W\d_]{3,}', rest)


def heading_issues(source):
    """Section titles that expose internal naming. Stable internal IDs stay in state; learners read meaningful titles."""
    lines = source.replace('\r\n', '\n').split('\n')
    issues = []
    for number, is_heading, text in prose_lines(lines):
        if not is_heading:
            continue
        if heading_is_placeholder(text):
            issues.append({'line': number + 1, 'heading': text, 'message': f"heading '{text}' is an unfilled template placeholder; "
                                                                           "replace it with what the learner is about to understand"})
        elif heading_is_internal(text):
            issues.append({'line': number + 1, 'heading': text, 'message': f"heading '{text}' names a workflow position or identifier, not what is being studied; "
                                                                           "retitle it to say what the learner is about to understand"})
    return issues


def derive_title(source, fallback):
    """A session without an explicit title is named by its first heading, not by its file name."""
    lines = parse_frontmatter(source.replace('\r\n', '\n'))[1].split('\n')
    headings = [(len(re.match(r'#+', lines[n])[0]), text) for n, is_heading, text in prose_lines(lines)
                if is_heading and text.strip() and not heading_is_internal(text) and not heading_is_placeholder(text)]
    for _, text in sorted(headings, key=lambda h: h[0])[:1]:  # the shallowest heading, first in the document on ties
        return rich_text.plain_text(rich_text.parse_inline(text)).strip()[:200] or fallback
    return fallback


def _inline(text, labels=None):
    """Inline rendering is the shared scientific grammar in rich_text.py (mirrored by the runtime's richtext.js)."""
    return rich_text.render_inline(text, labels)


_LIST_MARKER = re.compile(r'^( *)([-+*]|\d+[.)])\s+(.+)$')
_HEADING = re.compile(r'^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$')
_CALLOUT = re.compile(r'^\[!([a-zA-Z][\w-]*)\]([+-]?)\s*(.*)$')
# A question sits where its marker is, so probes and teaching read in the order they happened.
QUESTION_MARKER = re.compile(r'^<!--\s*ros-question:\s*([A-Za-z0-9_.:-]{1,128})\s*-->\s*$')
_IMAGE = re.compile(r'^!\[([^\]]*)\]\(resource:([a-zA-Z0-9_-]+)(?:\s+"([^"]*)")?\)\s*$')
# A widget sits where its marker is, exactly like a question: the explanation it belongs to, not the end of the page.
WIDGET_MARKER = re.compile(r'^<!--\s*ros-widget:\s*([A-Za-z0-9_.:-]{1,128})\s*-->\s*$')
VISUAL_CLASSES = {'schematic': 'Schematic, not to scale', 'analytic': 'Model-driven: computed from stated equations',
                  'empirical': 'Data-derived', 'source': 'Figure from a cited source'}


def _table_cells(line):
    """Split unescaped pipes outside inline code; retain escaped literal pipes."""
    cells, cell, code = [], [], False
    line = line.strip()
    if line.startswith('|'): line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'): line = line[:-1]
    i = 0
    while i < len(line):
        char = line[i]
        if char == '\\' and i + 1 < len(line) and line[i + 1] == '|':
            cell.append('|'); i += 2; continue
        if char == '$' and not code and i + 1 < len(line) and not line[i + 1].isspace():
            end = rich_text.closing_dollar(line, i + 1)  # |x| inside $...$ is mathematics, not a column break
            if end != -1:
                cell.append(line[i:end + 1]); i = end + 1; continue
        if char == '`': code = not code
        if char == '|' and not code:
            cells.append(''.join(cell).strip()); cell = []
        else: cell.append(char)
        i += 1
    return cells + [''.join(cell).strip()]


def markdown_html(source, page_title=None, questions=None, placed=None, widgets=None, figures=None, placement=None):
    """Component-oriented structural conversion; never infer assessments or answers.

    ``widgets`` / ``figures`` map declared IDs to their declarations so markers resolve in place;
    ``placement`` (a dict) collects which markers were seen, for diagnostics.

    Authored source is unchanged. Inline text follows the shared scientific grammar (rich_text.py):
    nested emphasis, TeX in four delimiter styles, labelled and numbered equations with references,
    sub/superscripts. Raw executable HTML is escaped. Two passes: the first discovers labelled
    equations in document order so a reference may precede the equation it cites.
    """
    found = []
    _markdown_html(source, page_title, questions, set(), {}, found, widgets, figures, None)
    labels = {name: number for number, name in enumerate(found, 1)}
    return _markdown_html(source, page_title, questions, placed, labels, None, widgets, figures, placement)


def _markdown_html(source, page_title, questions, placed, labels, found, widgets=None, figures=None, placement=None):
    _, body = parse_frontmatter(source.replace('\r\n', '\n'))
    if placement is not None:
        placement.setdefault('figures', []), placement.setdefault('widgets', []), placement.setdefault('questions', [])
    used_anchors = {}
    source_h1_seen = False
    emitted, widgets_seen = set(), set()
    inline = lambda text: _inline(text, labels)

    def anchor_for(title):
        base = 'section-' + _hash(title.encode())[:12]
        used_anchors[base] = used_anchors.get(base, 0) + 1
        return base if used_anchors[base] == 1 else base + '-' + str(used_anchors[base])

    def render(lines, depth=0):
        nonlocal source_h1_seen
        if depth > 32:
            return '<pre data-ros="legacy">' + html.escape('\n'.join(lines)) + '</pre>'
        out, i = [], 0
        def block_start(line):
            return (not line.strip() or _HEADING.match(line) or _LIST_MARKER.match(line) or QUESTION_MARKER.match(line.strip())
                    or WIDGET_MARKER.match(line.strip())
                    or line.startswith('>') or re.match(r'^\s*(?:```|~~~)', line) or rich_text.starts_display_math(line)
                    or re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*', line))
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            marker = QUESTION_MARKER.match(line.strip())
            if marker:
                if placement is not None: placement['questions'].append(marker[1])
                question = (questions or {}).get(marker[1])
                if question is not None and (placed is None or marker[1] not in placed):
                    out.append(_question_html(question))
                    if placed is not None: placed.add(marker[1])
                i += 1; continue
            widget_marker = WIDGET_MARKER.match(line.strip())
            if widget_marker:
                if placement is not None: placement['widgets'].append(widget_marker[1])
                widget = (widgets or {}).get(widget_marker[1])
                if widget is not None and widget_marker[1] not in widgets_seen:
                    widgets_seen.add(widget_marker[1])
                    out.append(_widget_html(widget))
                i += 1; continue
            image = _IMAGE.fullmatch(line.strip())
            if image:
                if placement is not None: placement['figures'].append(image[2])
                out.append(_figure_html(image, (figures or {}).get(image[2]), inline))
                i += 1; continue
            if i + 1 < len(lines) and '|' in line:
                headings, rules = _table_cells(line), _table_cells(lines[i + 1])
                if len(headings) == len(rules) and all(re.fullmatch(r':?-{3,}:?', r) for r in rules):
                    classes = ['ros-align-center' if r.startswith(':') and r.endswith(':') else 'ros-numeric' if r.endswith(':') else 'ros-align-left' for r in rules]
                    table = '<div class="ros-table-wrap" tabindex="0" role="region" aria-label="Scrollable table"><table><thead><tr>'
                    table += ''.join('<th scope="col" class="' + c + '">' + inline(h) + '</th>' for h, c in zip(headings, classes)) + '</tr></thead><tbody>'
                    i += 2
                    while i < len(lines) and '|' in lines[i] and lines[i].strip():
                        cells = _table_cells(lines[i])
                        if len(cells) != len(headings): break
                        table += '<tr>' + ''.join('<td class="' + c + '">' + inline(v) + '</td>' for v, c in zip(cells, classes)) + '</tr>'
                        i += 1
                    out.append(table + '</tbody></table></div>'); continue
            fence = re.match(r'^\s*(`{3,}|~{3,})([^\s`]*)\s*$', line)
            if fence:
                code, i = [], i + 1
                while i < len(lines) and not re.fullmatch(r'\s*' + re.escape(fence[1][0]) + '{' + str(len(fence[1])) + r',}\s*', lines[i]):
                    code.append(lines[i]); i += 1
                closed = i < len(lines)
                if closed: i += 1
                language = fence[2] if re.fullmatch(r'[\w+-]{1,32}', fence[2]) else ''
                attr = ' data-language="' + language + '"' if language else ''
                out.append('<pre class="ros-code" data-ros="' + ('code' if closed else 'legacy') + '"' + attr + '><code>' + html.escape('\n'.join(code)) + '</code></pre>')
                continue
            if rich_text.starts_display_math(line):
                block = rich_text.read_display_math(lines, i)
                if block:
                    label = block['label'] if block['label'] and block['label'] not in emitted else None
                    if label:
                        emitted.add(label)
                        if found is not None:
                            found.append(label)
                    out.append(rich_text.display_math_html(dict(block, label=label), labels.get(label)))
                    i = block['next']
                    continue
                # Not a well-formed display block (for example "$$ x $$ and more"): read it as an ordinary paragraph.
            heading = _HEADING.match(line)
            if heading:
                level, title = len(heading[1]), heading[2]
                anchor = anchor_for(title)
                if level == 1:
                    prior_h1 = source_h1_seen
                    duplicate = page_title is not None and not source_h1_seen and title.strip() == page_title.strip()
                    source_h1_seen = True
                    if duplicate:
                        # Keep historical fragment targets without a duplicate H1/TOC entry.
                        out.append('<span class="ros-heading-anchor" aria-hidden="true" id="' + anchor + '"></span>')
                        i += 1
                        continue
                    if page_title is not None or prior_h1: level = 2
                kind = {'concept':'concept','definition':'definition','derivation':'derivation','intuition':'intuition','evidence':'evidence','decision':'decision','research decision':'decision','questions':'question','questions asked':'question','open questions':'question','code':'code','reflection':'reflection','checkpoint':'checkpoint'}.get(title.lower().rstrip(':'))
                attr = ' data-ros="' + kind + '"' if kind else ''
                out.append(f'<h{level} class="ros-section-heading" id="{anchor}"{attr}>' + inline(title) + f'</h{level}>')
                i += 1
                continue
            if line.startswith('>'):
                quoted = []
                while i < len(lines) and lines[i].startswith('>'):
                    quoted.append(re.sub(r'^> ?', '', lines[i])); i += 1
                callout = _CALLOUT.match(quoted[0])
                if callout:
                    kind, fold, title = callout[1].lower(), callout[2], callout[3]
                    title = title or kind.replace('-', ' ').capitalize()
                    component = 'details' if fold else 'aside'
                    label = 'summary' if fold else 'div'
                    opened = ' open' if fold == '+' else ''
                    out.append('<' + component + ' class="ros-callout ros-callout-' + kind + '" data-ros="' + kind + '"' + opened + '><' + label + ' class="ros-callout-header">' + inline(title) + '</' + label + '><div class="ros-callout-body">' + render(quoted[1:], depth + 1) + '</div></' + component + '>')
                else:
                    out.append('<blockquote class="ros-quotation">' + render(quoted, depth + 1) + '</blockquote>')
                continue
            marker = _LIST_MARKER.match(line)
            if marker:
                indent, ordered = len(marker[1]), marker[2][0].isdigit()
                tag = 'ol' if ordered else 'ul'
                start = int(re.match(r'\d+', marker[2])[0]) if ordered else 1
                attrs = ' start="' + str(start) + '"' if ordered and start != 1 else ''
                items = []
                while i < len(lines):
                    current = _LIST_MARKER.match(lines[i])
                    if not current or len(current[1]) != indent or current[2][0].isdigit() != ordered: break
                    content_indent = current.start(3)
                    item = [current[3]]
                    number = int(re.match(r'\d+', current[2])[0]) if ordered else None
                    i += 1
                    while i < len(lines):
                        next_item = _LIST_MARKER.match(lines[i])
                        if next_item and len(next_item[1]) <= indent: break
                        if not lines[i].strip():
                            probe = i + 1
                            while probe < len(lines) and not lines[probe].strip(): probe += 1
                            if probe >= len(lines): i = probe; break
                            next_indent = len(lines[probe]) - len(lines[probe].lstrip(' '))
                            if next_indent <= indent: i = probe; break
                            item.append(''); i += 1; continue
                        leading = len(lines[i]) - len(lines[i].lstrip(' '))
                        if leading <= indent: break
                        item.append(lines[i][min(leading, content_indent):]); i += 1
                    task = re.match(r'^\[([ xX])\]\s+(.*)$', item[0])
                    checkbox = ''
                    if task:
                        item[0] = task[2]
                        checkbox = '<input type="checkbox" disabled aria-label="Recorded task status"' + (' checked' if task[1].lower() == 'x' else '') + '>'
                    value = ' value="' + str(number) + '"' if ordered else ''
                    items.append('<li' + value + '>' + checkbox + render(item, depth + 1) + '</li>')
                out.append('<' + tag + ' class="ros-list"' + attrs + '>' + ''.join(items) + '</' + tag + '>')
                continue
            if re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*', line):
                out.append('<hr>'); i += 1; continue
            paragraph = [line]; i += 1
            while i < len(lines) and not block_start(lines[i]) and not _IMAGE.fullmatch(lines[i].strip()):
                if i + 1 < len(lines) and '|' in lines[i]:
                    cells, rules = _table_cells(lines[i]), _table_cells(lines[i + 1])
                    if len(cells) == len(rules) and all(re.fullmatch(r':?-{3,}:?', r) for r in rules): break
                paragraph.append(lines[i]); i += 1
            # One parse for the whole paragraph, so emphasis, links and math can span soft line breaks.
            out.append('<p>' + inline('\n'.join(paragraph).rstrip()) + '</p>')
        return '\n'.join(out)

    return render(body.splitlines())


def _question_html(q):
    """Static fallback markup for one question; the runtime replaces it with the interactive panel."""
    kind = q.get("kind", "free-response")
    if kind not in QUESTION_KINDS:
        kind = "free-response"
    content = '<section data-ros="' + kind + '" data-question-id="' + html.escape(q["id"], quote=True) + '"><h3>' + _inline(str(q.get("prompt", ""))) + '</h3><form>'
    if kind in {"mcq", "multi"}:
        for i, option in enumerate(q.get("options", [])):
            value = option.get("value", str(i)) if isinstance(option, dict) else str(i)
            label = option.get("label", "") if isinstance(option, dict) else str(option)
            content += '<label><input name="answer" type="' + ("radio" if kind == "mcq" else "checkbox") + '" value="' + html.escape(str(value), quote=True) + '">' + _inline(str(label)) + '</label>'
    else:
        content += '<textarea name="answer" aria-label="Your response"></textarea>'
    content += '<button type="submit">Save response</button><button type="button" data-ros-action="reset">Reset</button><output data-ros-feedback></output></form>'
    for hint in q.get("hints", []):
        content += '<details data-ros="hint"><summary>Hint</summary>' + _inline(str(hint)) + '</details>'
    if "solution" in q:
        content += '<details data-ros="solution"><summary>Solution</summary>' + _inline(str(q["solution"])) + '</details>'
    return content + '</section>'


def _questions_html(state, placed=()):
    """Questions without a marker in the source (older sessions) follow the content."""
    return "\n".join(_question_html(q) for q in state["questions"] if q["id"] not in placed)


def _widget_html(w):
    return '<section data-ros="widget" data-widget="' + html.escape(w["kind"], quote=True) + '" id="' + html.escape(w["id"], quote=True) + '"><h3>' + html.escape(w.get("title", w["kind"].title() + " demonstration")) + '</h3></section>'


def _widgets_html(state, placed=()):
    """Legacy sessions only: widgets with no marker follow the content, as they always did."""
    return "".join(_widget_html(w) for w in state.get("widgets", []) if w["id"] not in placed)


def _figure_html(image, declared, inline):
    """A figure in place. A declared visual states what kind of evidence it is, so a schematic cannot pass for data."""
    attributes, label = '', ''
    if declared:
        if declared.get('visual_id'):
            attributes += ' data-visual-id="' + html.escape(declared['visual_id'], quote=True) + '"'
        if declared.get('visual_class') in VISUAL_CLASSES:
            attributes += ' data-visual-class="' + declared['visual_class'] + '"'
            text = VISUAL_CLASSES[declared['visual_class']]
            if declared['visual_class'] in ('analytic', 'empirical'):
                # A computed figure says whether its computation was independently checked; silence would imply it was.
                outcome = declared.get('verification_outcome')
                text += ' (verification: ' + outcome.replace('-', ' ') + ')' if outcome else ' (not independently verified)'
            label = '<span class="ros-visual-class" data-ros="visual-class">' + html.escape(text) + '</span>'
    caption = inline(image[3]) if image[3] else ''
    figcaption = '<figcaption>' + caption + (' ' if caption and label else '') + label + '</figcaption>' if caption or label else ''
    return ('<figure class="ros-figure" data-ros="figure"' + attributes + '><img data-resource-id="' + html.escape(image[2], quote=True)
            + '" alt="' + html.escape(image[1], quote=True) + '">' + figcaption + '</figure>')


def placements(state):
    """The figures, widgets and questions the lesson's Markdown actually places, in document order."""
    seen = {}
    markdown_html(state['source_markdown'], page_title=state['title'], questions={q['id']: q for q in state['questions']}, placed=set(),
                  widgets={w['id']: w for w in state.get('widgets', [])},
                  figures={resource_id(r): r for r in state.get('resources', []) if r.get('kind') == 'image'}, placement=seen)
    return seen


def placement_issues(state, seen=None):
    """Where each declared visual is (or is not) placed in the lesson. Pure and deterministic.

    Returns dicts with ``code``, ``id`` and an actionable ``message``. A session with ``placement: explicit``
    never has a visual appended silently; these are what it shows and what ``validate`` reports instead.
    """
    if seen is None:
        seen = placements(state)
    declared_figures = {resource_id(r) for r in state.get('resources', []) if r.get('kind') == 'image'}
    declared_widgets = {w['id'] for w in state.get('widgets', [])}
    issues = []
    for identifier in sorted(declared_figures - set(seen['figures'])):
        issues.append({'code': 'unplaced-figure', 'id': identifier,
                       'message': f"figure '{identifier}' is declared but has no placeholder in the lesson; add ![description](resource:{identifier} \"caption\") "
                                  f"where it belongs (html_sessions.py place --figure {identifier} --after-heading ...)"})
    for identifier in sorted(declared_widgets - set(seen['widgets'])):
        issues.append({'code': 'unplaced-widget', 'id': identifier,
                       'message': f"widget '{identifier}' is declared but has no marker in the lesson; add <!-- ros-widget: {identifier} --> "
                                  f"where it belongs (html_sessions.py place --widget {identifier} --after-heading ...)"})
    for identifier in sorted(set(seen['figures']) - declared_figures):
        issues.append({'code': 'undeclared-figure', 'id': identifier,
                       'message': f"the lesson places figure '{identifier}' but no image resource with that id is declared"})
    for identifier in sorted(set(seen['widgets']) - declared_widgets):
        issues.append({'code': 'undeclared-widget', 'id': identifier,
                       'message': f"the lesson places widget '{identifier}' but no widget with that id is declared"})
    for kind in ('figures', 'widgets'):
        for identifier in sorted({i for i in seen[kind] if seen[kind].count(i) > 1}):
            issues.append({'code': 'duplicate-placement', 'id': identifier, 'message': f"{kind[:-1]} '{identifier}' is placed more than once"})
    return issues


def _placement_notice(issues):
    """The visible, never-silent form of a placement problem."""
    return ''.join('<aside class="ros-diagnostic" data-ros="diagnostic" data-code="' + html.escape(i['code'], quote=True) + '" role="note">'
                   + html.escape(i['message']) + '</aside>' for i in issues)


def _frame_src(state):
    """A page that carries a vetted YouTube resource may frame the privacy-enhanced player, and nothing else. The Obsidian companion
    builds its own policy (frame-src 'none'), so embeds exist only on standalone pages."""
    for block in state.get("teaching", []):
        card = block.get("card") if isinstance(block, dict) else None
        if isinstance(card, dict) and any(isinstance(r, dict) and r.get("embed") == "youtube" for r in card.get("resources") or []):
            return "; frame-src https://www.youtube-nocookie.com"
    return ''


def _media_src(state, standalone):
    """A page whose cards or boards carry recorded narration may play audio from its own folder, or, when exported alone, from data it embeds. Nothing else."""
    if any(isinstance(b, dict) and isinstance(b.get("card"), dict) and b["card"].get("audio") for b in state.get("teaching", [])) or _board_audio(state):
        return "; media-src " + ("data:" if standalone else "'self'")
    return ''


def _board_audio(state):
    """The recordings of the board widgets that are still true: ``{widget id: {step id: entry}}``, leaving out any whose sentence has changed since it was
    recorded (the hash no longer matches) or whose step is gone, so a revised sentence is never read in the old recording."""
    found = {}
    for widget in state.get("widgets", []):
        if not isinstance(widget, dict) or widget.get("kind") != "board" or not isinstance(widget.get("audio"), dict):
            continue
        says = {s["id"]: s.get("say", "").strip() for s in widget["script"]["steps"]}
        current = {step: entry for step, entry in widget["audio"].items() if says.get(step) and _hash(says[step].encode("utf-8")) == entry["say_sha256"]}
        if current:
            found[widget["id"]] = current
    return found


def _audio_base(runtime_prefix):
    """Where the vault is, relative to this page: '' beside the runtime folder, '../' one folder down, and so on. None when the prefix does not say."""
    marker = "/.research-os/runtime"
    if runtime_prefix == ".research-os/runtime":
        return ""
    return runtime_prefix[:-len(marker)] + "/" if runtime_prefix.endswith(marker) else None


def _board_audio_urls(state, runtime_prefix, standalone, audio_data):
    """Where each board recording is played from, as for cards: a path relative to this page, or an embedded data URL in a standalone export. The page gets the
    length and the pause too; a step without an address plays with the page's other voices."""
    base, urls = _audio_base(runtime_prefix), {}
    for widget_id, steps in _board_audio(state).items():
        for step, entry in steps.items():
            url = (audio_data or {}).get(entry["file"]) if standalone else (None if base is None else base + urllib.parse.quote(entry["file"], safe="/"))
            if url:
                urls.setdefault(widget_id, {})[step] = {"url": url, "seconds": entry["seconds"], "pause": entry["pause"]}
    return urls


def _audio_urls(state, runtime_prefix, standalone, audio_data):
    """Where each carded recording is played from: a path relative to this page (vault pages) or an embedded data URL (standalone export).
    A page whose runtime prefix does not say where the vault is gets none, and falls back to the browser voice."""
    base = _audio_base(runtime_prefix)
    urls = {}
    for block in state.get("teaching", []):
        card = block.get("card") if isinstance(block, dict) else None
        audio = card.get("audio") if isinstance(card, dict) else None
        if not isinstance(audio, dict):
            continue
        for lang, path in audio.items():
            url = (audio_data or {}).get(path) if standalone else (None if base is None else base + urllib.parse.quote(path, safe="/"))
            if url:
                urls.setdefault(block["id"], {})[lang] = url
    return urls


def _teaching_source(state):
    """The lesson source as shown: implementation blocks carry their declared literacy items under their heading."""
    blocks = [b for b in state.get("teaching", []) if isinstance(b, dict) and b.get("kind") == "implementation" and isinstance(b.get("literacy"), dict)]
    cards = any(isinstance(b, dict) and isinstance(b.get("card"), dict) for b in state.get("teaching", []))
    if not blocks and not cards:
        return state["source_markdown"]
    import tutor_gate  # imports this module, so it is loaded on demand
    source = tutor_gate.expand_literacy(state["source_markdown"], blocks) if blocks else state["source_markdown"]
    return tutor_gate.expand_cards(source, state["teaching"]) if cards else source


def render_html(state, runtime_prefix=".research-os/runtime", standalone=False, resource_markup="", resource_scripts="", resource_images=None, audio_data=None):
    validate_state(state)
    placed, seen = set(), {}
    content = markdown_html(_teaching_source(state), page_title=state["title"], questions={q["id"]: q for q in state["questions"]}, placed=placed,
                            widgets={w["id"]: w for w in state.get("widgets", [])},
                            figures={resource_id(r): r for r in state.get("resources", []) if r.get("kind") == "image"}, placement=seen)
    # New sessions never append a visual silently: a visual with no place becomes a visible diagnostic. Historical
    # sessions (no placement mode) keep their old behaviour so their pages do not change under their authors.
    tail = _placement_notice(placement_issues(state, seen)) if state.get("placement") == "explicit" else _widgets_html(state, set(seen["widgets"]))
    if resource_images:
        def embed_image(match):
            image = match.group()
            identifier = re.search(r'data-resource-id="([^"]+)"', image)[1]
            data = resource_images.get(identifier)
            return image[:-1] + ' src="' + html.escape(data, quote=True) + '">' if data else image
        content = re.sub(r'<img data-resource-id="[^"]+"[^>]*>', embed_image, content)
    anchors = re.findall(r'<h([1-6])\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h\1>', content, re.S)
    navigation = ('<nav class="ros-toc" aria-label="Session sections"><details class="ros-toc-panel" open><summary>Contents</summary><ul>'
                  + ''.join('<li data-level="' + level + '"><a href="#' + anchor + '">' + label + '</a></li>' for level,anchor,label in anchors)
                  + '</ul></details></nav>') if anchors else ''
    # The title and optional subtitle are the whole header: kind/status/date badges added noise, not orientation.
    subtitle = state.get('metadata', {}).get('subtitle')
    subtitle_markup = ('<p class="ros-session-context">' + html.escape(subtitle) + '</p>') if isinstance(subtitle, str) and subtitle.strip() else ''
    header = '<header class="ros-session-header"><h1>' + html.escape(state['title']) + '</h1>' + subtitle_markup + '</header>'
    # The context binding holds local paths and is for agents, not the page or a shared export.
    page_state = {k: v for k, v in state.items() if k != "context"}
    import learning_advice
    page_state["canonical_advice"] = learning_advice.public(state)
    page_state["learning_preferences"] = learning_advice.public_preferences(state)
    audio_urls = _audio_urls(state, runtime_prefix, standalone, audio_data)
    if audio_urls:
        page_state["audio_urls"] = audio_urls  # for the page only: the stored session never holds a resolved location
    board_audio = _board_audio_urls(state, runtime_prefix, standalone, audio_data)
    if board_audio:
        page_state["board_audio"] = board_audio
    data = json.dumps(page_state, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    if standalone:
        css = (RUNTIME / "session.css").read_text(encoding="utf-8")
        js = (RUNTIME / "session.js").read_text(encoding="utf-8")
        resources = "<style>" + css + "</style>"
        script = "<script>" + js.replace("</script", "<\\/script") + "</script>"
    else:
        prefix = html.escape(runtime_prefix, quote=True)
        resources = '<link rel="stylesheet" href="' + prefix + '/session.css">'
        script = '<script src="' + prefix + '/session.js"></script>'
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\' \'unsafe-inline\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data:; font-src data:; connect-src \'none\'; form-action \'none\'; base-uri \'none\'' + _frame_src(state) + _media_src(state, standalone) + '">'
            + '<title>' + html.escape(state["title"]) + '</title>' + resources + '</head><body><main class="ros-document" id="ros-session">'
            + header
            + navigation + content + _questions_html(state, placed) + tail + resource_markup
            + '<details data-ros="legacy"><summary>Exact original Markdown</summary><pre>' + html.escape(state["source_markdown"]) + '</pre></details>'
            + '</main><script type="application/json" id="ros-session-data">' + data + '</script>' + script + resource_scripts + '</body></html>\n')


def render_bridge(state, relative_html):
    # Preserve the full note for existing Markdown-based graph/protocol readers.
    readable = ((state.get('plan') or {}).get('handout') or {}).get('readable') or {}
    link = '\nStudy handout: [[' + readable['note'] + ']]\n' if readable.get('note') else ''
    return state["source_markdown"] + BRIDGE_MARKER + '\n```ros-session\n' + relative_html + '\n```\n' + link


def _transaction_path(root, relative_md):
    md, _, _ = paths(root, relative_md)
    relative = md.relative_to(Path(root).resolve()).as_posix()
    return _path(root, '.research-os/transactions/' + _hash(relative.encode()) + '.json')


def recover_session(root, relative_md, apply=False):
    """Recover under the same lock used by authoring and browser state writes."""
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        return _recover_session_locked(root, relative_md, apply)


def _recover_session_locked(root, relative_md, apply=False):
    """Recover a journaled projection write only if no subsequent edits conflict."""
    journal = _transaction_path(root, relative_md)
    if not journal.exists():
        return {"pending": False, "dry_run": not apply}
    transaction = json.loads(journal.read_text(encoding='utf-8'))
    expected = {p.relative_to(Path(root).resolve()).as_posix() for p in paths(root, relative_md)}
    if transaction.get('schema_version') != 1 or {f['path'] for f in transaction.get('files', [])} != expected:
        raise ValueError('Invalid session recovery journal')
    for entry in transaction['files']:
        path = _path(root, entry['path'])
        raw = base64.b64decode(entry['after'], validate=True)
        if _hash(raw) != entry['after_sha256']:
            raise ValueError('Session recovery integrity failure')
        current = _hash(path.read_bytes()) if path.exists() else None
        if current not in {entry['before_sha256'], entry['after_sha256']}:
            raise ValueError('Session recovery conflict; later edits preserved')
    if apply:
        for entry in transaction['files']:
            _write(_path(root, entry['path']), base64.b64decode(entry['after'], validate=True))
        journal.unlink()
    return {"pending": True, "dry_run": not apply, "session": str(relative_md)}


def load_session(root, relative_md, check_bridge=True):
    md, view, data = paths(root, relative_md)
    if _transaction_path(root, relative_md).exists():
        raise ValueError("Interrupted session write; run recover before resuming")
    state = validate_state(json.loads(data.read_text(encoding="utf-8")))
    if check_bridge and md.read_bytes() != render_bridge(state, view.relative_to(Path(root).resolve()).as_posix()).encode("utf-8"):
        raise ValueError(f"Conflicting manual Markdown bridge edit: {relative_md}")
    return state


def _check_image(path, raw):
    """An SVG is drawing, never a carrier for script or outside references; it is checked whenever it is read for display."""
    if path.suffix.lower() == ".svg":
        import visual_assets  # imports this module, so it is loaded on demand
        problems = visual_assets.svg_problems(raw.decode("utf-8", errors="replace"))
        if problems:
            raise ValueError("Unsafe SVG resource " + path.name + ": " + "; ".join(problems))


def _save(root, relative_md, state):
    md, view, data = paths(root, relative_md)
    validate_state(state)
    for resource in state.get("resources", []):
        value = resource["path"]
        allowed = (view.stem + ".assets/", ".research-os/runtime/extensions/")
        if not value.startswith(allowed):
            raise ValueError("Resource outside approved local session directories")
        resource_path = _path(root, md.parent.relative_to(Path(root).resolve()) / value) if value.startswith(allowed[0]) else _path(root, value)
        if not resource_path.is_file() or resource_path.stat().st_size > 1024 * 1024:
            raise ValueError("Local session resource missing or exceeds limit")
        if resource["kind"] == "module":
            _approved_module(root, resource_path, resource)
        else:
            _check_image(resource_path, resource_path.read_bytes())
    prefix = os.path.relpath(Path(root).resolve() / ".research-os/runtime", view.parent).replace(os.sep, "/")
    outputs ={data: _json(state), view: render_html(state, prefix).encode("utf-8"),
               md: render_bridge(state, view.relative_to(Path(root).resolve()).as_posix()).encode("utf-8")}
    journal = _transaction_path(root, relative_md)
    if journal.exists():
        raise ValueError("Interrupted session write exists; use recover before updating")
    transaction = {"schema_version": 1, "session": str(relative_md), "files": []}
    for path, raw in outputs.items():
        before = path.read_bytes() if path.exists() else None
        transaction["files"].append({"path": path.relative_to(Path(root).resolve()).as_posix(),
            "before_sha256": _hash(before) if before is not None else None,
            "before": base64.b64encode(before).decode() if before is not None else None,
            "after_sha256": _hash(raw), "after": base64.b64encode(raw).decode()})
    _write(journal, _json(transaction))
    for path, raw in outputs.items():
        _write(path, raw)
    journal.unlink()
    return state


def create_session(root, relative_md, text, session_type=None, title=None, metadata=None, questions=None, widgets=None, resources=None, context=None):
    md, _, _ = paths(root, relative_md)
    md.parent.mkdir(parents=True, exist_ok=True)
    with Lock(md.with_suffix('.session.lock')):
        return _create_session(root, relative_md, text, session_type, title, metadata, questions, widgets, resources, context)


def _create_session(root, relative_md, text, session_type=None, title=None, metadata=None, questions=None, widgets=None, resources=None, context=None):
    md, view, data = paths(root, relative_md)
    if data.exists() or view.exists():
        raise ValueError(f"Session already exists: {relative_md}")
    if md.exists() and md.read_bytes() != text.encode("utf-8"):
        raise ValueError("Existing Markdown differs from requested session source")
    front, _ = parse_frontmatter(text.replace("\r\n", "\n"))
    state = {"schema_version": 1, "session_id": uuid.uuid4().hex,
             "type": session_type or front.get("type", "research-session"),
             "title": title or front.get("title") or derive_title(text, md.stem), "metadata": dict(metadata or front),
             "source_markdown": text, "events": [], "questions": list(questions or []),
             "open_questions": [], "lifecycle": front.get("status", "active"), "created_at": _now(), "updated_at": _now()}
    state["widgets"] = list(widgets or [])
    state["resources"] = list(resources or [])
    state["placement"] = "explicit"  # visuals sit where the lesson puts them; nothing is appended silently
    if context is not None:
        state["context"] = context
    if front.get("session_id"):
        state["session_id"] = front["session_id"]
    return _save(root, relative_md, state)


def update_session(root, relative_md, text=None, **changes):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        allowed = {"title", "metadata", "questions", "open_questions", "lifecycle", "widgets", "resources", "navigation", "teaching", "tutoring", "plan"}
        if set(changes) - allowed:
            raise ValueError("Unsupported session update fields")
        source = state["source_markdown"] if text is None else text
        front, _ = parse_frontmatter(source.replace("\r\n", "\n"))
        proposed_metadata = changes.get("metadata", {})
        if any(key in front and value != front[key] for key,value in proposed_metadata.items()):
            raise ValueError('Metadata contradicts source frontmatter; update the source explicitly')
        if 'lifecycle' in changes and front.get('status', changes['lifecycle']) != changes['lifecycle']:
            raise ValueError('Lifecycle contradicts source status; update the source explicitly')
        if 'plan' in changes:
            import session_plan
            session_plan.check(changes['plan'])
        teaching_changed = source != state['source_markdown'] or any(
            name in changes and changes[name] != state.get(name, [])
            for name in ('questions', 'widgets', 'teaching', 'resources'))
        if 'plan' in changes or teaching_changed:
            _ensure_context(state)
        if 'plan' in changes and state.get('plan'):
            changed_answers = answered_plan_changes(state['plan'], changes['plan'], state['events'])
            if changed_answers:
                raise ValueError('Answered assessment history must be preserved: ' + '; '.join(changed_answers))
            problems = plan_revision_problems(state['plan'], changes['plan'], state['events'])
            if problems:
                raise ValueError('The revised plan would move the learner: ' + '; '.join(problems))
        if (state.get('plan') or {}).get('pedagogy'):
            import pedagogy_budget
            before_budget = pedagogy_budget.project(state)
            prospective = dict(state, **changes)
            if before_budget['used']:
                initial = lambda s: s['tutoring'].get('budget', 5) if s.get('tutoring') is not None else (s.get('plan') or {}).get('budget', 5)
                if not (prospective.get('plan') or {}).get('pedagogy'):
                    raise ValueError('Cannot disable shared budget after assessment reservations')
                if initial(state) != initial(prospective):
                    raise ValueError('Initial diagnostic budget is frozen; use an explicit learner-requested extension')
            if 'questions' in changes:
                old_costs = {q['id']: q.get('units') for q in state['questions'] if isinstance(q.get('contract'), dict)}
                new_costs = {q['id']: q.get('units') for q in prospective['questions'] if isinstance(q.get('contract'), dict)}
                if any(new_costs.get(qid) != cost for qid, cost in old_costs.items()):
                    raise ValueError('Preserve existing contracted assessment budget reservations')
            after_budget = pedagogy_budget.project(prospective)
            if after_budget['used'] > max(before_budget['used'], after_budget['limit']):
                raise ValueError('New contracted assessments exceed shared diagnostic budget')
        state.update(changes)
        if "plan" in changes:
            records = _video_records(root, changes["plan"])
            if records:
                state["video_records"] = records
            else:
                state.pop("video_records", None)
        state["source_markdown"] = source
        state['metadata'].update(front)
        state['type'] = front.get('type', state['type'])
        state['lifecycle'] = front.get('status', state['lifecycle'])
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def _video_records(root, plan):
    """The vetted registry records that a plan's video segments name, as the snapshots a Teaching Card carries (``resources.card_resource``). The page never
    holds an address of its own: the Obsidian host plays a part of one of these snapshots, and only one that a segment of this plan names (RESOURCE_PROTOCOL.md).
    A record that is missing, not vetted, out of date or not an embeddable YouTube video is left out, so the host refuses it and the lecture goes on without it."""
    import resources
    segments = plan.get("segments") if isinstance(plan, dict) else None
    wanted = {seg["video"]["resource"] for seg in segments or [] if isinstance(seg, dict) and isinstance(seg.get("video"), dict)
              and isinstance(seg["video"].get("resource"), str)}
    if not wanted:
        return {}
    known, _ = resources.load_all(resources.registry_dir(root))
    return {rid: resources.card_resource(known[rid]) for rid in sorted(wanted)
            if rid in known and known[rid]["status"] == "vetted" and not resources.is_stale(known[rid]) and known[rid].get("embed") == "youtube"}


def _validate_video_records(records):
    """The shape of ``video_records``; the Obsidian host checks the same things again before it plays anything."""
    import resources
    if not isinstance(records, dict) or len(records) > 32:
        raise ValueError("Invalid video records")
    for rid, record in records.items():
        if (not isinstance(rid, str) or not resources.ID.fullmatch(rid) or not isinstance(record, dict) or record.get("id") != rid or record.get("embed") != "youtube"
                or not isinstance(record.get("title"), str) or len(record["title"]) > 200 or not isinstance(record.get("url"), str)):
            raise ValueError("Invalid video record")
        try:
            resources.https_url(record["url"])
            date = dt.date.fromisoformat(str(record.get("vetted_on")))
        except (resources.ResourceError, ValueError):
            raise ValueError("Invalid video record") from None
        if resources.youtube_id(record["url"]) != record.get("video_id") or not resources.YOUTUBE.fullmatch(str(record.get("video_id"))) or date.isoformat() != record["vetted_on"]:
            raise ValueError("Invalid video record")


def bind_context(receipt, request=None, preferences=None):
    """The durable form of a context receipt stored in a session (a binding, not the receipt)."""
    import context_kernel as ck
    import learning_advice
    bound = {"binding": ck.summary(receipt), "request": request or receipt["request"], "bound_at": _now(), "refreshed_at": None}
    advice = learning_advice.snapshot(receipt)
    if advice is not None:
        bound["advice"] = advice
    if preferences is not None:
        import learning_preferences
        bound["preferences"] = learning_preferences.validate(preferences)
    return bound


def waive_context(reason):
    """An explicit, recorded decision to work without graph context (never a default)."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A context waiver needs a reason")
    return {"waived": True, "reason": reason.strip(), "bound_at": _now()}


def bind_session_context(root, relative_md, receipt):
    """Adopt a context binding for an existing (e.g. historical) session; refuses a blocked receipt."""
    import context_kernel as ck
    ck.require(receipt)
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        state["context"] = bind_context(receipt, preferences=(state.get("context") or {}).get("preferences"))
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def set_learning_preferences(root, relative_md, preferences):
    """Persist an explicit learner choice through the existing locked writer.

    This changes presentation advice only. It does not reroute prepared lessons,
    write canonical records or require an optional model/provider service.
    """
    import learning_preferences
    value = learning_preferences.validate(preferences)
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        state = load_session(root, relative_md)
        bound = state.get('context')
        if bound is None:
            raise ValueError('Bind canonical context or explicitly waive it before saving learning preferences')
        changed = bound.get('preferences', {}) != value
        if changed:
            state['context'] = dict(bound, preferences=value)
            state['updated_at'] = _now()
            _save(root, relative_md, state)
        return {'session': str(relative_md), 'changed': changed, 'preferences': value}



def _ensure_context(state):
    """Precondition for tutoring actions: the bound context must still describe the canonical records.

    Sessions created without a binding (historical ones) are unaffected. A stale binding is rebuilt from
    its stored request; if the rebuilt context is blocked, the action is refused and nothing is written.
    """
    bound = state.get("context")
    if bound is None or bound.get("waived"):
        return
    import context_kernel as ck
    try:
        ck.require(bound["binding"], summary_only=True)
    except ck.ContextError as exc:
        if exc.code != "CONTEXT_STALE":
            raise
        receipt = ck.build(bound["request"])
        ck.require(receipt)
        import learning_advice
        state["context"] = dict(bound, binding=ck.summary(receipt), refreshed_at=_now())
        advice = learning_advice.snapshot(receipt)
        if advice is not None:
            state["context"]["advice"] = advice


def answer_open_question(root, relative_md, question_id, answer):
    """Record an actual agent answer without inventing assessment evidence."""
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 32000:
        raise ValueError('A nonempty bounded answer is required')
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        state = load_session(root, relative_md)
        record = next((q for q in state['open_questions'] if q.get('id') == question_id), None)
        if record is None:
            raise ValueError('Unknown open question')
        if record.get('answer'):
            if record['answer'] == answer:
                return state
            raise ValueError('Question already answered; existing answer preserved')
        _ensure_context(state)
        record.update(answer=answer, status='answered', answered_at=_now())
        return _save(root, relative_md, state)


def section_anchors(state):
    """Heading text -> anchor id, exactly as the page assigns them (a text that appears twice maps to its first anchor)."""
    content = markdown_html(state["source_markdown"], page_title=state["title"], questions={q["id"]: q for q in state["questions"]})
    anchors = {}
    for ident, label in re.findall(r'<h[1-6]\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h[1-6]>', content, re.S):
        anchors.setdefault(html.unescape(re.sub(r"<[^>]+>", "", label)).strip(), ident)
    return anchors


def answer_explanation_request(root, relative_md, request_id, heading):
    """Record that a requested explanation now exists under a heading of the lesson, so the learner can go there and come back.

    The explanation itself is ordinary lesson text added with append_session; this only links the request to it. A request
    is never learning evidence, and answering it changes nothing in the learner's record.
    """
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        record = next((r for r in state.get("explanation_requests", []) if r.get("id") == request_id), None)
        if record is None:
            raise ValueError("Unknown explanation request")
        anchor = section_anchors(state).get(str(heading).strip())
        if anchor is None:
            raise ValueError("No heading reads exactly " + repr(heading) + "; add the explanation to the lesson under that heading first")
        if record.get("answered_in") and record["answered_in"].get("section") == anchor:
            return state
        record.update(status="answered", answered_in={"section": anchor, "title": str(heading).strip()[:200]}, answered_at=_now())
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def declare_block(root, relative_md, block):
    """Declare what a section teaches, introduces and assumes (and, for implementation, its literacy items).

    The declaration must match a real heading of the lesson; tutor_gate.py check then holds the order of the lesson to
    the learner's recorded knowledge. Redeclaring an id replaces it.
    """
    import tutor_gate
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        others = [b for b in state.get("teaching", []) if not (isinstance(b, dict) and isinstance(block, dict) and b.get("id") == block.get("id"))]
        prospective = dict(state, teaching=others + [block])
        problems = [i for i in tutor_gate.block_issues(prospective)[0] if i["severity"] == "error"]
        if problems:
            raise ValueError("Teaching block: " + "; ".join(i["message"] for i in problems))
        if prospective['teaching'] != state.get('teaching', []):
            _ensure_context(state)
        state["teaching"] = prospective["teaching"]
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def append_session(root, relative_md, block):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        _ensure_context(state)
        state["source_markdown"] += block
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def append_event(root, relative_md, event):
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        event = dict(event)
        event.setdefault("event_id", uuid.uuid4().hex)
        prior = next((e for e in state["events"] if e["event_id"] == event["event_id"]), None)
        if prior is not None:
            if any(prior.get(k) != event.get(k) for k in ("type", "question_id", "response", "origin")):
                raise ValueError("Event identity reused with different content")
            return state
        import pedagogy_contract
        pedagogy_contract.validate_event(event, state)
        event["status"] = "pending-review"
        event.setdefault("created_at", _now())
        state["events"].append(event)
        if event["type"] == "open-question":
            record = {"id": event["event_id"], "session_id": state["session_id"], "concept": state["metadata"].get("concept"), "prompt": event.get("response", ""), "status": "open", "created_at": event["created_at"], "explanation_refs": []}
            if "origin" in event:
                record["origin"] = event["origin"]
            state["open_questions"].append(record)
        if event["type"] == "explanation-request":
            asked = {"id": event["event_id"], "mode": event["response"], "status": "open", "created_at": event["created_at"]}
            if "origin" in event:
                asked["origin"] = event["origin"]
            state.setdefault("explanation_requests", []).append(asked)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def _append_question(state, question):
    if not isinstance(question, dict) or not isinstance(question.get("id"), str) or not question["id"]:
        raise ValueError("A question needs a nonempty id")
    if any(q["id"] == question["id"] for q in state["questions"]):
        raise ValueError(f"Question already exists: {question['id']}")
    if question.get("kind", "free-response") not in QUESTION_KINDS:
        raise ValueError("Unsupported question kind")
    if not isinstance(question.get("prompt"), str) or not question["prompt"].strip():
        raise ValueError("A question needs a prompt")
    if "reviews" in question:
        raise ValueError("Reviews are recorded with review_response, not authored")
    if "contract" in question:
        # A probe is tied to one capability before it is posted: TESTS/ASSUMES/INTRODUCES, scope, dimension, method, units, criteria.
        import tutor_gate
        contract = question["contract"]
        assumed = set(contract.get("ASSUMES") or []) if isinstance(contract, dict) and isinstance(contract.get("ASSUMES"), list) else set()
        problems = [i["message"] for i in tutor_gate.question_issues(question, assumed) if i["severity"] == "error"]
        if problems:
            raise ValueError("Question contract: " + "; ".join(problems))
    if not QUESTION_MARKER.match("<!-- ros-question: " + question["id"] + " -->"):
        raise ValueError("Question ids use letters, digits, dot, underscore, colon or hyphen")
    state["questions"].append(dict(question))
    # Place the question where the session currently ends: after the teaching that led to it.
    if not re.search(r"^<!--\s*ros-question:\s*" + re.escape(question["id"]) + r"\s*-->\s*$", state["source_markdown"], re.M):
        source = state["source_markdown"]
        separator = "" if source.endswith("\n\n") else "\n" if source.endswith("\n") else "\n\n"
        state["source_markdown"] = source + separator + "<!-- ros-question: " + question["id"] + " -->\n"


def add_question(root, relative_md, question):
    """Post one new question; open session views show it live without reloading."""
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        _ensure_context(state)
        _append_question(state, question)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def edit_board(root, relative_md, widget_id, steps=None, after=None, open_=None):
    """The lecturer extends a board while it plays. New ``steps`` go at the end, or right after the step ``after`` (an answer to a question goes after the step
    the learner has reached); ``open_`` says whether more is coming (an open board shows "waiting for the tutor" at its end instead of finishing). Steps the
    page has already started must not change: the board treats a changed earlier step as a revision and waits for Replay. The result is checked with the same
    rules the page uses before anything is written; open views pick it up live. One lecturer writes to a session at a time (the supervision lease)."""
    import copy
    import board_script
    state = load_session(root, relative_md)
    widgets = copy.deepcopy(state.get("widgets", []))
    widget = next((w for w in widgets if w.get("id") == widget_id and w.get("kind") == "board"), None)
    if widget is None:
        raise ValueError(f"no board widget named {widget_id!r} in this session")
    script = widget["script"]
    existing = script.get("steps", [])
    index = len(existing)
    if after is not None:
        ids = [s.get("id") for s in existing]
        if after not in ids:
            raise ValueError(f"no step {after!r} on this board (steps: {', '.join(str(i) for i in ids)})")
        index = ids.index(after) + 1
    script["steps"] = existing[:index] + list(steps or []) + existing[index:]
    if open_ is not None:
        script["open"] = bool(open_)
    board_script.check(script)
    return update_session(root, relative_md, widgets=widgets)


def add_board(root, relative_md, widget_id, script, title=None, after_heading=None):
    """Put a blackboard into a session that has none (one started in prose, or before boards existed). The widget is declared and its marker is placed in the
    lesson, after the first heading containing ``after_heading`` or else at the end, so the page shows it at once. The script is checked with the page's rules
    first. An id already used by a widget is refused; extend an existing board with ``edit_board`` instead."""
    import copy
    import board_script
    board_script.check(script)
    state = load_session(root, relative_md)
    widgets = copy.deepcopy(state.get("widgets", []))
    if any(w.get("id") == widget_id for w in widgets):
        raise ValueError(f"a widget named {widget_id!r} already exists in this session")
    widgets.append({"id": widget_id, "kind": "board", "title": title or "The board", "script": script})
    marker = f"<!-- ros-widget: {widget_id} -->"
    lines = state["source_markdown"].replace("\r\n", "\n").split("\n")
    at = len(lines)
    if after_heading:
        needle = after_heading.strip().lower()
        for number, line in enumerate(lines):
            if line.startswith("#") and needle in line.lower():
                at = number + 1
                break
        else:
            raise ValueError(f"no heading containing {after_heading!r} in this session")
    lines[at:at] = ["", marker, ""]
    return update_session(root, relative_md, "\n".join(lines), widgets=widgets)


def board_position(root, relative_md, now=None):
    """Where the learner is in each lecture, as the Obsidian host last reported it (``<session>.board-position.json``), with its age. ``None`` when nothing has been
    reported (a standalone page, a view that was never opened). It is a hint for pacing and for where an answer belongs, never evidence of learning."""
    md, _, _ = paths(root, relative_md)
    path = md.with_suffix(".board-position.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("boards"), dict):
        return None
    stamp = time.time() if now is None else now
    out = {}
    for widget_id, record in data["boards"].items():
        if isinstance(record, dict) and isinstance(record.get("step"), str) and isinstance(record.get("status"), str):
            at = record.get("at")
            out[widget_id] = dict(record, age_seconds=round(stamp - at, 1) if isinstance(at, (int, float)) else None)
    if PLAN_LECTURE_WIDGET in out:
        # The lecture of a staged session is not a declared widget: the page reports it under a reserved id, and the segment it is in comes from the plan.
        try:
            plan = load_session(root, relative_md).get("plan") or {}
        except (OSError, ValueError):
            plan = {}
        owner = {step["id"]: seg["id"] for seg in plan.get("segments", []) for step in (seg.get("script") or {}).get("steps", [])}
        out[PLAN_LECTURE_WIDGET]["segment"] = owner.get(out[PLAN_LECTURE_WIDGET]["step"])
    return out or None


def review_response(root, relative_md, question_id, verdict, feedback="", next_question=None, transcript=None,
                    criteria_met=None, reviewed_by=None, rationale=None, response_event_id=None):
    """Record the tutor's verdict on the learner's latest actual response.

    The verdict and the question's prepared explanation appear in place of the
    learner's "Checking..." state. It is pending tutor feedback, not ledger
    evidence: canonical attempts still follow the learning protocol. One save can
    also post the next question and a transcript entry so the page updates once.

    A question that declares ``criteria`` is reviewed against every one of them (``criteria_met``, one true/false each):
    a reviewer cannot pass an answer without saying which criteria it met.
    """
    if verdict not in REVIEW_VERDICTS:
        raise ValueError("Verdict must be one of: " + ", ".join(REVIEW_VERDICTS))
    if not isinstance(feedback, str) or len(feedback) > 32000:
        raise ValueError("Feedback must be bounded text")
    md, _, _ = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md)
        question = next((q for q in state["questions"] if q["id"] == question_id), None)
        if question is None:
            raise ValueError("Unknown question")
        if transcript or next_question is not None:
            _ensure_context(state)  # a verdict alone teaches nothing new; new teaching or probes need current context
        answered = [e for e in state["events"] if e["type"] == "response" and e.get("question_id") == question_id]
        response = next((e for e in reversed(answered) if response_event_id in (None, e["event_id"])), None)
        if response is None:
            raise ValueError("No learner response to review; never invent an answer" if response_event_id is None else "Unknown response to review")
        review = {"response_event_id": response["event_id"], "verdict": verdict, "feedback": feedback.strip(), "reviewed_at": _now()}
        declared = question.get("criteria") or []
        if declared and verdict != "reviewed" and (not isinstance(criteria_met, list) or len(criteria_met) != len(declared)):
            raise ValueError("This question declares %d criteria; state for each whether it was met (criteria_met)" % len(declared))
        if criteria_met is not None:
            review["criteria_met"] = criteria_met
        if reviewed_by:
            review["reviewed_by"] = reviewed_by
        if rationale:
            review["rationale"] = rationale
        _validate_reviews([review])
        reviews = question.setdefault("reviews", [])
        # Reviewing a response also records, explicitly, which earlier unreviewed attempts it supersedes; none is dropped silently.
        settled = {r.get("response_event_id") for r in reviews} | {c for r in reviews for c in r.get("covers", [])}
        earlier = [e["event_id"] for e in answered[:answered.index(response)] if e["event_id"] not in settled]
        if earlier:
            review["covers"] = earlier
        same = lambda r: {k: v for k, v in r.items() if k not in ("reviewed_at", "covers")}
        if not reviews or same(reviews[-1]) != same(review):
            reviews.append(review)
        # Transcript first, then the next question, so the page reads in the order things happened.
        if transcript:
            separator = "" if state["source_markdown"].endswith("\n\n") else "\n" if state["source_markdown"].endswith("\n") else "\n\n"
            state["source_markdown"] += separator + transcript.strip("\n") + "\n"
        if next_question is not None:
            _append_question(state, next_question)
        state["updated_at"] = _now()
        return _save(root, relative_md, state)


def pending_activity(state):
    """Learner activity awaiting the session agent: unreviewed latest responses and unanswered questions."""
    items = []
    for q in state["questions"]:
        events = [e for e in state["events"] if e.get("question_id") == q["id"]]
        responses = [e for e in events if e["type"] == "response"]
        # A submission is handled when a review names it, or a review explicitly records covering it (an earlier attempt that a
        # later reviewed answer superseded). Nothing is dropped silently: an unreviewed submission stays pending.
        handled = set()
        order = [r["event_id"] for r in responses]
        for review in q.get("reviews", []):
            named = review.get("response_event_id")
            handled.add(named)
            handled.update(review.get("covers", []))
            # A review stands for the attempt it names and every attempt before it. v0.8 reviewed only the latest response and recorded no
            # `covers`, so without this rule each retry in an already-finished lesson would come back as pending work; v0.9 also lists the
            # earlier attempts it supersedes in `covers`, which agrees. A review of an earlier attempt never settles a later one.
            if named in order:
                handled.update(order[:order.index(named) + 1])
        for number, response in enumerate(responses, 1):
            if response["event_id"] in handled:
                continue
            when = response.get("created_at", "")
            confidence = next((e["response"] for e in reversed(events) if e["type"] == "confidence" and e.get("created_at", "") <= when),
                              next((e["response"] for e in reversed(events) if e["type"] == "confidence"), None))
            items.append({"kind": "response", "question_id": q["id"], "question_kind": q.get("kind", "free-response"),
                          "prompt": q.get("prompt", ""), "event_id": response["event_id"], "response": response.get("response"),
                          "created_at": response.get("created_at"), "attempt": number, "attempts": len(responses), "confidence": confidence,
                          "hints_revealed": max([int(e["response"]) for e in events if e["type"] == "hint" and isinstance(e.get("response"), int)
                                                 and e.get("created_at", "") <= when] or [0]),
                          "solution_seen_before_response": any(e["type"] == "solution" and e.get("created_at", "") < when for e in events)})
    # A written answer in a staged session never blocked the learner (verdict "pending"); it waits here until a plan review covers it. A review stands for the
    # answer it names and every earlier answer to the same question, in event order (the same rule as above, mirrored by pendingOf in runtime.js).
    plan_questions = {q.get("id"): q for tree in ("probe", "check") for q in ((state.get("plan") or {}).get(tree) or {}).get("questions", [])}
    written = {}
    for event in state["events"]:
        if event.get("type") == "plan-answer":
            written.setdefault(event.get("question_id"), []).append(event)
    for question_id, answers in written.items():
        order = [e["event_id"] for e in answers]
        handled = set()
        for review in state.get("plan_reviews", []):
            if review.get("question_id") == question_id and review.get("response_event_id") in order:
                handled.update(order[:order.index(review["response_event_id"]) + 1])
        for number, event in enumerate(answers, 1):
            response = event.get("response") if isinstance(event.get("response"), dict) else {}
            if response.get("verdict") != "pending" or event["event_id"] in handled:
                continue
            question = plan_questions.get(question_id) or {}
            items.append({"kind": "plan-answer", "question_id": question_id, "tree": response.get("tree"), "prompt": question.get("prompt", ""), "criteria": question.get("criteria", []),
                          "tests": question.get("tests"), "solution": question.get("solution"), "event_id": event["event_id"], "response": response.get("answer"),
                          "created_at": event.get("created_at"), "attempt": number, "attempts": len(answers)})
            practice = next((entry for entry in ((state.get("plan") or {}).get("pedagogy") or {}).get("practice", []) if entry["question_id"] == question_id), None)
            if practice:
                items[-1]["practice"] = {key: practice[key] for key in ("id", "version", "tier", "dimension", "answer_unit", "alternatives", "independent")}
    for record in state.get("open_questions", []):
        if not (isinstance(record.get("answer"), str) and record["answer"].strip()):
            items.append({"kind": "open-question", "id": record.get("id"), "prompt": record.get("prompt"), "created_at": record.get("created_at")})
    for record in state.get("explanation_requests", []):
        if record.get("status") == "open":
            items.append({"kind": "explanation-request", "id": record.get("id"), "mode": record.get("mode"), "wants": ADAPT_MODES.get(record.get("mode")),
                          "origin": record.get("origin"), "created_at": record.get("created_at")})
    return items


VOICE_FOLDER = Path(".research-os") / "voice"


def session_readiness(root, relative_md):
    """Check the prepared lesson and its deployed renderer before starting workers.

    This is a filesystem preflight, not proof that the desktop has displayed or
    played the lesson. Historical records remain readable without a plan.
    """
    state = load_session(root, relative_md)
    _ensure_context(state)
    issues = []
    if state['type'] not in {'tutor-session', 'course-session'}:
        return {'ready': True, 'issues': [], 'desktop_verified': False}
    plan = state.get('plan')
    if not plan:
        issues.append('SESSION_PLAN_MISSING: prepare and attach the lesson plan before starting; preserve existing answers')
    elif (plan.get('handout') or {}).get('readable'):
        # The validated native resource is self-contained in the plan. Optional
        # PDF export or library availability cannot make that content unreadable.
        pass
    elif (plan.get('handout') or {}).get('status') != 'built':
        issues.append('HANDOUT_NOT_BUILT: build the planned handout before calling the session ready')
    else:
        import handout
        try:
            located = handout.locate(root, str(relative_md))
            pdf = _path(root, located.get('pdf', '')) if located.get('pdf') else None
            if not located.get('built') or pdf is None or not pdf.read_bytes().startswith(b'%PDF'):
                issues.append('HANDOUT_MISSING: the built handout PDF is missing or invalid')
        except (OSError, ValueError) as exc:
            issues.append('HANDOUT_UNAVAILABLE: ' + str(exc))

    def compare(source, destination, label):
        if not source.is_dir():
            issues.append(label + '_BUNDLE_MISSING: reinstall the complete skill bundle')
            return
        for path in sorted(source.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            target = destination / path.relative_to(source)
            # Git may check text out with CRLF; that alone is not stale code.
            a = path.read_bytes()
            b = target.read_bytes() if target.is_file() else None
            if path.suffix in {'.js', '.css', '.json', '.md', '.py', '.txt'}:
                a = a.replace(b'\r\n', b'\n')
                b = b.replace(b'\r\n', b'\n') if b is not None else None
            if a != b:
                issues.append(label + '_DRIFT: ' + target.relative_to(Path(root)).as_posix())

    compare(RUNTIME, Path(root) / '.research-os/runtime', 'RUNTIME')
    if (Path(root) / '.obsidian').is_dir():
        companion = Path(__file__).resolve().parents[1] / 'extensions/obsidian-html'
        # README is documentation, not a deployed companion resource.
        for name in ('main.js', 'manifest.json', 'styles.css'):
            source = companion / name
            target = Path(root) / '.obsidian/plugins/research-os-html' / name
            if not source.is_file() or not target.is_file() or source.read_bytes().replace(b'\r\n', b'\n') != target.read_bytes().replace(b'\r\n', b'\n'):
                issues.append('COMPANION_DRIFT: ' + name + '; back up and update the companion, then reload Obsidian')
        for name in ('voice.py', 'voice_adapter.py', 'speech_text.py'):
            source = Path(__file__).with_name(name)
            target = Path(root) / '.obsidian/plugins/research-os-html/voice' / name
            if not source.is_file() or not target.is_file() or source.read_bytes().replace(b'\r\n', b'\n') != target.read_bytes().replace(b'\r\n', b'\n'):
                issues.append('COMPANION_DRIFT: voice/' + name + '; install the local voice recovery helper')
        try:
            enabled = json.loads((Path(root) / '.obsidian/community-plugins.json').read_text(encoding='utf-8'))
            if not isinstance(enabled, list) or 'research-os-html' not in enabled:
                issues.append('COMPANION_DISABLED: enable the Research OS HTML Sessions companion')
        except (OSError, ValueError):
            issues.append('COMPANION_UNCONFIGURED: cannot verify the enabled companion')
    return {'ready': not issues, 'issues': issues, 'desktop_verified': False,
            'recommendation': session_recommendation(root, relative_md, state)}


def start_session(root, relative_md, holder=None, provider="generic", timeout=None, voice=False, ensure=None):
    """Start the prepared core and connect a tutor. Voice is an explicit enhancement.

    ``ready`` describes the core; ``voice_ready`` describes optional workers.
    ``ensure`` replaces the worker launcher in tests. Voice failures retain text.
    """
    _, _, data = paths(root, relative_md)
    if not data.exists():
        raise SystemExit(f"The session does not exist yet: {relative_md}")
    result = {"session": str(relative_md), "voice": None, "voice_ready": False, "lease": None,
              "preflight": session_readiness(root, relative_md)}
    if not result['preflight']['ready']:
        result['ready'] = False
        return result
    # The documented command must connect without host-specific argument knowledge.
    provider = provider.strip().lower()
    holder = re.sub(r'[^A-Za-z0-9_.-]+', '-', holder or f'{provider}-tutor-{os.getpid()}').strip('-')
    import supervision
    if not supervision.HOLDER.fullmatch(holder) or not supervision.PROVIDER.fullmatch(provider):
        raise ValueError('Invalid tutor holder or provider; use a short identifier')
    existing, _ = supervision.read_lease(root, relative_md)
    if existing and supervision.alive(existing) and existing['holder'] != holder:
        raise supervision.SupervisionError('LEASE_HELD', 'Another tutor is supervising this session; resolve ownership before starting workers')
    import learning_advice
    result["advice_refresh"] = learning_advice.refresh(root, relative_md)
    snapshot = result['advice_refresh']['advice']
    if snapshot and snapshot['status'] == 'blocked':
        result['preflight']['ready'] = False
        result['preflight']['issues'].append('CONTEXT_BLOCKED: essential context became unavailable during startup')
        result['ready'] = False
        return result
    before = result['preflight'].get('recommendation') or {}
    if snapshot and snapshot['receipt_id'] and before.get('receipt_id') != snapshot['receipt_id']:
        result['preflight'] = session_readiness(root, relative_md)
        if not result['preflight']['ready']:
            result['ready'] = False
            return result
    if voice:
        import voice as voice_module
        directory = Path(root) / VOICE_FOLDER
        run = ensure or voice_module.ensure_workers
        options = {} if timeout is None else {"timeout": float(timeout)}
        try:
            result["voice"] = run(directory, voice_module.load_setup(directory), **options)
        except (OSError, ValueError, RuntimeError) as exc:
            result["voice"] = {"ready": False, "error": str(exc)}
        state = load_session(root, relative_md)
        if result['voice'].get('ready') and state.get('plan'):
            # Preparation belongs to startup, not to another learner request.
            try:
                result['audio_prefetch'] = voice_module.prefetch(directory, voice_module.plan_sentences(state['plan']))
            except (OSError, ValueError, RuntimeError) as exc:
                result['audio_prefetch'] = {"error": str(exc)}
    if holder:
        lease = supervision.heartbeat(root, relative_md, holder=holder, provider=provider, mode="working")
        result["lease"] = {"holder": lease["holder"], "expires_at": lease["expires_at"]}
    result["voice_ready"] = bool(result["voice"] and result["voice"].get("ready"))
    result["ready"] = True
    return result


def wait_for_activity(root, relative_md, timeout=900.0, interval=1.0, holder=None, provider="generic", ttl=None):
    """Bounded poll for an explicit learner submission; returns immediately if work is pending.

    Only explicit submissions count (Submit/Send), never idle timers or typing. A timeout is not the end of the lesson and
    not a claim that nobody is waiting: with ``holder`` this renews a supervision lease while listening (so the page can
    say the tutor is connected) and leaves it to expire afterwards (so the page says disconnected once nobody is).
    """
    _, _, data = paths(root, relative_md)
    deadline = time.monotonic() + max(0.0, float(timeout))
    supervise, last_beat = None, None
    if holder:
        import supervision
        supervise, ttl = supervision, ttl or supervision.DEFAULT_TTL
    while True:
        if supervise and (last_beat is None or time.monotonic() - last_beat >= ttl / 3):
            try:
                supervise.heartbeat(root, relative_md, holder=holder, provider=provider, mode="waiting", ttl=ttl)
            except supervise.SupervisionError as exc:
                return {"session": str(relative_md), "pending": [], "timed_out": False, "error": str(exc)}
            last_beat = time.monotonic()
        failure = None
        try:
            items = pending_activity(validate_state(json.loads(data.read_text(encoding="utf-8"))))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            items, failure = [], exc  # A writer may be mid-replace: reread until the deadline before calling it a failure.
        if items:
            if supervise:  # the agent now holds these: the page shows that it is reviewing them
                supervise.heartbeat(root, relative_md, holder=holder, provider=provider, mode="reviewing", ttl=ttl,
                                    reviewing=[i["event_id"] for i in items if i["kind"] in ("response", "plan-answer")])
            return {"session": str(relative_md), "pending": items, "timed_out": False}
        if time.monotonic() >= deadline:
            if failure is not None:
                # Unreadable is not idle: reporting "nothing pending" would let an agent stop listening to a session it cannot read.
                return {"session": str(relative_md), "pending": [], "timed_out": False, "error": "session state unreadable: " + type(failure).__name__ + ": " + str(failure)}
            return {"session": str(relative_md), "pending": [], "timed_out": True}
        time.sleep(interval)


SESSION_WORKFLOWS = {"tutor-session": "tutor", "course-session": "course-study", "research-session": "research-plan"}


def context_request(root, metadata, session_type=None, session=None, **overrides):
    """Kernel request for a session: its project and concept come from its own frontmatter."""
    import context_kernel as ck
    request = {"workflow": SESSION_WORKFLOWS.get(session_type, "tutor"), "vault": str(Path(root).resolve())}
    project = ck.wikilink_target(metadata.get("project")) or ck.wikilink_target(metadata.get("up"))
    if project:
        request["project"] = project
    concept = ck.wikilink_target(metadata.get("concept"))
    if concept and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", concept):
        request["target"] = {"kind": "concept", "id": concept}
    if session:
        request["session"] = session
    request.update({k: v for k, v in overrides.items() if v is not None})
    return request


def planning_request(root, relative_md, state, **overrides):
    """Preserve explicitly bound target/root/policy; refresh the evidence date.

    Changing a target is explicit (`context --target ... --bind`), never inferred
    from an answer, page selection or an incidental mention in lesson prose.
    """
    bound = (state or {}).get('context') or {}
    request = dict(bound['request']) if bound.get('request') else context_request(
        root, (state or {}).get('metadata', {}), (state or {}).get('type'), str(relative_md))
    request.update(vault=str(Path(root).resolve()), session=str(relative_md), as_of=dt.date.today().isoformat())
    request.update({key: value for key, value in overrides.items() if value is not None})
    return request


def session_recommendation(root, relative_md, state=None):
    """Startup projection, cached by the context kernel; no session/ledger writes."""
    import context_kernel as ck
    import learning_preferences
    state = state if state is not None else load_session(root, relative_md)
    bound = state.get('context') or {}
    if not bound or bound.get('waived'):
        result = {'policy_revision': 1, 'status': 'limited', 'evidence': False,
                'next': {'action': 'inspect_context'},
                'rationale': 'Historical or explicitly waived context: bind a current canonical target before claiming personalized instruction.',
                'adaptation': session_adaptation(state)}
        return learning_preferences.recommend(result, bound.get('preferences'), result['adaptation'])
    receipt, _, reused = ck.preflight(planning_request(root, relative_md, state))
    ck.require(receipt)
    result = dict(receipt['retrieval'].get('recommendation') or {
        'status': 'limited', 'evidence': False, 'next': {'action': 'inspect_context'},
        'rationale': 'This context workflow does not select tutoring actions.'},
        receipt_id=receipt['receipt_id'], cached=reused, adaptation=session_adaptation(state))
    return learning_preferences.recommend(result, bound.get('preferences'), result['adaptation'])


def _adapter_lines(root, project_root=None):
    """Which optional Obsidian adapters the vault has, from its files alone. Detection never blocks or changes a session."""
    try:
        import obsidian_plugins
        return obsidian_plugins.render(obsidian_plugins.summary(root, project_root=project_root))
    except Exception as exc:  # an optional convenience must not be able to break resuming
        return ["Adapter detection was unavailable (" + type(exc).__name__ + "); use the built-in routes."]


def session_context(root, relative_md, project_root=None, learning_root=None, as_of=None, library_root=None, target=None):
    """Resume brief built on the context kernel; also works before the session exists (bootstrap).

    The HTML page is a view, not memory. Nothing here grades, accepts or edits a session; the only
    write is the kernel's receipt cache under the vault's .research-os/context.
    """
    import context_kernel as ck
    root = Path(root).resolve()
    md, _, data = paths(root, relative_md)
    state = load_session(root, relative_md) if data.exists() else None
    if state is not None:
        metadata, session_type, source = state["metadata"], state["type"], state["source_markdown"]
    else:
        metadata, source = parse_frontmatter(md.read_text(encoding="utf-8").replace("\r\n", "\n")) if md.exists() else ({}, "")
        session_type = metadata.get("type")
    mentioned = sorted(set(re.findall(r"\b(?:RQ|H|EXP|DEC)-\d{3,}\b", source)))
    request = context_request(root, metadata, session_type, str(relative_md), project_root=project_root,
                              learning_root=learning_root, library_root=library_root, as_of=as_of, records=mentioned or None)
    if state is not None:
        request = planning_request(root, relative_md, state, project_root=project_root, learning_root=learning_root,
                                   library_root=library_root, as_of=as_of, target=target, records=mentioned or None)
    elif target is not None:
        request['target'] = target
    receipt, receipt_file, _ = ck.preflight(request)
    retrieval = receipt["retrieval"]
    learner, research = retrieval["learner"], retrieval["research"]
    sources = {s["name"]: s for s in receipt["sources"]}
    brief = {"session": str(relative_md), "exists": state is not None,
             "title": state["title"] if state else metadata.get("title", md.stem),
             "type": session_type, "lifecycle": state.get("lifecycle") if state else None,
             "updated_at": state.get("updated_at") if state else None,
             "pending": pending_activity(state) if state else [], "questions": [], "project": retrieval["project"],
             "research": None, "knowledge": None, "notes": [], "receipt": receipt,
             "receipt_file": str(receipt_file) if receipt_file else None, "blocked": receipt["outcome"] == "blocked",
             "adapters": _adapter_lines(root, project_root), "at_risk": ck.at_risk(receipt),
             "recommendation": retrieval.get('recommendation'),
             "adaptation": session_adaptation(state) if state else None}
    if brief['recommendation'] is not None:
        import learning_preferences
        brief['recommendation'] = learning_preferences.recommend(brief['recommendation'],
            ((state or {}).get('context') or {}).get('preferences'), brief['adaptation'])
    for q in (state["questions"] if state else []):
        responses = [e for e in state["events"] if e["type"] == "response" and e.get("question_id") == q["id"]]
        review = (q.get("reviews") or [None])[-1]
        brief["questions"].append({"id": q["id"], "kind": q.get("kind", "free-response"), "attempts": len(responses),
                                   "latest_response": responses[-1].get("response") if responses else None,
                                   "verdict": review["verdict"] if review and responses and review.get("response_event_id") == responses[-1]["event_id"] else None})
    if research:
        brief["research"] = {"root": sources["research"]["path"], "records": research["records_total"],
                             "errors": sources["research"]["counts"].get("errors", 0),
                             "active_questions": research["active_questions"], "active_hypotheses": research["active_hypotheses"],
                             "frontier": research["frontier"], "pending_validation": research["pending_validation"],
                             "pending_human_decisions": research["pending_human_decisions"],
                             "accepted_decisions": research["accepted_decisions"],
                             "session_records": [{"id": r["id"], "type": r["type"], "status": r["status"], "title": r["title"]}
                                                 for r in research["relevant_records"] if "requested" in r["relevance"]]}
    if learner:
        pick = lambda test: [{"id": n["id"], "title": n["title"], "state": n["state"], "freshness": n["freshness"]}
                             for n in learner["nodes"] if test(n)][:15]
        brief["knowledge"] = {"root": sources["learning"]["path"], "project": receipt["request"].get("project_id"),
                              "capabilities": learner["capabilities_total"], "states": learner["states"],
                              "frontier": pick(lambda n: n["frontier"]),
                              "stale_or_due": pick(lambda n: n["freshness"] in {"due", "overdue"} or n["state"] in {"stale", "fragile"}),
                              "diagnostics": learner["diagnostics"][:10]}
    return brief


def navigation_from_context(receipt, session=None, limit=40):
    """Where a learner can go from this session: prerequisites, earlier lessons, the first lesson on the concept and its
    research application. Derived only from recorded context; a source that is missing contributes nothing, nothing is invented.

    Targets are note names (or vault paths for sessions), which Obsidian resolves the way it resolves a wikilink, so they work
    wherever the learning and project roots sit relative to the vault.
    """
    retrieval = receipt.get("retrieval") or {}
    items, seen = [], set()

    def add(kind, label, target, note=None):
        if not label or target in seen or not rich_text.valid_note_target(target):
            return
        seen.add(target)
        entry = {"kind": kind, "label": str(label).strip()[:200], "target": target}
        if note:
            entry["note"] = note[:300]
        items.append(entry)

    stem = lambda path: re.sub(r"\.md\Z", "", str(path).replace("\\", "/").rsplit("/", 1)[-1]) if path else None
    nodes = (retrieval.get("learner") or {}).get("nodes", [])
    for node in sorted((n for n in nodes if not n.get("target") and n.get("distance")), key=lambda n: (n["distance"], n["id"])):
        add("prerequisite", node.get("title") or node["id"], stem(node.get("path")), f"{node['distance']} step(s) before the target; state: {node.get('state')}")
    current = str(session or "").replace("\\", "/")
    earlier = sorted((s for s in retrieval.get("sessions") or [] if str(s.get("path", "")).replace("\\", "/") != current),
                     key=lambda s: (s.get("updated_at") or "", s.get("path") or ""))
    if earlier:
        first = earlier[0]
        add("first-taught", first.get("title") or stem(first["path"]), str(first["path"]).replace("\\", "/"), "earliest recorded session on this concept")
        for s in reversed(earlier[1:][-5:]):
            add("earlier", s.get("title") or stem(s["path"]), str(s["path"]).replace("\\", "/"), s.get("type"))
    for record in (retrieval.get("research") or {}).get("relevant_records", []):
        if any(str(why).startswith("links concept") for why in record.get("relevance", [])):
            add("application", record.get("title") or record["id"], stem(record.get("path")), f"{record.get('type')} {record['id']}")
    return items[:limit]


def render_context(brief):
    """Compact Markdown for an agent resuming the session."""
    lines = [f"# Resume brief: {brief['title']}", "", f"Session `{brief['session']}` ({brief['type']}, {brief['lifecycle']}), updated {brief['updated_at']}." + ("" if brief.get("exists", True) else " Not created yet (bootstrap)."), ""]
    receipt = brief.get("receipt")
    if receipt:
        lines += [f"## Context: {receipt['outcome'].upper()}", "",
                  f"- Receipt `{receipt['receipt_id']}` ({receipt['workflow']}, {receipt['mode']})" + (f", file `{brief['receipt_file']}`" if brief.get("receipt_file") else "")]
        if receipt["outcome"] == "blocked":
            lines.append("- BLOCKED: essential context is unavailable (" + ", ".join(receipt["blocking"]) + "). Do not teach, post questions or edit this session until it is repaired.")
        lines += [f"- Limitation: {x}" for x in receipt["limitations"]] + [""]
    recommendation = brief.get('recommendation')
    if recommendation:
        lines += ['', '## Recommended next action', '',
                  f"- {recommendation['next']['action']} ({recommendation['status']}): {recommendation['rationale']}",
                  '- This is pacing advice, not a grade or a change to the current lesson.']
        policy = recommendation.get('policy')
        if policy and policy['preferences']:
            lines += [f"- Explicit study preferences: {json.dumps(policy['preferences'], ensure_ascii=False)}",
                      f"- Suggested presentation: {policy['action']}: {policy['reason']}"]
    adaptation = brief.get('adaptation')
    if adaptation:
        lines += ['', '## Session pacing', '', f"- {adaptation['action']}: {adaptation['reason']}",
                  '- A session review does not promote canonical evidence.']
    lines += ["", "## Awaiting you", ""]
    for item in brief["pending"]:
        if item["kind"] == "response":
            lines.append(f"- Review `{item['question_id']}` ({item['question_kind']}, submission {item['attempt']} of {item['attempts']}, confidence {item['confidence']}, hints {item['hints_revealed']}): {json.dumps(item['response'], ensure_ascii=False)[:400]}")
        elif item["kind"] == "plan-answer":
            lines.append(f"- Read the written answer to plan question `{item['question_id']}` ({item['tree']}, answer {item['attempt']} of {item['attempts']}): {json.dumps(item['response'], ensure_ascii=False)[:400]}"
                         f"; judge it against its criteria, then `plan-review` (the learner has already gone on)")
        elif item["kind"] == "explanation-request":
            lines.append(f"- Explain differently (`{item['id']}`): {item.get('wants') or item.get('mode')}" + (f", asked in \"{item['origin']['title']}\"" if item.get("origin") else "") + "; answer in the lesson, then answer-explanation")
        else:
            lines.append(f"- Answer open question `{item['id']}`: {str(item.get('prompt'))[:400]}")
    if not brief["pending"]:
        lines.append("- Nothing pending. Run `wait` to listen for the next submission.")
    lines += ["", "## Questions", ""] + [f"- `{q['id']}` {q['kind']}: {q['attempts']} attempt(s), verdict {q['verdict'] or '-'}" for q in brief["questions"]]
    if brief["project"]:
        lines += ["", "## Project memory", "", f"- Project note: `{brief['project']['note']}` (read its current state before teaching or deciding)", f"- Project ID `{brief['project']['id']}`, root `{brief['project']['path']}`"]
    research = brief["research"]
    if research:
        lines += ["", "## Research graph", "", f"- {research['records']} records under `{research['root']}`, {research['errors']} validation error(s)",
                  "- Active questions: " + (", ".join(research["active_questions"]) or "none"), "- Active hypotheses: " + (", ".join(research["active_hypotheses"]) or "none"),
                  "- Frontier (unranked): " + (", ".join(f"{f['id']} {f['transition']}" for f in research["frontier"]) or "none"),
                  "- Awaiting human decision: " + (", ".join(research["pending_human_decisions"]) or "none") + "; awaiting result validation: " + (", ".join(research["pending_validation"]) or "none")]
        lines += [f"- Accepted decision {d['id']}: {d['title']}" + (f" ({'; '.join(d['relevance'])})" if d["relevance"] else "")
                  for d in research.get("accepted_decisions", [])]
        for record in research["session_records"]:
            lines.append(f"- Session refers to {record['id']} ({record['type']}, {record['status']}): {record['title']}; load it with `research.py context --root \"{research['root']}\" --{ {'research-question': 'question', 'research-decision': 'decision'}.get(record['type'], record['type'])} {record['id']}`")
    if brief.get("at_risk"):
        lines += ["", "## Assumptions at risk", "",
                  "These are contradicted, unsupported, unresolved or unreadable in the records. Do not build on them without telling the researcher; "
                  "a build or experiment task is blocked until the researcher's approval names each one (`acknowledged_risks`)."]
        lines += [f"- {r['message']} (`{r['id']}`)" for r in brief["at_risk"]]
    knowledge = brief["knowledge"]
    if knowledge:
        lines += ["", "## Knowledge graph", "", f"- {knowledge['capabilities']} capabilities for `{knowledge['project']}` under `{knowledge['root']}`: " + ", ".join(f"{k} {v}" for k, v in sorted(knowledge["states"].items()))]
        lines += [f"- Frontier: {n['title']} ({n['id']}, {n['state']})" for n in knowledge["frontier"]]
        lines += [f"- Stale, fragile or due: {n['title']} ({n['id']}, {n['state']}, {n['freshness']})" for n in knowledge["stale_or_due"]]
    lines += [f"- Note: {n}" for n in brief["notes"]]
    if brief.get("adapters"):
        lines += ["", "## Obsidian adapters", ""] + [x if x.startswith("-") else "- " + x for x in brief["adapters"]]
        lines.append("- Use what is listed; otherwise use the built-in route. Plugin output is a presentation or a suggestion and never changes canonical state. Details: `python scripts/obsidian_plugins.py report --vault <vault>`.")
    return "\n".join(lines) + "\n"


def export_session(root, relative_md, destination):
    state = load_session(root, relative_md)
    md, view, _ = paths(root, relative_md)
    markup, scripts, images = "", "", {}
    used_images = set(re.findall(r'data-resource-id="([^"]+)"', markdown_html(state['source_markdown'])))
    for resource in state.get("resources", []):
        value = resource["path"]
        if value.startswith(view.stem + ".assets/"):
            path = _path(root, md.parent.relative_to(Path(root).resolve()) / value)
        elif value.startswith(".research-os/runtime/extensions/"):
            path = _path(root, value)
        else:
            raise ValueError("Unapproved export resource")
        raw = path.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("Export resource exceeds limit")
        if resource["kind"] == "image":
            _check_image(path, raw)
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}[path.suffix.lower()]
            data_url = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode()
            images[resource_id(resource)] = data_url
            # Only a historical session appends an unplaced figure; a new one reports it instead (see placement_issues).
            if resource_id(resource) not in used_images and state.get('placement') != 'explicit':
                markup += '<figure class="ros-figure"><img src="' + data_url + '" alt="' + html.escape(str(resource.get("alt", "Session illustration")), quote=True) + '"></figure>'
        else:
            _approved_module(root, path, resource)
            scripts += '<script>document.addEventListener("DOMContentLoaded",function(){' + raw.decode("utf-8").replace("</script", "<\\/script") + '\n},{once:true});</script>'
    audio_data, budget = {}, MAX_EXPORT_AUDIO_TOTAL
    wanted = []
    for block in state.get("teaching", []):
        card = block.get("card") if isinstance(block, dict) else None
        wanted += card["audio"].values() if isinstance(card, dict) and isinstance(card.get("audio"), dict) else ()
    for steps in _board_audio(state).values():   # only recordings still true of their sentences are worth the bytes
        wanted += [entry["file"] for entry in steps.values()]
    for path in wanted:
        if path in audio_data:
            continue
        try:
            source = _path(root, path)
            raw = source.read_bytes()
        except (OSError, ValueError):
            continue  # a missing recording leaves that card or step on the browser voice
        if len(raw) > MAX_EXPORT_AUDIO or len(raw) > budget:
            continue  # too large to embed: the exported page uses the browser voice for it
        budget -= len(raw)
        audio_data[path] = "data:" + AUDIO_TYPES[source.suffix.lower()] + ";base64," + base64.b64encode(raw).decode()
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Export destination already exists; choose a new file to preserve user data")
    _write(destination, render_html(state, standalone=True, resource_markup=markup, resource_scripts=scripts, resource_images=images, audio_data=audio_data).encode("utf-8"))
    return destination


def refresh_projection(root, relative_md, backup_directory, apply=False):
    """Refresh only generated HTML, preserving canonical JSON and Markdown bytes."""
    md, view, data = paths(root, relative_md)
    with Lock(md.with_suffix('.session.lock')):
        state = load_session(root, relative_md)
        protected = {md: md.read_bytes(), data: data.read_bytes()}
        before = view.read_bytes()
        prefix = os.path.relpath(Path(root).resolve() / '.research-os/runtime', view.parent).replace(os.sep, '/')
        after = render_html(state, prefix).encode('utf-8')
        report = {'path': view.relative_to(Path(root).resolve()).as_posix(), 'changed': before != after,
                  'before_sha256': _hash(before), 'after_sha256': _hash(after), 'dry_run': not apply}
        if apply and before != after:
            backup = Path(backup_directory) / view.relative_to(Path(root).resolve())
            if backup.exists(): raise ValueError('Projection backup already exists; choose a new backup directory')
            _write(backup, before)
            _write(view, after)
            report['backup'] = str(backup)
        if any(path.read_bytes() != raw for path, raw in protected.items()):
            raise ValueError('Protected session content changed during projection refresh')
        return report


def import_bridge(root, relative_md, apply=False):
    """Explicitly review and import a bridge edit; normal updates reject it."""
    md, view, data = paths(root, relative_md)
    with Lock(md.with_suffix(".session.lock")):
        state = load_session(root, relative_md, check_bridge=False)
        raw = md.read_bytes().decode("utf-8")
        if raw.count(BRIDGE_MARKER) != 1:
            raise ValueError("Bridge import requires exactly one intact session marker")
        source, trailer = raw.split(BRIDGE_MARKER)
        expected = render_bridge({**state, "source_markdown": ""}, view.relative_to(Path(root).resolve()).as_posix())[len(BRIDGE_MARKER):]
        if trailer != expected:
            raise ValueError("Bridge import cannot alter session embed or paths")
        result = {"path": str(relative_md), "changed": source != state["source_markdown"], "dry_run": not apply, "before_sha256": _hash(state["source_markdown"].encode()), "after_sha256": _hash(source.encode())}
        if apply and result["changed"]:
            backup = _path(root, ".research-os/imports/" + uuid.uuid4().hex)
            backup.mkdir(parents=True)
            for path in (md, view, data):
                _write(backup / path.name, path.read_bytes())
            _write(backup / "manifest.json", _json(result))
            state["source_markdown"] = source
            state["updated_at"] = _now()
            _save(root, relative_md, state)
            result["backup"] = backup.relative_to(Path(root).resolve()).as_posix()
        return result


def session_exceptions(root):
    path = Path(root) / ".research-os/session-exceptions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("exceptions"), list):
        raise ValueError("Invalid session exceptions manifest")
    for entry in data["exceptions"]:
        if not isinstance(entry, dict) or not entry.get("reason") or entry.get("kind") not in {"imported-archive", "pending-migration"}:
            raise ValueError("Invalid session exception")
        _path(root, entry["path"])
    return data["exceptions"]


def validate_sessions(root, exceptions=None):
    errors = []
    excluded = {e["path"] for e in session_exceptions(root)}
    excluded.update(exceptions or [])
    for candidate in inventory(root):
        if candidate["path"] in excluded or candidate["status"] == "exception":
            continue
        if candidate["status"] != "migrated":
            errors.append(f"{candidate['path']}: {candidate['status']} session missing HTML/state sidecars")
    for data in Path(root).rglob("*.state.json"):
        if {".git", ".claude"} & set(data.relative_to(root).parts):
            continue  # tool folders (agent worktrees hold full copies of the repository, fixtures included) are not sessions
        md = data.with_name(data.name[:-11] + ".md")
        if md.relative_to(root).as_posix() in excluded:
            continue  # a declared archive or fixture is reported by its owner, not validated as a live session
        try:
            state = load_session(root, md.relative_to(Path(root)))
            view = md.with_suffix(".html")
            prefix = os.path.relpath(Path(root).resolve() / ".research-os/runtime", view.parent).replace(os.sep, "/")
            # Host interaction writes state alone; the rendered content remains a
            # valid projection while bootstrap events are refreshed on next open.
            def without_bootstrap(value):
                return re.sub(r'(<script type="application/json" id="ros-session-data">).*?(</script>)', r'\1\2', value, flags=re.S)
            if without_bootstrap(view.read_bytes().decode("utf-8")) != without_bootstrap(render_html(state, prefix)):
                raise ValueError("HTML projection differs from structured state")
            # Only sessions created with explicit placement are held to it; older sessions keep their appended visuals.
            if state.get("placement") == "explicit":
                problems = placement_issues(state)
                if problems:
                    raise ValueError("visual placement: " + "; ".join(p["message"] for p in problems))
                titles = heading_issues(state["source_markdown"])
                if titles:
                    raise ValueError("section titles: " + "; ".join(f"line {t['line']}: {t['message']}" for t in titles))
                import tutor_gate
                tutoring = [i for i in tutor_gate.structural_issues(state) if i["severity"] == "error"]
                if tutoring:
                    raise ValueError("tutoring: " + "; ".join(i["where"] + ": " + i["message"] for i in tutoring))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{data.relative_to(root)}: {exc}")
    return errors


def inventory(root):
    report = []
    exceptions = {e["path"]: e for e in session_exceptions(root)}
    for md in sorted(Path(root).rglob("*.md")):
        rel = md.relative_to(root).as_posix()
        if md.name.upper() in {"SKILL.MD", "README.MD", "AGENTS.MD", "CLAUDE.MD"}:
            continue
        if any(part.lower() in {"docs", "policies", "scripts", "tests", "skills"} for part in md.relative_to(root).parts[:-1]):
            continue
        if any(part.startswith(".") for part in md.relative_to(root).parts) or any(part.lower() in {"templates", "90 templates"} for part in md.relative_to(root).parts[:-1]):
            continue
        try:
            source = md.read_bytes().decode("utf-8")
        except (UnicodeError, OSError) as exc:
            if any("session" in part.lower() for part in md.relative_to(root).parts[:-1]):
                report.append({"path": rel, "signals": ["session directory"], "status": "blocked", "error": str(exc)})
            continue
        front, body = parse_frontmatter(source.replace("\r\n", "\n"))
        if rel.startswith("assets/obsidian/") and re.search(r"^# \{\{title\}\}", body, re.M):
            continue
        signals = []
        type_ = front.get("type", "").lower()
        # Explicit record types take precedence over incidental narrative mentions.
        if type_ and "session" not in type_ and not front.get("session_type"):
            continue
        if "session" in type_:
            signals.append("frontmatter type")
        if any(part.lower() in {"sessions", "00 tutor sessions", "tutor sessions", "research sessions", "learning sessions", "study sessions", "course sessions"} for part in md.relative_to(root).parts[:-1]):
            signals.append("session directory")
        if re.search(r"^#{1,2}\s+.*(?:Tutor|Research|Learning|Study|Course|Recitation)\s+Session", body, re.M | re.I):
            signals.append("session heading")
        if front.get("session_id") or front.get("session_type"):
            signals.append("session metadata")
        if not signals:
            continue
        state_path = md.with_suffix(".state.json")
        status = "migrated" if state_path.exists() else ("ambiguous" if signals in (["session directory"], ["session heading"]) else "candidate")
        if rel in exceptions:
            status = "exception"
        candidate = {"path": rel, "signals": signals, "status": status, "sha256": _hash(md.read_bytes())}
        if rel in exceptions:
            candidate["exception"] = exceptions[rel]
        report.append(candidate)
    return report


def legacy_questions(source, metadata):
    """Recover only explicit active Q headings with a learner answer slot.

    Historical text is retained, never graded or treated as fresh evidence.
    Unrecognized formats remain visibly available in the exact-source panel.
    """
    if metadata.get("status", "").lower() not in {"active", "in-progress", "in_progress"}:
        return []
    lines = source.replace("\r\n", "\n").splitlines()
    questions = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{2,4})\s+(?:Q(?:uestion)?\s*\d+)[.\s:—-]*(.*)$", line, re.I)
        if not match:
            continue
        end = index + 1
        while end < len(lines) and not re.match(r"^#{1," + str(len(match[1])) + r"}\s", lines[end]):
            end += 1
        block = "\n".join(lines[index + 1:end])
        slot = re.search(r"(?:\*\*|#{1,6}\s*)?My answer(?:\*\*)?\s*:(?:\*\*)?\s*(.*)", block, re.I)
        if not slot:
            continue
        prompt = match[2].strip() or block[:slot.start()].strip()
        if not prompt:
            continue
        questions.append({"id": "legacy-q-" + str(len(questions) + 1), "kind": "free-response", "prompt": prompt, "historical_response": slot[1], "historical_source": block, "review_status": "unreviewed", "provenance": "explicit legacy question and learner answer slot"})
    return questions


def migrate(root, apply=False, journal=None, resume=False, rollback=False):
    root = Path(root).resolve()
    if not apply and not resume and not rollback:
        return _migrate_locked(root, apply, journal, resume, rollback)
    journal_path = _path(root, journal or '.research-os/migrations/v0.8.5/manifest.json')
    candidates = {r['path'] for r in inventory(root)}
    if journal_path.exists():
        log = json.loads(journal_path.read_text(encoding='utf-8'))
        candidates.update(r['path'] for r in log.get('records', []))
    with ExitStack() as locks:
        for relative in sorted(candidates):
            md, _, _ = paths(root, relative)
            locks.enter_context(Lock(md.with_suffix('.session.lock')))
        return _migrate_locked(root, apply, journal, resume, rollback)


def _migrate_locked(root, apply=False, journal=None, resume=False, rollback=False):
    """Journal all intended hashes and exact bytes before changing any candidate.

    Resume repairs only files whose hashes match either the recorded original or
    intended projection. Rollback has the same guard against concurrent edits.
    """
    root = Path(root).resolve()
    journal = _path(root, journal or ".research-os/migrations/v0.8.5/manifest.json")
    if not apply and not resume and not rollback:
        return {"dry_run": True, "candidates": inventory(root)}
    verify_only = False
    if journal.exists():
        log = json.loads(journal.read_text(encoding="utf-8"))
        if not resume and not rollback:
            if log.get("status") == "complete":
                candidates = inventory(root)
                if any(c["status"] in {"candidate", "blocked", "ambiguous"} for c in candidates):
                    raise ValueError("New unmigrated candidates found; use a new --journal for a new batch")
                # A complete journal is still verified against current files below.
                resume = True
                verify_only = True
            else:
                raise ValueError("Migration journal exists; use --resume or --rollback")
    else:
        if resume or rollback:
            raise ValueError("Migration journal missing")
        records = []
        for candidate in inventory(root):
            if candidate["status"] in {"migrated", "exception"}:
                continue
            if candidate["status"] in {"blocked", "ambiguous"}:
                raise ValueError(f"Unresolved {candidate['status']} session candidate: {candidate['path']}; review inventory and add a documented exception when appropriate")
            md, view, data = paths(root, candidate["path"])
            if view.exists() or data.exists():
                raise ValueError(f"Existing sidecar conflict: {candidate['path']}")
            raw = md.read_bytes()
            backup = journal.parent / "backups" / (uuid.uuid4().hex + ".md")
            _write(backup, raw)
            front, _ = parse_frontmatter(raw.decode("utf-8").replace("\r\n", "\n"))
            source = raw.decode("utf-8")
            state = {"schema_version": 1, "session_id": front.get("session_id", uuid.uuid4().hex), "type": front.get("type", "legacy-session"), "title": front.get("title", md.stem), "metadata": front, "source_markdown": source, "events": [], "questions": legacy_questions(source, front), "open_questions": [], "lifecycle": front.get("status", "legacy"), "created_at": _now(), "updated_at": _now(), "migration": {"conversion": "conservative structural HTML; unknown interactions preserved as legacy source", "historical_answers_reviewed": False}}
            prefix = os.path.relpath(root / ".research-os/runtime", view.parent).replace(os.sep, "/")
            outputs = {md.relative_to(root).as_posix(): render_bridge(state, view.relative_to(root).as_posix()).encode("utf-8"), view.relative_to(root).as_posix(): render_html(state, prefix).encode("utf-8"), data.relative_to(root).as_posix(): _json(state)}
            records.append({"path": candidate["path"], "signals": candidate["signals"], "backup": backup.relative_to(root).as_posix(), "before_hash": _hash(raw), "state": state, "outputs": {p: {"sha256": _hash(b), "content": b.decode("utf-8")} for p, b in outputs.items()}, "status": "prepared"})
        log = {"schema_version": 1, "root": str(root), "status": "prepared", "records": records, "discovery": inventory(root), "created_at": _now(), "recovery": "Run migrate --resume to finish unchanged projections, or migrate --rollback to restore verified exact originals."}
        _write(journal, _json(log))
    if log.get("root") != str(root) or log.get("schema_version") != 1:
        raise ValueError("Migration journal belongs to a different root/schema")
    # Preflight entire batch before changing a single file.
    for record in log["records"]:
        backup = _path(root, record["backup"])
        if _hash(backup.read_bytes()) != record["before_hash"]:
            raise ValueError("Migration backup integrity failure")
        for rel, projection in record["outputs"].items():
            path = _path(root, rel)
            if _hash(projection["content"].encode("utf-8")) != projection["sha256"]:
                raise ValueError("Migration journal integrity failure")
            if path.exists():
                digest = _hash(path.read_bytes())
                allowed = {projection["sha256"]}
                if rel == record["path"]:
                    allowed.add(record["before_hash"])
                if digest not in allowed:
                    raise ValueError(f"Migration conflict; refusing overwrite: {rel}")
            elif rel == record["path"]:
                raise ValueError(f"Missing migration source: {rel}")
    if verify_only:
        return {"dry_run": False, "status": "complete", "candidates": inventory(root), "journal": journal.relative_to(root).as_posix()}
    for record in log["records"]:
        if rollback:
            _write(_path(root, record["path"]), _path(root, record["backup"]).read_bytes())
            for rel in record["outputs"]:
                if rel != record["path"]:
                    _path(root, rel).unlink(missing_ok=True)
            record["status"] = "rolled-back"
        else:
            for rel, projection in record["outputs"].items():
                _write(_path(root, rel), projection["content"].encode("utf-8"))
            record["status"] = "complete"
        _write(journal, _json(log))
    log["status"] = "rolled-back" if rollback else "complete"
    _write(journal, _json(log))
    rows = ''.join('<tr><td>' + html.escape(r['path']) + '</td><td>' + html.escape(r['status']) + '</td><td>' + html.escape(', '.join(r['signals'])) + '</td><td>Conservative structural conversion. Original source retained in full; unknown question/solution pairings, tables, wikilinks and attachments remain legacy content. Historical answers are unreviewed.</td></tr>' for r in log['records'])
    _write(journal.parent / 'report.html', ('<!doctype html><meta charset="utf-8"><title>Research OS migration report</title><h1>v0.8.5 migration</h1><p>' + html.escape(log['status']) + '</p><table><thead><tr><th>Session</th><th>Status</th><th>Discovery</th><th>Conversion limitations</th></tr></thead><tbody>' + rows + '</tbody></table>').encode('utf-8'))
    updated = {r["path"]: {"path": r["path"], "signals": r["signals"], "status": r["status"]} for r in log["records"]}
    candidates = [updated.get(r["path"], r) for r in log.get("discovery", [])]
    return {"dry_run": False, "status": log["status"], "candidates": candidates, "journal": journal.relative_to(root).as_posix(), "recovery": log.get("recovery")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("validate")
    create = sub.add_parser("create", help="Create a session after a context preflight; refused when essential context is blocked")
    create.add_argument("session"); create.add_argument("--source", required=True, type=Path); create.add_argument("--type", dest="session_type"); create.add_argument("--title")
    create.add_argument("--workflow", help="context workflow (default follows the session type)")
    create.add_argument("--project"); create.add_argument("--target", help="concept:ID, capability:ID or record:ID")
    create.add_argument("--project-root", type=Path); create.add_argument("--learning-root", type=Path); create.add_argument("--library-root", type=Path)
    create.add_argument("--expect-empty", action="store_true", help="a new learner or project: empty graphs are expected")
    create.add_argument("--waive-context", metavar="REASON", help="record an explicit decision to work without graph context")
    update = sub.add_parser("update"); update.add_argument("session"); update.add_argument("--source", required=True, type=Path)
    append = sub.add_parser("append"); append.add_argument("session"); append.add_argument("--source", required=True, type=Path)
    event = sub.add_parser("event"); event.add_argument("session"); event.add_argument("--source", required=True, type=Path)
    answer = sub.add_parser("answer"); answer.add_argument("session"); answer.add_argument("question_id"); answer.add_argument("--source", required=True, type=Path)
    question = sub.add_parser("add-question", help="Post one question (JSON); open views show it live")
    question.add_argument("session"); question.add_argument("--source", required=True, type=Path)
    opened = sub.add_parser("board-open", help="Put a blackboard into a session that has none (JSON board script); the marker is placed in the lesson")
    opened.add_argument("session"); opened.add_argument("widget"); opened.add_argument("--source", required=True, type=Path, help="JSON: a board script, {board_schema: 1, open: true, steps: [...]}")
    opened.add_argument("--title"); opened.add_argument("--after-heading", help="place the board after the first heading containing this text (default: the end of the lesson)")
    board = sub.add_parser("board-append", help="Add steps to a lecture on a board while it plays (JSON list of steps); open views play them live")
    board.add_argument("session"); board.add_argument("widget"); board.add_argument("--source", required=True, type=Path, help="JSON: a list of steps, or {steps: [...]}")
    board.add_argument("--after", metavar="STEP_ID", help="insert right after this step instead of at the end (an answer goes after the step the learner has reached)")
    board.add_argument("--open", dest="board_open", choices=("true", "false"), help="true: more is coming (the board waits for it); false: this is the end of the lecture")
    planning = sub.add_parser("plan", help="Set the session plan (JSON, checked by session_plan.py): the page then runs the staged session; answers already given must stay in the plan")
    planning.add_argument("session"); planning.add_argument("--source", required=True, type=Path)
    reviewing = sub.add_parser("plan-review", help="Record the tutor verdict on a learner's written answer to a plan question (the learner has already gone on); optionally replace the plan in the same save")
    reviewing.add_argument("session"); reviewing.add_argument("question_id")
    reviewing.add_argument("--verdict", required=True, choices=REVIEW_VERDICTS)
    reviewing.add_argument("--feedback", type=Path, help="UTF-8 text file with the feedback shown under the learner's answer")
    reviewing.add_argument("--revise-plan", type=Path, help="JSON: the whole revised plan; refused if it would move a learner who has answered (see --allow-reroute)")
    reviewing.add_argument("--allow-reroute", action="store_true", help="accept a revised plan that changes where answered questions lead, or drops a segment the lecture started with")
    reviewing.add_argument("--criteria-met", help="comma-separated true/false, one per criterion the question declares")
    reviewing.add_argument("--reviewed-by", help="who judged the answer"); reviewing.add_argument("--rationale", type=Path)
    starting = sub.add_parser("start", help="Connect the tutor and start the prepared text core; voice is optional")
    starting.add_argument("session"); starting.add_argument("--holder", help="a name for this agent: renews the supervision lease so the page says a tutor is connected")
    starting.add_argument("--provider", default="generic"); starting.add_argument("--timeout", type=float, help="seconds to wait for each worker (default 180)")
    starting.add_argument("--no-voice", action="store_true", help="only connect the tutor; start no voice worker")
    starting.add_argument("--voice", action="store_true", help="also prepare optional voice workers (requires prior process approval)")
    position = sub.add_parser("board-position", help="Where the learner is in each lecture, as the Obsidian view last reported it")
    position.add_argument("session")
    review = sub.add_parser("review", help="Record the tutor verdict on the latest response; shown in place of 'Checking...'")
    review.add_argument("session"); review.add_argument("question_id")
    review.add_argument("--verdict", required=True, choices=REVIEW_VERDICTS)
    review.add_argument("--feedback", type=Path, help="UTF-8 text file with the feedback shown beside the question")
    review.add_argument("--next-question", type=Path, help="JSON question posted in the same save")
    review.add_argument("--transcript", type=Path, help="Markdown appended to the session transcript in the same save")
    review.add_argument("--criteria-met", help="comma-separated true/false, one per criterion the question declares")
    review.add_argument("--reviewed-by", help="who judged the answer"); review.add_argument("--rationale", type=Path)
    declare = sub.add_parser("declare-block", help="Declare what a section teaches, introduces and assumes (JSON); must match a heading")
    declare.add_argument("session"); declare.add_argument("--source", required=True, type=Path)
    explained = sub.add_parser("answer-explanation", help="Link a learner's explanation request to the heading where it is now explained")
    explained.add_argument("session"); explained.add_argument("request_id"); explained.add_argument("--heading", required=True)
    wait = sub.add_parser("wait", help="Block until an explicit learner submission awaits the agent (bounded)")
    wait.add_argument("session"); wait.add_argument("--timeout", type=float, default=900.0)
    wait.add_argument("--holder", help="a name for this agent: renews a supervision lease so the page can show a tutor is connected")
    wait.add_argument("--provider", default="generic"); wait.add_argument("--ttl", type=int, help="lease seconds (15..3600, default 90)")
    navigate = sub.add_parser("navigation", help="Derive related-lesson links (prerequisites, earlier lessons, application) from recorded context; dry run unless --apply")
    navigate.add_argument("session"); navigate.add_argument("--project-root", type=Path); navigate.add_argument("--learning-root", type=Path)
    navigate.add_argument("--library-root", type=Path); navigate.add_argument("--as-of"); navigate.add_argument("--apply", action="store_true")
    attach = sub.add_parser("attach-visual", help="Declare a registered visual (VIS-...) as an image of this session; place it next")
    attach.add_argument("session"); attach.add_argument("visual_id"); attach.add_argument("--resource-id")
    place = sub.add_parser("place", help="Put a declared figure or widget at an exact position in the lesson")
    place.add_argument("session")
    target = place.add_mutually_exclusive_group(required=True)
    target.add_argument("--figure", metavar="RESOURCE_ID"); target.add_argument("--widget", metavar="WIDGET_ID")
    position = place.add_mutually_exclusive_group(required=True)
    position.add_argument("--after-heading", metavar="TEXT", help="directly after the heading that reads exactly this")
    position.add_argument("--after-text", metavar="PHRASE", help="after the paragraph containing this (unique) phrase")
    position.add_argument("--at-end", action="store_true")
    place.add_argument("--alt", help="required for a figure: what a reader who cannot see it needs to know")
    place.add_argument("--caption")
    resume = sub.add_parser("context", help="Resume brief: pending learner activity plus research and knowledge graph state")
    resume.add_argument("session"); resume.add_argument("--project-root", type=Path); resume.add_argument("--learning-root", type=Path)
    resume.add_argument("--library-root", type=Path)
    resume.add_argument("--target", help="canonical concept:ID, capability:ID or project:ID; add --bind to persist the changed target")
    resume.add_argument("--as-of"); resume.add_argument("--json", action="store_true")
    resume.add_argument("--bind", action="store_true", help="store this context as the session's binding (adopts a historical session)")
    advice = sub.add_parser("refresh-advice", help="Refresh the bounded presentation snapshot from current canonical context; preserves answers and prepared content")
    advice.add_argument("session")
    preferences = sub.add_parser("preferences", help="Save explicit learner preferences from JSON; empty object clears preferences, without changing evidence or content")
    preferences.add_argument("session")
    preferences.add_argument("--source", type=Path, required=True)
    recovery = sub.add_parser("recover"); recovery.add_argument("session"); recovery.add_argument("--apply", action="store_true")
    bridge = sub.add_parser("import"); bridge.add_argument("session"); bridge.add_argument("--apply", action="store_true")
    export = sub.add_parser("export"); export.add_argument("session"); export.add_argument("destination", type=Path)
    refresh = sub.add_parser("refresh-projection", help="Regenerate only HTML; preserve source and canonical state")
    refresh.add_argument("session"); refresh.add_argument("--backup-directory", required=True, type=Path)
    refresh.add_argument("--apply", action="store_true")
    migration = sub.add_parser("migrate")
    mode = migration.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true"); mode.add_argument("--resume", action="store_true"); mode.add_argument("--rollback", action="store_true")
    migration.add_argument("--journal")
    args = parser.parse_args()
    root = args.root or Path(load_config()["vault"]["path"]).expanduser()
    if args.command == "inventory":
        result = inventory(root)
    elif args.command == "validate":
        result = validate_sessions(root)
    elif args.command == "export":
        result = str(export_session(root, args.session, args.destination))
    elif args.command == "refresh-projection":
        result = refresh_projection(root, args.session, args.backup_directory, args.apply)
    elif args.command == "create":
        install_runtime(root)
        text = args.source.read_bytes().decode("utf-8")
        if args.waive_context:
            context = waive_context(args.waive_context)
        else:
            import context_kernel as ck
            front = parse_frontmatter(text.replace("\r\n", "\n"))[0]
            request = context_request(root, front, args.session_type or front.get("type"), args.session, workflow=args.workflow,
                                      project=args.project, target=ck.parse_target(args.target), project_root=args.project_root,
                                      learning_root=args.learning_root, library_root=args.library_root,
                                      expect_empty=True if args.expect_empty else None)
            receipt, receipt_file, _ = ck.preflight(request)
            if receipt["outcome"] == "blocked":
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")
                print(json.dumps({"created": False, "reason": "essential context is unavailable", "blocking": receipt["blocking"],
                                  "limitations": receipt["limitations"], "receipt_file": str(receipt_file) if receipt_file else None},
                                 ensure_ascii=False, indent=2))
                raise SystemExit(2)
            context = bind_context(receipt)
        result = create_session(root, args.session, text, args.session_type, args.title, context=context)
    elif args.command == "navigation":
        brief = session_context(root, args.session, args.project_root, args.learning_root, args.as_of, args.library_root)
        if not brief["exists"]:
            raise SystemExit("The session does not exist yet; create it first")
        links = navigation_from_context(brief["receipt"], args.session)
        result = {"session": args.session, "applied": bool(args.apply), "navigation": links,
                  "context_outcome": brief["receipt"]["outcome"]}
        if args.apply:
            update_session(root, args.session, navigation=links)
    elif args.command in ("attach-visual", "place"):
        import visual_assets
        try:
            if args.command == "attach-visual":
                result = visual_assets.attach_visual(root, args.session, args.visual_id, args.resource_id)
            else:
                result = visual_assets.place_visual(root, args.session, figure=args.figure, widget=args.widget, after_heading=args.after_heading,
                                                    after_text=args.after_text, at_end=args.at_end, alt=args.alt, caption=args.caption)
        except visual_assets.VisualError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            raise SystemExit(2)
    elif args.command == "update":
        result = update_session(root, args.session, args.source.read_bytes().decode("utf-8"))
    elif args.command == "append":
        result = append_session(root, args.session, args.source.read_bytes().decode("utf-8"))
    elif args.command == "event":
        result = append_event(root, args.session, json.loads(args.source.read_text(encoding="utf-8")))
    elif args.command == "answer":
        result = answer_open_question(root, args.session, args.question_id, args.source.read_text(encoding="utf-8"))
    elif args.command == "add-question":
        result = add_question(root, args.session, json.loads(args.source.read_text(encoding="utf-8")))
    elif args.command == "board-append":
        loaded = json.loads(args.source.read_text(encoding="utf-8"))
        new_steps = loaded.get("steps") if isinstance(loaded, dict) else loaded
        if not isinstance(new_steps, list):
            raise SystemExit("error: the source must be a list of steps or {\"steps\": [...]}")
        result = edit_board(root, args.session, args.widget, new_steps, args.after, None if args.board_open is None else args.board_open == "true")
    elif args.command == "board-open":
        loaded = json.loads(args.source.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise SystemExit("error: the source must be a board script object")
        result = add_board(root, args.session, args.widget, loaded, args.title, args.after_heading)
    elif args.command == "plan":
        result = update_session(root, args.session, plan=json.loads(args.source.read_text(encoding="utf-8-sig")))
    elif args.command == "plan-review":
        result = review_plan_answer(root, args.session, args.question_id, args.verdict, args.feedback.read_text(encoding="utf-8") if args.feedback else "",
                                    reviewed_by=args.reviewed_by, rationale=args.rationale.read_text(encoding="utf-8") if args.rationale else None,
                                    criteria_met=[x.strip().lower() == "true" for x in args.criteria_met.split(",")] if args.criteria_met else None,
                                    revised_plan=json.loads(args.revise_plan.read_text(encoding="utf-8-sig")) if args.revise_plan else None, allow_reroute=args.allow_reroute)
    elif args.command == "start":
        result = start_session(root, args.session, args.holder, args.provider, args.timeout, voice=args.voice and not args.no_voice)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ready"] else 1)
    elif args.command == "board-position":
        result = board_position(root, args.session) or {"note": "nothing has been reported: no Obsidian view of this session has played a board yet"}
    elif args.command == "review":
        result = review_response(root, args.session, args.question_id, args.verdict,
                                 args.feedback.read_text(encoding="utf-8") if args.feedback else "",
                                 json.loads(args.next_question.read_text(encoding="utf-8")) if args.next_question else None,
                                 args.transcript.read_text(encoding="utf-8") if args.transcript else None,
                                 criteria_met=[x.strip().lower() == "true" for x in args.criteria_met.split(",")] if args.criteria_met else None,
                                 reviewed_by=args.reviewed_by, rationale=args.rationale.read_text(encoding="utf-8") if args.rationale else None)
    elif args.command == "declare-block":
        result = declare_block(root, args.session, json.loads(args.source.read_text(encoding="utf-8")))
    elif args.command == "answer-explanation":
        result = answer_explanation_request(root, args.session, args.request_id, args.heading)
    elif args.command == "wait":
        result = wait_for_activity(root, args.session, args.timeout, holder=args.holder, provider=args.provider, ttl=args.ttl)
    elif args.command == "context":
        import context_kernel as ck
        brief = session_context(root, args.session, args.project_root, args.learning_root, args.as_of, args.library_root,
                                target=ck.parse_target(args.target) if args.target else None)
        if args.bind:
            if brief["blocked"] or not brief["exists"]:
                raise SystemExit("Cannot bind: " + ("essential context is blocked" if brief["blocked"] else "the session does not exist yet"))
            bind_session_context(root, args.session, brief["receipt"])
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if not args.json:
            sys.stdout.write(render_context(brief))
        else:
            print(json.dumps(brief, ensure_ascii=False, indent=2))
        raise SystemExit(2 if brief["blocked"] else 0)
    elif args.command == "refresh-advice":
        import learning_advice
        result = learning_advice.refresh(root, args.session)
    elif args.command == "preferences":
        result = set_learning_preferences(root, args.session, json.loads(args.source.read_text(encoding="utf-8-sig")))
    elif args.command == "recover":
        result = recover_session(root, args.session, args.apply)
    elif args.command == "import":
        result = import_bridge(root, args.session, args.apply)
    else:
        result = migrate(root, args.apply, args.journal, args.resume, args.rollback)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if isinstance(result, dict) and "source_markdown" in result:
        # Write commands report what changed, not the whole session body.
        result = {"session": args.session, "updated_at": result.get("updated_at"), "questions": len(result["questions"]), "pending": pending_activity(result)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "validate" and result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
