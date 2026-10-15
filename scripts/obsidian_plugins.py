"""Which Obsidian adapters a vault actually has, and what Research OS does with each (or without it).

Read-only and standard-library only. Detection reads two small configuration files and each plugin's manifest; it never
installs, enables, updates or contacts anything, and a vault without Obsidian simply reports every adapter as absent.
Nothing here is required: every use case has a built-in route, and what an adapter produces is a presentation or a
suggestion. It never establishes readiness, retention, scientific support or approval (see the ``authority`` of each entry).

What the files can show is limited and stated: a plugin is "enabled" because Obsidian's own list says so, "compatible"
only when the plugin's ``minAppVersion`` is known to be met, and none of it means the plugin was run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import re
import sys

CONSULTED = '2026-10-13'
MANIFEST_LIMIT = 64 * 1024
CONFIG_LIMIT = 1024 * 1024

STATES = ('enabled', 'installed-disabled', 'enabled-but-missing', 'invalid', 'absent', 'unknown', 'builtin', 'file-present')
USE_CASES = ('search', 'navigation', 'retention', 'visuals', 'audio', 'semantic')
INTEGRATIONS = ('used', 'bridged', 'native', 'builtin', 'not-integrated')


def _adapter(name, kind, plugin, role, integration, uses, fallback, authority, consulted=None, facts=()):
    return dict(name=name, kind=kind, plugin=plugin, role=role, integration=integration, uses=uses, fallback=fallback,
                authority=authority, consulted=consulted, facts=list(facts))


ADAPTERS = {
    'excalidraw': _adapter(
        'Excalidraw', 'community', 'obsidian-excalidraw-plugin', 'visuals', 'used',
        'Conceptual schematics are generated as .excalidraw.md files with scripts/excalidraw_schematic.py, registered as inspected '
        'schematics and embedded with a caption; the drawing also exports a clean SVG that sessions place inline.',
        'Static SVG schematics through scripts/visual_assets.py; the session needs no plugin to display them.',
        'A drawing is a schematic, never a quantitative plot or evidence; arrows and proportions imply no measurement.',
        dict(version='2.29.0', min_app='1.8.7', source='https://raw.githubusercontent.com/zsviczian/obsidian-excalidraw-plugin/master/manifest.json'),
        ['Manifest id obsidian-excalidraw-plugin; drawings are .excalidraw.md notes (frontmatter excalidraw-plugin: parsed).',
         'Compressed scenes (compressed-json) are not read by Research OS; uncompressed JSON scenes are.']),
    'breadcrumbs': _adapter(
        'Breadcrumbs', 'community', 'breadcrumbs', 'navigation', 'used',
        'New session, plan and dashboard notes get an up link to the project note, and the prerequisite trail is shown as explicit '
        'edges; vault_health.py reports any display link that disagrees with the canonical prerequisites.',
        'Plain wikilinks and the session navigation panel (prerequisites, earlier lessons) built from the context receipt.',
        'A Breadcrumbs path is navigation, not a dependency; implied or transitive edges establish nothing. The canonical list wins.',
        dict(version='4.22.1', min_app='1.14.0', source='https://raw.githubusercontent.com/SkepticMystic/breadcrumbs/master/manifest.json'),
        ['4.15.0 and later require Obsidian 1.13.0 or newer; Dataview has not been required since 4.14.0.',
         'Implied relations come from Implied Edge Builders and transitive rules, configured in the plugin, so leave them unconfigured for fields that mirror canonical relations.',
         'window.BCAPI is intentionally minimal and read-only (fields, field_groups, refresh, get_neighbours, create_list_index); '
         'Research OS does not consume it, because it would blur explicit and implied edges.']),
    'bases': _adapter(
        'Bases', 'core', 'bases', 'navigation', 'used',
        'Dashboards embed views of the shipped .base files over canonical frontmatter (research, knowledge frontier, visual assets).',
        'Plain Markdown lists produced by the research and knowledge CLIs.',
        'A Base is a read-only view; it never stores, computes or changes state and is not an editable ledger.',
        dict(source='https://obsidian.md/help/bases/syntax'),
        ['A .base file is YAML with filters, formulas, properties, summaries and views; registerBasesView (custom views) exists since Obsidian 1.10.0.']),
    'graphify': _adapter(
        'Graphify code graph', 'file', None, 'navigation', 'used',
        'An explicit code_refs path on a research record is annotated with the graph nodes of that file (research.py --graphify).',
        'The research CLI ignores a missing or unreadable graph.',
        'Import and call edges are not scientific dependencies; Research OS never runs Graphify.'),
    'omnisearch': _adapter(
        'Omnisearch', 'community', 'omnisearch', 'search', 'bridged',
        'vault_search.py --omnisearch asks the plugin\'s own local HTTP server (loopback only, opt-in in the plugin settings) and '
        'merges nothing into canonical state; results are leads to older explanations.',
        'vault_search.py lexical search over the vault\'s Markdown notes and session bridges.',
        'A search hit is a lead, never evidence that something was taught, established or verified.',
        dict(version='1.31.0', min_app='1.13.3', source='https://raw.githubusercontent.com/scambier/obsidian-omnisearch/master/manifest.json'),
        ['In-app API: omnisearch.search(query) returns a promise of ResultNoteApi (score, vault, path, basename, foundWords, matches, excerpt).',
         'Optional HTTP server, off by default: GET http://localhost:51361/search?q=..., desktop only, stops when Obsidian closes.',
         'The documentation calls the API experimental, so the result shape may change; the bridge validates what it receives.']),
    'spaced-repetition': _adapter(
        'Spaced Repetition', 'community', 'obsidian-spaced-repetition', 'retention', 'bridged',
        'plugin_exports.py cards writes practice cards from reviewed session questions into a generated note. The plugin\'s own '
        'scheduling stays inside the plugin; Research OS neither reads nor copies it.',
        'The canonical retention schedule (retention.py) and the session page.',
        'Answering a card is not demonstration; scheduling inside the plugin never replaces the learning ledger or its due dates.',
        dict(version='1.15.4', min_app='1.2.8', source='https://raw.githubusercontent.com/st3v3nmw/obsidian-spaced-repetition/master/manifest.json'),
        ['Scheduling data is stored in the note files themselves (HTML comments for cards, frontmatter for notes) and decks come from tags.',
         'The exact comment syntax was not confirmed against current documentation, so Research OS writes cards without any scheduling data.']),
    'smart-connections': _adapter(
        'Smart Connections', 'community', 'smart-connections', 'semantic', 'bridged',
        'Related notes the researcher finds with the plugin can be recorded as suggestions (vault_search.py suggest); they are '
        'kept apart from canonical records and always labelled as unverified.',
        'vault_search.py related (lexical similarity), also a suggestion only.',
        'Semantic similarity is not a prerequisite, a dependency, support or agreement; a suggestion never becomes canonical by itself.',
        dict(version='4.7.2', min_app='1.8.7', source='https://raw.githubusercontent.com/brianpetro/obsidian-smart-connections/main/manifest.json'),
        ['No documented public API was found, and the project is source-available under its own license, so Research OS does not read its '
         'local embeddings or internals.']),
    'strange-new-worlds': _adapter(
        'Strange New Worlds', 'community', 'obsidian42-strange-new-worlds', 'navigation', 'not-integrated',
        'Nothing: it only shows reference counts beside text for a human reader.',
        'Native Backlinks and the outgoing-links pane.',
        'A count of references is not a measure of importance or dependence.',
        dict(min_app='1.7.2', source='https://community.obsidian.md/plugins/obsidian42-strange-new-worlds'),
        ['No programmatic interface was found; it is a reading aid, so installing it is the researcher\'s choice and nothing is built on it.']),
    'text-to-speech': _adapter(
        'Text to speech', 'builtin', None, 'audio', 'builtin',
        'Session pages offer a Listen control that reads a section with the browser\'s speech synthesis, local voices first; '
        'mathematics is read from its TeX source in words, or announced as an equation to read on the page.',
        'The page is fully readable without audio; with no speech synthesis or voices the control says so.',
        'Narration is a rendering of the text on the page and adds no content.',
        dict(source='https://community.obsidian.md/plugins/note-reader'),
        ['Community readers differ: some use a local Web Speech engine, one depends on an unofficial Microsoft endpoint, one needs a paid '
         'ElevenLabs key, one is macOS-only. None is required or bundled.']),
    'backlinks': _adapter(
        'Backlinks', 'core', 'backlink', 'navigation', 'native',
        'Works on the session Markdown bridge as it is: the bridge keeps the original wikilinks and headings.',
        'None needed.', 'Backlinks list mentions; a mention is not a dependency.'),
    'bookmarks': _adapter(
        'Bookmarks', 'core', 'bookmarks', 'navigation', 'native',
        'A researcher can bookmark a session bridge or a heading; the bridge keeps stable headings.',
        'None needed.', 'A bookmark records attention, not understanding.'),
    'outline': _adapter(
        'Outline', 'core', 'outline', 'navigation', 'native',
        'Shows the headings of the session bridge note; the page\'s own contents panel shows the same structure.',
        'The page\'s contents panel.', 'An outline is a view of headings.'),
    'page-preview': _adapter(
        'Page preview', 'core', 'page-preview', 'navigation', 'native',
        'Previews notes linked from bridge notes; links inside a sandboxed session page open as host-mediated requests instead.',
        'Host-mediated note links (new tab).', 'A preview is a view.'),
    'canvas': _adapter(
        'Canvas', 'core', 'canvas', 'navigation', 'bridged',
        'plugin_exports.py canvas writes a generated .canvas of canonical prerequisites (JSON Canvas 1.0) for a researcher to arrange.',
        'The prerequisite list in the context brief and the session navigation panel.',
        'A canvas is a drawing of the recorded prerequisites; arranging or editing it changes nothing canonical.',
        dict(source='https://jsoncanvas.org/spec/1.0/'),
        ['JSON Canvas 1.0: nodes (text, file, link, group) and edges with fromNode/toNode.']),
}

# What each use case prefers when usable, in order, and the built-in route that is always there.
PREFERENCE = {
    'search': (['omnisearch'], 'vault_search.py lexical search over notes and session bridges'),
    'navigation': (['breadcrumbs', 'bases', 'backlinks', 'outline', 'bookmarks', 'page-preview', 'canvas', 'graphify'],
                   'the session navigation panel and explicit prerequisites from the context receipt'),
    'retention': (['spaced-repetition'], 'the canonical retention schedule (retention.py)'),
    'visuals': (['excalidraw'], 'static SVG schematics placed inline (visual_assets.py)'),
    'audio': (['text-to-speech'], 'reading the page'),
    'semantic': (['smart-connections'], 'vault_search.py related (lexical), shown as a suggestion'),
}


def version_tuple(value):
    """(major, minor, patch) from '1.13.7' or '1.14.4-beta'; None if it does not start like a version."""
    match = re.match(r'\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', str(value or ''))
    return tuple(int(part or 0) for part in match.groups()) if match else None


def _read_json(path, limit=CONFIG_LIMIT):
    """(value, problem). A missing file is not a problem to report here; an unreadable one is."""
    try:
        if not path.is_file():
            return None, 'missing'
        raw = path.read_bytes()
        if len(raw) > limit:
            return None, 'too large to read'
        return json.loads(raw.decode('utf-8-sig')), None
    except (OSError, ValueError) as exc:
        return None, f'unreadable ({type(exc).__name__})'


def _enabled_community(config):
    value, problem = _read_json(config / 'community-plugins.json')
    if problem == 'missing':
        return [], None
    if problem or not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None, problem or 'not a list of plugin IDs'
    return value, None


def _core_plugins(config):
    """{id: enabled}. Accepts the object form (id -> bool) and a list of enabled IDs; falls back to the migration file."""
    for name in ('core-plugins.json', 'core-plugins-migration.json'):
        value, problem = _read_json(config / name)
        if problem == 'missing':
            continue
        if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, bool) for k, v in value.items()):
            return value, None
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return {item: True for item in value}, None
        return None, f'{name}: unexpected structure' if not problem else f'{name}: {problem}'
    return {}, None


def app_version_hint(config_dir=None):
    """(version, source) inferred from the update package Obsidian leaves in its configuration folder, else None.

    This is an inference from a file name such as obsidian-1.14.4.asar, not a query of the running application.
    """
    candidates = [Path(config_dir)] if config_dir else [Path(os.environ.get('APPDATA', '')) / 'obsidian', Path.home() / '.config/obsidian',
                                                         Path.home() / 'Library/Application Support/obsidian']
    best = None
    for folder in candidates:
        try:
            names = [p.name for p in folder.glob('obsidian-*.asar')] if folder.is_dir() else []
        except OSError:
            continue
        for name in names:
            found = version_tuple(name[len('obsidian-'):-len('.asar')])
            if found and (best is None or found > best[0]):
                best = (found, name)
    if best is None:
        return None
    return '.'.join(map(str, best[0])), f'inferred from the update package name {best[1]}'


def _manifest(config, plugin):
    folder = config / 'plugins' / plugin
    if not folder.is_dir():
        return None, 'no plugin folder'
    value, problem = _read_json(folder / 'manifest.json', MANIFEST_LIMIT)
    if problem:
        return None, f'manifest {problem}'
    if not isinstance(value, dict) or value.get('id') != plugin:
        return None, 'manifest does not name this plugin'
    return value, None


def _compatibility(manifest, app_version):
    minimum = version_tuple((manifest or {}).get('minAppVersion'))
    current = version_tuple(app_version)
    if minimum is None or current is None:
        return 'unchecked', 'the plugin\'s minimum Obsidian version or the running version is unknown'
    if current < minimum:
        return 'incompatible', f"requires Obsidian {manifest['minAppVersion']} or newer; this is {app_version}"
    return 'compatible', f"needs Obsidian {manifest['minAppVersion']}; this is {app_version}"


def _entry(key, spec, **fields):
    entry = dict(adapter=key, name=spec['name'], kind=spec['kind'], plugin=spec['plugin'], role=spec['role'], integration=spec['integration'],
                 state='absent', usable=False, listed=None, version=None, min_app=None, compatibility='unchecked', reasons=[])
    entry.update(fields)
    return entry


def detect(vault, *, obsidian_version=None, project_root=None):
    """One entry per adapter: state, whether it is usable, version and compatibility, and why. Never raises on a damaged config."""
    vault = Path(vault).expanduser()
    config = vault / '.obsidian'
    community, community_problem = _enabled_community(config)
    core, core_problem = _core_plugins(config)
    has_config = config.is_dir()
    result = {}
    for key, spec in ADAPTERS.items():
        if spec['kind'] == 'builtin':
            result[key] = _entry(key, spec, state='builtin', usable=True, reasons=['provided by the session page itself; needs no plugin'])
        elif spec['kind'] == 'file':
            root = Path(project_root).expanduser() if project_root else vault
            present = (root / 'graphify-out/graph.json').is_file()
            result[key] = _entry(key, spec, state='file-present' if present else 'absent', usable=present,
                                 reasons=['graphify-out/graph.json found; it is read only for explicit code_refs'] if present
                                 else ['no graphify-out/graph.json; the research CLI ignores it'])
        elif spec['kind'] == 'core':
            if core is None:
                result[key] = _entry(key, spec, state='unknown', reasons=[f'core plugin list unreadable: {core_problem}'])
            elif spec['plugin'] in core:
                on = core[spec['plugin']]
                result[key] = _entry(key, spec, state='enabled' if on else 'installed-disabled', usable=on,
                                     reasons=['enabled in the vault\'s core plugin list' if on else 'present but switched off in Obsidian settings'])
            else:
                result[key] = _entry(key, spec, state='absent', reasons=[
                    'not in the vault\'s core plugin list' + ('' if has_config else ' (no .obsidian folder: not an Obsidian vault?)')])
        else:
            plugin = spec['plugin']
            manifest, why = _manifest(config, plugin)
            if community is None:
                result[key] = _entry(key, spec, state='unknown', reasons=[f'community-plugins.json: {community_problem}'])
                continue
            listed = plugin in community
            if manifest is None and not listed and why == 'no plugin folder':
                result[key] = _entry(key, spec, listed=False, reasons=['not installed' + ('' if has_config else ' (no .obsidian folder: not an Obsidian vault?)')])
                continue
            if manifest is None:
                state = 'enabled-but-missing' if listed and why == 'no plugin folder' else 'invalid'
                result[key] = _entry(key, spec, state=state, listed=listed, reasons=[f'{why}; treated as not usable'])
                continue
            compatibility, compat_reason = _compatibility(manifest, obsidian_version)
            enabled = listed
            usable = enabled and compatibility != 'incompatible'
            reasons = ['enabled in community-plugins.json' if enabled else 'installed but not enabled', compat_reason]
            result[key] = _entry(key, spec, state='enabled' if enabled else 'installed-disabled', usable=usable, listed=listed,
                                 version=manifest.get('version'), min_app=manifest.get('minAppVersion'),
                                 compatibility=compatibility, reasons=reasons)
    return result


def plan(detected):
    """Per use case: what will be used given what is usable, the built-in fallback, and whether this is the degraded route."""
    rows = []
    for case in USE_CASES:
        preferred, fallback = PREFERENCE[case]
        usable = [key for key in preferred if detected.get(key, {}).get('usable')]
        skipped = [key for key in preferred if key not in usable]
        row = dict(use_case=case, providers=usable, fallback=fallback, degraded=not usable,
                   unavailable=[dict(adapter=key, state=detected[key]['state'], compatibility=detected[key]['compatibility'])
                                for key in skipped if key in detected],
                   instructions=[ADAPTERS[key]['uses'] for key in usable] or [f'Use {fallback}.'],
                   authority=[ADAPTERS[key]['authority'] for key in usable or preferred if key in ADAPTERS])
        rows.append(row)
    return rows


def summary(vault, *, obsidian_version=None, project_root=None, config_dir=None):
    """Compact, serializable detection for a session brief: what is usable and what falls back, with the version source stated."""
    version, source = (obsidian_version, 'given') if obsidian_version else (app_version_hint(config_dir) or (None, None))
    detected = detect(vault, obsidian_version=version, project_root=project_root)
    return dict(app_version=version, app_version_source=source,
                note='Detected from vault files only; Research OS did not run Obsidian or any plugin.',
                adapters={key: {k: entry[k] for k in ('state', 'usable', 'version', 'compatibility')} for key, entry in detected.items()},
                plan=plan(detected))


def render(report):
    """Short Markdown for an agent's brief."""
    lines = ['Detected from vault files only (Research OS did not run Obsidian or any plugin)'
             + (f"; Obsidian {report['app_version']} ({report['app_version_source']})." if report['app_version'] else '; the Obsidian version is unknown, so plugin compatibility is unchecked.')]
    for row in report['plan']:
        if row['degraded']:
            lines.append(f"- {row['use_case']}: built-in route ({row['fallback']})")
        else:
            lines.append(f"- {row['use_case']}: {', '.join(row['providers'])}, with the built-in route as fallback")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=['report', 'plan', 'registry'])
    parser.add_argument('--vault', type=Path, default=Path.cwd())
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--obsidian-version', help='the running Obsidian version (otherwise inferred from its update package, if found)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.command == 'registry':
        print(json.dumps(ADAPTERS, indent=2, ensure_ascii=False))
        return 0
    report = summary(args.vault, obsidian_version=args.obsidian_version, project_root=args.project_root)
    detected = detect(args.vault, obsidian_version=report['app_version'], project_root=args.project_root)
    if args.json:
        print(json.dumps(dict(report, detail=detected), indent=2, ensure_ascii=False))
        return 0
    if args.command == 'plan':
        print('\n'.join(render(report)))
        return 0
    print('\n'.join(render(report)[:1]))
    for key, entry in detected.items():
        mark = 'usable' if entry['usable'] else 'not usable'
        print(f"- {entry['name']} [{entry['kind']}]: {entry['state']}, {mark}" + (f", v{entry['version']}" if entry['version'] else '')
              + f" ({entry['integration']}): {'; '.join(entry['reasons'])}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
