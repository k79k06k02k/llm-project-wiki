#!/usr/bin/env python3
"""Wiki evaluation enforcer (Stop + PostToolUse pair).

Enforces the commit-time hard trigger from wiki-workflow.md at the tool layer
instead of by reading prose:

  - `mark-commit` mode (PostToolUse on Bash): when the executed command runs
    `git commit`, set `pending_commit` in the session state file.
  - default mode (Stop): if a commit is pending and the final message carries
    no wiki evaluation marker, block the stop and ask for the evaluation. A
    marker clears the flag. Replies that merely *mention* commits never block
    — the old prose regex (`git commit|commit <hash>`) false-positived on
    design discussions and command examples, and blocked every long reply.

Anti-loop: max 2 blocks per turn; the pass-through also clears the flag.
"""

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

# "Is this Bash command a git commit?" — a git segment containing `commit`,
# excluding plumbing like commit-graph / commit-tree. `[^|&;]*` keeps it inside
# one shell segment so `git log | grep commit` does not false-positive. Quotes
# and backslashes are stripped before matching so quoting cannot hide it.
COMMIT_RE = re.compile(r"\bgit\b[^|&;]*?\bcommit(?![\w-])")

# Wiki evaluation markers (Chinese and English). Flexible on spacing/casing but
# specific enough not to fire on incidental references to wiki file paths.
WIKI_EVAL_PATTERN = re.compile(
    r"Wiki\s*suggestion|No\s+wiki\s+updates\s+needed",
    re.IGNORECASE,
)

MAX_BLOCKS_PER_TURN = 2  # Max blocks per turn (infinite loop prevention)


def is_commit_command(command: str) -> bool:
    """True if the Bash command runs `git commit` (not commit-graph/-tree)."""
    normalized = command.replace('"', "").replace("'", "").replace("\\", "")
    return bool(COMMIT_RE.search(normalized))


def state_file(data: dict) -> str:
    """Stable per-session state path under the temp dir.

    The session key is hashed so exotic ids cannot form paths outside the temp
    dir, and a missing session_id falls back to transcript_path — a shared
    literal "unknown" default would make every such session share one state
    file and cross-pollute their block counters.
    """
    key = data.get("session_id") or data.get("transcript_path") or "unknown"
    digest = hashlib.md5(str(key).encode("utf-8")).hexdigest()[:16]
    return str(Path(tempfile.gettempdir()) / f"wiki-stop-{digest}.json")


def read_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {"block_count": 0}


def write_state(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def mark_commit(data: dict) -> None:
    """PostToolUse(Bash): flag the session when a git commit actually ran."""
    if data.get("tool_name") != "Bash":
        return
    tool_input = data.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not is_commit_command(command):
        return
    path = state_file(data)
    state = read_state(path)
    state["pending_commit"] = True
    write_state(path, state)


def handle_stop(data: dict) -> None:
    last_msg = data.get("last_assistant_message", "")
    path = state_file(data)

    # 1. Wiki evaluation marker found — allow stop, clear counter and flag
    if WIKI_EVAL_PATTERN.search(last_msg):
        write_state(path, {"block_count": 0})
        return

    state = read_state(path)

    # 2. No commit actually executed this session — never block, whatever the prose
    if not state.get("pending_commit"):
        return

    # 3. Anti-loop: already blocked >= 2 times this turn — allow stop
    if state.get("block_count", 0) >= MAX_BLOCKS_PER_TURN:
        write_state(path, {"block_count": 0})
        return

    # 4. Block and request wiki evaluation
    state["block_count"] = state.get("block_count", 0) + 1
    write_state(path, state)

    reason = (
        "Wiki evaluation: a git commit was made this session and no wiki "
        "evaluation marker followed. Quickly assess whether the work behind it "
        "produced knowledge worth recording in the project wiki.\n"
        '- If yes: propose using the "Wiki suggestion" format\n'
        '- If no: output the exact phrase "No wiki updates needed" so the hook '
        "knows the evaluation was performed"
    )
    print(json.dumps({"decision": "block", "reason": reason}))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # Cannot parse input — allow
    if not isinstance(data, dict):
        sys.exit(0)

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "mark-commit":
        mark_commit(data)
    else:
        handle_stop(data)
    sys.exit(0)


if __name__ == "__main__":
    main()
