"""Build disposable sessions with inline visuals for browser tests: python support_visual_session.py <empty-dir>.

Prints JSON with the generated paths. Not a test module; synthetic content only.
  placed.md  every figure and widget sits in the lesson where its marker is
  gap.md     a figure and a widget are declared but never placed (must be reported, not appended)
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
import scientific_verify as sv
import visual_assets as va

SPEC = {'title': 'Likelihood workflow', 'rows': [{'label': 'Steps', 'nodes': [
    {'id': 'a', 'text': 'Model the counts'}, {'id': 'b', 'text': 'Fit', 'kind': 'gate'}, {'id': 'c', 'text': 'Check', 'kind': 'done'}]}],
    'edges': [['a', 'b'], ['b', 'c']]}
PLOT = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60" width="120" height="60" role="img" aria-label="y equals four">'
        '<rect width="120" height="60" fill="#ffffff"/><polyline points="0,40 60,20 120,40" fill="none" stroke="#1f4e79" stroke-width="2"/></svg>')
LESSON = '''# Likelihood

## Setup

First paragraph before the figure.

## Fit

Paragraph that follows the workflow figure.

## Check

Paragraph under the check heading.

## Result

Paragraph before the widget.

Closing paragraph.
'''


def build(directory):
    directory = Path(directory)
    hs.install_runtime(directory)
    va.ensure_schematic(directory, SPEC, visual_id='VIS-flow', concepts=['probability.gamma-density'])
    (directory / 'Visuals/curve.svg').write_text(PLOT, encoding='utf-8')
    record = sv.run({'verification_schema': 1, 'verification_id': 'V-curve', 'claim': {'id': 'C', 'statement': 'the curve passes through four', 'consequence': 'routine'},
                     'checks': [{'id': 's', 'kind': 'evaluate', 'expression': '2 + 2', 'expected': 4}],
                     'reviewer': {'role': 'test-reviewer', 'context_exposure': 'bounded'}})
    (directory / 'Visuals/curve.verification.json').write_text(json.dumps(record), encoding='utf-8')
    (directory / 'Visuals/curve.visual.json').write_text(json.dumps({
        'visual_schema': 1, 'visual_id': 'VIS-curve', 'title': 'Curve', 'kind': 'model-driven-plot', 'concepts': ['probability.gamma-density'],
        'source_type': 'generated', 'verification_status': 'rendered', 'artifact': 'Visuals/curve.svg', 'quantitative': True, 'basis': 'y = 2 + 2',
        'verification_record': 'Visuals/curve.verification.json'}), encoding='utf-8')
    (directory / 'Sessions').mkdir(exist_ok=True)
    for name in ('placed', 'gap'):
        hs.create_session(directory, f'Sessions/{name}.md', LESSON, title=f'Inline visuals ({name})', widgets=[{'id': 'sample', 'kind': 'sampling'}])
        for visual in ('VIS-flow', 'VIS-curve'):
            va.attach_visual(directory, f'Sessions/{name}.md', visual)
    place = lambda **k: va.place_visual(directory, 'Sessions/placed.md', **k)
    place(figure='VIS-flow', after_heading='Fit', alt='Three boxes: model the counts, fit, check', caption='The workflow')
    place(figure='VIS-curve', after_heading='Check', alt='A tent-shaped curve', caption='Model curve')
    place(widget='sample', after_text='Paragraph before the widget')
    standalone = directory / 'placed-standalone.html'
    hs.export_session(directory, 'Sessions/placed.md', standalone)
    gap_standalone = directory / 'gap-standalone.html'
    hs.export_session(directory, 'Sessions/gap.md', gap_standalone)
    return {'root': str(directory), 'placed': str(directory / 'Sessions/placed.html'), 'placed_state': str(directory / 'Sessions/placed.state.json'),
            'gap': str(directory / 'Sessions/gap.html'), 'gap_state': str(directory / 'Sessions/gap.state.json'),
            'standalone': str(standalone), 'gap_standalone': str(gap_standalone),
            'assets': str(directory / 'Sessions/placed.assets'), 'gap_assets': str(directory / 'Sessions/gap.assets')}


if __name__ == '__main__':
    print(json.dumps(build(sys.argv[1])))
