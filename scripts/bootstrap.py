"""Candidate-only bootstrap of legacy learning material (dry-run report).

Reads historical tutor-session notes and proposes learning IDs, prerequisite edges,
project membership, retention-target suggestions and retrieval-history rows.
Nothing is written to the vault: a mention is not an attempt, a tutor explanation
is not learner evidence, an unanswered question is not evidence, confidence is not
an outcome, and every proposal needs human review before it becomes a record.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys

import knowledge

QUESTION = re.compile(r'^### (Q\d+)\b\s*(?:[—-]\s*)?(.*?)\s*$')
STATUS = re.compile(r'`(ACTIVE|ANSWERED)`')
OPTION = re.compile(r'^\s*(?:[-*]\s*)?\(?[A-Da-d][.)]\s+\S')
TEMPLATE_LABELS = {'Known foundation', 'Next concept', 'Target understanding'}
VERDICTS = [('partial', re.compile(r'^(partially|partly|mostly|almost)\b', re.I)),
            ('pass', re.compile(r'^(correct|right|yes)\b', re.I)),
            ('fail', re.compile(r'^(incorrect|not quite|not correct|wrong|no)\b', re.I))]


def fields(text: str) -> tuple[dict, str]:
    """Top-level scalar/list frontmatter only; anything else stays unread."""
    lines = text.lstrip('﻿').replace('\r\n', '\n').split('\n')
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        return {}, '\n'.join(lines)
    end = lines.index('---', 1)
    data = {}
    for line in lines[1:end]:
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*):\s*(.*)', line)
        if match:
            raw = match[2].strip()
            try:
                data[match[1]] = json.loads(raw) if raw[:1] in ('[', '"') else raw.strip("'")
            except ValueError:
                data[match[1]] = raw
    return data, '\n'.join(lines[end + 1:])


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def blocks(body: str) -> list[dict]:
    """Question blocks in the live probe section; fenced template examples are ignored."""
    lines = knowledge.unfenced_lines(body)
    result, current = [], None
    for line in lines:
        if line.startswith('## '):
            current = None
            continue
        match = QUESTION.match(line)
        if match:
            status = STATUS.search(line)
            current = {'id': match[1], 'topic': STATUS.sub('', match[2]).strip(' —-`'),
                       'status': status[1] if status else None, 'lines': []}
            result.append(current)
        elif line.startswith('### '):
            current = None
        elif current is not None:
            current['lines'].append(line)
    return result


def parse_block(block: dict) -> dict:
    lines = block['lines']
    marker = next((i for i, x in enumerate(lines) if x.strip().startswith('**My answer:**')), None)
    question = '\n'.join(lines[:marker if marker is not None else len(lines)]).strip()
    answer, verdict = [], []
    if marker is not None:
        i = marker + 1
        while i < len(lines) and not lines[i].lstrip().startswith('>') and not lines[i].strip():
            i += 1
        while i < len(lines) and lines[i].lstrip().startswith('>'):
            answer.append(lines[i].lstrip()[1:].strip())
            i += 1
        verdict = [x.strip() for x in lines[i:] if x.strip() and not re.match(r'- \[[ xX]\]', x.strip())]
    return dict(block, question=question, answer=' '.join(x for x in answer if x).strip(),
                verdict=' '.join(verdict).strip())


def classify(question: str) -> str:
    text = question.lower()
    if sum(bool(OPTION.match(x)) for x in question.splitlines()) >= 2:
        return 'mcq'
    if 'derive' in text:
        return 'derivation'
    if 'explain' in text or re.search(r'\bwhy\b', text):
        return 'explanation'
    return 'recall'


def outcome_of(verdict: str) -> str | None:
    for name, pattern in VERDICTS:
        if pattern.match(verdict):
            return name
    return None


def analyse(root: Path) -> dict:
    root = root.resolve()
    tracked = knowledge.discover(root, date.max)
    recorded = ' '.join(a.evidence for n in tracked.nodes.values() for a in n.attempts)
    sessions, candidates, diagnostics, edges = [], [], [], []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(x for x in folders if not x.startswith('.') and not (Path(directory) / x).is_symlink())
        for name in sorted(files):
            file = Path(directory) / name
            if not name.endswith('.md') or file.is_symlink():
                continue
            try:
                meta, body = fields(file.read_text(encoding='utf-8-sig'))
            except (OSError, UnicodeError) as exc:
                diagnostics.append(f'{name}: {exc}')
                continue
            if meta.get('type') != 'tutor-session':
                continue
            rel = file.relative_to(root).as_posix()
            when = re.match(r'\d{4}-\d{2}-\d{2}', str(meta.get('created', '')))
            refs = meta.get('learning_refs') if isinstance(meta.get('learning_refs'), list) else []
            refs = [r for r in refs if isinstance(r, str) and knowledge.ID.fullmatch(r)]
            topic = str(meta.get('topic') or file.stem)
            if len(refs) == 1:
                capability, basis = refs[0], 'declared'
            elif refs:
                capability, basis = None, 'ambiguous: several learning_refs declared'
            else:
                capability, basis = f'review-needed.{slug(topic) or slug(file.stem)}', 'proposed from topic; choose domain and ID'
            project = str(meta.get('project') or '')
            has_project = bool(knowledge.ID.fullmatch(project))
            session = {'path': rel, 'status': meta.get('status'), 'topic': topic, 'capability': capability,
                       'capability_basis': basis, 'projects': [project] if has_project else [],
                       'retention_target_suggestion': 'working' if has_project else None,
                       'already_tracked': capability in tracked.nodes if capability else False,
                       'questions': 0, 'answered': 0, 'eligible': 0}
            if not when:
                diagnostics.append(f'{rel}: no usable created date; attempts cannot be dated')
            section = re.search(r'## 4\. Dependency map.*?(?=\n## |\Z)', body, re.S)
            if section:
                labels = dict(re.findall(r'(\w+)\[([^\]]+)\]', section[0]))
                for a, b in re.findall(r'(\w+)(?:\[[^\]]*\])?\s*-->\s*(\w+)', section[0]):
                    pair = (labels.get(a, a), labels.get(b, b))
                    if not set(pair) & TEMPLATE_LABELS:
                        edges.append({'session': rel, 'prerequisite': pair[0], 'dependent': pair[1],
                                      'status': 'proposed; requires human review'})
            for raw in blocks(body):
                q = parse_block(raw)
                session['questions'] += 1
                if not q['answer']:
                    continue  # unanswered question: no evidence
                session['answered'] += 1
                method = classify(q['question'])
                outcome = outcome_of(q['verdict'])
                hinted = bool(re.search(r'\bhint', q['verdict'], re.I))
                confidence = re.search(r'confidence\s*[:=]\s*([^\n.;]+)', q['answer'], re.I)
                evidence = f"[[{file.stem}#{q['id']}]]"
                duplicate = f"[[{file.stem}#{q['id']}" in recorded
                reason = ('already recorded in a tracked learning record' if duplicate else
                          'no verdict recorded; outcome unknown' if outcome is None else
                          'no usable session date' if not when else '')
                row = None
                if not reason:
                    row = (f"| {when[0]} | bootstrap-{slug(file.stem)} | same-session | {method} | {outcome} | "
                           f"{'hinted' if hinted else 'none'} | {evidence} | |")
                    if capability in tracked.nodes and tracked.nodes[capability].meta['learning_schema'] == 2:
                        row += ' legacy | legacy | |'
                    session['eligible'] += 1
                candidates.append({
                    'session': rel, 'question': q['id'], 'topic': q['topic'], 'capability': capability,
                    'method': method, 'outcome': outcome,
                    'assistance': 'hinted' if hinted else 'none',
                    'assistance_basis': 'a hint is mentioned in the recorded verdict' if hinted else 'no hint recorded; verify',
                    'confidence_note': confidence[1].strip() if confidence else None,
                    'row': row, 'eligible': row is not None, 'reason': reason or 'candidate; requires human review'})
            if str(meta.get('status')) == 'closed' and not session['eligible']:
                session['note'] = 'closed with no new candidate attempt (none recorded, or already in a tracked record); no evidence is inferred'
            sessions.append(session)
    return {'dry_run': True, 'sessions': sessions, 'candidates': candidates, 'dependency_edges': edges,
            'tracked_capabilities': len(tracked.nodes), 'legacy_notes': tracked.legacy, 'diagnostics': diagnostics}


def render(report: dict) -> str:
    lines = ['# Legacy learning bootstrap (dry run)', '',
             'Proposals only. Nothing was written to the vault and no state was inferred.',
             'Retrieval rows are same-session; mentions, tutor explanations, unanswered questions',
             'and confidence ratings are not evidence. Review every row before adding it to a record.', '']
    for s in report['sessions']:
        lines += [f"## {s['path']}", f"- capability: {s['capability'] or '(choose)'} — {s['capability_basis']}",
                  f"- projects: {', '.join(s['projects']) or 'none'}; retention target suggestion: "
                  f"{s['retention_target_suggestion'] or 'unspecified (choose)'}",
                  f"- questions: {s['questions']}; answered: {s['answered']}; candidate rows: {s['eligible']}"]
        if s.get('note'):
            lines.append('- ' + s['note'])
        for c in (c for c in report['candidates'] if c['session'] == s['path']):
            lines.append(f"  - {c['question']} [{c['method']}]: {c['reason']}" + (f"\n    `{c['row']}`" if c['row'] else ''))
        lines.append('')
    if report['dependency_edges']:
        lines.append('## Proposed prerequisite edges (unmapped to IDs)')
        lines.extend(f"- {e['prerequisite']} -> {e['dependent']} ({e['session']})" for e in report['dependency_edges'])
    lines += ['', f"Tracked capabilities: {report['tracked_capabilities']}; legacy notes: {report['legacy_notes']}"]
    lines.extend(f'- WARNING {d}' for d in report['diagnostics'])
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--write-report', type=Path, help='explicit new file for the report; never overwritten')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if not args.root.is_dir():
        parser.error('root is not a directory')
    report = analyse(args.root)
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n' if args.json else render(report)
    if args.write_report:
        if args.write_report.exists():
            parser.error('refusing to overwrite an existing file')
        args.write_report.write_text(text, encoding='utf-8')
    else:
        print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
