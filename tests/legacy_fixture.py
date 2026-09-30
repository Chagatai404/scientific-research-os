"""Synthetic legacy vault modelled on real migration problems (no real data).

`build(root)` writes: many legacy notes with old labels, historical tutor answers
(correct, hinted, MCQ with no verdict, confidence ratings, an unanswered question),
a closed session with no demonstration, a session whose answer is already tracked,
one completed schema-1 record whose prerequisite has no record, a missing source
note and a course that has a project note but no course record.
Run `python tests/legacy_fixture.py OUT_DIR` to materialize it for inspection.
"""
from pathlib import Path
import sys

FENCE = '`' * 3
SESSIONS = 'Projects/AMS Demo/Tutor Sessions'


def session(topic, created, status, questions, refs='[]', extra=''):
    return (f'---\ntype: tutor-session\ntopic: "{topic}"\nproject: ams-demo\nstatus: {status}\n'
            f'created: "{created}"\nlearning_refs: {refs}\n---\n# {topic}\n\n## 3. Prerequisite probe\n\n{questions}\n'
            f'## 4. Dependency map\n\n{FENCE}mermaid\ngraph TD\n    V[Variance] --> C[Covariance]\n    C --> P[PCA]\n{FENCE}\n\n{extra}')


def q(n, topic, question, answer, verdict, status='ANSWERED'):
    return (f'### Q{n} — {topic} — `{status}`\n\n{question}\n\n**My answer:**\n\n> {answer}\n\n'
            f'- [ ] **Send this answer**\n\n{verdict}\n\n')


LEGACY_CONCEPTS = {
    'Variance': '---\ntype: concept\nstatus: solid\nlearning_state: solid\n---\n# Variance\n\n## Definition\n\nMean squared deviation.\n\n## Prerequisites\n\n- [[Mean]]\n',
    'Mean': '# Mean\n\nOld note without any frontmatter.\n',
    'Covariance': '---\ntype: concept\nstatus: learning\n---\n# Covariance\n\n## Definition\n\n## Prerequisites\n\n- [[ ]]\n',
    'Eigenvector': '---\ntype: concept\nstatus: understood\nlearning_state: retained\n---\n# Eigenvector\n\n## Definition\n\nA direction fixed by a linear map.\n\n## Prerequisites\n\n- [[Matrix]]\n\n## My current explanation\n',
    'PCA': '---\ntype: concept\nstatus: learning\nlearning_state: demonstrated\n---\n# PCA\n\n## Definition\n\nPrincipal directions of variance.\n\n## Prerequisites\n\n- [[Covariance]]\n',
    'Matrix': '---\ntype: concept\n---\n# Matrix\n',
}


def build(root: Path) -> Path:
    files = {
        'Projects/AMS Demo/AMS Demo.md': '---\ntype: project\nproject: ams-demo\ncourse: "stat-201"\n---\n# AMS Demo\n\nA project note; no course record exists for stat-201.\n',
        f'{SESSIONS}/2026-08-10 pca intro.md': session(
            'PCA intro', '2026-08-10 09:30', 'closed',
            q(1, 'Variance', 'What is variance?', 'Mean squared deviation from the mean. Confidence: 5/5', 'Correct.') +
            q(2, 'Covariance', 'Explain why covariance matrices are symmetric.', 'cov(x,y)=cov(y,x)',
              'Partially correct. Hint: look at the definition.') +
            q(3, 'Eigenvector', 'What is an eigenvector?', '', '', status='ACTIVE') +
            q(4, 'Orthogonality', 'Which pair is orthogonal?\nA) (1,0),(1,1)\nB) (1,0),(0,1)\nC) (1,1),(2,2)', 'B', ''),
            extra='## 6. Lesson log\n\n### Node 1 — PCA\n\nCorrect. PCA finds directions of maximal variance.\n\n'
                  'The learner understands PCA. See [[Source - Missing Paper]].\n'),
        f'{SESSIONS}/2026-08-15 variance recap.md': session(
            'Variance recap', '2026-08-15 18:00', 'closed', q(1, 'Variance', 'Define variance again.', '', '', status='ACTIVE')),
        f'{SESSIONS}/2026-08-20 gamma shape.md': session(
            'Gamma shape', '2026-08-20 10:00', 'closed',
            q(1, 'Shape', 'Explain the effect of the shape parameter.', 'It moves the peak away from zero.', 'Correct.'),
            refs='["probability.gamma-density"]'),
        'Learning/gamma-density.md': (
            '---\nlearning_schema: 1\nlearning_id: probability.gamma-density\ndomain: probability\nprojects: ["ams-demo"]\n'
            'courses: ["stat-201"]\nprerequisites: ["probability.density"]\nlearning_state: demonstrated\n---\n# Gamma density\n\n'
            '## Retrieval history\n\n| Date | Learning period | Timing | Method | Outcome | Assistance | Evidence | Next review |\n'
            '|---|---|---|---|---|---|---|---|\n'
            '| 2026-08-20 | gamma-intro | same-session | explanation | pass | none | [[2026-08-20 gamma shape#Q1]] | 2026-08-27 |\n'),
    }
    for name, text in LEGACY_CONCEPTS.items():
        files[f'Concepts/{name}.md'] = text
    for i in range(30):  # many old notes that must stay untracked
        files[f'Archive/old-{i:02d}.md'] = f'# Old note {i}\n\nlearning_state: solid\n' if i % 2 else f'---\ntype: concept\nstatus: solid\n---\n# Old {i}\n'
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


if __name__ == '__main__':
    print(build(Path(sys.argv[1])))
