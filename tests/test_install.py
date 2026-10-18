"""Exercise deployed instructions, not just source-document wording."""
from pathlib import Path
import sys
import tomllib
import tempfile
import unittest
from contextlib import redirect_stdout
import io
import json
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from common import parse_frontmatter
from vault import render_template

class InstallationTests(unittest.TestCase):
    def test_defense_skill_runs_standalone_and_symmetrically_for_both_providers(self):
        outcomes = []
        for provider in ('claude', 'codex'):
            base = self.tmp_path / f'{provider}-defense'
            with redirect_stdout(io.StringIO()):
                install.install_skills(base, False)
            scripts = base / 'defend-research/scripts'
            self.assertEqual((scripts / 'defense.py').read_bytes(), (ROOT / 'scripts/defense.py').read_bytes())
            project = self.tmp_path / f'{provider}-presentation'
            shutil.copytree(ROOT / 'examples/defense', project)
            generated = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'examples/defense/demo.py'),
                                        '--root', str(project), '--output', 'target.json'],
                                       cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            command = [sys.executable, '-S', '-B', str(scripts / 'defense.py')]
            modes = [('project', 'target.json'), ('ownership', 'ownership.json'), ('viva', 'target.json')]
            for mode, source in modes:
                result = subprocess.run(command + [mode, '--root', str(project), '--input', source, '--as-of', '2026-10-08'],
                                        cwd=self.tmp_path, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                data = json.loads(result.stdout)
                if mode == 'project':
                    outcomes.append([(row['scientific_support']['state'], row['personal_defensibility']) for row in data['claims']])
                    self.assertEqual(outcomes[-1][4], ('UNCERTAIN', 'UNKNOWN'))
                elif mode == 'ownership':
                    self.assertEqual(data['ownership'][0]['state'], 'OPEN_UNKNOWN')
                else:
                    self.assertEqual(data['action'], 'ask_one_question')
                    self.assertEqual(data['claim_id'], 'T-2')
            self.assertEqual((base / 'defend-research/references/DEFENSE_PROTOCOL.md').read_bytes(),
                             (ROOT / 'references/DEFENSE_PROTOCOL.md').read_bytes())
        self.assertEqual(*outcomes)

    def test_interruptible_tutoring_runs_standalone_in_both_provider_bundles(self):
        outcomes = []
        for provider in ('claude', 'codex'):
            base = self.tmp_path / f'{provider}-tutoring'
            with redirect_stdout(io.StringIO()):
                install.install_skills(base, False)
            scripts = base / 'tutor/scripts'
            self.assertEqual((scripts / 'tutor_session.py').read_bytes(), (ROOT / 'scripts/tutor_session.py').read_bytes())
            project = self.tmp_path / f'{provider}-lesson'
            shutil.copytree(ROOT / 'examples/tutoring', project)
            command = [sys.executable, '-S', '-B', str(scripts / 'tutor_session.py'), '--root', str(project)]
            result = subprocess.run(command + ['--input', 'session.json', '--output', 'checkpoint.json'],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            restarted = subprocess.run(command + ['--input', 'checkpoint.json'], cwd=self.tmp_path,
                                       capture_output=True, text=True)
            self.assertEqual(result.stdout, restarted.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report['budget']['used'], 4)
            self.assertEqual(report['branches'], [])
            outcomes.append(report)
            result = subprocess.run([sys.executable, '-S', '-B', str(scripts / 'knowledge.py'), '--root', str(project),
                                     '--capability', 'box.tool', '--json', '--as-of', '2026-10-02'],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['target']['mastery']['project_application']['tool_operation']['state'], 'unknown')
            result = subprocess.run([sys.executable, '-S', '-B', str(scripts / 'tutor_plan.py'), '--root', str(project),
                                     '--capability', 'box.method', '--as-of', '2026-10-02'],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['next']['action'], 'capability_repair')
        self.assertEqual(*outcomes)

    def test_tasks_run_standalone_and_symmetrically_in_both_bundles(self):
        outcomes = []
        for provider in ('claude', 'codex'):
            base = self.tmp_path / f'{provider}-tasks'
            install.install_skills(base, False)
            helper = base / 'research-session/scripts/tasks.py'
            self.assertEqual(helper.read_bytes(), (ROOT / 'scripts/tasks.py').read_bytes())
            project = self.tmp_path / f'{provider}-task-project'
            shutil.copytree(ROOT / 'examples/tasks', project)
            generated = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'examples/tasks/demo.py'),
                                        '--root', str(project), '--output', 'plan.json'], cwd=self.tmp_path,
                                       capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            command = [sys.executable, '-S', '-B', str(helper), '--root', str(project)]
            for args in (['plan', '--input', 'plan.json', '--apply'], ['start', 'scout'], ['start', 'verify'], ['start', 'visual']):
                result = subprocess.run(command + args, cwd=self.tmp_path, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(command + ['status'], cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = json.loads(result.stdout)['tasks']
            outcomes.append({row['task_id']: row['state'] for row in rows})
            self.assertEqual(list(outcomes[-1].values()).count('RUNNING'), 3)
            result = subprocess.run(command + ['cancel', 'scout', '--acknowledge-stopped'], cwd=self.tmp_path,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            states = {r['task_id']: r['state'] for r in json.loads(result.stdout)['tasks']}
            self.assertEqual(states['scout'], 'CANCELLED')
        self.assertEqual(*outcomes)

    def test_access_boundary_runs_symmetrically_without_site_packages(self):
        outcomes = []
        for provider in ('claude', 'codex'):
            base = self.tmp_path / f'{provider}-access'
            install.install_skills(base, False)
            helper = base / 'research-session/scripts/paper_access.py'
            self.assertEqual(helper.read_bytes(), (ROOT / 'scripts/paper_access.py').read_bytes())
            library, inbox = self.tmp_path / provider / 'library', self.tmp_path / provider / 'inbox'
            result = subprocess.run([sys.executable, '-S', '-B', str(helper), '--root', str(library),
                                     '--inbox', str(inbox), '--input', str(ROOT / 'examples/access/request.json')],
                                    cwd=self.tmp_path, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outcome = json.loads(result.stdout)
            self.assertEqual(outcome['record']['failure_reason'], 'manual-required')
            self.assertFalse(outcome['record']['saved'])
            self.assertFalse(library.exists())
            outcomes.append(result.stdout)
        self.assertEqual(*outcomes)

    def test_literature_checker_runs_symmetrically_without_repository_or_site_packages(self):
        results = []
        for provider in ('claude', 'codex'):
            base = self.tmp_path / f'{provider}-literature'
            install.install_skills(base, False)
            helper = base / 'research-session/scripts/literature_check.py'
            self.assertEqual(helper.read_bytes(), (ROOT / 'scripts/literature_check.py').read_bytes())
            command = [sys.executable, '-S', '-B', str(helper), '--root', str(ROOT / 'examples/literature'),
                       '--input', 'literature.json']
            result = subprocess.run(command + ['--facts-only'], cwd=self.tmp_path,
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            view = json.loads(result.stdout)
            self.assertEqual([item['atom']['claim_id'] for item in view['facts']], ['C-1'])
            self.assertEqual(len(view['qualified']), 3)
            self.assertEqual(len(view['papers']), 3)
            results.append(result.stdout)
            result = subprocess.run(command + ['--handoff', 'C-2'], cwd=self.tmp_path,
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            handoff = json.loads(result.stdout)
            self.assertNotIn('verification_status', handoff['claim'])
            self.assertNotIn('notes', handoff['claim'])
        self.assertEqual(*results)

    def test_compute_helpers_and_packs_are_standalone_and_provider_symmetric(self):
        expected = {"geant4", "pytorch", "sklearn", "pennylane", "qiskit", "root-scikit-hep"}
        for target in ("claude", "codex"):
            base = self.tmp_path / target
            install.install_skills(base, False)
            for name in install.COMPUTE_SKILLS:
                skill = base / name
                helper = skill / "scripts/scientific_tools.py"
                self.assertEqual(helper.read_bytes(), (ROOT / "scripts/scientific_tools.py").read_bytes())
                # Run from outside both checkout and skill, with site packages disabled.
                result = subprocess.run([sys.executable, "-S", "-B", str(helper), "list"],
                                        cwd=self.tmp_path, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({p["id"] for p in json.loads(result.stdout)}, expected)
                for tool in expected:
                    self.assertEqual((skill / "extensions/scientific-tools" / tool / "GUIDE.md").read_bytes(),
                                     (ROOT / "extensions/scientific-tools" / tool / "GUIDE.md").read_bytes())
            for name in ("pytorch", "sklearn", "pennylane", "qiskit", "root", "scikit-hep"):
                self.assertFalse((base / name).exists())
            result = subprocess.run([sys.executable, "-S", "-B", str(base / "geant4/scripts/scientific_tools.py"),
                                     "manifest", "--experiment", "temporary", "--repo", str(self.tmp_path)],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = self.tmp_path / f"{target}-manifest.json"
            path.write_text(result.stdout, encoding="utf-8")
            result = subprocess.run([sys.executable, "-S", "-B", str(base / "geant4/scripts/computational_manifest.py"), str(path)],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["declared"], {})

    def test_compute_agent_contracts_are_identical_and_self_contained(self):
        claude, codex = self.tmp_path / "claude", self.tmp_path / "codex"
        install.install_agents_claude(claude, False)
        install.install_agents_codex(codex, False)
        for role, protocols in install.COMPUTE_AGENTS.items():
            _, claude_body = parse_frontmatter((claude / f"{role}.md").read_text(encoding="utf-8"))
            codex_body = tomllib.loads((codex / f"{role}.toml").read_text(encoding="utf-8"))["developer_instructions"]
            self.assertEqual(claude_body.strip(), codex_body.strip())
            for name in ("COMPUTATIONAL_PROTOCOL.md", "SOURCE_POLICY.md", *protocols):
                self.assertIn((ROOT / "references" / name).read_text(encoding="utf-8").strip(), claude_body)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp_path = Path(temporary.name)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_installed_skills_have_current_shared_references(self):
        tmp_path = self.tmp_path
        base = tmp_path / "skills"
        install.install_skills(base, False)
        # Reinstallation must replace stale policy copies too.
        stale = base / "tutor" / "references" / "LEARNING_PROTOCOL.md"
        stale.write_text("obsolete", encoding="utf-8")
        install.install_skills(base, False)
        for skill in (ROOT / "skills").iterdir():
            if not (skill / "SKILL.md").is_file():
                continue
            assert (base / skill.name / "SKILL.md").read_bytes() == (skill / "SKILL.md").read_bytes()
            for reference in (ROOT / "references").glob("*.md"):
                assert (base / skill.name / "references" / reference.name).read_bytes() == reference.read_bytes()


    def test_both_agent_formats_preserve_roles_and_bundle_canonical_policy(self):
        tmp_path = self.tmp_path
        claude, codex = tmp_path / "claude", tmp_path / "codex"
        install.install_agents_claude(claude, False)
        install.install_agents_codex(codex, False)
        policy = (ROOT / "references" / "AGENT_POLICY.md").read_text(encoding="utf-8")
        research = (ROOT / "references" / "RESEARCH_PROTOCOL.md").read_text(encoding="utf-8")
        boundaries = research[research.index("## Blocker / relevance triage"):research.index("## Scientific invariants")]
        for source in (ROOT / "agents").glob("*.md"):
            meta, role = parse_frontmatter(source.read_text(encoding="utf-8"))
            installed_meta, claude_body = parse_frontmatter((claude / source.name).read_text(encoding="utf-8"))
            config = tomllib.loads((codex / f'{meta["name"]}.toml').read_text(encoding="utf-8"))
            assert installed_meta == meta
            assert config["name"] == meta["name"]
            for body in (claude_body, config["developer_instructions"]):
                assert role.strip() in body
                assert policy in body
                assert boundaries.strip() in body
                if meta["name"] in {"literature-scout", "source-verifier", "visualizer"}:
                    assert (ROOT / "references" / "SOURCE_POLICY.md").read_text(encoding="utf-8") in body
                if meta["name"] == "visualizer":
                    assert (ROOT / "references" / "VISUALIZATION_PROTOCOL.md").read_text(encoding="utf-8") in body
                if meta["name"] in {"literature-scout", "source-verifier", "adversarial-reviewer"}:
                    compact = (ROOT / "references/EVIDENCE_FORMAT.md").read_text(encoding="utf-8").split("## Storage and tooling", 1)[0]
                    self.assertIn(compact.strip(), body)
                    self.assertNotIn("## Derivations", body)

    def test_installed_evidence_helper_runs_without_repository_or_packages(self):
        base = self.tmp_path / "skills"
        install.install_skills(base, False)
        for name in ("research-session", "research-review"):
            helper = base / name / "scripts/validate_evidence.py"
            self.assertEqual(helper.read_bytes(), (ROOT / "scripts/validate_evidence.py").read_bytes())
            result = subprocess.run(
                [sys.executable, "-S", str(helper), str(ROOT / "examples/evidence"), "--markdown", "--facts-only"],
                cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("EXACT_SUPPORT", result.stdout)


    def test_workflow_skills_install_for_both_targets_without_site_packages(self):
        """Exercise actual target routing with third-party packages unavailable."""
        config = {"install": {
            "claude_skills": str(self.tmp_path / "claude-skills"),
            "claude_agents": str(self.tmp_path / "claude-agents"),
            "codex_skills": str(self.tmp_path / "codex-skills"),
            "codex_agents": str(self.tmp_path / "codex-agents"),
        }}
        program = (
            "import json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import install\n"
            "config = json.loads(sys.argv[2])\n"
            "target = sys.argv[3]\n"
            "install.load_config = lambda: config\n"
            "sys.argv = ['install.py', '--target', target]\n"
            "install.main()\n"
        )
        canonical = (ROOT / "references/VISUALIZATION_PROTOCOL.md").read_text(encoding="utf-8")
        for target in ("claude", "codex"):
            result = subprocess.run(
                [sys.executable, "-S", "-B", "-c", program, str(ROOT / "scripts"), json.dumps(config), target],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            skill = self.tmp_path / f"{target}-skills/science-visualize"
            self.assertEqual((skill / "SKILL.md").read_bytes(), (ROOT / "skills/science-visualize/SKILL.md").read_bytes())
            self.assertEqual((skill / "references/VISUALIZATION_PROTOCOL.md").read_text(encoding="utf-8"), canonical)
            latex = self.tmp_path / f"{target}-skills/notes-to-latex"
            self.assertEqual((latex / "SKILL.md").read_bytes(), (ROOT / "skills/notes-to-latex/SKILL.md").read_bytes())
            self.assertEqual((latex / "references/LATEX_TRANSCRIPTION_PROTOCOL.md").read_bytes(),
                             (ROOT / "references/LATEX_TRANSCRIPTION_PROTOCOL.md").read_bytes())
            course = self.tmp_path / f"{target}-skills/course-study"
            self.assertEqual((course / "SKILL.md").read_bytes(), (ROOT / "skills/course-study/SKILL.md").read_bytes())
            for name in ("COURSE_LEARNING_PROTOCOL.md", "LEARNING_PROTOCOL.md"):
                self.assertEqual((course / "references" / name).read_bytes(), (ROOT / "references" / name).read_bytes())

            graph = self.tmp_path / f"{target}-skills/tutor/scripts"
            result = subprocess.run(
                [sys.executable, '-S', '-B', str(graph / 'knowledge.py'), '--root', str(ROOT / 'examples/ontology'),
                 '--concept', 'box-counting', '--json', '--as-of', '2026-10-02'],
                cwd=self.tmp_path, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['nodes']), 2)
            result = subprocess.run(
                [sys.executable, '-S', '-B', str(graph / 'tutor_plan.py'), '--root', str(ROOT / 'examples/ontology'),
                 '--block', 'block-9', '--focus', 'box-counting', '--as-of', '2026-10-02'],
                cwd=self.tmp_path, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)['next']
            self.assertEqual(decision['action'], 'prerequisite_probe')
            self.assertEqual(decision['concept'], 'scale-invariance')
            self.assertEqual((graph.parent / 'references/TUTOR_PLANNING.md').read_bytes(),
                             (ROOT / 'references/TUTOR_PLANNING.md').read_bytes())
            result = subprocess.run([sys.executable, '-S', '-B', str(graph / 'migrate_learning.py'), '--help'],
                                    cwd=self.tmp_path, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            library_config = self.tmp_path / f'{target}-papers.toml'
            library_config.write_text('[paper_library]\nroot = "unused-library"\n', encoding='utf-8')
            manifest = self.tmp_path / f'{target}-papers.json'
            manifest.write_text(json.dumps([{'title': 'Offline fixture', 'other_id': 'fixture',
                                            'source_url': 'https://example.org/fixture', 'screening': 'found'}]), encoding='utf-8')
            spec = self.tmp_path / f'{target}-visual.json'
            spec.write_text(json.dumps({'need': 'geometry', 'goal': 'Explain counted cells'}), encoding='utf-8')
            commands = [
                ['retention.py', '--root', str(ROOT / 'examples/ontology'), '--domain', 'mathematics', '--as-of', '2026-10-02'],
                ['math_notes.py', str(ROOT / 'assets/obsidian/01_Concept.md')],
                ['visual_intent.py', '--spec', str(spec)],
                ['knowledge_maps.py', '--root', str(ROOT / 'examples/ontology'), '--as-of', '2026-10-02'],
                ['paper_library.py', '--config', str(library_config), '--input', str(manifest)],
            ]
            for helper, *args in commands:
                self.assertEqual((graph / helper).read_bytes(), (ROOT / 'scripts' / helper).read_bytes())
                result = subprocess.run([sys.executable, '-S', '-B', str(graph / helper), *args],
                                        cwd=self.tmp_path, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, f'{target}/{helper}: {result.stderr}')
            self.assertFalse((self.tmp_path / 'unused-library').exists())

        result = subprocess.run(
            [sys.executable, "-S", "-B", str(ROOT / "scripts/validate.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_status_reports_content_drift_not_modification_time(self):
        base = self.tmp_path / 'status-skills'
        with redirect_stdout(io.StringIO()):
            install.install_skills(base, False)
        self.assertEqual(set(install.skill_status(base).values()), {'current'})
        stale = base / 'tutor/SKILL.md'
        stale.write_text(stale.read_text(encoding='utf-8') + '\nlocal edit\n', encoding='utf-8')
        # An old timestamp on identical content is still current.
        import os
        os.utime(base / 'derive/SKILL.md', (1, 1))
        state = install.skill_status(base)
        self.assertEqual(state['tutor'], 'drifted')
        self.assertEqual(state['derive'], 'current')
        # Matching SKILL.md and version labels do not cover the executable bundle.
        (base / 'derive/scripts/html_sessions.py').write_text('# stale helper\n')
        (base / 'course-study/assets/html-runtime/stages.js').unlink()
        (base / 'study-source/extensions/obsidian-html/main.js').write_text('// old host\n')
        state = install.skill_status(base)
        for name in ('derive', 'course-study', 'study-source'):
            self.assertEqual(state[name], 'drifted')

    def test_renamed_skill_is_retired_not_deleted_and_foreign_directories_are_left(self):
        base = self.tmp_path / 'rename-skills'
        legacy = base / 'visualize'
        (legacy / 'references').mkdir(parents=True)
        (legacy / 'SKILL.md').write_text('---\nname: visualize\n---\nold\n', encoding='utf-8')
        (legacy / 'references/SOURCE_POLICY.md').write_text('policy', encoding='utf-8')
        with redirect_stdout(io.StringIO()):
            install.install_skills(base, True)
        self.assertTrue(legacy.is_dir(), 'dry run must not move anything')
        with redirect_stdout(io.StringIO()):
            install.install_skills(base, False)
        self.assertFalse(legacy.exists())
        self.assertTrue(any((base / '.research-os-retired').rglob('SKILL.md')))
        self.assertTrue((base / 'science-visualize/SKILL.md').is_file())
        foreign = self.tmp_path / 'foreign-skills'
        (foreign / 'visualize').mkdir(parents=True)
        (foreign / 'visualize/SKILL.md').write_text('---\nname: visualize\n---\nsomeone else\n', encoding='utf-8')
        with redirect_stdout(io.StringIO()):
            install.install_skills(foreign, False)
        self.assertTrue((foreign / 'visualize/SKILL.md').is_file(), 'not a Research OS install: left alone')

    def test_dry_run_creates_no_files(self):
        tmp_path = self.tmp_path
        target = tmp_path / "not-created"
        install.install_skills(target / "skills", True)
        install.install_agents_claude(target / "claude", True)
        install.install_agents_codex(target / "codex", True)
        assert not target.exists()

    def test_obsidian_templates_install_without_touching_existing_notes(self):
        vault = self.tmp_path / "vault"
        vault.mkdir()
        note = vault / "Existing concept.md"
        original = "---\nstatus: solid\n---\nMy existing understanding.\n"
        note.write_text(original, encoding="utf-8")
        cfg = {"vault": {"path": str(vault), "templates_dir": "Templates"}}
        install.install_obsidian(cfg, True)
        self.assertFalse((vault / "Templates").exists())
        install.install_obsidian(cfg, False)
        self.assertEqual(note.read_text(encoding="utf-8"), original)
        for source in (ROOT / "assets/obsidian").glob("*.md"):
            installed = vault / "Templates" / source.name
            self.assertEqual(installed.read_bytes(), source.read_bytes())
            rendered = render_template(installed.read_text(encoding="utf-8"), "Sample topic")
            for placeholder in ("{{title}}", "{{date}}", "{{time}}"):
                self.assertNotIn(placeholder, rendered)
        quiz, _ = parse_frontmatter((vault / "Templates/03_Quizbook_Topic.md").read_text(encoding="utf-8"))
        for key in ("learning_id", "first_learned", "last_retrieval", "next_review"):
            self.assertEqual(quiz[key], "")
        self.assertEqual(quiz["learning_state"], "unknown")
        for name in ("13_Knowledge_Graph.md", "14_Learning_Goal.md", "15_Course.md", "16_Course_Session.md"):
            self.assertTrue((vault / "Templates" / name).exists())
