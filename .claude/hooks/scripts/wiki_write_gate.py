#!/usr/bin/env python3
"""PreToolUse gate for wiki writes under the `auto` write policy.

This hook is the deterministic enforcement layer for `write_policy: auto`. It
only governs the `wiki/` tree and only acts when the policy is `auto`; in every
other case it exits silently (allow).

The index is two-level (index.md + index-<slug>.md) and the log is a weekly
file tree (wiki/log/<year>/<monday>.md); maintenance exemptions and the
flat-layout check account for both.

Classification (first match wins):
  1. Bash rm/git rm/mv or shell redirect/tee into wiki -> deny
  2. wiki/log/ tree maintenance (.md only)             -> allow (no confidence)
  3. Write/Edit to a non-flat or non-.md wiki path     -> deny
  4. index*.md / README.md / legacy log.md maintenance -> allow (no confidence)
  5. resulting confidence == high                      -> allow + surface diff
  6. resulting confidence == medium / low              -> deny
  7. resulting confidence missing / unparseable        -> deny (fail-closed)
"""

import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_session_start import project_root, resolve_write_policy

CONFIDENCE_RE = re.compile(r"^confidence:\s*(\S+)\s*$", re.MULTILINE)


def is_maintenance(name: str, root: Path) -> bool:
    """Top-level index/README files carry no confidence frontmatter.

    `index-<slug>.md` is exempt only when the slug is actually listed in the
    directory column of wiki/index.md — otherwise any knowledge page could
    dodge the confidence check by taking an index- prefix (fail-closed: if
    index.md is missing or unreadable, no index-* file is exempt).

    `log.md` stays exempt for downstream projects installed before the log
    moved to the weekly wiki/log/ tree.
    """
    if name in {"README.md", "index.md", "log.md"}:
        return True
    if not name.startswith("index-"):
        return False
    try:
        index_text = (root / "wiki" / "index.md").read_text(encoding="utf-8")
    except Exception:
        return False
    return name in re.findall(r"index-[a-z0-9-]+\.md", index_text)


def parse_confidence(text: str) -> str | None:
    """Pull the frontmatter confidence value (lowercased) or None."""
    text = text.lstrip("\ufeff")
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
    # APFS is case-insensitive but case-preserving: resolve() does not
    # normalize WIKI/ back to wiki/, so the comparison must ignore case or the
    # whole gate can be bypassed with a case variant.
    if not parts or parts[0].lower() != "wiki":
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
    # Strip quotes and backslashes before matching, otherwise shell quoting or
    # escaping like "wiki"/x.md, "tee", or wi\ki slips past the regexes below.
    command = command.replace('"', "").replace("'", "").replace("\\", "")
    # Deny any destructive op (rm/git rm/mv) that references the wiki directory,
    # whether a specific page (wiki/p.md), a glob (wiki/*), or the dir itself
    # (rm -rf wiki). `wiki` must be a path segment, so unrelated names like
    # wiki-notes.txt do not match.
    destructive = re.search(r"\b(rm|git\s+rm|mv)\b", command, re.IGNORECASE)
    references_wiki = re.search(r"(?<![\w.-])wiki(?=/|['\"\s]|$)", command, re.IGNORECASE)
    if destructive and references_wiki:
        deny("刪除或移動 wiki 目錄或頁面")
    # Shell redirects / tee into wiki (cat > wiki/x.md, tee -a wiki/x.md) would
    # bypass the Write/Edit confidence check, so they are denied. [^|;&]* keeps
    # the match inside one pipeline segment, so reads out of wiki like
    # `cat wiki/a.md > /tmp/b` are not caught. Scope note: only >, >>, and tee
    # are covered; other file-writing tricks (python -c, curl -o, ...) cannot
    # be enumerated by regex — the limitation is documented in wiki-workflow.md.
    writes_into_wiki = re.search(
        r"(?:>{1,2}|\btee\b(?:\s+-a)?)[^|;&]*(?<![\w.-])wiki/", command, re.IGNORECASE
    )
    if writes_into_wiki:
        deny("透過 shell 重導向或 tee 寫入 wiki")
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
    if not file_path or not isinstance(file_path, (str, Path)):
        allow_silent()

    # Resolve relative paths against the project root, not the cwd (the hook may
    # run from a subdirectory). An absolute file_path is unchanged by this join.
    target = (root / Path(file_path)).resolve()
    rel = wiki_relative(target, root)
    if rel is None:
        allow_silent()  # not a wiki path -> gate is inert

    # Rule 2: the weekly log tree is maintenance (wiki/log/index.md,
    # wiki/log/<year>/<monday>.md) — allowed without confidence, .md only.
    if len(rel.parts) > 2 and rel.parts[1] == "log":
        if rel.suffix != ".md":
            deny("寫到 wiki/log/ 樹裡不允許的檔案類型（僅 .md）")
        allow_silent()

    # Rule 3: knowledge pages must be flat wiki/<name>.md
    if len(rel.parts) != 2 or rel.suffix != ".md":
        deny("寫到 wiki/ 樹裡不允許的位置（需扁平的 wiki/<name>.md 或 wiki/log/ 週檔）")

    # Rule 4: maintenance files carry no confidence
    if is_maintenance(rel.name, root):
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

    if not isinstance(data, dict):
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
