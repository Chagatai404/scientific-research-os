"""Adaptive commands run from both helper inventories without repository imports."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts')]
import install
from support_p0_text_flow import build, ingest, SESSION
import plan_evidence


class AdaptiveHelperBundles(unittest.TestCase):
    def test_session_and_graph_helper_closures_execute_real_adaptive_commands(self):
        source = Path(install.__file__).parent
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / 'fixture'
            vault.mkdir()
            fixture = build(vault)
            answer = 'Mean 1, squared centred distances 9; adding a constant shifts the centre equally.'
            ingest(vault, [dict(event_id='original-check', type='plan-answer', question_id='novel',
                response=dict(tree='check', answer=answer, verdict='pending'))],
                dict(question_id='novel', verdict='correct', criteria_met=[True, True], reviewed_by='synthetic bundle reviewer'))
            mapping = dict(fixture['evidence_mapping'], response_event_id='original-check',
                           response_sha256=plan_evidence.response_digest(answer))
            mapping_file = root / 'mapping.json'
            mapping_file.write_text(json.dumps(mapping), encoding='utf-8')
            choices = root / 'choices.json'
            choices.write_text('{"objective":"exam","language":"tr","time_minutes":15}', encoding='utf-8')
            for name, inventory in [('session', set(install.SESSION_HELPERS)),
                                    ('graph', set(install.SESSION_HELPERS) | set(install.GRAPH_HELPERS))]:
                self.assertTrue({'learning_preferences.py', 'plan_evidence.py'} <= inventory)
                scripts = root / name / 'scripts'
                scripts.mkdir(parents=True)
                for helper in inventory:
                    shutil.copyfile(source / helper, scripts / helper)
                def command(helper, *args):
                    result = subprocess.run([sys.executable, '-S', '-B', str(scripts / helper), *args],
                        cwd=root, env={**os.environ, 'PYTHONPATH': '', 'PYTHONUTF8': '1'},
                        capture_output=True, text=True, encoding='utf-8', timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return json.loads(result.stdout)
                smoke = subprocess.run([sys.executable, '-S', '-B', '-c',
                    'import sys;sys.path.insert(0,sys.argv[1]);import pedagogy_contract,pedagogy_budget,pedagogy_socratic,pedagogy_explanations,pedagogy_practice,pedagogy_source_comparison,pedagogy_terms,pedagogy_bloom,pedagogy_analogies,pedagogy_roles,tutor_session;print("P1 imports OK")', str(scripts)],
                    cwd=root, env={**os.environ,'PYTHONPATH':''},capture_output=True,text=True,timeout=60)
                self.assertEqual(smoke.returncode,0,smoke.stderr)
                self.assertIn('P1 imports OK',smoke.stdout)
                saved = command('html_sessions.py', '--root', str(vault), 'preferences', SESSION, '--source', str(choices))
                self.assertEqual(saved['preferences']['language'], 'tr')
                self.assertNotIn('policy', saved)
                proposal = command('plan_evidence.py', '--root', str(vault), '--session', SESSION,
                    '--question', 'novel', '--mapping', str(mapping_file), '--learning-root', fixture['learning'])
                self.assertTrue(proposal['proposable'])
                self.assertEqual(proposal['response_event_id'], 'original-check')
                self.assertEqual(proposal['retention']['status'], 'not-assessed')


if __name__ == '__main__':
    unittest.main()
