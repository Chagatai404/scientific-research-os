"""Check explicitly declared question plans; not a natural-language concept detector."""


def question_issues(plan: dict, established: set[str]) -> list[str]:
    required = {'TESTS', 'ASSUMES', 'INTRODUCES'}
    if not isinstance(plan, dict) or set(plan) != required:
        return ['question requires TESTS, ASSUMES, INTRODUCES']
    for key in ('TESTS', 'ASSUMES'):
        if not isinstance(plan[key], list) or any(not isinstance(x, str) or not x.strip() for x in plan[key]):
            return [f'{key}: expected concept IDs']
    if not plan['TESTS']:
        return ['TESTS: intended capability required']
    definitions = plan['INTRODUCES']
    if not isinstance(definitions, dict) or any(not isinstance(k, str) or not k.strip()
            or not isinstance(v, str) or not v.strip() for k, v in definitions.items()):
        return ['INTRODUCES: definitions required before use']
    # Intentionally probing an assumption belongs in TESTS, with scoring separated.
    unresolved = set(plan['ASSUMES']) - established - set(plan['TESTS']) - definitions.keys()
    return [f'unresolved assumption: {key}' for key in sorted(unresolved)]


def terminology_issues(terms: list[dict], established: set[str], tested: set[str] | None = None) -> list[str]:
    """Inspect declared first occurrences; caller must inspect real wording/order."""
    issues = []
    tested = tested or set()
    for term in terms:
        if (not isinstance(term, dict) or not all(isinstance(term.get(k), str) and term[k].strip()
                for k in ('name', 'concept', 'kind', 'use')) or
                term['kind'] not in {'term', 'abbreviation', 'symbol', 'method', 'theorem', 'model', 'algorithm'} or
                term['use'] not in {'required', 'label'}):
            issues.append('invalid terminology declaration')
            continue
        if term['use'] == 'label' or term['concept'] in established or term['concept'] in tested:
            continue
        if term['kind'] == 'abbreviation' and not str(term.get('expansion', '')).strip():
            issues.append(f"{term['name']}: expand abbreviation before use")
        if not isinstance(term.get('definition'), str) or not term['definition'].strip():
            issues.append(f"{term['name']}: define before use")
    return issues


def scoped_question_issues(plan: dict, established: set[str], *, scope: str,
                          dimension: str, method: str, context: str = '',
                          independent_example: bool = False) -> list[str]:
    """Check declared scope alongside the existing question contract, never wording."""
    from knowledge import SCOPES, validate_attempt_scope
    issues = question_issues(plan, established)
    if scope not in SCOPES:
        return issues + ['new questions require an explicit conceptual/transfer/project_application scope']
    try:
        validate_attempt_scope(scope, dimension, context, method)
    except ValueError as exc:
        issues.append(str(exc))
    if scope == 'transfer' and independent_example is not True:
        issues.append('transfer requires an explicitly independent example')
    return issues
