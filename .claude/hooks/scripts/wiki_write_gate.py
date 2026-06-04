#!/usr/bin/env python3
"""PreToolUse gate for wiki writes under the `auto` write policy.

This hook is the deterministic enforcement layer for `write_policy: auto`. It
only governs the `wiki/` tree and only acts when the policy is `auto`; in every
other case it exits silently (allow). See
docs/superpowers/specs/2026-06-04-wiki-auto-write-policy-design.md.

Classification (first match wins):
  1. Bash rm/git rm/mv of a wiki/*.md page          -> deny
  2. Write/Edit to a non-flat or non-.md wiki path   -> deny
  3. wiki/index.md or wiki/log.md maintenance        -> allow (no confidence)
  4. resulting confidence == high                    -> allow + surface diff
  5. resulting confidence == medium / low            -> deny
  6. resulting confidence missing / unparseable      -> deny (fail-closed)
"""

import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VALID_POLICIES = {"require_approval", "auto", "open"}
CONFIDENCE_RE = re.compile(r"^confidence:\s*(\S+)\s*$", re.MULTILINE)
MAINTENANCE = {"index.md", "log.md"}


def project_root() -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if output:
            return Path(output)
    except Exception:
        pass
    return Path.cwd()


def resolve_write_policy(root: Path) -> str:
    """Read the active write policy. Fail closed to require_approval."""
    try:
        config = json.loads((root / "wiki.config.json").read_text(encoding="utf-8"))
    except Exception:
        return "require_approval"

    policy = config.get("write_policy")
    if policy in VALID_POLICIES:
        return policy

    if "require_human_approval" in config:
        return "require_approval" if config.get("require_human_approval") else "open"

    return "require_approval"


def parse_confidence(text: str) -> str | None:
    """Pull the frontmatter confidence value (lowercased) or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    front = text[3:end]
    match = CONFIDENCE_RE.search(front)
    if not match:
        return None
    value = match.group(1).strip().lower()
    return value if value in {"high", "medium", "low"} else None


def wiki_relative(path: Path, root: Path) -> Path | None:
    """Return the path relative to root if it is under wiki/, else None."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return None
    parts = rel.parts
    if not parts or parts[0] != "wiki":
        return None
    return rel


def allow_silent() -> None:
    sys.exit(0)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{reason}；這是高風險的 wiki 操作。請用「Wiki suggestion」"
                        "格式提案並等待批准，不要直接寫入。"
                    ),
                }
            }
        )
    )
    sys.exit(0)


def allow_with_message(message: str) -> None:
    print(
        json.dumps(
            {
                "systemMessage": message,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                },
            }
        )
    )
    sys.exit(0)


def handle_bash(command: str, root: Path) -> None:
    # Only concerned with destructive operations on a wiki page.
    if not re.search(r"\bwiki/[^\s'\"]+\.md\b", command):
        allow_silent()
    if re.search(r"\b(rm|git\s+rm|mv)\b", command):
        deny("刪除或移動既有 wiki 頁面")
    allow_silent()


def resulting_content(tool_name: str, tool_input: dict, target: Path) -> str | None:
    """The full page text after the operation, or None if it cannot be derived."""
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        try:
            current = target.read_text(encoding="utf-8")
        except Exception:
            return None
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        if old and old in current:
            if tool_input.get("replace_all"):
                return current.replace(old, new)
            return current.replace(old, new, 1)
        return current
    return None


def change_message(rel: Path, tool_name: str, tool_input: dict, target: Path) -> str:
    name = rel.name
    if tool_name == "Edit":
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        body = f"- {old}\n+ {new}"
        return f"Wiki：對 {name} 的高信心寫入。改動：\n{body}"
    # Write
    new_content = tool_input.get("content", "")
    if target.exists():
        try:
            old_content = target.read_text(encoding="utf-8")
        except Exception:
            old_content = ""
        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=name,
                tofile=name,
            )
        )
        return f"Wiki：對 {name} 的高信心寫入。改動：\n{diff}"
    preview = "\n".join(new_content.splitlines()[:12])
    return f"Wiki：建立高信心新頁 {name}。內容預覽：\n{preview}"


def handle_write_edit(tool_name: str, tool_input: dict, root: Path) -> None:
    file_path = tool_input.get("file_path")
    if not file_path:
        allow_silent()

    target = Path(file_path)
    rel = wiki_relative(target, root)
    if rel is None:
        allow_silent()  # not a wiki path -> gate is inert

    # Rule 2: must be a flat wiki/<name>.md
    if len(rel.parts) != 2 or rel.suffix != ".md":
        deny("寫到 wiki/ 樹裡不允許的位置（需扁平的 wiki/<name>.md）")

    # Rule 3: maintenance files carry no confidence
    if rel.name in MAINTENANCE:
        allow_silent()

    content = resulting_content(tool_name, tool_input, target)
    if content is None:
        deny("無法判定寫入後的頁面內容")

    confidence = parse_confidence(content)
    if confidence == "high":
        allow_with_message(change_message(rel, tool_name, tool_input, target))
    if confidence in {"medium", "low"}:
        deny(f"寫入後頁面 confidence 為 {confidence}")
    deny("寫入後頁面 confidence 缺失或無法解析")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    root = project_root()
    if resolve_write_policy(root) != "auto":
        sys.exit(0)  # gate inert outside auto mode

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool_name == "Bash":
        handle_bash(tool_input.get("command", ""), root)
    elif tool_name in {"Write", "Edit"}:
        handle_write_edit(tool_name, tool_input, root)

    sys.exit(0)


if __name__ == "__main__":
    main()
