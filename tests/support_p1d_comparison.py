"""Export a source comparison over a real raw attempt in a disposable test vault."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import html_sessions as hs
from test_handout import make_vault, SESSION
from test_pedagogy_source_comparison import prepared


def build(folder, access='excerpt'):
    root = Path(folder)
    make_vault(root, with_plan=False)
    plan, comparison, state = prepared(access)
    plan['budget'] = 8
    hs.update_session(root, SESSION, text='---\ntype: course-session\n---\n# Synthetic source comparison\n\nDisposable source snapshot, not a real article.\n', plan=plan)
    hs.append_event(root, SESSION, {'event_id':'summary-issued', 'type':'checkpoint', 'question_id':None, 'response':'pedagogy-probe:why:1'})
    hs.append_event(root, SESSION, state['events'][0])
    hs.review_plan_answer(root, SESSION, 'why', 'incorrect', feedback='Historical review for the original summary only.',
        reviewed_by='reviewer: scripted fixture', rationale='The supplied summary does not meet either prepared squared-distance criterion.', criteria_met=[False, False])
    plan['pedagogy']['comparisons'] = [comparison]
    hs.update_session(root, SESSION, plan=plan)
    exported = root / 'comparison-standalone.html'
    hs.export_session(root, SESSION, exported)
    return {'standalone':str(exported), 'session':SESSION}


if __name__ == '__main__': print(json.dumps(build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'excerpt')))
