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
