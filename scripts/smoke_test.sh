#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_HOOK="$ROOT_DIR/.claude/hooks/scripts/wiki_stop_hook.py"

run_case() {
  local name="$1"
  local hook="$2"
  local input="$3"
  local expected="$4"
  local expected_text="${5:-}"
  local output
  local exit_code

  set +e
  output="$(printf '%s' "$input" | python3 "$hook")"
  exit_code="$?"
  set -e

  if [ "$exit_code" -ne 0 ]; then
    echo "FAIL: $name exited with $exit_code"
    exit 1
  fi

  if [ "$expected" = "block" ] && [[ "$output" != *'"decision": "block"'* ]]; then
    echo "FAIL: $name expected block, got: $output"
    exit 1
  fi

  if [ -n "$expected_text" ] && [[ "$output" != *"$expected_text"* ]]; then
    echo "FAIL: $name expected output to contain '$expected_text', got: $output"
    exit 1
  fi

  if [ "$expected" = "allow" ] && [ -n "$output" ]; then
    echo "FAIL: $name expected allow, got: $output"
    exit 1
  fi

  echo "PASS: $name"
}

LONG_MESSAGE="$(python3 - <<'PY'
print("This is a substantial response. " * 60)
PY
)"
SESSION_PREFIX="smoke-$(date +%s)-$$"

run_case "short response is allowed" \
  "$CLAUDE_HOOK" \
  "{\"session_id\":\"$SESSION_PREFIX-short\",\"last_assistant_message\":\"Done.\"}" \
  "allow"

run_case "long response without marker is blocked" \
  "$CLAUDE_HOOK" \
  "{\"session_id\":\"$SESSION_PREFIX-long\",\"last_assistant_message\":\"$LONG_MESSAGE\"}" \
  "block"

run_case "wiki suggestion marker is allowed" \
  "$CLAUDE_HOOK" \
  "{\"session_id\":\"$SESSION_PREFIX-suggestion\",\"last_assistant_message\":\"Wiki suggestion: update architecture notes.\"}" \
  "allow"

run_case "no updates marker is allowed" \
  "$CLAUDE_HOOK" \
  "{\"session_id\":\"$SESSION_PREFIX-none\",\"last_assistant_message\":\"No wiki updates needed\"}" \
  "allow"

echo
echo "All hook smoke tests passed."

empty_target="$(mktemp -d)"
existing_target="$(mktemp -d)"
trap 'rm -rf "$empty_target" "$existing_target"' EXIT

git -C "$empty_target" init >/dev/null
"$ROOT_DIR/scripts/install.sh" "$empty_target" >/tmp/llm-project-wiki-install-empty.log
test -f "$empty_target/.claude/settings.json"
test -f "$empty_target/.claude/hooks/scripts/wiki_session_start.py"
test -f "$empty_target/.claude/hooks/scripts/wiki_stop_hook.py"
test -f "$empty_target/.claude/hooks/scripts/wiki_write_gate.py"
test -x "$empty_target/.claude/scripts/wiki-search.sh"
test -f "$empty_target/wiki/index-architecture.md"
test -f "$empty_target/wiki/index-integrations.md"
test -f "$empty_target/wiki/index-debugging.md"
test -f "$empty_target/wiki/index-decisions.md"
test -f "$empty_target/wiki/log/index.md"
test -f "$empty_target/wiki/log/2026/2026-05-11.md"
test ! -e "$empty_target/wiki/log.md"
test -f "$empty_target/.codex/hooks.json"
test ! -e "$empty_target/.codex/hooks"
test -f "$empty_target/.agents/skills/wiki-review/SKILL.md"
test -f "$empty_target/.agents/skills/wiki-review/agents/openai.yaml"
test ! -e "$empty_target/.codex/skills/wiki-review/SKILL.md"
python3 -m json.tool "$empty_target/.claude/settings.json" >/dev/null
python3 -m json.tool "$empty_target/.codex/hooks.json" >/dev/null

hook_cmd() {
  python3 - "$1" "$2" "$3" <<'PY'
import json
import sys
from pathlib import Path

hooks = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(hooks["hooks"][sys.argv[2]][0]["hooks"][int(sys.argv[3])]["command"])
PY
}

claude_session_start_index_cmd="$(hook_cmd "$empty_target/.claude/settings.json" SessionStart 0)"
claude_session_start_git_cmd="$(hook_cmd "$empty_target/.claude/settings.json" SessionStart 1)"
codex_session_start_index_cmd="$(hook_cmd "$empty_target/.codex/hooks.json" SessionStart 0)"
codex_session_start_git_cmd="$(hook_cmd "$empty_target/.codex/hooks.json" SessionStart 1)"

test "$(cd "$empty_target/wiki" && CLAUDE_PROJECT_DIR="$empty_target" sh -c "$claude_session_start_index_cmd" | python3 -c 'import json,sys; print("Project wiki categories" in json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])')" = "True"
test "$(cd "$empty_target/wiki" && CLAUDE_PROJECT_DIR="$empty_target" sh -c "$claude_session_start_git_cmd" | python3 -c 'import json,sys; print("Git status:" in json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])')" = "True"
test "$(cd "$empty_target/wiki" && sh -c "$codex_session_start_index_cmd" | python3 -c 'import json,sys; text=json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"]; print("Project wiki categories" in text and "do not add a visible no-op marker" in text)')" = "True"
test "$(cd "$empty_target/wiki" && sh -c "$codex_session_start_git_cmd" | python3 -c 'import json,sys; print("Git status:" in json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])')" = "True"

echo "PASS: installed Claude and Codex session hooks run from a project subdirectory"

# Write policy: install.sh ships wiki.config.json (write_policy: require_approval).
test -f "$empty_target/wiki.config.json"

assert_index_contains() {
  local name="$1"
  local index_cmd="$2"
  local use_project_dir="$3"
  local needle="$4"
  local result

  if [ "$use_project_dir" = "claude" ]; then
    result="$(cd "$empty_target/wiki" && CLAUDE_PROJECT_DIR="$empty_target" sh -c "$index_cmd" | python3 -c 'import json,sys; print(sys.argv[1] in json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])' "$needle")"
  else
    result="$(cd "$empty_target/wiki" && sh -c "$index_cmd" | python3 -c 'import json,sys; print(sys.argv[1] in json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])' "$needle")"
  fi

  if [ "$result" != "True" ]; then
    echo "FAIL: $name expected injected policy to contain '$needle'"
    exit 1
  fi
}

# Installed default (require_human_approval: true) -> approval required.
assert_index_contains "claude policy required (default)" "$claude_session_start_index_cmd" "claude" "human approval REQUIRED"
assert_index_contains "codex policy required (default)" "$codex_session_start_index_cmd" "codex" "human approval REQUIRED"

# Toggle off -> approval not required.
printf '{\n  "require_human_approval": false\n}\n' >"$empty_target/wiki.config.json"
assert_index_contains "claude policy not required" "$claude_session_start_index_cmd" "claude" "human approval NOT required"
assert_index_contains "codex policy not required" "$codex_session_start_index_cmd" "codex" "human approval NOT required"

# Missing config -> fail closed to approval required.
rm -f "$empty_target/wiki.config.json"
assert_index_contains "claude policy fail-closed" "$claude_session_start_index_cmd" "claude" "human approval REQUIRED"
assert_index_contains "codex policy fail-closed" "$codex_session_start_index_cmd" "codex" "human approval REQUIRED"

echo "PASS: wiki.config.json toggles the injected write policy (with fail-closed default)"

git -C "$existing_target" init >/dev/null
mkdir -p "$existing_target/.claude" "$existing_target/.codex" "$existing_target/wiki"
cat >"$existing_target/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo existing",
            "timeout": 1
          }
        ]
      }
    ]
  }
}
JSON
cat >"$existing_target/.codex/hooks.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo existing codex",
            "timeout": 1
          }
        ]
      }
    ]
  }
}
JSON
printf 'existing index\n' >"$existing_target/wiki/index.md"

"$ROOT_DIR/scripts/install.sh" "$existing_target" >/tmp/llm-project-wiki-install-existing.log

python3 - "$existing_target/.claude/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
commands = []
for event_entries in settings.get("hooks", {}).values():
    for event_entry in event_entries:
        for hook in event_entry.get("hooks", []):
            commands.append(hook.get("command", ""))

assert any(command == "echo existing" for command in commands)
assert any("wiki_stop_hook.py" in command for command in commands)
assert any("wiki_session_start.py" in command for command in commands)
PY

test "$(cat "$existing_target/wiki/index.md")" = "existing index"
ls "$existing_target/.claude"/settings.json.bak.* >/dev/null

echo "PASS: install script preserves existing files and merges Claude hooks"

python3 - "$existing_target/.codex/hooks.json" <<'PY'
import json
import sys
from pathlib import Path

settings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
commands = []
for event_entries in settings.get("hooks", {}).values():
    for event_entry in event_entries:
        for hook in event_entry.get("hooks", []):
            commands.append(hook.get("command", ""))

assert any(command == "echo existing codex" for command in commands)
assert any(".claude/hooks/scripts/wiki_session_start.py" in command for command in commands)
PY

ls "$existing_target/.codex"/hooks.json.bak.* >/dev/null

echo "PASS: install script preserves existing files and merges Codex hooks"
echo
echo "All smoke tests passed."
