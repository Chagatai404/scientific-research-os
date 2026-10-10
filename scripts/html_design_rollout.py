"""Backed-up v0.8.5 visual rollout. Dry run by default; never install templates.

Installed code must match a known upstream baseline or the requested repository
version. Unexpected local edits stop preflight before any installation changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import html_sessions as sessions

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(data):
    return data.replace(b'\r\n', b'\n')


def rollout(vault, providers, backup, apply=False):
    vault, backup = vault.resolve(), backup.resolve()
    targets = []
    names = ('theme.css', 'session.css', 'runtime.js', 'session.js')
    for name in names:
        targets.append((vault / '.research-os/runtime' / name, 'assets/html-runtime/' + name))
    for provider in providers:
        for runtime in sorted(provider.glob('*/assets/html-runtime')):
            for name in names:
                targets.append((runtime / name, 'assets/html-runtime/' + name))
            targets.append((runtime.parents[1] / 'scripts/html_sessions.py', 'scripts/html_sessions.py'))
    targets.append((vault / '.obsidian/plugins/research-os-html/main.js', 'extensions/obsidian-html/main.js'))
    known = {}
    changes = []
    for index, (target, source) in enumerate(targets):
        after = (ROOT / source).read_bytes()
        if source not in known:
            known[source] = {normalized(after)}
            for ref in ('e50692b', '188ce3d', 'b473868'):
                known[source].add(normalized(subprocess.check_output(['git', 'show', f'{ref}:{source}'], cwd=ROOT)))
        before = target.read_bytes()
        if normalized(before) not in known[source]:
            raise ValueError(f'Locally modified installation; refusing overwrite: {target}')
        if before != after:
            changes.append({'target': str(target), 'source': source, 'backup': str(backup / 'installed' / f'{index:03d}-{target.name}'), 'before_sha256': digest(before), 'after_sha256': digest(after)})
    canonical = sorted((vault / '01 Projects').rglob('*.state.json'))
    protected = {}
    refresh = []
    for data in canonical:
        md = data.with_name(data.name[:-len('.state.json')] + '.md')
        relative = md.relative_to(vault).as_posix()
        sessions.load_session(vault, relative)
        for path in (md, data):
            protected[str(path)] = digest(path.read_bytes())
        refresh.append(sessions.refresh_projection(vault, relative, backup / 'sessions'))
    templates = []
    for directory in (vault / '90 Templates', vault / 'Templates'):
        if directory.exists():
            templates.extend(directory.rglob('*.md'))
    for path in templates:
        protected[str(path)] = digest(path.read_bytes())
    result = {'dry_run': not apply, 'backup': str(backup), 'runtime_count': (len(targets) - 1 - sum(1 for _, source in targets if source == 'scripts/html_sessions.py')) // 4,
              'session_count': len(canonical), 'template_count': len(templates), 'changes': changes,
              'projections': refresh, 'protected_sha256': protected}
    if apply:
        if backup.exists():
            raise ValueError('Use a fresh backup directory')
        # Back up every installed file and write the recovery manifest first.
        for change in changes:
            target = Path(change['target'])
            if digest(target.read_bytes()) != change['before_sha256']:
                raise ValueError(f'Installation changed during preflight: {target}')
            sessions._write(Path(change['backup']), target.read_bytes())
        sessions._write(backup / 'manifest.json', sessions._json(result))
        for change in changes:
            sessions._write(Path(change['target']), (ROOT / change['source']).read_bytes())
        for row in refresh:
            sessions.refresh_projection(vault, str(Path(row['path']).with_suffix('.md')), backup / 'sessions', True)
        for path, expected in protected.items():
            if digest(Path(path).read_bytes()) != expected:
                raise ValueError(f'Protected content changed: {path}')
        result['protected_verified'] = True
        result['status'] = 'complete'
        sessions._write(backup / 'manifest.json', sessions._json(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True, type=Path)
    parser.add_argument('--provider-root', action='append', default=[], type=Path)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(rollout(args.vault, args.provider_root, args.backup, args.apply), indent=2))


if __name__ == '__main__':
    main()
