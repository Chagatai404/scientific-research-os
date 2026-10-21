"""Actual synthetic written-work critique plus genuine existing-family exports.

Temporary roots only. Source snapshots are declared synthetic/public teaching;
no provider, learner-code execution, live vault or research approval is used.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
from pedagogy_contract import digest
from pedagogy_source_comparison import source_digest
from test_handout import make_vault,SESSION
from test_pedagogy_roles import prepared


def build(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True);main=root/'main';make_vault(main,with_plan=False)
    plan,entry,state=prepared();plan['budget']=8;plan['pedagogy'].pop('critiques')
    plan['pedagogy']['practice']=[dict(id='editor-variance-practice',target=plan['target'],version=1,sources=deepcopy(entry['sources']),tree='probe',question_id='why',question_sha256=entry['question_sha256'],tier='intermediate',dimension='derivation',answer_unit='',alternatives=['Expand the centered square or use the first-two-moment identity under finite-second-moment assumptions.'],independent=False)]
    hs.update_session(main,SESSION,text='---\ntype: course-session\n---\n# Synthetic role routing and actual written work\n',plan=plan)
    clean=root/'roles-clean.html';hs.export_session(main,SESSION,clean)
    hs.append_event(main,SESSION,state['events'][0]);plan['pedagogy']['critiques']=[entry];hs.update_session(main,SESSION,plan=plan)
    pending=root/'roles-pending.html';hs.export_session(main,SESSION,pending)
    hs.review_plan_answer(main,SESSION,'why','incorrect','Subtract the squared mean rather than adding it; disclose the finite-moment assumptions.',reviewed_by='Synthetic browser reviewer',criteria_met=[False,False])
    review=hs.load_session(main,SESSION)['plan_reviews'][-1];entry['review_snapshot']=deepcopy(review);entry['review_sha256']=digest(review);entry['version']+=1;hs.update_session(main,SESSION,plan=plan)
    reviewed=root/'roles-reviewed.html';hs.export_session(main,SESSION,reviewed)
    bad=deepcopy(plan);bad['pedagogy']['critiques'][0]['findings'][0]['location']['line_start']=1;bad['pedagogy']['critiques'][0]['findings'][0]['location']['line_end']=1
    try:hs.update_session(main,SESSION,plan=bad)
    except (ValueError,RuntimeError) as error:assert 'line' in str(error).lower() or 'quote' in str(error).lower(),str(error)
    else:raise AssertionError('Trusted writer accepted critique quote outside actual raw line')
    missing=deepcopy(plan);unavailable=missing['pedagogy']['critiques'][0];unavailable.update(id='editor-source-unavailable',source=dict(entry['source'],access='unavailable',text='',sha256=source_digest('')),findings=[],checked=[],review_snapshot=None,review_sha256=None)
    un_session='01 Projects/Stats/Sessions/roles-unavailable.md';hs.create_session(main,un_session,'# Unavailable critique source\n');without=deepcopy(missing);without['pedagogy'].pop('critiques');hs.update_session(main,un_session,plan=without);hs.append_event(main,un_session,state['events'][0]);hs.update_session(main,un_session,plan=missing)
    missing_export=root/'roles-unavailable.html';hs.export_session(main,un_session,missing_export)
    # Reuse actual trusted family-specific authoring helpers, preserving their
    # real targets and canonical glossary/source constraints instead of placing
    # unrelated scientific examples under one artificial target.
    from support_p1d_comparison import build as comparison
    from support_p1e_terms import build as terms
    from support_p1f_bloom import build as bloom
    from support_p1g_analogies import build as analogies
    exports={}
    for family,builder in [('comparisons',comparison),('terms',terms),('bloom',bloom),('analogies',analogies)]:
        exports[family]=builder(root/family)
    return dict(clean=str(clean),pending=str(pending),reviewed=str(reviewed),unavailable=str(missing_export),families=exports)


if __name__=='__main__':print(json.dumps(build(sys.argv[1])))
