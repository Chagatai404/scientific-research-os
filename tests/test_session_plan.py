"""Session plans: the example is valid, every kind of mistake is named, and the branching a page will run is decided here first."""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import session_plan as sp

EXAMPLE = json.loads((ROOT / 'examples' / 'session-plan-variance.json').read_text(encoding='utf-8'))


def mutated(change):
    plan = copy.deepcopy(EXAMPLE)
    change(plan)
    return plan


def problems_of(change):
    return '\n'.join(sp.validate(mutated(change)))


def question(plan, qid, tree='probe'):
    return next(q for q in plan[tree]['questions'] if q['id'] == qid)


def segment(plan, sid):
    return next(s for s in plan['segments'] if s['id'] == sid)


class TheExample(unittest.TestCase):
    def test_the_worked_example_is_valid_and_has_no_warnings(self):
        self.assertEqual(sp.validate(EXAMPLE), [])
        self.assertEqual(sp.warnings(EXAMPLE), [])

    def test_the_summary_says_what_the_session_costs(self):
        s = sp.summary(EXAMPLE)
        self.assertEqual((s['questions'], s['worst_case_probe_units'], s['budget']), (3, 3, 5))
        self.assertEqual(s['segments'], {'core': 3, 'repair': 1, 'extension': 1})
        self.assertEqual(s['video_segments'], 1)
        self.assertGreater(s['core_minutes'], 3.0)           # the video part alone is 3 minutes

    def test_check_raises_with_the_first_problems(self):
        with self.assertRaisesRegex(ValueError, 'invalid session plan'):
            sp.check({'plan_schema': 2})
        self.assertIs(sp.check(EXAMPLE), EXAMPLE)


class Wording(unittest.TestCase):
    def test_unknown_keys_and_the_schema_are_refused(self):
        self.assertIn("unknown key 'extra'", problems_of(lambda p: p.update(extra=1)))
        self.assertIn('plan_schema must be 1', problems_of(lambda p: p.update(plan_schema=2)))
        self.assertIn('a session plan must be an object', '\n'.join(sp.validate([])))

    def test_titles_name_the_topic_not_a_position_or_an_unfilled_slot(self):
        self.assertIn('not a position or identifier', problems_of(lambda p: p.update(title='Block 9 - Content 3')))
        self.assertIn('unfilled template slot', problems_of(lambda p: p.update(title='[Name the concept this part teaches]')))
        self.assertIn('not a position', problems_of(lambda p: segment(p, 'spread').update(title='Q3 recap')))

    def test_mathematics_in_a_prompt_is_not_mistaken_for_a_template_slot(self):
        def maths(p):
            question(p, 'twopoint')['prompt'] = 'Find E[X^2] - (E[X])^2 and E[(X - mu)^2] for X on [a, b).'
        self.assertEqual(sp.validate(mutated(maths)), [])


class Questions(unittest.TestCase):
    def test_a_choice_needs_exactly_one_right_option_and_feedback_on_the_wrong_ones(self):
        self.assertIn('exactly one option must be correct (found 0)', problems_of(lambda p: [o.pop('correct', None) for o in question(p, 'scale')['options']]))
        self.assertIn('exactly one option must be correct (found 2)', problems_of(lambda p: question(p, 'scale')['options'][0].update(correct=True)))
        self.assertIn('options[0].feedback', problems_of(lambda p: question(p, 'scale')['options'][0].pop('feedback')))
        self.assertIn('same text', problems_of(lambda p: question(p, 'scale')['options'][2].update(text='12')))

    def test_every_question_needs_what_it_tests_and_a_solution_that_explains(self):
        self.assertIn('tests: required', problems_of(lambda p: question(p, 'why').pop('tests')))
        self.assertIn('solution: required', problems_of(lambda p: question(p, 'why').pop('solution')))

    def test_numeric_and_short_questions_carry_their_own_keys(self):
        self.assertIn('answer:', problems_of(lambda p: question(p, 'twopoint').pop('answer')))
        self.assertIn('tolerance: must not be negative', problems_of(lambda p: question(p, 'twopoint')['answer'].update(tolerance=-1)))
        self.assertIn('feedback_wrong', problems_of(lambda p: question(p, 'twopoint').pop('feedback_wrong')))
        self.assertIn('criteria', problems_of(lambda p: question(p, 'why').update(criteria=[])))
        self.assertIn("unknown key 'options' for a short question", problems_of(lambda p: question(p, 'why').update(options=[])))
        self.assertIn('units must be a whole number', problems_of(lambda p: question(p, 'scale').update(units=0)))


class TheTree(unittest.TestCase):
    def test_a_target_that_is_not_a_question_is_named(self):
        self.assertIn("leads to 'nowhere'", problems_of(lambda p: question(p, 'scale').update(on_wrong='nowhere')))

    def test_loops_and_unreachable_questions_are_refused(self):
        self.assertIn('leads to itself', problems_of(lambda p: question(p, 'scale').update(on_correct='scale')))
        self.assertIn('loop back', problems_of(lambda p: question(p, 'why').update(next='scale')))
        self.assertIn("can never be reached", problems_of(lambda p: question(p, 'scale').update(on_correct='why', on_wrong='why')))

    def test_the_longest_path_must_fit_the_diagnostic_budget(self):
        self.assertIn('over the budget of 2', problems_of(lambda p: p.update(budget=2)))
        self.assertNotIn('over the budget', problems_of(lambda p: p.update(budget=3)))
        self.assertIn('budget:', problems_of(lambda p: p.update(budget=9)))

    def test_a_distractor_that_routes_elsewhere_counts_on_its_own_path(self):
        def branch(p):
            question(p, 'scale')['options'][0]['next'] = 'why'      # the 12-answer skips the numeric question
            question(p, 'twopoint')['units'] = 4
        plan = mutated(branch)
        self.assertEqual(sp.validate(plan), ['probe: the longest path costs 6 diagnostic units, over the budget of 5'])
        self.assertEqual(sp.judge(question(plan, 'scale'), 'a')['next'], 'why')
        self.assertEqual(sp.judge(question(plan, 'scale'), 'c')['next'], 'twopoint')

    def test_the_check_is_its_own_tree_and_may_not_reuse_probe_ids(self):
        def reuse(p):
            question(p, 'again', 'check').update(id='scale')
            p['check']['start'] = 'scale'
        self.assertIn('repeat those of the probe', problems_of(reuse))


class Judging(unittest.TestCase):
    def test_a_choice_is_judged_by_option_with_the_feedback_of_that_option(self):
        q = question(EXAMPLE, 'scale')
        self.assertEqual(sp.judge(q, 'b'), {'verdict': 'correct', 'feedback': None, 'next': 'twopoint'})
        wrong = sp.judge(q, 'c')
        self.assertEqual(wrong['verdict'], 'wrong')
        self.assertIn('Adding 5 slides every value', wrong['feedback'])
        with self.assertRaises(ValueError):
            sp.judge(q, 'z')

    def test_a_number_is_judged_by_its_tolerance(self):
        q = question(EXAMPLE, 'twopoint')
        self.assertEqual(sp.judge(q, 1.0004)['verdict'], 'correct')
        self.assertEqual(sp.judge(q, 2)['verdict'], 'wrong')
        self.assertIn('E[X^2]', sp.judge(q, 2)['feedback'])
        with self.assertRaises(ValueError):
            sp.judge(q, '1')
        with self.assertRaises(ValueError):
            sp.judge(q, True)

    def test_a_free_response_never_blocks_and_waits_for_the_agent(self):
        self.assertEqual(sp.judge(question(EXAMPLE, 'why'), 'any words'), {'verdict': 'pending', 'feedback': None, 'next': 'end'})


class Segments(unittest.TestCase):
    def test_a_wrong_answer_inserts_the_repair_before_the_segment_it_names(self):
        self.assertEqual(sp.lecture_path(EXAMPLE, {'scale': 'wrong', 'twopoint': 'correct'}), ['spread', 'scale-repair', 'scale', 'see-it'])

    def test_mastery_adds_the_extension_at_the_end_and_nothing_else(self):
        self.assertEqual(sp.lecture_path(EXAMPLE, {'scale': 'correct', 'twopoint': 'correct'}), ['spread', 'scale', 'see-it', 'moment-form'])
        self.assertEqual(sp.lecture_path(EXAMPLE, {'scale': 'correct', 'twopoint': 'wrong'}), ['spread', 'scale', 'see-it'])

    def test_a_question_not_asked_or_not_yet_judged_triggers_nothing(self):
        self.assertEqual(sp.lecture_path(EXAMPLE, {}), ['spread', 'scale', 'see-it'])
        self.assertEqual(sp.lecture_path(EXAMPLE, {'scale': 'pending', 'twopoint': 'pending'}), ['spread', 'scale', 'see-it'])

    def test_roles_and_conditions_must_agree(self):
        self.assertIn('plays_if', problems_of(lambda p: segment(p, 'scale-repair').pop('plays_if')))
        self.assertIn("'zzz' is not a probe question", problems_of(lambda p: segment(p, 'scale-repair')['plays_if'].update(wrong=['zzz'])))
        self.assertIn('a repair plays when any of these were answered wrong', problems_of(lambda p: segment(p, 'scale-repair').update(plays_if={'correct': ['scale']})))
        self.assertIn('core segment always plays', problems_of(lambda p: segment(p, 'spread').update(plays_if={'wrong': ['scale']})))
        self.assertIn('a repair says which core segment', problems_of(lambda p: segment(p, 'scale-repair').pop('before')))
        self.assertIn('must name a core segment', problems_of(lambda p: segment(p, 'scale-repair').update(before='moment-form')))
        self.assertIn('at least one core segment', problems_of(lambda p: [s.update(role='extension', plays_if={'correct': ['scale']}) for s in p['segments'] if s['role'] == 'core']))

    def test_a_segment_has_a_script_a_video_or_both_and_a_script_must_be_spoken(self):
        self.assertIn('a board script, a video, or both', problems_of(lambda p: segment(p, 'see-it').pop('video')))
        silent = lambda p: segment(p, 'spread').update(script={'board_schema': 1, 'steps': [{'id': 'x', 'do': [{'op': 'write', 'text': 'hi', 'at': [1, 1]}]}]})   # noqa: E731
        self.assertIn('must be spoken', problems_of(silent))
        self.assertIn('board_schema', problems_of(lambda p: segment(p, 'spread')['script'].pop('board_schema')))

    def test_the_whole_lecture_is_one_board_so_ids_may_not_repeat_across_segments(self):
        self.assertIn('the lecture as a whole', problems_of(lambda p: segment(p, 'scale')['script']['steps'][0].update(id='sp1')))
        self.assertIn('the lecture as a whole', problems_of(lambda p: p['anticipated'][0]['steps'][0].update(id='sc1')))


class Videos(unittest.TestCase):
    def test_a_video_is_a_registry_record_and_a_part_to_play_never_an_address(self):
        self.assertIn('registry record', problems_of(lambda p: segment(p, 'see-it')['video'].update(resource='https://youtu.be/abc')))
        self.assertIn('registry record', problems_of(lambda p: segment(p, 'see-it')['video'].update(resource='abc')))
        self.assertIn("unknown key 'url'", problems_of(lambda p: segment(p, 'see-it')['video'].update(url='https://youtu.be/abc')))

    def test_only_the_part_that_teaches_is_played(self):
        self.assertIn('start/end', problems_of(lambda p: segment(p, 'see-it')['video'].update(start=100, end=100)))
        self.assertIn('start/end', problems_of(lambda p: segment(p, 'see-it')['video'].update(start=0, end=1801)))
        self.assertIn('start/end', problems_of(lambda p: segment(p, 'see-it')['video'].update(start=-1)))
        self.assertIn('start/end', problems_of(lambda p: segment(p, 'see-it')['video'].update(start='0')))
        self.assertEqual(sp.validate(mutated(lambda p: segment(p, 'see-it')['video'].update(start=0, end=1800))), [])

    def test_a_video_says_what_to_notice(self):
        self.assertIn('notice', problems_of(lambda p: segment(p, 'see-it')['video'].pop('notice')))

    def test_a_segment_may_introduce_its_video_with_a_board_script(self):
        def both(p):
            segment(p, 'see-it')['script'] = {'board_schema': 1, 'steps': [{'id': 'v1', 'say': 'Watch this next.', 'do': []}]}
        self.assertEqual(sp.validate(mutated(both)), [])


class AnticipatedAndHandout(unittest.TestCase):
    def test_an_anticipated_question_belongs_to_a_segment_and_is_matched_by_lower_case_words(self):
        self.assertIn('segment: must be a segment id', problems_of(lambda p: p['anticipated'][0].update(segment='nope')))
        self.assertIn('lower-case', problems_of(lambda p: p['anticipated'][0].update(match=['Why'])))
        self.assertIn('label', problems_of(lambda p: p['anticipated'][0].update(label='x' * 61)))

    def test_the_handout_folder_stays_inside_the_library(self):
        for bad in ('../escape', '/abs/path', 'C:/x', '.hidden/x', 'a\\b', 'a//b', ''):
            self.assertIn('handout.directory', problems_of(lambda p, d=bad: p['handout'].update(directory=d)), bad)
        self.assertEqual(sp.validate(mutated(lambda p: p['handout'].update(directory='Course/Handouts/2026-10-18 variance'))), [])
        self.assertIn('handout.status', problems_of(lambda p: p['handout'].update(status='done')))
        self.assertIn('sections[0]', problems_of(lambda p: p['handout'].update(sections=['Section 1'])))

    def test_a_probe_whose_right_answers_sit_in_one_place_is_warned_about(self):
        def same(p):
            question(p, 'why')['next'] = 'a1'
            for qid, onward in (('a1', 'a2'), ('a2', 'end')):
                extra = copy.deepcopy(question(p, 'scale'))
                extra['id'] = qid
                extra['options'][0]['text'] = 'one' if qid == 'a1' else 'two'
                extra['on_correct'] = extra['on_wrong'] = onward
                p['probe']['questions'].append(extra)
            p['budget'] = 8
        plan = mutated(same)
        self.assertEqual(sp.validate(plan), [])
        self.assertTrue(any('position 2' in w for w in sp.warnings(plan)), sp.warnings(plan))


CASES = json.loads((ROOT / 'tests' / 'fixtures' / 'plan-cases.json').read_text(encoding='utf-8'))


def events_of(items):
    return [({'event_id': f'e{i}', 'type': 'checkpoint', 'question_id': None, 'response': item} if isinstance(item, str)
             else {'event_id': f'e{i}', 'type': 'plan-answer', 'question_id': item[0], 'response': {'answer': item[1], 'verdict': 'pending', 'tree': item[2]}})
            for i, item in enumerate(items)]


class SharedWithThePage(unittest.TestCase):
    """tests/stages-unit.js runs these same cases against assets/html-runtime/stages.js."""

    def test_judging(self):
        questions = {q['id']: q for tree in ('probe', 'check') for q in EXAMPLE[tree]['questions']}
        for case in CASES['judge']:
            with self.subTest(case['name']):
                if case.get('error'):
                    with self.assertRaises(ValueError):
                        sp.judge(questions[case['question']], case['answer'])
                    continue
                got = sp.judge(questions[case['question']], case['answer'])
                self.assertEqual((got['verdict'], got['next']), (case['expect']['verdict'], case['expect']['next']))
                if 'feedback_contains' in case['expect']:
                    self.assertIn(case['expect']['feedback_contains'], got['feedback'])

    def test_the_lecture_path(self):
        for case in CASES['paths']:
            with self.subTest(case['name']):
                self.assertEqual(sp.lecture_path(EXAMPLE, case['results']), case['expect'])

    def test_where_the_learner_is(self):
        for case in CASES['replay']:
            with self.subTest(case['name']):
                got = sp.replay(EXAMPLE, case['tree'], events_of(case['events']))
                self.assertEqual([f"{t['id']}:{t['verdict']}" for t in got['trail']], case['expect']['trail'])
                self.assertEqual((got['current'], got['done']), (case['expect']['current'], case['expect']['done']))

    def test_which_stage(self):
        for case in CASES['stages']:
            with self.subTest(case['name']):
                self.assertEqual(sp.stage_of(EXAMPLE, events_of(case['events'])), case['expect'])


class InASession(unittest.TestCase):
    """A plan lives in the session state; the page's answers are recorded as plan-answer events and nothing else about them is trusted."""

    def setUp(self):
        import html_sessions as hs
        self.hs = hs
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'Sessions').mkdir()
        hs.install_runtime(self.root)
        hs.create_session(self.root, 'Sessions/P.md', '# Variance\n\nText.\n', title='Variance')
        hs.update_session(self.root, 'Sessions/P.md', plan=EXAMPLE)

    def event(self, **fields):
        base = {'type': 'plan-answer', 'question_id': 'scale', 'response': {'answer': 'b', 'verdict': 'correct', 'tree': 'probe'}}
        return self.hs.append_event(self.root, 'Sessions/P.md', {**base, **fields})

    def test_a_plan_answer_is_saved_and_is_not_pending_work_or_evidence(self):
        state = self.event()
        self.assertEqual(state['events'][-1]['status'], 'pending-review')
        self.assertEqual(self.hs.pending_activity(self.hs.load_session(self.root, 'Sessions/P.md')), [])

    def test_an_invalid_plan_is_refused_and_the_old_one_is_kept(self):
        broken = copy.deepcopy(EXAMPLE)
        broken['probe']['start'] = 'nowhere'
        with self.assertRaises(ValueError):
            self.hs.update_session(self.root, 'Sessions/P.md', plan=broken)
        self.assertEqual(self.hs.load_session(self.root, 'Sessions/P.md')['plan']['probe']['start'], 'scale')

    def test_plan_answers_must_name_a_plan_question_and_a_known_shape(self):
        for bad in ({'question_id': 'nope'}, {'response': {'answer': 'b', 'verdict': 'great', 'tree': 'probe'}}, {'response': {'answer': 'b', 'verdict': 'correct', 'tree': 'elsewhere'}},
                    {'response': {'answer': 'b', 'verdict': 'correct', 'tree': 'probe', 'mastery': True}}, {'response': 'b'}, {'response': {'answer': True, 'verdict': 'correct', 'tree': 'probe'}}):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    self.event(**bad)

    def test_a_plan_answer_cannot_award_anything(self):
        with self.assertRaises(ValueError):
            self.event(mastery=True)

    def test_a_plan_cannot_drop_a_question_that_already_has_an_answer(self):
        self.event()
        smaller = copy.deepcopy(EXAMPLE)
        smaller['probe']['questions'] = [q for q in smaller['probe']['questions'] if q['id'] != 'scale']
        smaller['probe']['start'] = 'twopoint'
        for segment in smaller['segments']:
            if segment.get('plays_if'):
                segment['plays_if'] = {'wrong': ['twopoint']} if segment['role'] == 'repair' else {'correct': ['twopoint']}
        with self.assertRaises(ValueError):
            self.hs.update_session(self.root, 'Sessions/P.md', plan=smaller)

    def test_the_plan_command_sets_the_plan(self):
        import subprocess
        source = self.root / 'plan.json'
        source.write_text(json.dumps({**EXAMPLE, 'title': 'Variance, revised'}), encoding='utf-8')
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.root), 'plan', 'Sessions/P.md', '--source', str(source)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.hs.load_session(self.root, 'Sessions/P.md')['plan']['title'], 'Variance, revised')


class Command(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/session_plan.py'), *args], capture_output=True, text=True, encoding='utf-8')

    def test_check_and_path_report_through_exit_codes(self):
        example = str(ROOT / 'examples' / 'session-plan-variance.json')
        done = self.run_cli('check', example)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)['valid'])
        done = self.run_cli('path', example, 'scale=wrong')
        self.assertEqual(done.stdout.split(), ['spread', 'scale-repair', 'scale', 'see-it'])
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.json'
            bad.write_text(json.dumps({'plan_schema': 1}), encoding='utf-8')
            done = self.run_cli('check', str(bad))
            self.assertEqual(done.returncode, 1)
            self.assertIn('probe', done.stdout)
            self.assertEqual(self.run_cli('check', str(Path(tmp) / 'missing.json')).returncode, 2)


def with_why_repair(plan):
    """The worked example plus a repair that plays when the written answer ('why') was wrong, so a tutor's verdict on it can change the lecture."""
    repair = json.loads(json.dumps(segment(plan, 'scale-repair')).replace('"rp', '"wr'))
    repair.update(id='why-repair', title='What a variance is made of', plays_if={'wrong': ['why']})
    plan['segments'].append(repair)
    segment(plan, 'moment-form')['plays_if']['correct'] = ['scale', 'twopoint', 'why']      # the extension now needs the written answer to be right too
    return plan


class WrittenAnswers(unittest.TestCase):
    """A written answer never blocks the learner, but the agent must see it: it is pending work until a plan review covers it, the review is pending tutor
    feedback (never evidence), and it can still change a lecture that has not started."""

    def setUp(self):
        import html_sessions as hs
        self.hs = hs
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'Sessions').mkdir()
        hs.install_runtime(self.root)
        hs.create_session(self.root, 'Sessions/P.md', '# Variance\n\nText.\n', title='Variance')
        hs.update_session(self.root, 'Sessions/P.md', plan=mutated(with_why_repair))

    def load(self):
        return self.hs.load_session(self.root, 'Sessions/P.md')

    def answer(self, question_id, answer, verdict, tree='probe'):
        return self.hs.append_event(self.root, 'Sessions/P.md', {'type': 'plan-answer', 'question_id': question_id, 'response': {'answer': answer, 'verdict': verdict, 'tree': tree}})

    def mark(self, text):
        return self.hs.append_event(self.root, 'Sessions/P.md', {'type': 'checkpoint', 'question_id': None, 'response': text})

    def written(self, text='because a square is never negative'):
        self.answer('scale', 'b', 'correct')
        self.answer('twopoint', 1, 'correct')
        return self.answer('why', text, 'pending')['events'][-1]['event_id']

    def review(self, verdict='correct', feedback='Good.', **options):
        return self.hs.review_plan_answer(self.root, 'Sessions/P.md', 'why', verdict, feedback, **options)

    def test_a_written_answer_is_pending_work_the_agent_is_handed_with_its_prompt_and_criteria(self):
        event_id = self.written()
        items = self.hs.pending_activity(self.load())
        self.assertEqual([i['kind'] for i in items], ['plan-answer'])
        self.assertEqual((items[0]['question_id'], items[0]['event_id'], items[0]['response'], items[0]['tree']), ('why', event_id, 'because a square is never negative', 'probe'))
        self.assertIn('never be negative', items[0]['prompt'])
        self.assertEqual(len(items[0]['criteria']), 2)
        waited = self.hs.wait_for_activity(self.root, 'Sessions/P.md', timeout=0)
        self.assertEqual([i['event_id'] for i in waited['pending']], [event_id])
        import supervision
        self.assertEqual(supervision.view(self.load(), None)['pending'], 1)
        with self.assertRaisesRegex(supervision.SupervisionError, 'await the tutor'):
            supervision.record_status(self.root, 'Sessions/P.md', 'completed')

    def test_answers_judged_on_the_page_are_not_pending_work(self):
        self.answer('scale', 'b', 'correct')
        self.answer('twopoint', 7, 'wrong')
        self.assertEqual(self.hs.pending_activity(self.load()), [])

    def test_the_wait_lease_names_the_written_answer_it_is_reviewing(self):
        import supervision
        event_id = self.written()
        self.hs.wait_for_activity(self.root, 'Sessions/P.md', timeout=0, holder='tutor-a')
        lease, _ = supervision.read_lease(self.root, 'Sessions/P.md')
        self.assertEqual((lease['mode'], lease['reviewing']), ('reviewing', [event_id]))

    def test_the_resume_brief_asks_for_a_plan_review(self):
        self.written()
        text = self.hs.render_context({'title': 'T', 'session': 'S', 'type': 'tutor-session', 'lifecycle': 'active', 'updated_at': 'x', 'receipt': None,
                                       'pending': self.hs.pending_activity(self.load()), 'questions': [], 'project': None, 'research': None, 'knowledge': None, 'notes': []})
        self.assertIn('plan-review', text)
        self.assertIn('plan question `why`', text)

    def test_a_plan_review_covers_the_answer_and_never_touches_it_or_awards_anything(self):
        event_id = self.written()
        before = copy.deepcopy(self.load()['events'])
        done = self.review('partially-correct', 'You have the square; say why an average of squares cannot be negative.', reviewed_by='tutor-a', criteria_met=[False, True])
        state = self.load()
        self.assertEqual(state['events'], before)                              # the learner's answer is exactly as it was
        review = state['plan_reviews'][0]
        self.assertEqual((review['question_id'], review['response_event_id'], review['verdict'], review['reviewed_by'], review['criteria_met']), ('why', event_id, 'partially-correct', 'tutor-a', [False, True]))
        self.assertFalse({'mastery', 'credit', 'retained', 'evidence'} & set(review))
        self.assertEqual(self.hs.pending_activity(state), [])
        self.assertEqual(done['pending'], [])
        self.assertEqual(done['stage'], 'handout')

    def test_a_review_is_only_for_a_written_answer_that_exists(self):
        with self.assertRaisesRegex(ValueError, 'No learner answer'):
            self.review()
        self.answer('scale', 'b', 'correct')
        with self.assertRaisesRegex(ValueError, 'judged on the page'):
            self.hs.review_plan_answer(self.root, 'Sessions/P.md', 'scale', 'correct')
        with self.assertRaisesRegex(ValueError, 'Unknown plan question'):
            self.hs.review_plan_answer(self.root, 'Sessions/P.md', 'nowhere', 'correct')
        self.written()
        with self.assertRaisesRegex(ValueError, 'declares 2 criteria'):
            self.review(criteria_met=[True])
        with self.assertRaisesRegex(ValueError, 'Verdict must be'):
            self.review('great')

    def test_reviews_are_append_only_and_cannot_be_set_directly(self):
        self.written()
        self.review('incorrect', 'First reading.')
        self.review('correct', 'On a second look this is right.')
        self.assertEqual([r['verdict'] for r in self.load()['plan_reviews']], ['incorrect', 'correct'])
        self.review('correct', 'On a second look this is right.')            # the same review again adds nothing
        self.assertEqual(len(self.load()['plan_reviews']), 2)
        with self.assertRaisesRegex(ValueError, 'Unsupported session update fields'):
            self.hs.update_session(self.root, 'Sessions/P.md', plan_reviews=[])

    def test_a_forged_review_is_refused_by_the_state_check(self):
        event_id = self.written()
        good = {'question_id': 'why', 'response_event_id': event_id, 'verdict': 'correct', 'feedback': 'ok', 'reviewed_at': '2026-10-18T10:00:00+00:00'}
        state = self.load()
        self.hs.validate_state(dict(state, plan_reviews=[good]))
        for bad in ({'response_event_id': 'nope'}, {'question_id': 'scale'}, {'question_id': 'nowhere'}, {'verdict': 'mastered'}, {'mastery': 1}, {'credit': True},
                    {'criteria_met': [True]}, {'reviewed_at': 'yesterday'}):
            with self.subTest(bad), self.assertRaises(ValueError):
                self.hs.validate_state(dict(state, plan_reviews=[dict(good, **bad)]))

    def test_a_verdict_changes_a_lecture_that_has_not_started_and_cannot_change_one_that_has(self):
        self.written()
        before = self.hs.plan_lecture(self.load())
        self.assertNotIn('why-repair', before['path'])
        self.assertNotIn('moment-form', before['path'])                       # a written answer awaiting review satisfies no extension
        done = self.review('incorrect', 'A variance is a mean of squares; start there.')
        self.assertEqual(done['lecture_path_before'], before['path'])
        self.assertIn('why-repair', done['lecture_path'])
        self.assertLess(done['lecture_path'].index('why-repair'), done['lecture_path'].index('scale'))     # the repair plays before the core segment it names
        self.assertFalse(done['lecture_started'])
        self.review('correct', 'Yes, on a second look.')
        path = self.hs.plan_lecture(self.load())['path']
        self.assertNotIn('why-repair', path)
        self.assertIn('moment-form', path)                                     # every question is now right, so the extension plays
        # once the lecture has started its path is the one it started with
        self.mark('stage:lecture')
        self.mark('lecture-path:spread,scale,see-it')
        self.mark('lecture-step:sp2')
        later = self.review('incorrect', 'Actually, no.')
        self.assertTrue(later['lecture_started'])
        self.assertEqual(later['lecture_path'], ['spread', 'scale', 'see-it'])
        self.assertEqual(later['stage'], 'lecture')

    def test_a_revised_plan_replaces_the_plan_in_the_same_save(self):
        self.written()
        revised = mutated(with_why_repair)
        question(revised, 'twopoint')['prompt'] = 'Reworded: what is the variance of two values 1 and 3?'
        revised['title'] = 'Variance, second try'
        done = self.review('partially-correct', 'Half of it.', revised_plan=revised)
        state = self.load()
        self.assertEqual((state['plan']['title'], len(state['plan_reviews']), done['plan_revised']), ('Variance, second try', 1, True))
        self.assertIn('Reworded', question(state['plan'], 'twopoint')['prompt'])

    def test_a_revision_that_would_move_the_learner_is_refused_and_the_review_with_it(self):
        self.written()
        moved = mutated(with_why_repair)
        scale = question(moved, 'scale')
        right = next(o for o in scale['options'] if o.get('correct'))
        wrong = next(o for o in scale['options'] if not o.get('correct'))
        right.pop('correct'); right['feedback'] = 'No.'
        wrong['correct'] = True; wrong.pop('feedback', None)
        self.assertEqual(sp.validate(moved), [])                               # a valid plan, only one that would re-judge an answer already given
        with self.assertRaisesRegex(ValueError, 'would move the learner; nothing was saved'):
            self.review('incorrect', 'x', revised_plan=moved)
        self.assertNotIn('plan_reviews', self.load())                          # nothing was saved
        self.assertEqual(question(self.load()['plan'], 'scale')['options'], question(mutated(with_why_repair), 'scale')['options'])
        done = self.review('incorrect', 'x', revised_plan=moved, allow_reroute=True)       # a deliberate decision
        self.assertTrue(done['plan_revised'])

    def test_a_revision_may_not_drop_a_segment_the_lecture_started_with(self):
        self.written()
        self.mark('stage:lecture')
        self.mark('lecture-path:spread,scale,moment-form,see-it')
        smaller = mutated(with_why_repair)
        smaller['segments'] = [s for s in smaller['segments'] if s['id'] != 'moment-form']
        self.assertEqual(sp.validate(smaller), [])
        problems = self.hs.plan_revision_problems(self.load()['plan'], smaller, self.load()['events'])
        self.assertEqual(len(problems), 1)
        self.assertIn('moment-form', problems[0])
        with self.assertRaisesRegex(ValueError, 'moment-form'):
            self.review('correct', 'x', revised_plan=smaller)

    def test_a_revision_may_not_send_a_finished_tree_on_to_new_questions(self):
        self.written()
        longer = mutated(with_why_repair)
        question(longer, 'why')['next'] = 'extra'
        longer['probe']['questions'].append(dict(question(longer, 'twopoint'), id='extra', on_correct='end', on_wrong='end', prompt='One more number: the variance of 2 and 4?'))
        self.assertEqual(sp.validate(longer), [])
        problems = self.hs.plan_revision_problems(self.load()['plan'], longer, self.load()['events'])
        self.assertTrue(any('somewhere else' in p for p in problems), problems)

    def test_the_lecture_checkpoints_are_ordinary_checkpoints(self):
        self.mark('lecture-path:spread,scale')
        self.mark('lecture-step:sc1')
        events = self.load()['events']
        self.assertEqual(self.hs.recorded_lecture_path(events), ['spread', 'scale'])
        self.assertIsNone(self.hs.recorded_lecture_path([]))

    def test_the_review_effects_are_the_ones_the_page_applies(self):
        cases = json.loads((ROOT / 'tests' / 'fixtures' / 'supervision-cases.json').read_text(encoding='utf-8'))['review_effects']['cases']
        for case in cases:
            with self.subTest(case['id']):
                self.assertEqual(self.hs.reviewed_results(case['results'], case['reviews']), case['expect'])

    def test_the_staged_lecture_reports_its_position_under_a_reserved_id(self):
        position = self.root / 'Sessions' / 'P.board-position.json'
        position.write_text(json.dumps({'schema': 1, 'boards': {'plan-lecture': {'step': 'sc2', 'index': 4, 'count': 9, 'status': 'playing', 'at': 1.0}}}), encoding='utf-8')
        reported = self.hs.board_position(self.root, 'Sessions/P.md', now=11.0)['plan-lecture']
        self.assertEqual((reported['step'], reported['segment'], reported['status'], reported['age_seconds']), ('sc2', 'scale', 'playing', 10.0))
        state = self.load()
        with self.assertRaisesRegex(ValueError, 'reserved'):
            self.hs.validate_state(dict(state, widgets=[{'id': 'plan-lecture', 'kind': 'board', 'script': {'board_schema': 1, 'steps': [{'id': 'a', 'say': 'Hello there.'}]}}]))

    def test_the_command_records_a_review_and_prints_what_the_lecture_does_now(self):
        self.written()
        feedback = self.root / 'feedback.txt'
        feedback.write_text('A variance is a mean of squares; start there.', encoding='utf-8')
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/html_sessions.py'), '--root', str(self.root), 'plan-review', 'Sessions/P.md', 'why', '--verdict', 'incorrect',
                               '--feedback', str(feedback), '--reviewed-by', 'tutor-a'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual((printed['verdict'], printed['pending'], printed['lecture_started']), ('incorrect', [], False))
        self.assertIn('why-repair', printed['lecture_path'])
        self.assertEqual(self.load()['plan_reviews'][0]['feedback'], 'A variance is a mean of squares; start there.')


if __name__ == '__main__':
    unittest.main()
