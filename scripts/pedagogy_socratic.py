"""Pure, attempt-bound teaching advice. This never writes or awards evidence."""
from pedagogy_contract import digest


def project(entry, question, events=(), reviews=()):
    """Recommend help without disclosing any hint/solution text by default."""
    base = dict(available=False, evidence=False, assisted=False, level=0,
                solution=False, response_event_id=None, action='unavailable')
    if not isinstance(entry, dict) or not isinstance(question, dict) or entry.get('question_id') != question.get('id') or entry.get('question_sha256') != digest(question):
        return base
    if entry.get('tree') not in ('probe', 'check') or not isinstance(entry.get('hints'), list) or not entry['hints']:
        return base
    latest = None
    level, solution, assisted = 0, False, False
    for event in events:
        if event.get('question_id') != entry['question_id']:
            continue
        response = event.get('response')
        if not isinstance(response, dict):
            continue
        if event.get('type') == 'plan-answer' and response.get('tree') == entry['tree'] and event.get('event_id'):
            latest = event
            # Help can be revised, but an assisted history never becomes independent.
            level, solution = 0, False
        elif event.get('type') == 'pedagogy-help':
            expected = dict(entry_id=entry.get('id'), version=entry.get('version'), tree=entry['tree'],
                            question_sha256=entry['question_sha256'], prior_response_event_id=latest.get('event_id') if latest else None)
            if type(response.get('version')) is not int or set(response) != set(expected) | {'level'} or any(response.get(k) != v for k, v in expected.items()):
                continue
            value = response['level']
            if value == 'solution':
                solution, assisted = True, True
            elif type(value) is int and 1 <= value <= len(entry['hints']) and value <= level + 1:
                level, assisted = max(level, value), True
    review = None
    if latest:
        for item in reviews:
            if item.get('question_id') == entry['question_id'] and item.get('response_event_id') == latest['event_id']:
                review = item
    verdict = 'unanswered'
    if latest:
        # A raw numeric/choice key never claims to judge written reasoning.
        verdict = latest['response'].get('verdict', 'pending') if question.get('kind') != 'short' else 'pending'
        if review and review.get('verdict') in ('correct', 'incorrect', 'partially-correct'):
            criteria = review.get('criteria_met')
            verdict = review['verdict']
            if verdict == 'correct' and criteria is not None and (not isinstance(criteria, list) or not criteria or not all(v is True for v in criteria)):
                verdict = 'pending'
    action = 'await_review' if verdict == 'pending' else 'revise' if verdict in ('wrong', 'incorrect', 'partially-correct') else 'continue' if verdict == 'correct' else 'attempt'
    return dict(base, available=True, assisted=assisted, level=level, solution=solution,
                response_event_id=latest['event_id'] if latest else None, action=action, verdict=verdict)
