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


VALID_POLICIES = {"require_approval", "auto", "open"}


def resolve_write_policy(root: Path) -> str:
    """Resolve the active write policy. Fail closed: default to require_approval.

    Resolution order:
      1. A valid `write_policy` enum value.
      2. Legacy `require_human_approval` boolean (true -> require_approval,
         false -> open).
      3. require_approval (fail-closed: missing/unreadable/invalid config).
    """
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


def write_policy_text(policy: str) -> str:
    if policy == "open":
        return (
            "Wiki write policy (wiki.config.json): human approval NOT required "
            "(open). When you find durable knowledge, you may write the wiki page "
            "directly without waiting for approval — still update wiki/index.md, "
            'append to wiki/log.md, and output a wiki evaluation marker (e.g. "Wiki '
            'suggestion") so the Stop hook passes.'
        )
    if policy == "auto":
        return (
            "Wiki write policy (wiki.config.json): auto. You may write a wiki page "
            "directly only when its resulting frontmatter confidence is `high`. A "
            "PreToolUse gate enforces this deterministically: writes whose "
            "resulting confidence is `medium`, `low`, or missing — plus deletes and "
            "writes to the wrong location inside wiki/ — are blocked and must be "
            'proposed with the "Wiki suggestion" format instead. High-confidence '
            "writes are allowed, but the gate surfaces their diff to the human, so "
            "set confidence honestly. Still update wiki/index.md, append to "
            "wiki/log.md, and output a wiki evaluation marker so the Stop hook passes."
        )
    return (
        "Wiki write policy (wiki.config.json): human approval REQUIRED. "
        'Propose updates with the "Wiki suggestion" format and wait for '
        "explicit approval before creating, updating, or deleting any wiki page."
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
            f"{write_policy_text(resolve_write_policy(root))}"
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
