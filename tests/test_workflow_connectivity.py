"""Every workflow piece stays reachable from what is actually installed.

Each skill names protocols, helper scripts and agents. A rename, a new session
format or an installer change can silently disconnect one of them, so this test
installs the skills and checks that everything a skill points to is present
where that skill will look for it.
"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install

REFERENCE = re.compile(r"\b([A-Z0-9_.]+(?:PROTOCOL|POLICY|FORMAT|LADDER|MODEL|PLANNING|MAPS|LIBRARY|RENDERING)\.md)\b")
SCRIPT = re.compile(r"scripts/([a-z_]+\.py)")
SESSION_COMMANDS = ("context", "add-question", "review", "wait", "answer", "append", "create", "update", "validate")


class WorkflowConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.installed = Path(cls.temp.name) / "skills"
        with redirect_stdout(io.StringIO()):
            install.install_skills(cls.installed, False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def skills(self):
        return sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").exists())

    def test_every_named_protocol_exists_and_is_installed_with_the_skill(self):
        for skill in self.skills():
            for name in set(REFERENCE.findall((skill / "SKILL.md").read_text(encoding="utf-8"))):
                with self.subTest(skill=skill.name, reference=name):
                    self.assertTrue((ROOT / "references" / name).is_file())
                    self.assertTrue((self.installed / skill.name / "references" / name).is_file())

    def test_protocols_only_point_at_existing_protocols(self):
        for document in sorted((ROOT / "references").glob("*.md")):
            for name in set(REFERENCE.findall(document.read_text(encoding="utf-8"))):
                with self.subTest(document=document.name, reference=name):
                    self.assertTrue((ROOT / "references" / name).is_file())

    def test_every_helper_a_skill_or_its_protocols_name_is_installed_with_it(self):
        for skill in self.skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            named = set(SCRIPT.findall(text))
            # The shared session protocol is part of every skill's instructions.
            named |= set(SCRIPT.findall((ROOT / "references/HTML_SESSION_PROTOCOL.md").read_text(encoding="utf-8")))
            for script in named:
                if not (ROOT / "scripts" / script).is_file():
                    continue  # Project-local paths such as a project's own scripts are not ours to bundle.
                with self.subTest(skill=skill.name, script=script):
                    self.assertTrue((self.installed / skill.name / "scripts" / script).is_file())

    def test_installed_resume_brief_runs_from_every_skill(self):
        # `context` imports research and knowledge in-process; a missing module would degrade it silently.
        for skill in self.skills():
            with self.subTest(skill=skill.name):
                result = subprocess.run([sys.executable, "-c", "import html_sessions, research, knowledge, ontology"],
                                        cwd=self.installed / skill.name / "scripts", capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_skill_loads_memory_and_uses_the_live_session_loop(self):
        for skill in self.skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertIn("references/HTML_SESSION_PROTOCOL.md", text)
                self.assertIn("html_sessions.py context", text)
        protocol = (ROOT / "references/HTML_SESSION_PROTOCOL.md").read_text(encoding="utf-8")
        for required in ("research.py context", "knowledge.py", "tutor_plan.py", "visuals.py", "add-question", "review", "wait"):
            self.assertIn(required, protocol)

    def test_documented_session_commands_exist(self):
        help_text = subprocess.run([sys.executable, str(ROOT / "scripts/html_sessions.py"), "--help"],
                                   capture_output=True, text=True, check=True).stdout
        for command in SESSION_COMMANDS:
            self.assertIn(command, help_text)

    def test_named_agents_exist(self):
        agents = {p.stem for p in (ROOT / "agents").glob("*.md")}
        for skill in self.skills():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            for agent in re.findall(r"`([a-z]+(?:-[a-z]+)+)` agent|the ([a-z]+(?:-[a-z]+)+) agent", text):
                name = next(a for a in agent if a)
                if name.endswith(("reviewer", "scout", "verifier", "auditor", "visualizer")):
                    with self.subTest(skill=skill.name, agent=name):
                        self.assertIn(name, agents)

    def test_session_templates_no_longer_use_the_checkbox_loop(self):
        # Legacy readers still parse historical checkbox notes; new sessions submit in the HTML view.
        for template in sorted((ROOT / "assets/obsidian").glob("*_Session.md")):
            with self.subTest(template=template.name):
                self.assertNotIn("Send this answer", template.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
