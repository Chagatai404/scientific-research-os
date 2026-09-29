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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from common import parse_frontmatter
from vault import render_template

class InstallationTests(unittest.TestCase):
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


    def test_visualize_installs_for_both_targets_without_site_packages(self):
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
            skill = self.tmp_path / f"{target}-skills/visualize"
            self.assertEqual((skill / "SKILL.md").read_bytes(), (ROOT / "skills/visualize/SKILL.md").read_bytes())
            self.assertEqual((skill / "references/VISUALIZATION_PROTOCOL.md").read_text(encoding="utf-8"), canonical)
        result = subprocess.run(
            [sys.executable, "-S", "-B", str(ROOT / "scripts/validate.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


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
        self.assertTrue((vault / "Templates/13_Knowledge_Graph.md").exists())
