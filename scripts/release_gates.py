"""Run every release gate and report what actually executed.

A gate that cannot run (missing browser, no Node) is reported as SKIPPED with
its reason, never as passed. Exit status is nonzero if any executed gate fails
or, with --strict, if any gate was skipped.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CHROME_CANDIDATES = (
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
)
BROWSER_TESTS = ('html-runtime-browser.js', 'html-browser-e2e.cjs', 'html-components-browser.cjs',
                 'html-design-browser.cjs', 'html-gallery-browser.cjs', 'html-navigation-browser.cjs',
                 'html-tutor-browser.cjs', 'html-visual-parity.cjs')
NODE_TESTS = ('html-host.test.js', 'html-runtime-unit.js')
SESSION_INPUT_TESTS = {'html-navigation-browser.cjs'}
# Needs material the repository cannot supply; reported as SKIPPED, never as passed.
EXTERNAL_INPUT_TESTS = {'html-visual-parity.cjs': 'requires the externally supplied recitation reference page and a real session (see docs/v0.8.5-html-visual-parity.md)'}


def find_playwright():
    if os.environ.get('ROS_PLAYWRIGHT'):
        return os.environ['ROS_PLAYWRIGHT']
    npm = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@playwright/cli/node_modules/playwright'
    return str(npm) if npm.is_dir() else None


def find_chrome():
    if os.environ.get('ROS_BROWSER'):
        return os.environ['ROS_BROWSER']
    return next((c for c in CHROME_CANDIDATES if Path(c).exists()), None)


def run(name, command, env=None, cwd=ROOT, timeout=900):
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                              encoding='utf-8', errors='replace')
        status = 'PASS' if done.returncode == 0 else 'FAIL'
        tail = (done.stdout + done.stderr).strip().splitlines()[-6:]
    except subprocess.TimeoutExpired:
        status, tail = 'FAIL', [f'timed out after {timeout}s']
    return dict(gate=name, status=status, seconds=round(time.monotonic() - started, 1), tail=tail)


def skipped(name, reason):
    return dict(gate=name, status='SKIPPED', seconds=0, tail=[reason])


def fixture_session(vault):
    """Generate a disposable session for browser tests that take a rendered page as input.

    The vault must live outside the repository: validate.py scans the tree for sessions.
    """
    sys.path.insert(0, str(ROOT / 'scripts'))
    import html_sessions
    # Sections must be taller than the viewport so scrolling decides which one is current.
    body = '\n\n'.join(f'Paragraph {n} of the section, with $x_{n}^2$ and enough prose to occupy vertical space.' for n in range(1, 25))
    source = '# Gate session\n\n' + '\n\n'.join(f'## Section {i}\n\n{body}' for i in range(1, 6)) + '\n'
    html_sessions.create_session(vault, 'gate.md', source, title='Gate session')
    return vault / 'gate.html'


def gates(only=None):
    env = dict(os.environ, PYTHONUTF8='1')
    node = shutil.which('node')
    wanted = lambda name: only is None or any(part in name for part in only)
    if wanted('python'):
        yield run('python-unittest', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'], env)
    if wanted('validate'):
        yield run('repository-validate', [sys.executable, 'scripts/validate.py'], env)
    for test in NODE_TESTS:
        if wanted('node:' + test):
            yield run('node:' + test, [node, 'tests/' + test], env) if node else skipped('node:' + test, 'node not found')
    playwright, chrome = find_playwright(), find_chrome()
    for test in BROWSER_TESTS:
        name = 'browser:' + test
        if not wanted(name):
            continue
        if not (node and playwright and chrome):
            missing = [n for n, v in (('node', node), ('playwright', playwright), ('chrome', chrome)) if not v]
            yield skipped(name, 'missing ' + ', '.join(missing))
            continue
        if test in EXTERNAL_INPUT_TESTS:
            yield skipped(name, EXTERNAL_INPUT_TESTS[test])
            continue
        with tempfile.TemporaryDirectory(prefix='ros-gate-') as vault:
            arguments = [str(fixture_session(Path(vault)))] if test in SESSION_INPUT_TESTS else []
            yield run(name, [node, 'tests/' + test, *arguments], {**env, 'ROS_PLAYWRIGHT': playwright, 'ROS_BROWSER': chrome})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', action='append', help='substring filter on gate names (repeatable)')
    parser.add_argument('--strict', action='store_true', help='treat SKIPPED gates as failures')
    parser.add_argument('--json', type=Path, help='write the machine-readable report here')
    args = parser.parse_args(argv)
    results = []
    for result in gates(args.only):
        results.append(result)
        print(f"{result['status']:8} {result['gate']} ({result['seconds']}s)", flush=True)
        if result['status'] != 'PASS':
            for line in result['tail']:
                print('         ' + line)
    counts = {s: sum(r['status'] == s for r in results) for s in ('PASS', 'FAIL', 'SKIPPED')}
    print('SUMMARY ' + ', '.join(f'{k}={v}' for k, v in counts.items()))
    if args.json:
        args.json.write_text(json.dumps(dict(results=results, counts=counts), indent=2), encoding='utf-8')
    return 1 if counts['FAIL'] or (args.strict and counts['SKIPPED']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
