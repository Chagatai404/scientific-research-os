"""Actual trusted publication/export of synthetic optional cognitive activities.

No live vault, provider, listener or scientific approval is involved.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
from test_handout import make_vault,SESSION


def build(folder):
    root=Path(folder);make_vault(root,with_plan=False)
    fixture=json.loads((ROOT/'tests/fixtures/p1f/mse-challenges.json').read_text(encoding='utf8'))
    plan=deepcopy(fixture['plan'])
    hs.update_session(root,SESSION,text='---\ntype: course-session\n---\n# Synthetic MSE cognitive activities\n\nDisposable browser verification.\n',plan=plan)
    exported=root/'bloom-standalone.html';hs.export_session(root,SESSION,exported)
    # Authored family references are immutable by both id and exact version.
    bad=deepcopy(plan);bad['pedagogy']['practice'][0]['version']+=1
    try:
        hs.update_session(root,SESSION,plan=bad)
    except (ValueError,RuntimeError) as error:
        assert 'bloom' in str(error).lower() and 'version' in str(error).lower(),str(error)
    else:
        raise AssertionError('Trusted writer accepted stale Bloom practice version')
    assert hs.load_session(root,SESSION)['plan']==plan
    hs.append_event(root,SESSION,{'type':'plan-answer','event_id':'bloom-original-create','question_id':'mse-create',
        'response':{'tree':'check','answer':'My original construction chooses a two-point distribution but does not verify all moment constraints.','verdict':'pending'}})
    hs.review_plan_answer(root,SESSION,'mse-create','partially-correct',
        'Show both the normalization and the required first and second moment checks.',
        reviewed_by='Synthetic browser fixture reviewer',criteria_met=[True,False,False])
    reviewed=root/'bloom-reviewed.html';hs.export_session(root,SESSION,reviewed)
    missing_plan=deepcopy(plan);missing_plan['pedagogy']['bloom'][0]['challenges']=[c for c in missing_plan['pedagogy']['bloom'][0]['challenges'] if c['level'] not in ('evaluate','create')]
    missing_session='01 Projects/Stats/Sessions/bloom-missing.md'
    hs.create_session(root,missing_session,'# Missing optional challenge levels\n');hs.update_session(root,missing_session,plan=missing_plan)
    missing=root/'bloom-missing.html';hs.export_session(root,missing_session,missing)
    # The historical per-tree route budget remains intact; the shared diagnostic
    # issue gate independently caps all actual prepared probe issuance at one.
    exhausted_plan=deepcopy(plan);exhausted_plan['budget']=1
    exhausted_session='01 Projects/Stats/Sessions/bloom-exhausted.md'
    hs.create_session(root,exhausted_session,'# Shared budget boundary\n');hs.update_session(root,exhausted_session,plan=exhausted_plan)
    hs.append_event(root,exhausted_session,{'type':'checkpoint','event_id':'bloom-reserved-remember','question_id':None,'response':'pedagogy-probe:mse-remember:1'})
    try:
        hs.append_event(root,exhausted_session,{'type':'checkpoint','event_id':'bloom-over-budget','question_id':None,'response':'pedagogy-probe:mse-create:1'})
    except (ValueError,RuntimeError) as error:
        assert 'budget' in str(error).lower(),str(error)
    else:
        raise AssertionError('Trusted writer accepted over-budget Bloom task issuance')
    exhausted=root/'bloom-exhausted.html';hs.export_session(root,exhausted_session,exhausted)
    return {'standalone':str(exported),'reviewed':str(reviewed),'missing':str(missing),'exhausted':str(exhausted),'session':SESSION}


if __name__=='__main__':print(json.dumps(build(sys.argv[1])))
