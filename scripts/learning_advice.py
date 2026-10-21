"""Bounded presentation snapshots of canonical advice; never a learning ledger."""
from copy import deepcopy
from datetime import date
import re

FIELDS={'advice_schema','evidence','status','context_outcome','action','reason','as_of','receipt_id'}


def validate(value):
    if not isinstance(value,dict) or set(value)-{'for_target'} not in (FIELDS, FIELDS | {'target', 'next'}) or type(value['advice_schema']) is not int or value['advice_schema']!=1 or value['evidence'] is not False:
        raise ValueError('Invalid canonical advice snapshot')
    if (not isinstance(value['status'],str) or value['status'] not in {'ready','limited','blocked'}
            or not isinstance(value['context_outcome'],str) or value['context_outcome'] not in {'ready','degraded','blocked'}):
        raise ValueError('Invalid canonical advice status')
    if not isinstance(value['action'],str) or not re.fullmatch(r'[a-z_]{1,60}',value['action']):
        raise ValueError('Invalid canonical advice action')
    if not isinstance(value['reason'],str) or not 1<=len(value['reason'])<=600:
        raise ValueError('Invalid canonical advice reason')
    if not isinstance(value['as_of'],str) or date.fromisoformat(value['as_of']).isoformat()!=value['as_of']:
        raise ValueError('Invalid canonical advice date')
    if value['receipt_id'] is not None and (not isinstance(value['receipt_id'],str) or not re.fullmatch(r'[0-9a-f]{32}',value['receipt_id'])):
        raise ValueError('Invalid advice receipt identity')
    if value['status']=='ready' and value['receipt_id'] is None:
        raise ValueError('Ready advice requires a canonical context receipt')
    if (value['context_outcome']=='blocked') != (value['status']=='blocked') or value['status']=='blocked' and value['action']!='repair_context':
        raise ValueError('Blocked context cannot suggest instruction')
    if 'for_target' in value and (not isinstance(value['for_target'],str) or not 1<=len(value['for_target'])<=300 or re.search(r'[\x00-\x1f\x7f]',value['for_target']) or 'target' in value and value['for_target']!=value['target']):
        raise ValueError('Invalid canonical advice target identity')
    if 'target' in value:
        target, step = value['target'], value['next']
        if (not isinstance(target, str) or not 1 <= len(target) <= 300 or re.search(r'[\x00-\x1f\x7f]', target)
                or not isinstance(step, dict) or set(step) != {'scope', 'dimension'}
                or not isinstance(step.get('scope'),str) or not isinstance(step.get('dimension'),str)
                or step.get('scope') not in {'conceptual', 'transfer', 'project_application'}
                or step.get('dimension') not in {'recognition', 'explanation', 'derivation', 'transfer', 'application'}):
            raise ValueError('Invalid bounded practice advice binding')
    return value


def snapshot(receipt):
    recommendation=receipt['retrieval'].get('recommendation')
    if not recommendation: return None
    result = {'advice_schema':1,'evidence':False,'status':recommendation['status'],
                     'context_outcome':receipt['outcome'],'action':recommendation['next']['action'],
                     'reason':recommendation['rationale'][:600],'as_of':receipt['as_of'],'receipt_id':receipt['receipt_id']}
    target, step = recommendation.get('target'), recommendation.get('next')
    if isinstance(target,dict) and isinstance(target.get('id'),str):
        result['for_target']=target['id']
    if (recommendation['status'] == 'ready' and receipt['outcome'] == 'ready' and isinstance(target,dict)
            and isinstance(target.get('id'),str) and isinstance(step,dict)
            and ((target.get('kind') == 'concept' and step.get('concept') == target['id'])
                 or (target.get('kind') == 'capability' and step.get('capability') == target['id']))
            and isinstance(step.get('scope'),str) and isinstance(step.get('dimension'),str)
            and step.get('scope') in {'conceptual','transfer','project_application'}
            and step.get('dimension') in {'recognition','explanation','derivation','transfer','application'}):
        result.update(target=target['id'],next={key:step[key] for key in ('scope','dimension')})
    return validate(result)


def public(state):
    value=(state.get('context') or {}).get('advice')
    return deepcopy(validate(value)) if value is not None else None


def public_preferences(state):
    """Explicit presentation choices only; no potentially stale policy cache."""
    import learning_preferences
    bound = state.get('context') or {}
    if 'preferences' not in bound:
        return None
    return {'preferences': learning_preferences.validate(bound['preferences'])}


def validate_vocabulary(value):
    import terms
    if (not isinstance(value,dict) or set(value)!={'vocabulary_schema','as_of','states'}
            or type(value['vocabulary_schema']) is not int or value['vocabulary_schema']!=1
            or not isinstance(value['as_of'],str) or date.fromisoformat(value['as_of']).isoformat()!=value['as_of']):
        raise ValueError('Invalid vocabulary presentation snapshot')
    states=value['states']
    if states is not None:
        if not isinstance(states,dict) or len(states)>40:
            raise ValueError('Bounded vocabulary states required')
        for term,languages in states.items():
            if not isinstance(term,str) or not terms.ID.fullmatch(term) or not isinstance(languages,dict) or len(languages)>8:
                raise ValueError('Invalid vocabulary term snapshot')
            for language,state in languages.items():
                if not isinstance(language,str) or not terms.LANG.fullmatch(language) or not isinstance(state,str) or state not in terms.STATES:
                    raise ValueError('Invalid recorded vocabulary language state')
    return value


def public_vocabulary(state):
    value=(state.get('context') or {}).get('vocabulary')
    if value is None:return None
    validate_vocabulary(value)
    prepared={row['term_id'] for entry in ((state.get('plan') or {}).get('pedagogy') or {}).get('terms',[]) for row in entry['terms']}
    if value['states'] is not None and set(value['states'])-prepared:
        raise ValueError('Vocabulary states must belong to prepared canonical terms')
    return deepcopy(value)


def refresh_vocabulary_in_state(root,state):
    """Readonly dated projection of actual term authority at meaningful boundaries."""
    import terms
    bound=state.get('context')
    if bound is None:
        return False # Never invent a canonical binding or context waiver.
    entries=((state.get('plan') or {}).get('pedagogy') or {}).get('terms',[])
    old=bound.get('vocabulary')
    if not entries:
        bound.pop('vocabulary',None)
        return old is not None
    prepared={row['term_id']:row for entry in entries for row in entry['terms']}
    ids=list(prepared)[:40]
    snapshot={'vocabulary_schema':1,'as_of':date.today().isoformat(),'states':None}
    try:
        glossary,problems=terms.load_glossary(terms.learner_dir(root))
        if not problems and all(key in glossary for key in ids):
            concepts=sorted({concept for key in ids for concept in prepared[key]['concepts']})
            brief=terms.brief(root,concepts,max_terms=40)
            brief_states=terms.term_view(brief)
            if brief_states is not None:
                validate_vocabulary(dict(snapshot,states={key:value for key,value in brief_states.items() if key in ids}))
            events,event_problems=terms.load_events(terms.learner_dir(root))
            # Use the existing authoritative fold rather than a truncated brief
            # that may spend its budget on unrelated shaky terms.
            recorded=terms.term_states(events)
            if not brief.get('diagnostics') and not event_problems:
                snapshot['states']={key:{language:state for language,state in recorded.get(key,{}).items() if language in prepared[key]['labels']} for key in ids}
        validate_vocabulary(snapshot)
    except (OSError,ValueError,TypeError):
        snapshot['states']=None
    bound['vocabulary']=snapshot
    return old!=snapshot


def refresh_in_state(root, session, state, *, require_usable=False):
    """Called under the session lock at meaningful boundaries, never per page view.

    Feedback may still be saved when context fails. Revised teaching must instead
    refuse the transaction. A blocked snapshot never replaces the last usable
    binding or authorizes new instruction.
    """
    import context_kernel as ck
    import html_sessions as hs
    bound=state.get('context') or {}
    if not bound or bound.get('waived'): return refresh_vocabulary_in_state(root,state)
    old=deepcopy(bound)
    try:
        receipt,_,_=ck.preflight(hs.planning_request(root,session,state))
        if require_usable or receipt['outcome']!='blocked': ck.require(receipt)
        if not receipt['retrieval'].get('recommendation'): return refresh_vocabulary_in_state(root,state)
        if receipt['outcome']!='blocked':
            fresh=hs.bind_context(receipt, preferences=bound.get('preferences'))
            fresh['bound_at']=bound.get('bound_at',fresh['bound_at'])
            # Preserve timestamps on an unchanged receipt, request and snapshot.
            fresh['refreshed_at']=bound.get('refreshed_at')
            state['context']=fresh
        else:
            state['context']=dict(bound,advice=snapshot(receipt))
    except (ck.ContextError,OSError,ValueError):
        if require_usable: raise
        state['context']=dict(bound,advice={'advice_schema':1,'evidence':False,'status':'limited',
            'context_outcome':'degraded','action':'inspect_context','receipt_id':None,'as_of':date.today().isoformat(),
            'reason':'Current knowledge advice could not be refreshed. Ask the tutor to check context; prior advice does not establish current knowledge.'})
    refresh_vocabulary_in_state(root,state)
    changed={k:v for k,v in old.items() if k!='refreshed_at'}!={k:v for k,v in state['context'].items() if k!='refreshed_at'}
    if changed: state['context']['refreshed_at']=hs._now()
    return changed


def refresh(root,session):
    import html_sessions as hs
    md,_,_=hs.paths(root,session)
    with hs.Lock(md.with_suffix('.session.lock')):
        state=hs.load_session(root,session)
        changed=refresh_in_state(root,session,state)
        if changed:
            state['updated_at']=hs._now()
            hs._save(root,session,state)
        return {'session':str(session),'changed':changed,'advice':public(state),'adaptation':hs.session_adaptation(state)}
