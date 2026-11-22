"""Tests for git-guard.py: which commands it stops, which it lets through, and how it answers.

    python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "git-guard.py")


def load_module():
    spec = importlib.util.spec_from_file_location("git_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load_module()

# Commands the guard must stop: each one commits, publishes, rewrites history, or changes a remote.
STOPPED = [
    'git commit -m "x"',
    "git commit --amend --no-edit",
    "git push",
    "git push --force-with-lease origin main",
    "git merge feature",
    "git rebase -i main",
    "git rebase --continue",
    "git cherry-pick abc123",
    "git revert HEAD",
    "git am < fix.mbox",
    "git tag v1.0",
    "git reset --hard HEAD~1",
    "git filter-branch --tree-filter 'rm -f secret' HEAD",
    "git filter-repo --path secret --invert-paths",
    "Git Push",
    # global options before the subcommand
    "git -C repo commit -m x",
    'git -C "/tmp/Mobile Documents/(5) Other/repo" commit -m x',
    "git -C '/tmp/a b' push",
    "git -C ~/Mobile\\ Documents/repo push",
    'git -C "$HOME/Library/Mobile Documents/repo" push',
    "git -C \"a\"'b c' push",
    'git --git-dir="/tmp/a b/.git" --work-tree="/tmp/a b" commit -m x',
    "git -c user.name=x -c user.email=y commit -m z",
    "git --no-pager push",
    # however git is reached
    "/usr/bin/git push",
    "sudo git push",
    "GIT_SSH_COMMAND='ssh -i key' git push",
    'bash -c "git push origin main"',
    "sh -c 'cd /tmp/x && git commit -m y'",
    # hidden in a chain
    "cd repo && git push",
    "git status; git commit -m x",
    'git add . && git commit -m "wip" || echo failed',
    "git status\ngit push",
    "npm test | git commit -F -",
    # remotes
    "git remote add origin https://example.com/x/y.git",
    "git remote set-url origin git@example.com:x/y.git",
    "git remote rm origin",
    "git remote remove origin",
    "git remote rename origin upstream",
    # branches
    "git branch -d old",
    "git branch -D old",
    "git branch -m old new",
    "git branch -M main",
    "git branch -dr origin/old",
    "git branch --delete old",
    "git branch --move old new",
    "git for-each-ref --format='%(refname:short)' refs/heads | xargs git branch -d",
    # clean
    "git clean -fd",
    "git clean -xdf",
    "git clean -n -f",
    "git clean --force",
    # gh
    "gh pr create --fill",
    "gh pr merge 12 --squash",
    "gh pr close 12",
    "gh pr edit 12 --title x",
    "gh release create v1.0",
    "gh release delete v1.0",
    "gh repo create x --public",
    "gh repo delete x --yes",
    "gh repo edit --visibility public",
]

# Commands the guard must let through: reading state, local work that is easy to undo.
PASSED = [
    "git status",
    "git diff",
    "git log --oneline -20",
    "git log --grep=push",
    'git log --grep "fix push"',
    "git show HEAD",
    "git branch",
    "git branch -a",
    "git branch -vv",
    "git branch --show-current",
    "git branch --merged",
    "git branch --contains HEAD",
    "git branch new-feature",
    "git branch --set-upstream-to=origin/main",
    "git remote -v",
    "git remote show origin",
    "git fetch --all",
    "git stash",
    "git checkout -b feature",
    "git switch main",
    "git add .",
    "git ls-files",
    "git clean -n",
    "git clean --dry-run",
    "git init -b main",
    "git config --global user.name",
    "git rev-parse HEAD",
    'git -C "/tmp/a b" status',
    'git -C "/tmp/a b" log --grep=commit',
    "gh pr view 12",
    "gh pr view 12 --json closed",
    "gh pr list",
    "gh pr checks 12",
    "gh repo view",
    "gh repo clone x/y",
    "gh release list",
    'echo "remember to push"',
    "cat .gitignore",
    "cd ~/git/project && ls",
    "brew install git",
    "python3 -m unittest discover -s tests -v",
    "",
    "   ",
]

# The patterns of the first version, before quoted -C paths, --delete, --move, clustered branch
# flags, and --force were handled. Everything they stopped must still be stopped.
FIRST_VERSION = [
    re.compile(r"\bgit\b(?:\s+-\S+(?:\s+\S+)?)*\s+(?:commit|push|merge|rebase|cherry-pick|revert"
               r"|am|tag|reset|filter-branch|filter-repo)\b", re.I),
    re.compile(r"\bgit\b.*\bremote\b\s+(?:add|remove|rm|rename|set-url)\b", re.I),
    re.compile(r"\bgit\b.*\bbranch\b.*\s-(?:d|D|m|M)\b", re.I),
    re.compile(r"\bgit\b.*\bclean\b.*\s-\w*f", re.I),
    re.compile(r"\bgh\b\s+(?:pr|release|repo)\b.*\b(?:create|merge|edit|delete|close)\b", re.I),
]


def first_version_stops(command):
    segments = re.split(r"(?:;|&&|\|\||\||\n)", command)
    return any(p.search(s) for s in segments for p in FIRST_VERSION)


def run_hook(payload, *args):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, SCRIPT] + list(args), input=data,
                          capture_output=True, text=True, timeout=20)


class Matching(unittest.TestCase):
    def test_stops_every_dangerous_command(self):
        missed = [c for c in STOPPED if guard.matched_segment(c) is None]
        self.assertEqual(missed, [], "let through")

    def test_lets_every_safe_command_through(self):
        stopped = [c for c in PASSED if guard.matched_segment(c) is not None]
        self.assertEqual(stopped, [], "stopped")

    def test_still_stops_everything_the_first_version_stopped(self):
        corpus = STOPPED + PASSED + [a + " && " + b for a in PASSED[:10] for b in STOPPED[:10]]
        regressions = [c for c in corpus if first_version_stops(c) and guard.matched_segment(c) is None]
        self.assertEqual(regressions, [])

    def test_names_the_segment_that_was_stopped(self):
        self.assertEqual(guard.matched_segment("git status && git push origin main"),
                         "git push origin main")

    def test_ignores_non_string_commands(self):
        for value in (None, 42, ["git", "push"], {"command": "git push"}):
            self.assertIsNone(guard.matched_segment(value))

    def test_long_option_runs_stay_fast(self):
        # A hook that outlasts its timeout lets the command through, so no input may be slow.
        import time
        options = " ".join("-x%d" % i for i in range(200))
        quoted = " ".join('-C "a b"%d' % i for i in range(200))
        for command in ("git %s status" % options, "git %s push" % options,
                        "git %s status" % quoted, 'git -C ' + '"x"' * 200 + " status"):
            start = time.time()
            guard.matched_segment(command)
            self.assertLess(time.time() - start, 0.5, command[:60])
        self.assertIsNotNone(guard.matched_segment("git %s push" % options))


class Hook(unittest.TestCase):
    def test_stopped_command_asks(self):
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git push"}})
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("standing rule", out["permissionDecisionReason"])

    def test_deny_mode_blocks(self):
        result = run_hook({"tool_input": {"command": "git commit -m x"}}, "--deny")
        out = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("Run this command yourself", out["permissionDecisionReason"])

    def test_safe_command_is_silent(self):
        result = run_hook({"tool_input": {"command": "git status"}})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_malformed_payloads_stay_out_of_the_way(self):
        for payload in ("not json", "", "[]", '"git push"', '{"tool_input": "git push"}',
                        '{"tool_input": {"command": 7}}', '{}'):
            result = run_hook(payload)
            self.assertEqual((result.returncode, result.stdout), (0, ""), payload)
            self.assertEqual(result.stderr, "", payload)


class CheckCommand(unittest.TestCase):
    def check(self, *args):
        return subprocess.run([sys.executable, SCRIPT, "--check"] + list(args),
                              capture_output=True, text=True, timeout=20)

    def test_check_reports_a_stop_and_exits_1(self):
        result = self.check("git status && git push")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "ask: git push")

    def test_check_reports_deny_mode(self):
        result = subprocess.run([sys.executable, SCRIPT, "--deny", "--check", "git", "push"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stdout.strip()), (1, "deny: git push"))

    def test_check_passes_a_safe_command(self):
        result = self.check("git", "log", "--grep=push")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "passes: git log --grep=push"))


if __name__ == "__main__":
    unittest.main()
