"""Tests for install.sh. Every run points at a throwaway HOME, settings.json, and hooks folder,
so your real ~/.claude is never touched.

    python3 -m unittest discover -s tests -v
"""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "install.sh")


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="git-guard-install-")
        self.home = os.path.join(self.tmp, "home")
        self.dest = os.path.join(self.tmp, "hooks")
        self.settings = os.path.join(self.tmp, "settings.json")
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_install(self, *args, default_paths=False):
        env = dict(os.environ, HOME=self.home)
        paths = [] if default_paths else ["--dest", self.dest, "--settings", self.settings]
        return subprocess.run(["bash", INSTALL] + paths + list(args), env=env,
                              capture_output=True, text=True, timeout=60)

    def read(self, path=None):
        with open(path or self.settings) as fh:
            return json.load(fh)

    def write(self, data):
        with open(self.settings, "w") as fh:
            json.dump(data, fh)

    def ours(self, data):
        return [h for g in data.get("hooks", {}).get("PreToolUse", [])
                for h in g.get("hooks", []) if "git-guard.py" in h.get("command", "")]

    def backups(self):
        return glob.glob(self.settings + ".bak-*")

    def test_fresh_install_wires_pretooluse_for_bash(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.read()
        self.assertEqual(data["hooks"]["PreToolUse"], [{
            "matcher": "Bash",
            "hooks": [{
                "type": "command",
                "command": 'python3 "%s/git-guard.py"' % self.dest,
                "timeout": 10,
                "statusMessage": "Checking git guard",
            }],
        }])
        installed = os.path.join(self.dest, "git-guard.py")
        self.assertTrue(os.access(installed, os.X_OK))
        with open(installed) as a, open(os.path.join(ROOT, "git-guard.py")) as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(self.backups(), [], "nothing to back up on a fresh install")

    def test_second_run_changes_nothing(self):
        self.run_install()
        result = self.run_install()
        self.assertIn("settings already up to date", result.stdout)
        self.assertEqual(len(self.ours(self.read())), 1)
        self.assertEqual(self.backups(), [])

    def test_keeps_everything_else_and_backs_up(self):
        other = {"type": "command", "command": "python3 other-hook.py"}
        self.write({
            "model": "opus",
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [other]}],
                "Stop": [{"hooks": [{"type": "command", "command": "notify.py"}]}],
            },
        })
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.read()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "notify.py"}]}])
        self.assertIn(other, data["hooks"]["PreToolUse"][0]["hooks"])
        self.assertEqual(len(self.ours(data)), 1)
        self.assertEqual(len(self.backups()), 1)

    def test_existing_entry_in_a_shared_group_is_updated_in_place(self):
        cmd = 'python3 "%s/git-guard.py"' % self.dest
        shared = {"matcher": "Bash", "hooks": [
            {"type": "command", "command": cmd, "timeout": 10, "statusMessage": "Checking git guard"},
            {"type": "command", "command": "other.sh", "timeout": 10},
        ]}
        self.write({"hooks": {"PreToolUse": [shared]}})
        result = self.run_install()
        self.assertIn("settings already up to date", result.stdout)
        self.assertEqual(self.read()["hooks"]["PreToolUse"], [shared])

    def test_deny_and_back_to_ask(self):
        self.run_install("--deny")
        self.assertTrue(self.ours(self.read())[0]["command"].endswith("--deny"))
        self.run_install("--ask")
        hooks = self.ours(self.read())
        self.assertEqual(len(hooks), 1)
        self.assertFalse(hooks[0]["command"].endswith("--deny"))

    def test_default_location_stores_a_portable_command(self):
        result = self.run_install(default_paths=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.read(os.path.join(self.home, ".claude", "settings.json"))
        self.assertEqual(self.ours(data)[0]["command"], 'python3 "$HOME/.claude/hooks/git-guard.py"')
        self.assertTrue(os.path.exists(os.path.join(self.home, ".claude", "hooks", "git-guard.py")))

    def test_uninstall_removes_only_ours(self):
        other = {"type": "command", "command": "other.sh"}
        self.write({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [other]}]}})
        self.run_install()
        result = self.run_install("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read()["hooks"]["PreToolUse"], [{"matcher": "Bash", "hooks": [other]}])
        self.assertTrue(os.path.exists(os.path.join(self.dest, "git-guard.py")), "file kept without --purge")

    def test_uninstall_purge_leaves_a_clean_file(self):
        self.run_install()
        result = self.run_install("--uninstall", "--purge")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read(), {})
        self.assertFalse(os.path.exists(os.path.join(self.dest, "git-guard.py")))

    def test_refuses_settings_that_are_not_an_object(self):
        with open(self.settings, "w") as fh:
            fh.write("[1, 2]")
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        with open(self.settings) as fh:
            self.assertEqual(fh.read(), "[1, 2]")

    def test_unknown_option_exits_2(self):
        self.assertEqual(self.run_install("--bogus").returncode, 2)

    def test_installed_guard_works(self):
        self.run_install()
        result = subprocess.run(["python3", os.path.join(self.dest, "git-guard.py"), "--check", "git push"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stdout.strip()), (1, "ask: git push"))


if __name__ == "__main__":
    unittest.main()
