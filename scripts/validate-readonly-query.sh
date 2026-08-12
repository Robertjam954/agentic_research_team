#!/usr/bin/env bash
# PreToolUse guard for the biomed-data-analyst subagent.
# Allows only read-only data access; blocks mutating SQL / Mongo operations and
# destructive shell commands. Reads the Bash tool input as JSON on stdin
# (.tool_input.command). Exit 2 blocks the call and returns the message to Claude.
set -euo pipefail

input="$(cat 2>/dev/null || true)"

# Extract the command string from the hook's JSON payload.
cmd="$(printf '%s' "$input" | python3 -c '
import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

low="$(printf '%s' "$cmd" | tr "[:upper:]" "[:lower:]")"

# Mutating SQL/Mongo verbs and destructive shell operations.
deny='(^|[^a-z])(insert|update|delete|drop|truncate|alter|grant|revoke|merge)([^a-z]|$)'
deny_mongo='\.(insert|insertone|insertmany|update|updateone|updatemany|delete|deleteone|deletemany|remove|replaceone|drop|renamecollection|createindex)\('
deny_fs='(^|[^a-z])(rm|mv|chmod|chown|dd)([^a-z]|$)'

if printf '%s' "$low" | grep -Eq "$deny" \
  || printf '%s' "$low" | grep -Eq "$deny_mongo" \
  || printf '%s' "$low" | grep -Eq "$deny_fs"; then
  echo "Read-only guard: the biomed-data-analyst may not run mutating or destructive operations. Use SELECT / find only." >&2
  exit 2
fi

exit 0
