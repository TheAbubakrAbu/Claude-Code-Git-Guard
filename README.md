# Claude Code Git Guard

**A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) hook that makes Claude ask before it commits, pushes, or rewrites git history.** Every `git commit`, `git push`, `git reset`, branch deletion, or `gh pr merge` becomes a permission prompt you approve, however the command is dressed up: behind `cd x &&`, inside `bash -c`, or after `git -C "a path with spaces"`.

[![tests](https://github.com/TheAbubakrAbu/Claude-Code-Git-Guard/actions/workflows/tests.yml/badge.svg)](https://github.com/TheAbubakrAbu/Claude-Code-Git-Guard/actions/workflows/tests.yml)

Created by **Abubakr Elmallah** on **July 29, 2026**.

## At a glance

| | |
|---|---|
| **1** file | `git-guard.py`, Python 3.8+, standard library only |
| **0** dependencies | nothing to `pip install` |
| **1** event | `PreToolUse`, for the `Bash` tool |
| **2** modes | ask (a prompt you approve) or deny (an absolute block) |
| **0** bytes written | no log, no state, no network |
| **27** tests | run on macOS and Ubuntu on every push |

---

## Table of Contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [What it stops](#what-it-stops)
- [Getting Started](#getting-started)
- [Commands](#commands)
- [Settings](#settings)
- [How it decides](#how-it-decides)
- [Teach Claude the other half](#teach-claude-the-other-half)
- [Known Limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Privacy & Data](#privacy--data)
- [Testing](#testing)
- [Uninstall](#uninstall)
- [License](#license)
- [Feedback & Contact](#feedback--contact)

---

## Why this exists

**A rule in `CLAUDE.md` is a request. A hook is a gate.**

"Never commit or push unless I ask, in that message" is easy to write down and easy for a model to talk itself out of. The task "seems to require it" (set up GitHub Pages, deploy the site), you asked for a commit three messages ago, the change is small, the branch is yours. Each of those has ended in a commit nobody asked for.

Permission rules do not close the gap either. An allow rule such as `Bash(git:*)`, which saves you from approving `git status` all day, lets `git push` through with it.

This hook reads every Bash command before it runs. When one would commit, publish, rewrite history, or change a remote, it answers `ask`, and Claude Code puts the decision in front of you. When you did ask for it, you approve the prompt. When you did not, you have just been saved a `git push --force`. **The failure direction is always toward asking.**

## Features

- **Sees through wrappers:** catches the command behind `cd repo &&`, after `;` or `||`, on its own line of a multi-line command, inside `bash -c "..."` and `sh -c '...'`, after `sudo` or an environment assignment, and as `/usr/bin/git`.
- **Skips git's global options:** `git -C <dir>`, `-c key=value`, `--git-dir=...`, `--work-tree=...`, and `--no-pager` before the subcommand do not hide it, including quoted paths with spaces (`git -C "$HOME/Library/Mobile Documents/repo" push`) and backslash-escaped ones (`Mobile\ Documents`).
- **Reading is never stopped:** `status`, `log`, `diff`, `show`, `branch -a`, `remote -v`, `fetch`, `ls-files`, and friends pass silently, including `git log --grep=push`.
- **Ask or deny:** the default is a prompt you approve; `--deny` makes it a block that not even an explicit request gets past.
- **Never in Claude's way:** an unmatched command, a malformed payload, or a non-Bash payload falls through silently with exit code 0. No input can make it slow: every pattern runs in linear time, so no command can outlast the hook's timeout and slip through.
- **Testable from the shell:** `git-guard.py --check 'any command'` prints what the guard would do.

## What it stops

| Category | Commands |
| --- | --- |
| Commits and history | `commit`, `merge`, `rebase`, `cherry-pick`, `revert`, `am`, `reset`, `tag`, `filter-branch`, `filter-repo` |
| Publishing | `push` (any form, including `--force`) |
| Remotes | `remote add`, `remote remove` / `rm`, `remote rename`, `remote set-url` |
| Branches | `branch -d`, `-D`, `-m`, `-M`, clusters such as `-dr`, and `--delete` / `--move` |
| Untracked files | `clean -f`, `clean -fd`, `clean -xdf`, `clean --force` |
| GitHub CLI | `gh pr`, `gh release`, and `gh repo` with `create`, `merge`, `edit`, `delete`, or `close` |

Everything else passes. `git clean -n` (a dry run) and `git branch new-feature` (creating a branch) are not stopped.

## Getting Started

1. **Clone the project:**

   ```bash
   git clone https://github.com/TheAbubakrAbu/Claude-Code-Git-Guard.git
   cd Claude-Code-Git-Guard
   ```

2. **Run the installer:**

   ```bash
   ./install.sh                 # or: ./install.sh --deny
   ```

   It copies `git-guard.py` to `~/.claude/hooks/` and wires it into `~/.claude/settings.json` as a `PreToolUse` hook for `Bash`. A backup of `settings.json` is written first, your other hooks are left alone, and running it again changes nothing.

3. **Check it:**

   ```bash
   python3 ~/.claude/hooks/git-guard.py --check 'cd repo && git push'
   # ask: git push
   ```

4. **Restart your Claude Code sessions.** Hooks are read when a session starts. Run `/hooks` inside Claude Code to see it listed.

## Commands

### Installer

| Command | Description |
| --- | --- |
| `./install.sh` | Install the guard in ask mode |
| `./install.sh --deny` | Install it in deny mode (`--ask` switches back) |
| `./install.sh --dest DIR` | Put `git-guard.py` in `DIR` instead of `~/.claude/hooks` |
| `./install.sh --settings FILE` | Wire it into another `settings.json`, for example a project's `.claude/settings.json` |
| `./install.sh --uninstall` | Remove the hook from `settings.json`, keep the file |
| `./install.sh --uninstall --purge` | Also delete `git-guard.py` |

### The hook

| Command | Description |
| --- | --- |
| `python3 ~/.claude/hooks/git-guard.py --check 'CMD'` | Print `ask: <segment>` and exit 1 if CMD would be stopped, or `passes: CMD` and exit 0 |
| `python3 ~/.claude/hooks/git-guard.py --deny --check 'CMD'` | The same, as deny mode would answer |
| `python3 ~/.claude/hooks/git-guard.py` | The hook itself: reads Claude Code's payload on stdin |

## Settings

There is one setting, the mode, and it lives in the hook's command in `settings.json`:

| Mode | Command | What happens |
| --- | --- | --- |
| **ask** (default) | `python3 "$HOME/.claude/hooks/git-guard.py"` | Claude Code shows a permission prompt with the reason "Blocked by your standing rule: never commit, push, or rewrite git history unless you explicitly ask for it in that message." You approve it when you did ask. |
| **deny** | `python3 "$HOME/.claude/hooks/git-guard.py" --deny` | The command is refused with "Run this command yourself." Claude cannot run it even when you ask; you run it in your own terminal. |

Switch with `./install.sh --deny` or `./install.sh --ask`. The entry it writes:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/git-guard.py\"",
            "timeout": 10,
            "statusMessage": "Checking git guard"
          }
        ]
      }
    ]
  }
}
```

## How it decides

Claude Code sends the hook a JSON payload on stdin before every Bash command; the command is in `tool_input.command`.

1. **Split into segments** on `;`, `&&`, `||`, `|`, and newlines, so `git log --grep=push` in one segment is never mistaken for a push in another.
2. **Match each segment** against five patterns, one per row of [What it stops](#what-it-stops). The git pattern skips global options first: an option is a word starting with `-`, its value (as in `-C <dir>`) is the next word unless that word also starts with `-`, and a word may hold quoted text with spaces or backslash escapes.
3. **Answer.** On the first segment that matches, it prints a `permissionDecision` of `ask` (or `deny`) with its reason and exits 0. If nothing matches, it prints nothing and exits 0, and the command runs exactly as it would have without the hook.

The patterns are written so that each character of a command can be read only one way. That keeps every check linear in the length of the command: a 2,000-word command is checked in milliseconds, and nothing can make the hook run into its 10 second timeout (a hook that times out lets the command through).

## Teach Claude the other half

The hook makes sure you are asked. If you also want Claude not to try in the first place, to leave its work uncommitted, and to show you the exact files, commit message, and branch before it does commit, paste [docs/CLAUDE.md-snippet.md](docs/CLAUDE.md-snippet.md) into your `~/.claude/CLAUDE.md`.

## Known Limitations

- **It errs toward asking.** A few harmless commands get a prompt: `git tag -l` (it is still `tag`), `git reset HEAD file` to unstage, `gh pr list --search merge`, and a `grep "git push"` or `echo` that merely mentions a stopped command. Splitting on `;` and `|` also splits inside quoted strings. Approve those, or ignore them in deny mode.
- **It reads the command, not what the command runs.** A script that pushes (`./deploy.sh`), a git alias (`git config alias.p push`, then `git p`), `make release`, or a raw API call (`curl` or `gh api` against GitHub) is not seen.
- **Some destructive commands are outside its list.** `git pull` (which can merge), `git stash drop`, `git checkout -- .`, `git restore`, `git switch -C`, `git branch -f`, `gh issue`, and `gh pr comment` pass. The list matches the CLAUDE.md rule it enforces; edit `PATTERNS` in `git-guard.py` to add your own.
- **Only the Bash tool.** Git operations through an MCP server or another tool do not go through this hook.
- **Hooks are read when a session starts.** After installing, switching modes, or uninstalling, restart open sessions.

## Troubleshooting

- **No prompt for a command that should be stopped.** Run `python3 ~/.claude/hooks/git-guard.py --check 'the command'`. If it says `passes`, the command is outside the list (see [Known Limitations](#known-limitations)); if it says `ask`, run `/hooks` in a fresh session and check the `PreToolUse` entry is there. `python3` must be on the PATH of whatever launched Claude Code.
- **You run Claude Code in a mode that skips permission prompts.** Try a harmless stopped command (`git tag -l`) and check the prompt still appears. If it does not, install with `--deny`, which refuses the command instead of asking.
- **Too many prompts.** `--check` prints the segment that matched, which shows which pattern fired.
- **The prompt appears twice.** Another hook or a permission rule also asks. Run `/hooks` and look for a second entry.

## Privacy & Data

**Claude Code Git Guard** keeps nothing:
- **What it reads:** the Bash command in the payload, nothing else from it.
- **What it writes:** nothing. No log, no state file, no network access.
- **What the installer changes:** `~/.claude/settings.json` (backed up to `settings.json.bak-<time>` first) and `~/.claude/hooks/git-guard.py`.

## Testing

```bash
python3 -m unittest discover -s tests -v                  # 27 tests, nothing outside a temp folder is touched
python3 git-guard.py --check 'git -C "/tmp/a b" push'     # try any command by hand
```

The tests cover 60 commands that must be stopped and 47 that must pass, check that everything the first published version stopped is still stopped, feed the hook malformed payloads, time worst-case inputs, and run the installer against a throwaway `HOME` and `settings.json`. A hygiene test keeps em dashes, home-folder paths, and signing identities out of the repository. The [GitHub Actions workflow](.github/workflows/tests.yml) runs the suite on macOS and Ubuntu and exercises the installer end to end.

## Uninstall

```bash
./install.sh --uninstall          # removes the settings entry, keeps the file
./install.sh --uninstall --purge  # also deletes git-guard.py
```

## License

This project is licensed under the [MIT License](LICENSE). Feel free to use, modify, and distribute the code, but please provide attribution.

## Feedback & Contact

I'd love to hear your thoughts! Open an issue, or reach out with feedback, feature requests, or questions:
- **Email:** contact@abubakrelmallah.com
- **Website:** [abubakrelmallah.com](https://abubakrelmallah.com/)
- **LinkedIn:** [Abubakr Elmallah](https://www.linkedin.com/in/abubakr-elmallah-416a0b273/)
