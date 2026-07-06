#!/usr/bin/env python3
"""Enforce a lightweight wiki evaluation at Claude Stop time.

The hook allows trivial responses, but blocks substantial responses that do
not contain one of the wiki evaluation markers:

- Wiki suggestion
- No wiki updates needed

The block is not a write operation. It only asks the agent to decide whether
the session produced durable knowledge worth proposing for the project wiki.
"""

import json
import re
import sys
import tempfile


WIKI_EVAL_PATTERN = re.compile(
    r"Wiki\s*suggestion|No\s+wiki\s+updates\s+needed",
    re.IGNORECASE,
)

TRIVIAL_THRESHOLD = 800
MAX_BLOCKS_PER_TURN = 2


def get_state_file(session_id: str) -> str:
    return f"{tempfile.gettempdir()}/wiki-stop-{session_id}.json"


def read_state(session_id: str) -> dict:
    try:
        with open(get_state_file(session_id), encoding="utf-8") as state_file:
            return json.load(state_file)
    except Exception:
        return {"block_count": 0}


def write_state(session_id: str, state: dict) -> None:
    with open(get_state_file(session_id), "w", encoding="utf-8") as state_file:
        json.dump(state, state_file)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    last_msg = data.get("last_assistant_message", "")

    if WIKI_EVAL_PATTERN.search(last_msg):
        write_state(session_id, {"block_count": 0})
        sys.exit(0)

    state = read_state(session_id)

    if state["block_count"] >= MAX_BLOCKS_PER_TURN:
        write_state(session_id, {"block_count": 0})
        sys.exit(0)

    is_commit = bool(re.search(r"git commit|commit [a-f0-9]{7,}", last_msg))

    if not is_commit and len(last_msg) < TRIVIAL_THRESHOLD:
        sys.exit(0)

    state["block_count"] += 1
    write_state(session_id, state)

    reason = (
        "Wiki evaluation: quickly assess whether this response contains "
        "knowledge worth recording in the project wiki.\n"
        '- If yes: propose using the "Wiki suggestion" format\n'
        '- If no: output the exact phrase "No wiki updates needed" so the hook '
        "knows the evaluation was performed"
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
