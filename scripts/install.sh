#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/target/project" >&2
  exit 1
fi

TARGET_DIR="$1"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -d "$TARGET_DIR" ]; then
  echo "Target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

if ! git -C "$TARGET_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "warning: target is not inside a git repository; subdirectory hook root detection will be limited" >&2
fi

copy_if_missing() {
  local src="$1"
  local dest="$2"

  if [ -e "$dest" ]; then
    echo "skip existing: $dest"
    return
  fi

  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  echo "created: $dest"
}

merge_hook_json() {
  local src="$1"
  local dest="$2"

  mkdir -p "$(dirname "$dest")"

  if [ ! -e "$dest" ]; then
    cp "$src" "$dest"
    echo "created: $dest"
    return
  fi

  if [ ! -f "$dest" ]; then
    echo "skip non-file: $dest"
    return
  fi

  python3 - "$src" "$dest" <<'PY'
import copy
import json
import shutil
import sys
import time
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])

try:
    source = json.loads(source_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"error: template hooks JSON is invalid: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    target = json.loads(target_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"error: existing hooks JSON is invalid: {target_path}: {exc}", file=sys.stderr)
    print("No changes were made. Fix the JSON, then run install.sh again.", file=sys.stderr)
    sys.exit(1)

if not isinstance(source, dict) or not isinstance(target, dict):
    print("error: hooks JSON root must be an object", file=sys.stderr)
    sys.exit(1)

source_hooks = source.get("hooks", {})
target_hooks = target.setdefault("hooks", {})

if not isinstance(source_hooks, dict) or not isinstance(target_hooks, dict):
    print("error: hooks must be an object", file=sys.stderr)
    sys.exit(1)

changed = False

for event_name, source_entries in source_hooks.items():
    if not isinstance(source_entries, list):
        continue

    target_entries = target_hooks.setdefault(event_name, [])
    if not isinstance(target_entries, list):
        print(f"error: hooks.{event_name} must be an array", file=sys.stderr)
        sys.exit(1)

    existing = {
        json.dumps(entry, sort_keys=True, separators=(",", ":"))
        for entry in target_entries
    }

    for entry in source_entries:
        key = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        if key in existing:
            continue
        target_entries.append(copy.deepcopy(entry))
        existing.add(key)
        changed = True

if not changed:
    print(f"already configured: {target_path}")
    sys.exit(0)

backup_path = target_path.with_name(
    f"{target_path.name}.bak.{time.strftime('%Y%m%d%H%M%S')}"
)
shutil.copy2(target_path, backup_path)
target_path.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")

print(f"merged hooks: {target_path}")
print(f"backup: {backup_path}")
PY
}

merge_hook_json "$SOURCE_DIR/.claude/settings.json" "$TARGET_DIR/.claude/settings.json"
copy_if_missing "$SOURCE_DIR/.claude/rules/wiki-workflow.md" "$TARGET_DIR/.claude/rules/wiki-workflow.md"
copy_if_missing "$SOURCE_DIR/.claude/hooks/scripts/wiki_session_start.py" "$TARGET_DIR/.claude/hooks/scripts/wiki_session_start.py"
copy_if_missing "$SOURCE_DIR/.claude/hooks/scripts/wiki_stop_hook.py" "$TARGET_DIR/.claude/hooks/scripts/wiki_stop_hook.py"
copy_if_missing "$SOURCE_DIR/.claude/hooks/scripts/wiki_write_gate.py" "$TARGET_DIR/.claude/hooks/scripts/wiki_write_gate.py"
copy_if_missing "$SOURCE_DIR/.claude/skills/wiki-review/SKILL.md" "$TARGET_DIR/.claude/skills/wiki-review/SKILL.md"
copy_if_missing "$SOURCE_DIR/.agents/skills/wiki-review/SKILL.md" "$TARGET_DIR/.agents/skills/wiki-review/SKILL.md"
copy_if_missing "$SOURCE_DIR/.agents/skills/wiki-review/agents/openai.yaml" "$TARGET_DIR/.agents/skills/wiki-review/agents/openai.yaml"
merge_hook_json "$SOURCE_DIR/.codex/hooks.json" "$TARGET_DIR/.codex/hooks.json"
copy_if_missing "$SOURCE_DIR/wiki/README.md" "$TARGET_DIR/wiki/README.md"
copy_if_missing "$SOURCE_DIR/wiki/index.md" "$TARGET_DIR/wiki/index.md"
copy_if_missing "$SOURCE_DIR/wiki/log.md" "$TARGET_DIR/wiki/log.md"
copy_if_missing "$SOURCE_DIR/wiki/system-overview.md" "$TARGET_DIR/wiki/system-overview.md"
copy_if_missing "$SOURCE_DIR/wiki.config.json" "$TARGET_DIR/wiki.config.json"

chmod +x "$TARGET_DIR/.claude/hooks/scripts/wiki_session_start.py"
chmod +x "$TARGET_DIR/.claude/hooks/scripts/wiki_stop_hook.py"
chmod +x "$TARGET_DIR/.claude/hooks/scripts/wiki_write_gate.py"

echo
echo "LLM Project Wiki installed."
echo "Next: open the target project with Claude Code or Codex."
echo "Review .claude/settings.json and .codex/hooks.json before trusting hooks."
