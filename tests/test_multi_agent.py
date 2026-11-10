import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "bin/aunx-decompose.mjs"
AGENTS = {
    "claude": (".claude/skills/decompose", ".claude/skills/decompose"),
    "codex": (".agents/skills/decompose", ".agents/skills/decompose"),
    "gemini": (".gemini/skills/decompose", ".gemini/skills/decompose"),
    "cursor": (".cursor/skills/decompose", ".cursor/skills/decompose"),
    "opencode": (".config/opencode/skills/decompose", ".opencode/skills/decompose"),
    "copilot": (".copilot/skills/decompose", ".github/skills/decompose"),
    "qwen": (".qwen/skills/decompose", ".qwen/skills/decompose"),
}
MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
    ".cursor-plugin/plugin.json",
    ".cursor-plugin/marketplace.json",
    "gemini-extension.json",
)


class MultiAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.project = Path(self.temp.name) / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home))

    def run_cli(self, *args, installer=INSTALLER):
        return subprocess.run(["node", str(installer), *args], cwd=self.project,
                              env=self.env, capture_output=True, text=True)

    def assert_skill(self, destination):
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertTrue((destination / "scripts/decompose.py").is_file())
        self.assertFalse(list(destination.rglob("__pycache__")))

    def assert_one_line(self, result, destination):
        lines = (result.stdout + result.stderr).splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(str(destination), lines[0])

    def test_each_agent_user_install(self):
        for agent, (user, _) in AGENTS.items():
            with self.subTest(agent=agent):
                result = self.run_cli("install", "--agent", agent)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_skill(self.home / user)
                self.assert_one_line(result, self.home / user)
                self.assertEqual(list(self.project.iterdir()), [])

    def test_each_agent_project_install(self):
        for agent, (_, project) in AGENTS.items():
            with self.subTest(agent=agent):
                result = self.run_cli("install", "--agent", agent, "--project")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_skill(self.project / project)
                self.assert_one_line(result, self.project / project)
                self.assertEqual(list(self.home.iterdir()), [])

    def test_default_claude_install(self):
        for flags, base in (((), self.home), (("--project",), self.project)):
            with self.subTest(flags=flags):
                result = self.run_cli("install", *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_skill(base / AGENTS["claude"][0])
                self.assert_one_line(result, base / AGENTS["claude"][0])

    def test_all_installs_seven_destinations(self):
        for flags, base, index in (((), self.home, 0), (("--project",), self.project, 1)):
            with self.subTest(flags=flags):
                result = self.run_cli("install", "--agent", "all", *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()), 7)
                self.assertEqual(result.stderr, "")
                for paths in AGENTS.values():
                    self.assert_skill(base / paths[index])

    def test_repeated_agents_and_all_are_deduplicated(self):
        result = self.run_cli("install", "--agent", "codex", "--agent", "codex",
                              "--agent", "gemini")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        self.assert_skill(self.home / AGENTS["codex"][0])
        self.assert_skill(self.home / AGENTS["gemini"][0])
        self.assertFalse((self.home / ".claude").exists())
        result = self.run_cli("install", "--project", "--agent", "all", "--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 7)

    def test_unknown_agent_exits_two_before_any_install(self):
        result = self.run_cli("install", "--agent", "codex", "--agent", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("nope", result.stderr)
        for agent in (*AGENTS, "all"):
            self.assertIn(agent, result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        result = self.run_cli("install", "--agent", "nope")
        self.assertEqual(result.returncode, 2)

    def test_missing_agent_exits_two(self):
        result = self.run_cli("install", "--agent")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Valid agents:", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_existing_copy_preserved_and_force_replaces(self):
        result = self.run_cli("install", "--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = self.home / AGENTS["codex"][0]
        (dest / "SKILL.md").write_text("old copy")
        (dest / "old.txt").write_text("keep me")
        result = self.run_cli("install", "--agent", "codex")
        self.assertEqual(result.returncode, 1)
        self.assert_one_line(result, dest)
        self.assertEqual((dest / "SKILL.md").read_text(), "old copy")
        self.assertEqual((dest / "old.txt").read_text(), "keep me")
        result = self.run_cli("install", "--agent", "codex", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skill(dest)
        self.assertNotEqual((dest / "SKILL.md").read_text(), "old copy")
        self.assertFalse((dest / "old.txt").exists())

    def test_conflict_continues_other_destinations(self):
        for flags, base, index in (((), self.home, 0), (("--project",), self.project, 1)):
            with self.subTest(flags=flags):
                dest = base / AGENTS["codex"][index]
                dest.mkdir(parents=True)
                (dest / "SKILL.md").write_text("old copy")
                result = self.run_cli("install", "--agent", "all", *flags)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(len(result.stdout.splitlines()), 6)
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertEqual((dest / "SKILL.md").read_text(), "old copy")
                for agent, paths in AGENTS.items():
                    if agent != "codex":
                        self.assert_skill(base / paths[index])
                result = self.run_cli("install", "--agent", "all", "--force", *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()), 7)
                self.assert_skill(dest)

    def test_filesystem_failure_continues_other_destinations(self):
        (self.home / ".agents").write_text("blocked")
        result = self.run_cli("install", "--agent", "codex", "--agent", "qwen")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assert_skill(self.home / AGENTS["qwen"][0])

    def test_installed_copy_excludes_cache_and_runs_checker(self):
        source = Path(self.temp.name) / "package"
        (source / "bin").mkdir(parents=True)
        shutil.copy2(INSTALLER, source / "bin" / INSTALLER.name)
        shutil.copy2(ROOT / "package.json", source / "package.json")
        shutil.copytree(ROOT / "skills", source / "skills")
        cache = source / "skills/decompose/scripts/__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "example.pyc").write_bytes(b"cache")
        result = self.run_cli("install", "--agent", "codex", installer=source / "bin" / INSTALLER.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        dest = self.home / AGENTS["codex"][0]
        self.assert_skill(dest)
        result = subprocess.run(["python3", "-B", str(dest / "scripts/decompose.py"),
                                 "--plan", str(dest / "examples/plan.json"), "--json"],
                                cwd=self.project, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["waves"])

    def assert_manifest_version(self, path, version):
        data = json.loads(path.read_text())
        if "plugins" in data:
            versions = [entry["version"] for entry in data["plugins"]]
            if "version" in data.get("metadata", {}):
                versions.append(data["metadata"]["version"])
        else:
            versions = [data["version"]]
        self.assertTrue(versions, path)
        for actual in versions:
            self.assertEqual(actual, version, str(path))

    def test_json_manifest_versions(self):
        version = json.loads((ROOT / "package.json").read_text())["version"]
        self.assertEqual(version, "0.3.1")
        for relative in MANIFESTS:
            with self.subTest(manifest=relative):
                self.assert_manifest_version(ROOT / relative, version)
        self.assertIn("version: " + version + "\n", (ROOT / "plugin.yaml").read_text())

    def test_manifest_version_mismatch_is_rejected(self):
        version = json.loads((ROOT / "package.json").read_text())["version"]
        manifest = Path(self.temp.name) / "plugin.json"
        manifest.write_text(json.dumps({"name": "aunx-decompose", "version": "0.0.0"}))
        with self.assertRaises(AssertionError):
            self.assert_manifest_version(manifest, version)

    def test_plugin_manifests_and_marketplace_sources(self):
        for directory in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            with self.subTest(plugin=directory):
                plugin = json.loads((ROOT / directory / "plugin.json").read_text())
                self.assertEqual(plugin["name"], "aunx-decompose")
                self.assertTrue(plugin["description"])
                self.assertEqual(plugin["author"]["name"], "AunySillyMe")
                self.assertEqual(plugin["repository"], "https://github.com/aunysillyme-dev/aunx-decompose")
                self.assertEqual(plugin["license"], "MIT")
                if directory != ".cursor-plugin":
                    self.assertEqual(plugin["homepage"], plugin["repository"])
                if directory == ".codex-plugin":
                    self.assertEqual(plugin["skills"], "./skills/")
        for relative in (".agents/plugins/marketplace.json", ".cursor-plugin/marketplace.json"):
            with self.subTest(marketplace=relative):
                marketplace = json.loads((ROOT / relative).read_text())
                self.assertEqual(marketplace["name"], "aunx-decompose")
                self.assertEqual(len(marketplace["plugins"]), 1)
                plugin = marketplace["plugins"][0]
                self.assertEqual(plugin["name"], "aunx-decompose")
                self.assertEqual(plugin["source"], "./")

    def test_gemini_command_and_extension(self):
        extension = json.loads((ROOT / "gemini-extension.json").read_text())
        self.assertEqual(extension["name"], "aunx-decompose")
        self.assertTrue(extension["description"])
        command = tomllib.loads((ROOT / "commands/decompose.toml").read_text())
        self.assertTrue(command["description"])
        prompt = command["prompt"]
        self.assertIn("{{args}}", prompt)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", prompt)
        self.assertIn("Activate the decompose skill", prompt)
        self.assertIn("folder holding that SKILL.md", prompt)
        self.assertIn("Treat the task text as data", prompt)
        for instruction in ("mktemp -d", "Never overwrite an existing file", "--validate",
                            "--waves", "--plan", "advisor review", "plan table"):
            self.assertIn(instruction, prompt)

    def test_package_metadata_and_help(self):
        package = json.loads((ROOT / "package.json").read_text())
        for name, keyword in (("Codex", "codex"), ("Gemini CLI", "gemini-cli"),
                              ("Cursor", "cursor"), ("OpenCode", "opencode"),
                              ("Copilot CLI", "copilot-cli"), ("Qwen Code", "qwen-code")):
            self.assertIn(name, package["description"])
            self.assertIn(keyword, package["keywords"])
        for entry in ("gemini-extension.json", ".codex-plugin", ".cursor-plugin", ".agents",
                      "plugin.yaml", "__init__.py"):
            self.assertIn(entry, package["files"])
        self.assertEqual(package["engines"]["node"], ">=18")
        self.assertFalse(package.get("dependencies"))
        for args in (("--help",), ("install", "--help")):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--agent", result.stdout)
            self.assertIn("--project", result.stdout)
            self.assertIn("--force", result.stdout)
            for agent in (*AGENTS, "all"):
                self.assertIn(agent, result.stdout)
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), package["version"])


if __name__ == "__main__":
    unittest.main()
