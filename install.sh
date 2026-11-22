#!/usr/bin/env bash
# Claude Code Git Guard installer.
#   ./install.sh                                  wire the guard into PreToolUse for Bash
#   ./install.sh --deny                           block instead of asking (no prompt to approve)
#   ./install.sh --dest ~/.claude/hooks           where git-guard.py goes
#   ./install.sh --settings ~/.claude/settings.json
#   ./install.sh --uninstall                      remove the settings entry, keep the file
#   ./install.sh --uninstall --purge              also delete git-guard.py
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
MODE="ask"
UNINSTALL=0
PURGE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --deny) MODE="deny"; shift ;;
    --ask) MODE="ask"; shift ;;
    --dest) DEST="$2"; shift 2 ;;
    --settings) SETTINGS="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required (macOS: xcode-select --install)" >&2; exit 1; }

DEST="${DEST/#\~/$HOME}"
SETTINGS="${SETTINGS/#\~/$HOME}"

if [ "$UNINSTALL" = 0 ]; then
  mkdir -p "$DEST"
  cp "$HERE/git-guard.py" "$DEST/git-guard.py"
  chmod +x "$DEST/git-guard.py"
fi

# The command stored in settings.json. $HOME keeps it portable between Macs.
if [ "$DEST" = "$HOME/.claude/hooks" ]; then
  CMD='python3 "$HOME/.claude/hooks/git-guard.py"'
else
  CMD="python3 \"$DEST/git-guard.py\""
fi
if [ "$MODE" = "deny" ]; then
  CMD="$CMD --deny"
fi

python3 - "$SETTINGS" "$CMD" "$UNINSTALL" <<'PY'
import json, os, shutil, sys, time

path, cmd, uninstall = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
EVENT = "PreToolUse"

try:
    with open(path) as fh:
        data = json.load(fh)
except FileNotFoundError:
    data = {}
if not isinstance(data, dict):
    sys.exit("%s is not a JSON object; fix it by hand first" % path)
before = json.dumps(data, sort_keys=True)
hooks = data.setdefault("hooks", {})


def ours(hook):
    return isinstance(hook, dict) and "git-guard.py" in str(hook.get("command", ""))


if uninstall:
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            inner = [h for h in group.get("hooks", []) if not ours(h)]
            if inner or not group.get("hooks"):
                kept.append(dict(group, hooks=inner) if group.get("hooks") else group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
else:
    groups = hooks.setdefault(EVENT, [])
    found = False
    for group in groups:
        for hook in group.get("hooks", []):
            if ours(hook):
                found = True
                hook["type"] = "command"
                hook["command"] = cmd
                hook.setdefault("timeout", 10)
                hook.setdefault("statusMessage", "Checking git guard")
    if not found:
        groups.append({
            "matcher": "Bash",
            "hooks": [{
                "type": "command",
                "command": cmd,
                "timeout": 10,
                "statusMessage": "Checking git guard",
            }],
        })

if json.dumps(data, sort_keys=True) == before:
    print("settings already up to date: " + path)
else:
    if os.path.exists(path):
        backup = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        n = 1
        while os.path.exists(backup):  # two runs in one second must not share a backup
            backup = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S") + "-%d" % n
            n += 1
        shutil.copy(path, backup)
        print("backed up " + backup)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    print(("removed from " if uninstall else "wired into ") + path)
PY

if [ "$UNINSTALL" = 1 ]; then
  if [ "$PURGE" = 1 ]; then
    rm -f "$DEST/git-guard.py"
    echo "deleted $DEST/git-guard.py"
  else
    echo "kept $DEST/git-guard.py (add --purge to delete it)"
  fi
  exit 0
fi

cat <<EOF

Installed
  hook     $DEST/git-guard.py
  event    PreToolUse, matcher Bash
  mode     $MODE   ($( [ "$MODE" = ask ] && echo "a permission prompt you approve" || echo "an absolute block" ))

Next
  python3 "$DEST/git-guard.py" --check 'git push'    see what the guard would stop
  Restart your Claude Code sessions: hooks are read when a session starts.
EOF
