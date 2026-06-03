#!/usr/bin/env python3
"""Load project wiki context at session start."""

import json
import os
import subprocess
import sys
from pathlib import Path


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


def require_human_approval(root: Path) -> bool:
    """Read the wiki write policy. Fail closed: default to requiring approval."""
    try:
        config = json.loads((root / "wiki.config.json").read_text(encoding="utf-8"))
        return bool(config.get("require_human_approval", True))
    except Exception:
        return True


def write_policy_text(root: Path) -> str:
    if require_human_approval(root):
        return (
            "Wiki write policy (wiki.config.json): human approval REQUIRED. "
            'Propose updates with the "Wiki suggestion" format and wait for '
            "explicit approval before creating, updating, or deleting any wiki page."
        )
    return (
        "Wiki write policy (wiki.config.json): human approval NOT required. "
        "When you find durable knowledge, you may write the wiki page directly "
        "without waiting for approval — still update wiki/index.md, append to "
        'wiki/log.md, and output a wiki evaluation marker (e.g. "Wiki suggestion") '
        "so the Stop hook passes."
    )


def emit_context(text: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                }
            }
        )
    )


def git_output(root: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).rstrip()
    except Exception:
        return ""


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    root = project_root()

    if mode == "wiki-index":
        index_path = root / "wiki" / "index.md"
        if not index_path.is_file():
            print("{}")
            return
        emit_context(
            "Project wiki index:\n\n"
            f"{index_path.read_text(encoding='utf-8')}\n\n"
            "Codex wiki review rule: every substantial final response must "
            "evaluate whether the conversation produced durable project "
            "knowledge. If yes, include a visible `Wiki suggestion`. If no, "
            "do not add a visible no-op marker; keep the transcript clean.\n\n"
            f"{write_policy_text(root)}"
        )
        return

    if mode == "git-context":
        status = git_output(root, ["status", "-s"])
        latest_commit = git_output(root, ["log", "-1", "--format=%h %s (%cr)"])
        emit_context(f"Git status:\n{status}\n\nLatest commit:\n{latest_commit}\n")
        return

    print("{}")


if __name__ == "__main__":
    main()
