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
        emit_context(f"Project wiki index:\n\n{index_path.read_text(encoding='utf-8')}")
        return

    if mode == "git-context":
        status = git_output(root, ["status", "-s"])
        latest_commit = git_output(root, ["log", "-1", "--format=%h %s (%cr)"])
        emit_context(f"Git status:\n{status}\n\nLatest commit:\n{latest_commit}\n")
        return

    print("{}")


if __name__ == "__main__":
    main()
