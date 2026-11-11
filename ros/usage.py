"""Usage and cost meter: what the providers reported, summed from the run records, never estimated.

Tokens come only from ``run.usage`` events (what an adapter reported); a run whose provider reported nothing counts as
``unknown``. Cost exists only where the person configured a price (``usage.price`` events, versioned per model, the latest
whose effective date is not after the run's day) and is None otherwise; subscription CLIs (codex, claude) are
"included in subscription", never a cost. Prices are per one million tokens. Read through one incremental fold, with an
index by conversation, so a call does not scan the record. Standard library only."""
from __future__ import annotations

import re

from . import execution

SUBSCRIPTION = ('codex', 'claude')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}$')


def _n(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def normalize(usage):
    """Reported usage as {input, output, cached, requests} (input excludes cached tokens); None when it holds no token count."""
    if not isinstance(usage, dict):
        return None
    u = usage.get('total') if isinstance(usage.get('total'), dict) else usage
    pick = lambda *keys: next((v for k in keys if (v := _n(u.get(k))) is not None), None)
    details = u.get('prompt_tokens_details') if isinstance(u.get('prompt_tokens_details'), dict) else {}
    cached = pick('cachedInputTokens', 'cached_input_tokens', 'cache_read_input_tokens')
    if cached is None:
        cached = _n(details.get('cached_tokens'))
    inp = pick('inputTokens', 'input_tokens', 'prompt_tokens')
    out = pick('outputTokens', 'output_tokens', 'completion_tokens')
    if inp is None and out is None and cached is None:
        return None
    inp = inp or 0
    if 'cache_read_input_tokens' not in u:  # codex and OpenAI count cached tokens inside the input; Claude does not
        inp = max(0, inp - (cached or 0))
    inp += _n(u.get('cache_creation_input_tokens')) or 0
    return {'input': inp, 'output': out or 0, 'cached': cached or 0, 'requests': pick('requests', 'request_count') or 1}


def _state(rec):
    def step(state, ev):
        data = ev['data']
        if ev['type'] == 'run.queued':
            row = {'id': ev['subject'], 'ts': ev['ts'], 'conversation': data.get('conversation'), 'model': data.get('model') or '',
                   'usage': None, 'context_chars': data.get('context_chars'), 'context_limit': data.get('context_limit')}
            state['runs'][ev['subject']] = row
            state['conv'].setdefault(row['conversation'], []).append(ev['subject'])
        elif ev['type'] == 'run.usage' and ev['subject'] in state['runs']:
            row = state['runs'][ev['subject']]
            row['usage'] = normalize(data.get('usage'))
            for k in ('context_chars', 'context_limit'):
                if data.get(k) is not None:
                    row[k] = data[k]
        elif ev['type'] == 'usage.price':
            state['prices'].setdefault(ev['subject'], []).append(dict(data, model=ev['subject']))
    return rec.fold('usage.v1', ('run.queued', 'run.usage', 'usage.price'), lambda: {'runs': {}, 'conv': {}, 'prices': {}}, step)


def prices(rec):
    """Every configured price, each model's versions in the order configured."""
    return {m: list(v) for m, v in _state(rec)['prices'].items()}


def configure_price(rec, model, input, output, cached=None, currency='USD', effective=None):
    """Record a new price version for one model (per one million tokens). Nothing is guessed: every figure is the person's."""
    model = (model or '').strip()
    if not model:
        raise ValueError('name the model (profile id) the price is for')
    figures = {'input': input, 'output': output, 'cached': cached}
    for name, v in figures.items():
        if v is not None and _n(v) is None:
            raise ValueError(f'the {name} price is a non-negative number per million tokens')
    if input is None or output is None:
        raise ValueError('give both the input and the output price per million tokens')
    currency = (currency or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        raise ValueError('currency is a three-letter code such as USD')
    if not effective or not DATE.match(effective):
        raise ValueError('effective is the date the price starts to apply, YYYY-MM-DD')
    version = len(_state(rec)['prices'].get(model, [])) + 1
    rec.append('usage.price', model, dict(figures, currency=currency, effective=effective, version=version), actor='person')
    return {'model': model, 'version': version, 'currency': currency, 'effective': effective, **figures}


def _price_for(table, model, day):
    rows = [p for p in table.get(model, []) if p['effective'] <= day]
    return max(rows, key=lambda p: (p['effective'], p['version'])) if rows else None


def _cost(usage, price):
    if price is None or usage is None:
        return None
    if usage['cached'] and price.get('cached') is None:
        return None  # cached tokens with no configured cached price: unpriced, not assumed
    return (usage['input'] * price['input'] + usage['output'] * price['output'] + usage['cached'] * (price.get('cached') or 0)) / 1e6


def _identity(row, profiles):
    profile = profiles.get(row['model'])
    provider = profile['provider'] if profile else row['model'].split(':')[0].split('-')[0]
    return provider, (profile['model'] if profile else row['model'])


def summary(rec, scope='workspace', id=None, since=None):
    if scope not in ('conversation', 'workspace', 'record'):
        raise ValueError('scope is conversation, workspace or record')
    if scope == 'conversation' and not id:
        raise ValueError('a conversation scope needs its id')
    state = _state(rec)
    ids = state['conv'].get(id, []) if scope == 'conversation' else list(state['runs'])
    profiles = {p['id']: p for p in execution.profiles(rec)}
    groups, total = {}, {'runs': 0, 'reported': 0, 'unknown': 0, 'input': 0, 'output': 0, 'cached': 0, 'requests': 0}
    for rid in ids:
        row = state['runs'][rid]
        if since and row['ts'] < since:
            continue
        provider, model = _identity(row, profiles)
        g = groups.setdefault((provider, model), {'provider': provider, 'model': model, 'runs': 0, 'reported': 0, 'unknown': 0, 'input': 0, 'output': 0,
                                                  'cached': 0, 'requests': 0, 'cost': None, 'currency': None, 'unpriced': 0,
                                                  'subscription': provider in SUBSCRIPTION})
        g['runs'] += 1
        u = row['usage']
        if u is None:
            g['unknown'] += 1
            continue
        g['reported'] += 1
        for k in ('input', 'output', 'cached', 'requests'):
            g[k] += u[k]
        if g['subscription']:
            continue
        day = row['ts'][:10]
        price = _price_for(state['prices'], row['model'], day) or (_price_for(state['prices'], model, day) if model != row['model'] else None)
        c = _cost(u, price)
        if c is None:
            g['unpriced'] += 1
        elif g['currency'] in (None, price['currency']):
            g['cost'] = (g['cost'] or 0) + c
            g['currency'] = price['currency']
        else:
            g['unpriced'] += 1
    for g in groups.values():
        g['cost_status'] = ('subscription' if g['subscription'] else 'unknown' if not g['reported'] else 'unpriced' if g['cost'] is None
                            else 'partial' if g['unpriced'] else 'priced')
        for k in total:
            total[k] += g[k]
    costs = {g['currency'] for g in groups.values() if g['cost'] is not None}
    total['cost'] = sum(g['cost'] for g in groups.values() if g['cost'] is not None) if len(costs) == 1 else None
    total['currency'] = next(iter(costs)) if len(costs) == 1 else None
    total['cost_complete'] = bool(groups) and all(g['subscription'] or g['cost_status'] == 'priced' for g in groups.values())
    out = {'scope': scope, 'id': id, 'since': since, 'total': total, 'models': sorted(groups.values(), key=lambda g: (g['provider'], g['model']))}
    if scope == 'conversation':
        out['context'] = _context(state, ids, profiles)
    return out


def _context(state, ids, profiles):
    """The newest run's context size against the model's context limit, both only as recorded; otherwise unknown."""
    for rid in reversed(ids):
        row = state['runs'][rid]
        profile = profiles.get(row['model'])
        limit = row.get('context_limit') or (profile or {}).get('context_limit')
        used = row.get('context_chars')
        if _n(used) is not None and _n(limit):
            return {'known': True, 'used': used, 'limit': limit, 'unit': 'characters', 'fraction': min(1.0, used / limit), 'run': rid}
        return {'known': False, 'limit': limit if _n(limit) else None, 'unit': 'characters', 'run': rid}
    return {'known': False, 'limit': None, 'unit': 'characters', 'run': None}
