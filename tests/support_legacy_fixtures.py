"""Regenerate tests/fixtures/legacy-v0.8.7/ with the real v0.8.7 code (provenance for test_legacy_compat.py; not run by the gates).

    git worktree add <dir> a058df2 --detach          # the v0.8.7 release commit
    python tests/support_legacy_fixtures.py <dir> tests/fixtures/legacy-v0.8.7

The fixtures are the bytes v0.8.7 wrote: a session triple with retries, a latest-only review, answered and open questions and an unplaced
figure and widget; a learning capability, a research record, a paper catalog record without a reading depth, a visual registry record and a
task state. Everything is synthetic. The v0.9 tests copy them to a temporary directory and never modify them.
"""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys

source, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
sys.path.insert(0, str(source / 'scripts'))
import html_sessions as hs        # noqa: E402  (the v0.8.7 module, not this checkout's)
import paper_library as lib       # noqa: E402
import tasks                      # noqa: E402

assert (source / 'VERSION').read_text().strip() == '0.8.7', 'run this against a v0.8.7 checkout'
out.mkdir(parents=True, exist_ok=True)
(out / 'Sessions').mkdir(exist_ok=True)

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60" width="120" height="60" role="img" aria-label="tent">'
       '<rect width="120" height="60" fill="#ffffff"/><polyline points="0,40 60,20 120,40" fill="none" stroke="#1f4e79" stroke-width="2"/></svg>')
(out / 'Sessions/legacy.assets').mkdir(exist_ok=True)
# v0.8.7 sessions accept raster images only (SVG arrived in v0.9): a 1x1 PNG.
PNG = __import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
(out / 'Sessions/legacy.assets/tent.png').write_bytes(PNG)

LESSON = '''---
type: tutor-session
concept: box-counting
---
# Box counting, first pass

## Why count boxes

Cover the set with boxes of side eps and count N(eps). See [[Idea note]] and $N(\\epsilon)\\propto\\epsilon^{-D}$.

<!-- ros-question: shape -->

## The slope

The slope of log N against log 1/eps estimates the dimension.

<!-- ros-question: scale -->
'''
hs.create_session(out, 'Sessions/legacy.md', LESSON, title='Box counting, first pass', questions=[
    {'id': 'shape', 'kind': 'free-response', 'prompt': 'What does the slope estimate?', 'solution': 'The box-counting dimension.', 'hints': ['Think about scaling.']},
    {'id': 'scale', 'kind': 'free-response', 'prompt': 'Why does the box size need to shrink?'}],
    widgets=[{'id': 'sample', 'kind': 'sampling'}],
    resources=[{'id': 'tent', 'kind': 'image', 'path': 'legacy.assets/tent.png', 'alt': 'A tent-shaped curve'}])
for key, text in (('r1', 'It estimates the dimension, I think.'), ('r2', 'The slope is the box-counting dimension.')):
    hs.append_event(out, 'Sessions/legacy.md', {'event_id': key, 'type': 'response', 'question_id': 'shape', 'response': text})
hs.append_event(out, 'Sessions/legacy.md', {'event_id': 'h1', 'type': 'hint', 'question_id': 'shape', 'response': 1})
hs.append_event(out, 'Sessions/legacy.md', {'event_id': 'r3', 'type': 'response', 'question_id': 'scale', 'response': 'Because the limit needs small boxes.'})
hs.review_response(out, 'Sessions/legacy.md', 'shape', 'correct', 'Yes: the slope is the dimension.')   # v0.8.7: the latest response only
hs.append_event(out, 'Sessions/legacy.md', {'event_id': 'oq1', 'type': 'open-question', 'question_id': None, 'response': 'Does the slope depend on the range of eps?'})
hs.answer_open_question(out, 'Sessions/legacy.md', 'oq1', 'Yes, fit only where the log-log plot is straight.')
hs.append_event(out, 'Sessions/legacy.md', {'event_id': 'oq2', 'type': 'open-question', 'question_id': None, 'response': 'What about noisy data?'})

(out / 'Notes').mkdir(exist_ok=True)
(out / 'Notes/Idea note.md').write_text('# Idea note\n\nBoxes of side eps; count the occupied ones.\n', encoding='utf-8')
(out / '01 Projects/Demo').mkdir(parents=True, exist_ok=True)
(out / '01 Projects/Demo/Demo.md').write_text('---\ntype: project\nproject_id: ecal\n---\n# Demo\n', encoding='utf-8')
(out / '02 Knowledge').mkdir(exist_ok=True)
(out / '02 Knowledge/box.md').write_text('---\nlearning_schema: 1\nlearning_id: box.explain\ndomain: fractal-geometry\nprerequisites: []\nprojects: ["ecal"]\n---\n# Box counting\n', encoding='utf-8')
(out / 'research').mkdir(exist_ok=True)
(out / 'research/RQ-1.md').write_text('---\nresearch_schema: 1\ntype: research-question\nid: RQ-1\nproject: ecal\nstatus: active\ncreated: 2026-09-30\n---\n# Example question\n', encoding='utf-8')

lib.ingest(out / 'library', {'title': 'Scale geometry', 'year': 2026, 'doi': '10.1234/example', 'authors': ['Fixture Author'], 'source_url': 'https://example.org/source',
                             'concepts': ['box-counting'], 'projects': ['ecal'], 'screening': 'useful', 'relevance_notes': 'Synthetic fixture relevant to counting.'},
           apply=True, as_of=datetime.date(2026, 9, 30))

(out / 'Visuals').mkdir(exist_ok=True)
(out / 'Visuals/old.svg').write_text(SVG, encoding='utf-8')
(out / 'Visuals/old.visual.json').write_text(json.dumps({'visual_schema': 1, 'visual_id': 'VIS-old', 'title': 'Old schematic', 'kind': 'conceptual-schematic',
                                                        'concepts': ['box-counting'], 'source_type': 'schematic', 'verification_status': 'inspected',
                                                        'artifact': 'Visuals/old.svg'}, indent=2), encoding='utf-8')

project = out / 'project'
project.mkdir(exist_ok=True)
(project / 'question.txt').write_text('Synthetic neutral question.', encoding='utf-8')
reference = tasks.bind(project, 'question.txt', 'question')
tasks.plan(project, {'task_schema': 1, 'tasks': [{
    'task_id': 'scout', 'role': 'literature-scout', 'goal': 'Prepare a synthetic bounded result', 'stage': 3, 'research_refs': [], 'input_refs': [reference],
    'dependencies': [], 'independence_group': None, 'context_exposure': {'mode': 'bounded', 'input_paths': ['question.txt'], 'notes': 'Only declared fixture inputs.'},
    'permissions': {'write_paths': [], 'run': False, 'approval_ref': None}, 'provider': 'manual', 'writer_workspace': None}]},
    apply=True, now='2026-10-08T10:00:00Z')

# Remove what an installer regenerates and what is never part of the user's records.
if (out / '.research-os').exists():
    shutil.rmtree(out / '.research-os')
for lock in out.rglob('*.lock'):
    lock.unlink()
manifest = {str(p.relative_to(out)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
(out / 'manifest.json').write_text(json.dumps({'generated_by': 'v0.8.7 (a058df2)', 'files': manifest}, indent=2), encoding='utf-8')
print(json.dumps({'files': len(manifest)}))
