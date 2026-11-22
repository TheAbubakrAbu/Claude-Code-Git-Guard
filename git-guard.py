#!/usr/bin/env python3
"""
Claude Code Git Guard: a PreToolUse(Bash) hook that never lets Claude commit, push, or
rewrite git history on its own.

Reads the hook payload on stdin. If the Bash command would create a commit, publish to a
remote, rewrite history, or change a remote through `gh`, it answers with a
permissionDecision of "ask", so Claude Code shows a permission prompt.

"ask" (not "deny") is deliberate: the standing rule is "never unless I say so", so you stay
the gate on every single one. When you HAVE asked for it, you approve the prompt. Run it with
--deny to make it an absolute block that even an explicit request cannot pass.

Anything not matched falls through silently and behaves exactly as before.

  git-guard.py                 the hook (reads the payload on stdin)
  git-guard.py --deny          the hook, blocking instead of asking
  git-guard.py --check CMD     print whether CMD would be stopped, and exit 1 if it would
"""
import json
import re
import sys

DECISION = "ask"

# Each pattern is matched against a single command segment (split on ; && || | and newlines)
# so `git log --grep=push` in one segment can't be confused with a real push.
GIT_SUBCOMMANDS = (
    "commit|push|merge|rebase|cherry-pick|revert|am|tag|reset"
    "|filter-branch|filter-repo"
)

# One shell word: quoted text (which may hold spaces), a backslash escape such as the "\ " in
# Mobile\ Documents, or any other non-space character. Lets `git -C "My Project" commit`
# through the option-skipping below; \S alone would stop at the first space in the path.
# The alternatives never overlap (a quote with no partner later on is matched on its own, as
# is a trailing backslash), so each character can be read only one way: a regex with
# overlapping alternatives takes exponential time on inputs such as "x""x""x"...
WORD = r"""(?:"[^"]*"|"(?![^"]*")|'[^']*'|'(?![^']*')|\\.|\\$|[^\s"'\\])+"""

# git plus its global options, such as -C <dir>, -c key=value, --git-dir=<path>, --no-pager.
# An option's value never starts with "-": a word that does is the next option. Without that
# rule, a long run of options could be split into option/value pairs in exponentially many
# ways, and a command could outlast the hook's timeout and slip through unchecked.
GIT_AND_OPTIONS = r"\bgit\b(?:\s+-%s(?:\s+(?!-)%s)?)*" % (WORD, WORD)

PATTERNS = [
    # git commit / push / merge / rebase / reset / tag / history rewrites
    re.compile(r"%s\s+(?:%s)\b" % (GIT_AND_OPTIONS, GIT_SUBCOMMANDS), re.I),
    # git remote add|remove|rename|set-url  (repointing where code publishes to)
    re.compile(r"\bgit\b.*\bremote\b\s+(?:add|remove|rm|rename|set-url)\b", re.I),
    # git branch -d/-D/-m/-M, also inside a cluster (-dr) or spelled --delete/--move
    # (deleting or renaming branches)
    re.compile(r"\bgit\b.*\bbranch\b.*\s(?:-[a-z]*[dm][a-z]*|--delete|--move)\b", re.I),
    # git clean -f or --force  (deletes untracked files irreversibly)
    re.compile(r"\bgit\b.*\bclean\b.*\s(?:-\w*f|--force\b)", re.I),
    # gh pr/release/repo create|merge|edit|delete|close
    re.compile(r"\bgh\b\s+(?:pr|release|repo)\b.*\b(?:create|merge|edit|delete|close)\b", re.I),
]

SEGMENT_SPLIT = re.compile(r"(?:;|&&|\|\||\||\n)")

REASON = {
    "ask": (
        "Blocked by your standing rule: never commit, push, or rewrite git history "
        "unless you explicitly ask for it in that message. Approve only if you just "
        "asked for this."
    ),
    "deny": (
        "Blocked by Git Guard: Claude may not commit, push, or rewrite git history here. "
        "Run this command yourself."
    ),
}


def matched_segment(command):
    """The first segment of `command` that would be stopped, or None."""
    if not isinstance(command, str) or not command.strip():
        return None
    for segment in SEGMENT_SPLIT.split(command):
        if any(p.search(segment) for p in PATTERNS):
            return segment.strip()
    return None


def main(argv):
    decision = "deny" if "--deny" in argv else DECISION

    if "--check" in argv:
        rest = argv[argv.index("--check") + 1:]
        command = " ".join(a for a in rest if a != "--deny")
        segment = matched_segment(command)
        if segment is None:
            print("passes: " + command)
            return 0
        print("%s: %s" % (decision, segment))
        return 1

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # malformed payload: stay out of the way
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    if not isinstance(tool_input, dict):
        return 0  # not a Bash payload: stay out of the way

    if matched_segment(tool_input.get("command")) is not None:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": REASON[decision],
                }
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
