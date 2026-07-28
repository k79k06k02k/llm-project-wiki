#!/usr/bin/env python3
"""Wiki evaluation enforcer for Claude Code and Codex.

Claude Code uses the Stop + PostToolUse pair to enforce the commit-time hard
trigger from wiki-workflow.md:

  - `mark-commit` mode (PostToolUse on Bash): when the executed command runs
    `git commit`, set `pending_commit` in the session state file.
  - default mode (Stop): if a commit is pending and the final message carries
    no wiki evaluation marker, block the stop and ask for the evaluation.
    Replies that merely *mention* commits never block.

Codex uses `codex` mode on every Stop event. SessionStart asks the agent to
output `No wiki suggestion` when no suggestion is needed. A missing marker
blocks once with a continuation prompt; Codex's `stop_hook_active` flag then
prevents a loop.
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

# A marker must occupy its own visible line outside a Markdown code fence.
# This prevents prose such as "the docs require No wiki suggestion" from
# accidentally bypassing the evaluation. The HTML marker remains compatible
# with conversations started before the visible marker changed.
WIKI_EVAL_LINE_PATTERN = re.compile(
    r'^[ \t]*(?:>[ \t]*)*(?:#{1,6}[ \t]+)?(?:'
    r'(?:\*\*)?Wiki[ \t]+suggestion(?:\*\*)?(?:[ \t]*[:：].*)?|'
    r'(?:\*\*)?No[ \t]+wiki[ \t]+suggestion(?:\*\*)?|'
    r'(?:\*\*)?No[ \t]+wiki[ \t]+updates[ \t]+needed(?:\*\*)?|'
    r'<!--[ \t]*wiki-evaluated[ \t]*-->'
    r')[ \t]*$',
    re.IGNORECASE,
)
FENCE_PATTERN = re.compile(r'^[ \t]*(?:>[ \t]*)*(`{3,}|~{3,})')

MAX_BLOCKS_PER_TURN = 2  # Max blocks per turn (infinite loop prevention)


def has_wiki_eval_marker(message: str) -> bool:
    """Return True for a standalone marker line outside fenced code blocks."""
    in_fence = False
    fence_char = ""
    fence_length = 0

    for line in message.splitlines():
        fence = FENCE_PATTERN.match(line)
        if fence:
            token = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = token[0]
                fence_length = len(token)
            elif (
                token[0] == fence_char
                and len(token) >= fence_length
                and not line[fence.end():].strip()
            ):
                in_fence = False
            continue

        if not in_fence and WIKI_EVAL_LINE_PATTERN.fullmatch(line):
            return True

    return False


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
    last_msg = data.get("last_assistant_message")
    if not isinstance(last_msg, str):
        last_msg = ""
    path = state_file(data)

    # 1. Wiki evaluation marker found — allow stop, clear counter and flag
    if has_wiki_eval_marker(last_msg):
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


def handle_codex_stop(data: dict) -> None:
    """Require one Wiki evaluation pass before Codex ends a turn."""
    last_msg = data.get("last_assistant_message")
    if not isinstance(last_msg, str):
        last_msg = ""

    if has_wiki_eval_marker(last_msg) or data.get("stop_hook_active") is True:
        print("{}")
        return

    reason = (
        "Wiki evaluation required before ending this turn. Review the work and "
        "decide whether it produced durable project knowledge that is not "
        "already obvious from the code.\n"
        "- If yes: add a visible `Wiki suggestion` with the target page and "
        "what should be recorded.\n"
        "- If no: output exactly `No wiki suggestion`."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except Exception:
        if mode == "codex":
            print("{}")
        sys.exit(0)  # Cannot parse input — allow
    if not isinstance(data, dict):
        if mode == "codex":
            print("{}")
        sys.exit(0)

    if mode == "mark-commit":
        mark_commit(data)
    elif mode == "codex":
        handle_codex_stop(data)
    else:
        handle_stop(data)
    sys.exit(0)


if __name__ == "__main__":
    main()
