#!/usr/bin/env python3
"""Enforce a lightweight wiki evaluation marker at Codex Stop time.

Normal responses should include one of these markers:

- visible `Wiki suggestion` when durable project knowledge should be recorded
- hidden `<!-- No wiki updates needed -->` when there is nothing to record

The hook only blocks when a substantial response forgets the marker. This keeps
the regular transcript clean while preserving the wiki review gate.
"""

import json
import re
import sys


WIKI_EVAL_PATTERN = re.compile(
    r"Wiki\s*suggestion|No\s+wiki\s+updates\s+needed",
    re.IGNORECASE,
)

TRIVIAL_THRESHOLD = 800
MAX_BLOCKS_PER_TURN = 1


def get_state_file(session_id: str) -> str:
    return f"/tmp/wiki-stop-{session_id}.json"


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
        "Missing wiki evaluation marker. Add a visible `Wiki suggestion` if "
        "durable project knowledge should be recorded; otherwise add hidden "
        "`<!-- No wiki updates needed -->` at the end of the response."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
