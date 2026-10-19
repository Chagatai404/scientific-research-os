"""Bounded presentation snapshots of canonical advice; never a learning ledger."""
from copy import deepcopy
from datetime import date
import re

FIELDS={'advice_schema','evidence','status','context_outcome','action','reason','as_of','receipt_id'}


def validate(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or type(value['advice_schema']) is not int or value['advice_schema']!=1 or value['evidence'] is not False:
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
    return value


def snapshot(receipt):
    recommendation=receipt['retrieval'].get('recommendation')
    if not recommendation: return None
    return validate({'advice_schema':1,'evidence':False,'status':recommendation['status'],
                     'context_outcome':receipt['outcome'],'action':recommendation['next']['action'],
                     'reason':recommendation['rationale'][:600],'as_of':receipt['as_of'],'receipt_id':receipt['receipt_id']})


def public(state):
    value=(state.get('context') or {}).get('advice')
    return deepcopy(validate(value)) if value is not None else None


def refresh_in_state(root, session, state, *, require_usable=False):
    """Called under the session lock at meaningful boundaries, never per page view.

    Feedback may still be saved when context fails. Revised teaching must instead
    refuse the transaction. A blocked snapshot never replaces the last usable
    binding or authorizes new instruction.
    """
    import context_kernel as ck
    import html_sessions as hs
    bound=state.get('context') or {}
    if not bound or bound.get('waived'): return False
    old=deepcopy(bound)
    try:
        receipt,_,_=ck.preflight(hs.planning_request(root,session,state))
        if require_usable or receipt['outcome']!='blocked': ck.require(receipt)
        if not receipt['retrieval'].get('recommendation'): return False
        if receipt['outcome']!='blocked':
            fresh=hs.bind_context(receipt)
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
