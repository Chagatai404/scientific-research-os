"""Session plans: what a tutor decides before the learner sees anything, as plain JSON that any agent can write and the repository checks.

Standard library only (and ``board_script`` for the lecture steps). A plan holds

* a **probe**: a small tree of questions. Each question carries its own answer key and feedback, and says which question comes next for a right and a wrong
  answer, so the page can run it with no agent turn between questions. A free-response question is reviewed by the agent in the background and never blocks;
* **segments** of lecture, each a complete board script: the core path, repair segments chosen when the probe shows a gap, extension segments for a learner who
  shows mastery;
* **anticipated questions** with ready board answers;
* the **handout** (title, directory in the course or project library, sections) and a final **check**.

Branching is two-level: the page follows the tree and picks segments instantly; the agent revises the plan only at a stage boundary or for a question the plan
did not anticipate. Nothing here is evidence of learning: a branch taken is a pacing decision, and the diagnostic budget of ``TUTOR_PLANNING.md`` still counts
every question.

    python session_plan.py check plan.json                    exit 0 if valid, 1 and the problems if not
    python session_plan.py path plan.json q1=wrong q2=correct  the lecture segments that would play for those results
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

import board_script

SCHEMA = 1
ID = re.compile(r'[A-Za-z0-9_-]{1,64}')
CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
PLACEHOLDER = re.compile(r'\[[^\]\n]*\b[A-Za-z]{2,}\s+[A-Za-z]{2,}\b[^\]\n]*\]')   # an unfilled slot such as [Name the concept]; E[X^2] and [a, b) are maths
WORKFLOW_LABEL = re.compile(r'\b(block|rq|section|question|q)[ -]?\d+\b', re.I)   # a position or identifier is not a title
END = 'end'
KINDS = ('choice', 'numeric', 'short')
ROLES = ('core', 'repair', 'extension')
HANDOUT_STATES = ('planned', 'draft', 'built')
DEFAULT_BUDGET, MAX_BUDGET = 5, 8
MAX_QUESTIONS, MAX_SEGMENTS, MAX_ANTICIPATED, MAX_PROMPT, MAX_TEXT = 40, 40, 120, 2000, 1000
WORDS_PER_MINUTE = 150                                             # for the length estimate only

QUESTION_KEYS = {
    'choice': ('id', 'kind', 'prompt', 'options', 'on_correct', 'on_wrong', 'units', 'tests', 'assumes', 'introduces', 'solution', 'hint'),
    'numeric': ('id', 'kind', 'prompt', 'answer', 'feedback_wrong', 'on_correct', 'on_wrong', 'units', 'tests', 'assumes', 'introduces', 'solution', 'hint'),
    'short': ('id', 'kind', 'prompt', 'criteria', 'next', 'units', 'tests', 'assumes', 'introduces', 'solution', 'hint'),
}
OPTION_KEYS = ('id', 'text', 'correct', 'feedback', 'next')


def _text(value, limit: int = MAX_TEXT) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not CONTROL.search(value)


def _id(value) -> bool:
    return isinstance(value, str) and bool(ID.fullmatch(value))


def _learner_text(value, where: str, problems: list, limit: int = MAX_TEXT) -> None:
    if not _text(value, limit):
        problems.append(f'{where}: must be text of 1 to {limit} characters')
    elif PLACEHOLDER.search(value):
        problems.append(f'{where}: an unfilled template slot ("{PLACEHOLDER.search(value).group(0)}") is still in the text')


def _plain_title(value, where: str, problems: list) -> None:
    _learner_text(value, where, problems, 200)
    if isinstance(value, str) and WORKFLOW_LABEL.search(value):
        problems.append(f'{where}: a title says what is studied, not a position or identifier ("{WORKFLOW_LABEL.search(value).group(0)}")')


# ---------------------------------------------------------------------------------------------------- the question tree

def _check_question(q, where: str, ids: set, problems: list) -> None:
    if not isinstance(q, dict):
        problems.append(f'{where}: a question must be an object')
        return
    kind = q.get('kind')
    if kind not in KINDS:
        problems.append(f'{where}.kind: kind must be one of {", ".join(KINDS)}')
        return
    for key in q:
        if key not in QUESTION_KEYS[kind]:
            problems.append(f"{where}: unknown key '{key}' for a {kind} question")
    ident = q.get('id')
    if not _id(ident):
        problems.append(f'{where}.id: id must be 1 to 64 letters, digits, - or _')
    elif ident in ids:
        problems.append(f"{where}.id: duplicate id '{ident}'")
    else:
        ids.add(ident)
    _learner_text(q.get('prompt'), f'{where}.prompt', problems, MAX_PROMPT)
    for key in ('tests', 'solution'):
        if not _text(q.get(key), MAX_PROMPT):
            problems.append(f'{where}.{key}: required; {"what the question tests" if key == "tests" else "the reasoning, not only the key"}')
    for key in ('assumes', 'introduces', 'hint'):
        if key in q and not _text(q[key], MAX_PROMPT):
            problems.append(f'{where}.{key}: must be text')
    if 'units' in q and not (type(q['units']) is int and 1 <= q['units'] <= 4):
        problems.append(f'{where}.units: units must be a whole number from 1 to 4 (what the question counts against the diagnostic budget)')
    if kind == 'choice':
        options = q.get('options')
        if not isinstance(options, list) or not 2 <= len(options) <= 6:
            problems.append(f'{where}.options: a choice question has 2 to 6 options')
            return
        seen, correct = set(), 0
        for j, option in enumerate(options):
            at = f'{where}.options[{j}]'
            if not isinstance(option, dict):
                problems.append(f'{at}: an option must be an object')
                continue
            for key in option:
                if key not in OPTION_KEYS:
                    problems.append(f"{at}: unknown key '{key}'")
            if not _id(option.get('id')) or option['id'] in seen:
                problems.append(f'{at}.id: a unique id of letters, digits, - or _')
            else:
                seen.add(option['id'])
            _learner_text(option.get('text'), f'{at}.text', problems, 500)
            if option.get('correct') is True:
                correct += 1
            elif 'correct' in option and option['correct'] is not False:
                problems.append(f'{at}.correct: true or false')
            if option.get('correct') is not True and not _text(option.get('feedback'), MAX_PROMPT):
                problems.append(f'{at}.feedback: a wrong option needs feedback that names the mistake it stands for')
        if correct != 1:
            problems.append(f'{where}.options: exactly one option must be correct (found {correct})')
        texts = [o['text'].strip().lower() for o in options if isinstance(o, dict) and isinstance(o.get('text'), str)]
        if len(set(texts)) != len(texts):
            problems.append(f'{where}.options: two options have the same text')
    elif kind == 'numeric':
        answer = q.get('answer')
        if not (isinstance(answer, dict) and set(answer) <= {'value', 'tolerance'} and 'value' in answer):
            problems.append(f'{where}.answer: {{"value": number, "tolerance": number}}')
        else:
            for key in ('value', 'tolerance'):
                if key in answer and not (isinstance(answer[key], (int, float)) and not isinstance(answer[key], bool) and abs(answer[key]) < 1e12):
                    problems.append(f'{where}.answer.{key}: must be a number')
            if isinstance(answer.get('tolerance'), (int, float)) and answer['tolerance'] < 0:
                problems.append(f'{where}.answer.tolerance: must not be negative')
        if not _text(q.get('feedback_wrong'), MAX_PROMPT):
            problems.append(f'{where}.feedback_wrong: required; say what a wrong number usually means')
    else:
        criteria = q.get('criteria')
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 8 or not all(_text(c, 400) for c in criteria):
            problems.append(f'{where}.criteria: 1 to 8 criteria the agent will judge the answer against')


def _targets(q: dict) -> list:
    """Every question id (or ``end``) a question can lead to."""
    if q.get('kind') == 'short':
        return [q.get('next')]
    found = [q.get('on_correct'), q.get('on_wrong')]
    found += [o.get('next') for o in q.get('options', []) if isinstance(o, dict) and o.get('next') is not None]
    return found


def validate_tree(tree, where: str, budget: int, problems: list) -> dict:
    """Check one question tree (the probe or the final check) and return facts about it (little if the tree itself is unusable)."""
    if not isinstance(tree, dict):
        problems.append(f'{where}: must be an object with "start" and "questions"')
        return {}
    for key in tree:
        if key not in ('start', 'questions', 'budget'):
            problems.append(f"{where}: unknown key '{key}'")
    questions = tree.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        problems.append(f'{where}.questions: 1 to {MAX_QUESTIONS} questions')
        return {}
    ids: set = set()
    for i, q in enumerate(questions):
        _check_question(q, f'{where}.questions[{i}]', ids, problems)
    by_id = {q['id']: q for q in questions if isinstance(q, dict) and _id(q.get('id'))}
    start = tree.get('start')
    if start not in by_id:
        problems.append(f'{where}.start: must be the id of a question')
        return {'ids': set(by_id)}
    wrong_ref = False
    for qid, q in by_id.items():
        for target in _targets(q):
            if target != END and target not in by_id:
                problems.append(f"{where}: question '{qid}' leads to '{target}', which is not a question (use \"{END}\" to finish)")
                wrong_ref = True
            elif target == qid:
                problems.append(f"{where}: question '{qid}' leads to itself")
                wrong_ref = True
    if wrong_ref:
        return {'ids': set(by_id)}
    # reachability, cycles and the longest path (in budget units) over the question graph
    state, cycle, longest = {}, [], {}

    def walk(qid: str) -> int:
        if state.get(qid) == 'done':
            return longest[qid]
        if state.get(qid) == 'open':
            cycle.append(qid)
            return 0
        state[qid] = 'open'
        q = by_id[qid]
        onward = max([0 if t == END else walk(t) for t in _targets(q)] or [0])
        state[qid] = 'done'
        longest[qid] = (q.get('units') if type(q.get('units')) is int else 1) + onward
        return longest[qid]
    worst = walk(start)
    if cycle:
        problems.append(f"{where}: the questions loop back to '{cycle[0]}'; a probe moves forward")
        return {'ids': set(by_id)}
    for qid in by_id:
        if qid not in state:
            problems.append(f"{where}: question '{qid}' can never be reached from '{start}'")
    if worst > budget:
        problems.append(f'{where}: the longest path costs {worst} diagnostic units, over the budget of {budget}')
    return {'ids': set(by_id), 'worst_units': worst}


# ---------------------------------------------------------------------------------------------------- whole plans

MAX_VIDEO_SECONDS, MAX_VIDEO_START = 1800, 4 * 3600


def _check_video(video, where: str, problems: list) -> None:
    """A segment that plays a video someone else made instead of the tutor drawing the idea on the board. The plan names a registry record
    (``resources.py``) and the part to play; it never carries an address. Whether the record is vetted, and by someone other than the one who found it,
    is checked when the session starts (``RESOURCE_PROTOCOL.md``), not by this static check."""
    if not isinstance(video, dict):
        problems.append(f'{where}: must be an object')
        return
    for key in video:
        if key not in ('resource', 'start', 'end', 'notice'):
            problems.append(f"{where}: unknown key '{key}'")
    if not (isinstance(video.get('resource'), str) and re.fullmatch(r'RES-[A-Za-z0-9_-]{1,60}', video['resource'])):
        problems.append(f'{where}.resource: the id of a registry record (RES-…); the plan never holds an address')
    start, end = video.get('start'), video.get('end')
    numbers = all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in (start, end))
    if not numbers or not 0 <= start < end <= MAX_VIDEO_START + MAX_VIDEO_SECONDS or end - start > MAX_VIDEO_SECONDS:
        problems.append(f'{where}.start/end: seconds, start before end, a part of at most {MAX_VIDEO_SECONDS // 60} minutes (play the part that teaches, not the whole video)')
    _learner_text(video.get('notice'), f'{where}.notice', problems, 500)


def _safe_directory(value) -> bool:
    if not _text(value, 300) or '\\' in value or value.startswith(('/', '.')) or re.match(r'^[A-Za-z]:', value):
        return False
    return all(p and p != '..' and not p.startswith('.') for p in value.split('/'))


def validate(plan) -> list[str]:
    """Every problem found, each starting with where it is. An empty list means the plan is valid."""
    problems: list[str] = []
    if not isinstance(plan, dict):
        return ['a session plan must be an object']
    if plan.get('plan_schema') != SCHEMA:
        problems.append(f'plan_schema must be {SCHEMA}')
    for key in plan:
        if key not in ('plan_schema', 'title', 'target', 'budget', 'probe', 'segments', 'anticipated', 'handout', 'check'):
            problems.append(f"unknown key '{key}'")
    _plain_title(plan.get('title'), 'title', problems)
    if not _text(plan.get('target'), 300):
        problems.append('target: the concept or capability this session teaches')
    budget = plan.get('budget', DEFAULT_BUDGET)
    if not (type(budget) is int and 1 <= budget <= MAX_BUDGET):
        problems.append(f'budget: a whole number from 1 to {MAX_BUDGET} (default {DEFAULT_BUDGET})')
        budget = DEFAULT_BUDGET
    probe = validate_tree(plan.get('probe'), 'probe', budget, problems)
    check_tree = {}
    if 'check' in plan:
        check_budget = plan['check'].get('budget', DEFAULT_BUDGET) if isinstance(plan['check'], dict) else DEFAULT_BUDGET
        if not (type(check_budget) is int and 1 <= check_budget <= MAX_BUDGET):
            problems.append(f'check.budget: a whole number from 1 to {MAX_BUDGET}')
            check_budget = DEFAULT_BUDGET
        check_tree = validate_tree(plan['check'], 'check', check_budget, problems)
    if probe.get('ids') and check_tree.get('ids') and probe['ids'] & check_tree['ids']:
        problems.append(f"check: question ids repeat those of the probe ({', '.join(sorted(probe['ids'] & check_tree['ids']))})")

    segments = plan.get('segments')
    seg_ids, core_ids, lecture_steps = set(), [], []
    if not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        problems.append(f'segments: 1 to {MAX_SEGMENTS} lecture segments')
        segments = []
    for i, seg in enumerate(segments):
        where = f'segments[{i}]'
        if not isinstance(seg, dict):
            problems.append(f'{where}: a segment must be an object')
            continue
        for key in seg:
            if key not in ('id', 'role', 'title', 'plays_if', 'before', 'script', 'video', 'covers'):
                problems.append(f"{where}: unknown key '{key}'")
        if not _id(seg.get('id')):
            problems.append(f'{where}.id: id must be 1 to 64 letters, digits, - or _')
        elif seg['id'] in seg_ids:
            problems.append(f"{where}.id: duplicate id '{seg['id']}'")
        else:
            seg_ids.add(seg['id'])
        role = seg.get('role')
        if role not in ROLES:
            problems.append(f'{where}.role: role must be one of {", ".join(ROLES)}')
        _plain_title(seg.get('title'), f'{where}.title', problems)
        if 'covers' in seg and not (isinstance(seg['covers'], list) and all(_text(c, 200) for c in seg['covers'])):
            problems.append(f'{where}.covers: a list of the ideas this segment explains')
        if role == 'core':
            if 'plays_if' in seg:
                problems.append(f'{where}: a core segment always plays and has no plays_if')
            if _id(seg.get('id')):
                core_ids.append(seg['id'])
        elif role in ('repair', 'extension'):
            wanted = 'wrong' if role == 'repair' else 'correct'
            rule = seg.get('plays_if')
            if not (isinstance(rule, dict) and set(rule) == {wanted} and isinstance(rule[wanted], list) and rule[wanted]):
                problems.append(f'{where}.plays_if: {{"{wanted}": [question ids]}} — a {role} plays when {"any of" if role == "repair" else "all of"} these were answered {wanted}')
            else:
                for qid in rule[wanted]:
                    if qid not in (probe.get('ids') or set()):
                        problems.append(f"{where}.plays_if: '{qid}' is not a probe question")
        script, video = seg.get('script'), seg.get('video')
        if video is not None:
            _check_video(video, f'{where}.video', problems)
        if script is None and video is None:
            problems.append(f'{where}: a segment has a board script, a video, or both (the script plays first)')
        elif script is not None and not isinstance(script, dict):
            problems.append(f'{where}.script: a board script')
        elif script is not None:
            for issue in board_script.validate(script):
                problems.append(f'{where}.script: {issue}')
            steps = script.get('steps') if isinstance(script.get('steps'), list) else []
            if not any(isinstance(s, dict) and str(s.get('say', '')).strip() for s in steps):
                problems.append(f'{where}.script: a lecture segment must be spoken (no step has a sentence)')
            lecture_steps.extend(s for s in steps if isinstance(s, dict))
    if segments and not core_ids:
        problems.append('segments: at least one core segment')
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        if 'before' in seg:
            if seg.get('role') == 'core' or seg['before'] not in core_ids:
                problems.append("segments[%d].before: must name a core segment (and only a repair or extension has it)" % i)
        elif seg.get('role') == 'repair':
            problems.append(f'segments[{i}].before: a repair says which core segment it comes before')

    anticipated = plan.get('anticipated', [])
    if not isinstance(anticipated, list) or len(anticipated) > MAX_ANTICIPATED:
        problems.append(f'anticipated: a list of at most {MAX_ANTICIPATED} questions')
        anticipated = []
    for i, item in enumerate(anticipated):
        where = f'anticipated[{i}]'
        if not isinstance(item, dict):
            problems.append(f'{where}: must be an object')
            continue
        for key in item:
            if key not in ('segment', 'label', 'match', 'steps'):
                problems.append(f"{where}: unknown key '{key}'")
        if item.get('segment') not in seg_ids:
            problems.append(f'{where}.segment: must be a segment id')
        _learner_text(item.get('label'), f'{where}.label', problems, 60)
        match = item.get('match')
        if not (isinstance(match, list) and 1 <= len(match) <= 12 and all(isinstance(m, str) and m == m.lower() and 1 <= len(m.strip()) <= 40 for m in match)):
            problems.append(f'{where}.match: 1 to 12 lower-case words or phrases that identify the question')
        steps = item.get('steps')
        if isinstance(steps, list):
            for issue in board_script.validate({'board_schema': board_script.SCHEMA, 'steps': steps}):
                problems.append(f'{where}.steps: {issue}')
            lecture_steps.extend(s for s in steps if isinstance(s, dict))
        else:
            problems.append(f'{where}.steps: a list of board steps')
    # one board plays all of it: step and drawing ids must not collide across segments and answers
    if lecture_steps and not problems:
        for issue in board_script.validate({'board_schema': board_script.SCHEMA, 'steps': lecture_steps}):
            problems.append(f'the lecture as a whole: {issue}')

    handout = plan.get('handout')
    if handout is not None:
        if not isinstance(handout, dict):
            problems.append('handout: must be an object')
        else:
            for key in handout:
                if key not in ('title', 'directory', 'status', 'sections'):
                    problems.append(f"handout: unknown key '{key}'")
            _plain_title(handout.get('title'), 'handout.title', problems)
            if not _safe_directory(handout.get('directory')):
                problems.append('handout.directory: a folder inside the course or project library (relative, no .., no drive, nothing hidden)')
            if handout.get('status', 'planned') not in HANDOUT_STATES:
                problems.append(f'handout.status: one of {", ".join(HANDOUT_STATES)}')
            sections = handout.get('sections')
            if not (isinstance(sections, list) and 1 <= len(sections) <= 40):
                problems.append('handout.sections: 1 to 40 section headings')
            else:
                for j, s in enumerate(sections):
                    _plain_title(s, f'handout.sections[{j}]', problems)
    return problems


def check(plan) -> dict:
    problems = validate(plan)
    if problems:
        raise ValueError('invalid session plan: ' + '; '.join(problems[:8]))
    return plan


# ---------------------------------------------------------------------------------------------------- running a plan (the page does the same)

def judge(question: dict, answer) -> dict:
    """What the learner's answer means for one question: ``{"verdict": correct|wrong|pending, "feedback": text|None, "next": question id|"end"}``.

    A choice is judged by option id, a number by its tolerance; a free response is ``pending`` (the agent reviews it later) and goes straight on. This is a
    pacing decision made locally, not a grade: nothing here is evidence."""
    kind = question['kind']
    if kind == 'short':
        return {'verdict': 'pending', 'feedback': None, 'next': question['next']}
    if kind == 'choice':
        option = next((o for o in question['options'] if o['id'] == answer), None)
        if option is None:
            raise ValueError(f"'{answer}' is not an option of question '{question['id']}'")
        if option.get('correct') is True:
            return {'verdict': 'correct', 'feedback': None, 'next': question['on_correct']}
        return {'verdict': 'wrong', 'feedback': option['feedback'], 'next': option.get('next', question['on_wrong'])}
    if not isinstance(answer, (int, float)) or isinstance(answer, bool):
        raise ValueError('a numeric question is answered with a number')
    spec = question['answer']
    if abs(answer - spec['value']) <= spec.get('tolerance', 0):
        return {'verdict': 'correct', 'feedback': None, 'next': question['on_correct']}
    return {'verdict': 'wrong', 'feedback': question['feedback_wrong'], 'next': question['on_wrong']}


def lecture_path(plan: dict, results: dict) -> list[str]:
    """The segment ids that play, in order, for ``results`` (question id -> ``correct`` or ``wrong``; anything else, or a question not asked, triggers nothing).

    Core segments always play in the order written. A repair plays before the core segment it names when any question it lists was answered wrong; an
    extension plays when all its questions were answered correctly, before the core segment it names, or after the last one. Several of the same kind keep
    the order written."""
    before: dict[str, list[str]] = {}
    tail: list[str] = []
    for seg in plan['segments']:
        if seg['role'] == 'core':
            continue
        rule = seg['plays_if']
        plays = (any(results.get(q) == 'wrong' for q in rule['wrong']) if seg['role'] == 'repair'
                 else all(results.get(q) == 'correct' for q in rule['correct']))
        if plays:
            (before.setdefault(seg['before'], []) if 'before' in seg else tail).append(seg['id'])
    path: list[str] = []
    for seg in plan['segments']:
        if seg['role'] == 'core':
            path += before.get(seg['id'], []) + [seg['id']]
    return path + tail


def replay(plan: dict, name: str, events: list) -> dict:
    """Where the learner is in a question tree (``probe`` or ``check``), rebuilt from the saved ``plan-answer`` events alone: the questions answered in order
    with their verdicts, the question to answer now, and whether the tree is finished. The page does the same, so a reload shows the same place."""
    tree = plan.get(name)
    if not tree:
        return {'trail': [], 'current': None, 'done': True, 'results': {}}
    questions = {q['id']: q for q in tree['questions']}
    latest = {}
    for event in events:
        response = event.get('response')
        if event.get('type') == 'plan-answer' and isinstance(response, dict) and response.get('tree') == name:
            latest[event['question_id']] = event
    trail, results, seen, qid = [], {}, set(), tree['start']
    while qid != END:
        question = questions.get(qid)
        if question is None or qid in seen:
            break
        seen.add(qid)
        event = latest.get(qid)
        judged = None
        if event is not None:
            try:
                judged = judge(question, event['response']['answer'])
            except (ValueError, KeyError, TypeError):
                judged = None
        if judged is None:
            return {'trail': trail, 'current': qid, 'done': False, 'results': results}
        trail.append({'id': qid, 'answer': event['response']['answer'], 'verdict': judged['verdict'], 'feedback': judged['feedback'], 'next': judged['next']})
        results[qid] = judged['verdict']
        qid = judged['next']
    return {'trail': trail, 'current': None, 'done': True, 'results': results}


def stage_of(plan: dict, events: list) -> str:
    """The stage a session is in (``probe``, ``handout``, ``lecture``, ``check`` or ``done``), from the saved events, never from a timer."""
    if not replay(plan, 'probe', events)['done']:
        return 'probe'
    reached = {e['response'][6:] for e in events if e.get('type') == 'checkpoint' and isinstance(e.get('response'), str) and e['response'].startswith('stage:')}
    if 'lecture' not in reached:
        return 'handout'
    if 'check' not in reached:
        return 'lecture'
    if plan.get('check') and not replay(plan, 'check', events)['done']:
        return 'check'
    return 'done'


def summary(plan: dict) -> dict:
    """Facts for the agent: how long the lecture is, what the probe can cost."""
    words = {s['id']: sum(len(str(step.get('say', '')).split()) for step in (s.get('script') or {}).get('steps', [])) for s in plan['segments']}
    core = [s for s in plan['segments'] if s['role'] == 'core']
    video_seconds = sum(s['video']['end'] - s['video']['start'] for s in core if 'video' in s)
    worst = validate_tree(plan['probe'], 'probe', MAX_BUDGET, []).get('worst_units')
    return {'title': plan['title'], 'questions': len(plan['probe']['questions']), 'worst_case_probe_units': worst, 'budget': plan.get('budget', DEFAULT_BUDGET),
            'segments': {role: sum(s['role'] == role for s in plan['segments']) for role in ROLES},
            'video_segments': sum('video' in s for s in plan['segments']), 'core_minutes': round(sum(words[s['id']] for s in core) / WORDS_PER_MINUTE + video_seconds / 60, 1), 'anticipated': len(plan.get('anticipated', [])), 'handout': (plan.get('handout') or {}).get('status'),
            'check_questions': len((plan.get('check') or {}).get('questions', []))}


def warnings(plan: dict) -> list[str]:
    """Things worth a look that are not errors: a probe whose right answers all sit in the same place gives the position away."""
    found = []
    for name in ('probe', 'check'):
        tree = plan.get(name) or {}
        positions = [next(i for i, o in enumerate(q['options']) if o.get('correct') is True) for q in tree.get('questions', []) if q.get('kind') == 'choice']
        if len(positions) >= 3 and len(set(positions)) == 1:
            found.append(f'{name}: every multiple-choice question has its right answer in position {positions[0] + 1}; vary the order')
    if plan.get('handout') is None:
        found.append('no handout is planned')
    if not plan.get('anticipated'):
        found.append('no anticipated questions: every question the learner asks waits for an agent turn')
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check').add_argument('plan', type=Path)
    walk = sub.add_parser('path')
    walk.add_argument('plan', type=Path)
    walk.add_argument('results', nargs='*', help='question=correct|wrong')
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    problems = validate(plan)
    if problems:
        print('\n'.join(problems))
        return 1
    if args.command == 'check':
        print(json.dumps({'valid': True, **summary(plan), 'warnings': warnings(plan)}, indent=2, ensure_ascii=False))
        return 0
    results = dict(item.split('=', 1) for item in args.results if '=' in item)
    print('\n'.join(lecture_path(plan, results)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
