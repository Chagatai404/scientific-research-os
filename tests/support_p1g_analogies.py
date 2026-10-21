"""Trusted writer/export for public-source teaching and synthetic learner records.

The real temporary ledger is used; no live vault or detector replication occurs.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import html_sessions as hs
from pedagogy_contract import digest
from test_handout import make_vault,SESSION


def build(folder,lecture=False):
    root=Path(folder);make_vault(root,with_plan=False)
    fixture=json.loads((ROOT/'tests/fixtures/p1g/box-counting-analogies.json').read_text(encoding='utf8'))
    plan=deepcopy(fixture['plan']);replacement=plan['pedagogy']['analogies'].pop()
    if lecture:
        unrelated=deepcopy(plan['segments'][0]);unrelated.update(id='geometry-unrelated',title='A separate lesson without a prepared analogy',covers=['Source attribution boundaries'])
        unrelated['script']['steps']=[{'id':'geometry-unrelated-intro','say':'This separate lesson discusses source attribution. No analogy has been authored for this segment.'}]
        plan['segments'].append(unrelated)
    # Keep the transfer task genuinely off the initially shown Check card, so
    # browser assertions exercise both assignment and issue acknowledgement.
    gateway=deepcopy(plan['probe']['questions'][0]);gateway.update(id='geometry-check-gateway',prompt='Check gateway: how many width-one-quarter squares cover a unit square?',on_correct='geometry-transfer',on_wrong='geometry-transfer')
    plan['check']['start']=gateway['id'];plan['check']['budget']=2;plan['check']['questions'].insert(0,gateway)
    hs.update_session(root,SESSION,text='---\ntype: course-session\n---\n# Synthetic geometry teaching\n\nPublic-source scope and synthetic misconception records.\n',plan=plan)
    baseline=root/'analogies-baseline.html';hs.export_session(root,SESSION,baseline)
    bad=deepcopy(plan);bad['pedagogy']['practice'][0]['version']+=1
    try:hs.update_session(root,SESSION,plan=bad)
    except (ValueError,RuntimeError) as error:assert 'version' in str(error).lower(),str(error)
    else:raise AssertionError('Stale analogy practice version accepted')
    entry=plan['pedagogy']['analogies'][0]
    hs.append_event(root,SESSION,{'type':'checkpoint','event_id':'actual-presented-analogy','question_id':None,'response':f"pedagogy-analogy:{entry['id']}:{entry['version']}"})
    changed=deepcopy(plan);changed['segments'][0]['script']['steps'][0]['say']+=' Changed source-bound lesson.'
    changed['pedagogy']['analogies'][0]['segment_sha256']=digest(changed['segments'][0])
    try:hs.update_session(root,SESSION,plan=changed)
    except (ValueError,RuntimeError):pass
    else:raise AssertionError('Presented analogy silently retargeted its changed segment')
    raw=deepcopy(fixture['state']['events'][0]);raw.pop('created_at',None);hs.append_event(root,SESSION,raw)
    review=fixture['state']['plan_reviews'][0]
    hs.review_plan_answer(root,SESSION,raw['question_id'],review['verdict'],review['feedback'],reviewed_by=review['reviewed_by'],criteria_met=review['criteria_met'])
    actual=hs.load_session(root,SESSION)['plan_reviews'][-1]
    replacement['replacement']['review_snapshot']=deepcopy(actual);replacement['replacement']['review_sha256']=digest(actual)
    plan['pedagogy']['analogies'].append(replacement);hs.update_session(root,SESSION,plan=plan)
    reviewed=root/'analogies-reviewed.html';hs.export_session(root,SESSION,reviewed)
    hs.append_event(root,SESSION,{'type':'checkpoint','event_id':'actual-presented-replacement','question_id':None,'response':f"pedagogy-analogy:{replacement['id']}:{replacement['version']}"})
    newer=deepcopy(raw);newer['event_id']='actual-newer-transfer-attempt';newer['response']['answer']='I now distinguish finite readout scaling from the limit, but this revised explanation still requires its own review.'
    hs.append_event(root,SESSION,newer)
    historical=root/'analogies-historical.html';hs.export_session(root,SESSION,historical)
    return {'standalone':str(baseline),'reviewed':str(reviewed),'historical':str(historical),'session':SESSION}


if __name__=='__main__':print(json.dumps(build(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='lecture')))
