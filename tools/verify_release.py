"""Check a release folder (or a GitHub release asset list JSON) against latest.yml.

Usage: python tools/verify_release.py <release-dir | assets.json>
For an assets.json, latest.yml must sit next to it (sha512 is then not re-checked).
"""
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

FEED = 'latest.yml'
INSTALLER = re.compile(r'^Research-OS-Setup-.+-.+\.exe$')


def parse_feed(text):
    files = []
    for line in text.splitlines():
        m = re.match(r'(\s*)(-\s*)?(url|sha512|size):\s*(.+?)\s*$', line)
        if not m or not m.group(1):
            continue  # only the indented entries under files:
        key, val = m.group(3), m.group(4).strip('\'"')
        if key == 'url':
            files.append({'url': val})
        elif files and key not in files[-1]:
            files[-1][key] = int(val) if key == 'size' else val
    return files


def verify_release(target):
    """Return a list of problems; an empty list means the release is complete."""
    p = Path(target)
    digest = None
    if p.is_file() and p.suffix == '.json':
        data = json.loads(p.read_text(encoding='utf8'))
        data = data.get('assets', data) if isinstance(data, dict) else data
        sizes = {a['name']: a.get('size') for a in data}
        feed_path = p.with_name(FEED)
    elif p.is_dir():
        sizes = {f.name: f.stat().st_size for f in p.iterdir() if f.is_file()}
        feed_path = p / FEED

        def digest(name):
            return base64.b64encode(hashlib.sha512((p / name).read_bytes()).digest()).decode()
    else:
        return [f'{target} is not a folder or asset list JSON']
    if FEED not in sizes or not feed_path.is_file():
        return [f'missing update feed {FEED}']
    problems = []
    if not any(INSTALLER.match(n) for n in sizes):
        problems.append('no installer (Research-OS-Setup-<version>-<arch>.exe) found')
    files = parse_feed(feed_path.read_text(encoding='utf8'))
    if not files:
        problems.append(f'{FEED} lists no files')
    for f in files:
        name = f['url']
        if name not in sizes:
            problems.append(f'{name} is in {FEED} but missing from the release')
            continue
        if 'size' in f and sizes[name] is not None and sizes[name] != f['size']:
            problems.append(f'{name}: size {sizes[name]} does not match {FEED} ({f["size"]})')
        if digest and 'sha512' in f and digest(name) != f['sha512']:
            problems.append(f'{name}: sha512 does not match {FEED}')
    return problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage: verify_release.py <release-dir | assets.json>')
        return 2
    problems = verify_release(argv[0])
    if problems:
        print('FAIL')
        for x in problems:
            print(' -', x)
        return 1
    print('PASS: release matches latest.yml')
    return 0


if __name__ == '__main__':
    sys.exit(main())
