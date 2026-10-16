"""Teaching Card, word strip, mechanical teaching lint and layered lecture notes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import html_sessions as hs
import teaching_lint as tl
from test_tutor_gate import Base

SOURCE = '''# Waiting for events

## One event

Waiting for one event takes an average time. We call the rate the intensity.

## Several events

Now wait for several events. The shape parameter counts them.

### A side note

A short remark.

## Last section

Nothing new here.
'''
ONE = {'id': 'one', 'heading': 'One event', 'kind': 'concept', 'target': 'exponential-distribution',
       'introduces': {'intensity': 'How many events happen per unit time.'},
       'card': {'core_idea': 'The wait for one event has an average set by the intensity.', 'predict': 'Does a higher intensity shorten the wait?',
                'retrieve': 'What does the intensity count?', 'no_visual_reason': 'A sentence carries this idea.'}}
SEVERAL = {'id': 'several', 'heading': 'Several events', 'kind': 'concept', 'target': 'gamma-density',
           'introduces': {'shape parameter': 'The number of events we wait for.'}, 'terms': ['intensity'],
           'card': {'core_idea': 'Waiting for several events adds their waits.', 'no_visual_reason': 'Words are enough here.'}}


def codes(result):
    return sorted(i['code'] for i in result['issues'])


class CardShape(Base):
    def test_a_valid_card_is_accepted_and_bad_ones_are_refused_with_the_reason(self):
        name = self.make(SOURCE)
        self.declare(name, ONE)
        for bad, expect in ((dict(ONE['card'], extra=1), 'only'), ({'predict': 'x'}, 'core_idea'), ({'core_idea': 'ok', 'visual': 'v1', 'no_visual_reason': 'r'}, 'not both'),
                            ({'core_idea': 'ok', 'spoken': {'English': 'hi'}}, 'language code'), ({'core_idea': 'x' * 401}, 'core_idea'), ('text', 'only')):
            with self.assertRaisesRegex(ValueError, expect):
                hs.declare_block(self.root, name, dict(ONE, id='bad', card=bad))


class Projection(Base):
    def projected(self, *blocks):
        name = self.make(SOURCE)
        self.declare(name, *blocks)
        state = self.state(name)
        return state, hs._teaching_source(state)

    def test_card_blocks_show_idea_prediction_and_words_before_the_prose_and_recall_after(self):
        state, shown = self.projected(ONE, SEVERAL)
        self.assertEqual(state['source_markdown'], SOURCE, 'the stored lesson is never changed')
        order = [shown.index(m) for m in ('## One event', '[!concept] In one idea', '[!predict] Predict first', '[!glossary]+ New words in this section',
                                          'Waiting for one event takes', '[!recall]- Check yourself', '## Several events')]
        self.assertEqual(order, sorted(order))
        self.assertIn('- **intensity** — How many events happen per unit time.', shown)

    def test_a_later_block_is_reminded_of_words_introduced_earlier_and_the_recall_closes_its_subsections(self):
        _, shown = self.projected(ONE, dict(SEVERAL, card=dict(SEVERAL['card'], retrieve='What does the shape parameter count?')))
        self.assertIn('[!glossary]- Words from earlier in this lesson\n> - intensity — How many events happen per unit time.', shown)
        recall = shown.index('What does the shape parameter count?')
        self.assertGreater(recall, shown.index('A short remark.'), 'the recall prompt comes after the sub-section, at the section end')
        self.assertLess(recall, shown.index('## Last section'))

    def test_sessions_without_cards_render_exactly_as_before(self):
        name = self.make(SOURCE)
        self.declare(name, {k: v for k, v in ONE.items() if k != 'card'})
        self.assertEqual(hs._teaching_source(self.state(name)), SOURCE)

    def test_the_page_has_a_glossary_component_and_the_prediction_is_not_a_checkpoint(self):
        state, _ = self.projected(ONE, SEVERAL)
        page = hs.render_html(state)
        self.assertEqual(page.count('data-ros="glossary"'), 3, 'new words twice, plus one reminder of earlier words')
        self.assertIn('data-ros="predict"', page)
        self.assertNotIn('data-ros="checkpoint"', page, 'a prediction prompt must not receive a "record checkpoint" control')
        self.assertIn('In one idea', page)


class BlockLint(Base):
    counter = 0

    def lint(self, source, *blocks, **kwargs):
        BlockLint.counter += 1
        name = self.make(source, name=f'lint{BlockLint.counter}.md')
        self.declare(name, *blocks)
        return tl.lint_blocks(self.state(name), **kwargs)

    def test_a_clean_card_block_has_no_findings(self):
        self.assertEqual(self.lint(SOURCE, ONE)['issues'], [])

    def test_missing_card_and_missing_prompts_are_reported(self):
        self.assertEqual(codes(self.lint(SOURCE, {k: v for k, v in ONE.items() if k != 'card'})), ['CARD_MISSING'])
        thin = dict(ONE, card={'core_idea': 'Short idea.', 'no_visual_reason': 'Words suffice.'})
        self.assertEqual(codes(self.lint(SOURCE, thin)), ['PREDICT_MISSING', 'RETRIEVE_MISSING'])

    def test_core_idea_must_be_short(self):
        long = dict(ONE, card=dict(ONE['card'], core_idea='One. Two. Three sentences are too many.'))
        self.assertEqual(codes(self.lint(SOURCE, long)), ['CORE_IDEA_LONG'])

    def test_formula_first_density_and_long_paragraphs(self):
        source = '# T\n\n## One event\n\n$$\nf(x) = \\lambda e^{-\\lambda x}\n$$\n\n' + ' '.join(['word'] * 90) + '\n\n$$a$$\n\n$$b$$\n\n$$c$$\n'
        self.assertEqual(codes(self.lint(source, ONE)), ['FORMULA_DENSITY', 'FORMULA_FIRST', 'LONG_PARAGRAPH'])

    def test_no_visual_is_satisfied_by_a_figure_marker_a_reason_or_a_declared_visual(self):
        no_reason = dict(ONE, card={k: v for k, v in ONE['card'].items() if k != 'no_visual_reason'})
        self.assertEqual(codes(self.lint(SOURCE, no_reason)), ['NO_VISUAL'])
        self.assertEqual(self.lint(SOURCE, dict(ONE, card=dict(no_reason['card'], visual='VIS-1')))['issues'], [])
        marked = SOURCE.replace('We call the rate the intensity.', 'We call the rate the intensity.\n\n![the curve](resource:VIS-1 "caption")')
        self.assertEqual(self.lint(marked, no_reason)['issues'], [])

    def test_a_term_used_before_the_section_that_introduces_it(self):
        early = SOURCE.replace('Waiting for one event takes an average time.', 'The shape parameter will matter later.')
        complete = dict(SEVERAL, card=dict(SEVERAL['card'], predict='Longer or shorter?', retrieve='What does it count?'))
        result = self.lint(early, ONE, complete)
        self.assertEqual(codes(result), ['TERM_BEFORE_INTRO'])
        self.assertIn("'shape parameter'", result['issues'][0]['message'])

    def test_spoken_scripts_are_checked_for_notation_length_and_language(self):
        spoken = dict(ONE, card=dict(ONE['card'], spoken={'en': 'The density is f of x equals lambda e to the minus lambda x.',
                                                          'tr': 'Yoğunluk f(x) = λ e^{-λx}.'}))
        result = self.lint(SOURCE, spoken, lang='de', require_spoken=True)
        self.assertEqual(codes(result), ['SPOKEN_HAS_MATH', 'SPOKEN_LANGUAGE'])
        flagged = [i for i in result['issues'] if i['code'] == 'SPOKEN_HAS_MATH']
        self.assertEqual(len(flagged), 1)
        self.assertIn('spoken[tr]', flagged[0]['message'])
        long = dict(ONE, card=dict(ONE['card'], spoken={'en': ' '.join(['word'] * 230)}))
        self.assertEqual(codes(self.lint(SOURCE, long)), ['SPOKEN_LONG'])
        self.assertEqual(codes(self.lint(SOURCE, ONE, require_spoken=True)), ['SPOKEN_MISSING'])

    def test_a_glossary_term_that_is_used_undeclared_and_unknown_is_flagged(self):
        glossary = {'intensity': {'labels': {'en': 'intensity', 'tr': 'yoğunluk'}, 'concepts': []}}
        undeclared = dict(ONE, introduces={})
        self.assertEqual(codes(self.lint(SOURCE, undeclared, glossary=glossary, term_states={}, lang='en')), ['UNDECLARED_TERM'])
        known = self.lint(SOURCE, undeclared, glossary=glossary, term_states={'intensity': {'en': 'defined'}}, lang='en')
        self.assertEqual(known['issues'], [])
        declared = self.lint(SOURCE, dict(undeclared, terms=['intensity']), glossary=glossary, term_states={}, lang='en')
        self.assertEqual(declared['issues'], [])

    def test_the_output_says_what_it_cannot_judge(self):
        self.assertIn('does not judge', self.lint(SOURCE, ONE)['note'])


GOOD_NOTE = '''---
type: lecture-note
concept: gamma-density
up: ["[[Gamma distribution]]"]
---
# Gamma density

## L0 Gist

A gamma density describes the wait for several events.

### Words you need

- **shape parameter** — the number of events we wait for.

## L1 Core in 60 seconds

> [!question]- What does the shape parameter count?
> The events we wait for.

> [!question]- What happens to the typical wait as it grows?
> It gets longer.

> [!question]- When is it not a good model?
> When events are not independent.

## L2 Lecture

Waiting for one event, then another, adds their waits.

## L3 Derivation and sources

The sum of waits follows from convolution. Source: https://example.org/gamma
'''


class LectureNotes(unittest.TestCase):
    def test_a_well_formed_note_is_clean(self):
        self.assertEqual(tl.lint_note(GOOD_NOTE)['issues'], [])

    def test_the_template_has_the_right_shape_and_is_reported_as_unfilled(self):
        result = tl.lint_note((ROOT / 'assets/obsidian/25_Lecture_Note.md').read_text(encoding='utf-8'))
        self.assertEqual(result['errors'], 0)
        self.assertIn('NOTE_PLACEHOLDER', codes(result))
        self.assertIn('NOTE_L1_ANSWER', codes(result))

    def test_missing_or_misordered_layers_are_an_error(self):
        result = tl.lint_note(GOOD_NOTE.replace('## L2 Lecture', '## Lecture'))
        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['issues'][-1]['code'], 'NOTE_LAYERS')
        swapped = GOOD_NOTE.replace('## L1 Core in 60 seconds', '## L9 tmp').replace('## L2 Lecture', '## L1 Core in 60 seconds').replace('## L9 tmp', '## L2 Lecture')
        self.assertEqual(tl.lint_note(swapped)['errors'], 1)

    def test_open_questions_few_questions_and_a_long_gist_are_flagged(self):
        opened = GOOD_NOTE.replace('[!question]- What does', '[!question] What does')
        self.assertEqual(codes(tl.lint_note(opened)), ['NOTE_L1_OPEN'])
        few = GOOD_NOTE.replace('> [!question]- When is it not a good model?\n> When events are not independent.\n', '')
        self.assertEqual(codes(tl.lint_note(few)), ['NOTE_L1_QUESTIONS'])
        verbose = GOOD_NOTE.replace('A gamma density describes the wait for several events.', ' '.join(['gist'] * 35))
        self.assertEqual(codes(tl.lint_note(verbose)), ['NOTE_L0_LONG'])

    def test_frontmatter_sources_and_word_list_format_are_checked(self):
        bare = GOOD_NOTE.replace('concept: gamma-density\n', '').replace('Source: https://example.org/gamma', 'no citation')
        self.assertEqual(codes(tl.lint_note(bare)), ['NOTE_FRONTMATTER', 'NOTE_L3_SOURCES'])
        bad_words = GOOD_NOTE.replace('- **shape parameter** — the number', '- shape parameter: the number')
        self.assertEqual(codes(tl.lint_note(bad_words)), ['NOTE_WORDS_FORMAT'])

    def test_first_screen_budget(self):
        heavy = GOOD_NOTE.replace('- **shape parameter** — the number of events we wait for.', '- **shape parameter** — ' + ' '.join(['word'] * 420))
        self.assertIn('NOTE_FIRST_SCREEN', codes(tl.lint_note(heavy)))


class Cli(unittest.TestCase):
    def test_note_cli_exit_status_and_strict_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, odd = Path(tmp) / 'good.md', Path(tmp) / 'odd.md'
            good.write_text(GOOD_NOTE, encoding='utf-8')
            odd.write_text(GOOD_NOTE.replace('[!question]- What does', '[!question] What does'), encoding='utf-8')
            script = str(ROOT / 'scripts/teaching_lint.py')

            def run(*args):
                return subprocess.run([sys.executable, '-S', '-B', script, *args], capture_output=True, text=True, encoding='utf-8', cwd=tmp)

            self.assertEqual(run('note', str(good), '--strict').returncode, 0)
            self.assertEqual(run('note', str(odd)).returncode, 0, 'a warning alone does not fail')
            self.assertEqual(run('note', str(odd), '--strict').returncode, 1)
            self.assertEqual(json.loads(run('note', str(odd)).stdout)['issues'][0]['code'], 'NOTE_L1_OPEN')


if __name__ == '__main__':
    unittest.main()
