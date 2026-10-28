"""Explicit notebook worker. Invoked after a human request; never on attachment.

Scratch execution isolates data, not the operating system. Only trusted notebooks may run.
"""
import hashlib
import json
from pathlib import Path
import sys
from . import notebook_coverage, notebook_trace

def run(request):
    root = Path(request['root']).resolve()
    if request['action'] == 'coverage':
        result = notebook_coverage.scan(root, src=request.get('src', 'src'), package=request.get('package'))
        previous = request.get('previous', {})
        from datetime import date
        state = notebook_coverage.update_state(previous, result, date.today().isoformat())
        return {'ok': True, 'coverage': result, 'ledger': state, 'note': 'A test file being present does not prove that tests ran or passed.'}
    path = request['path']
    file = (root / path).resolve()
    if not file.is_relative_to(root) or file.suffix != '.ipynb': raise ValueError('notebook leaves the source grant')
    if hashlib.sha256(file.read_bytes()).hexdigest() != request['revision']: raise ValueError('notebook changed since permission was recorded')
    approval = {'id': 'selected', 'path': path, 'approved_by': request['by'], 'approved_at': request.get('approved_at', ''), 'timeout': request['timeout'], 'groups': request.get('groups', []), 'inputs': [], 'max_input_mb': 1}
    approval['revision'] = request['revision']
    record = {'approved_notebooks': [approval]}
    result = notebook_trace.mutation_exercise(root, record, 'selected', request['mutation'], run=request.get('execute', False)) if request.get('mutation') else notebook_trace.trace_notebook(root, record, 'selected', run=request.get('execute', False))
    return {'ok': True, **result}

def main():
    try: result = run(json.load(sys.stdin))
    except Exception as exc: result = {'ok': False, 'error': str(exc)[:2000]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1
if __name__ == '__main__': raise SystemExit(main())
