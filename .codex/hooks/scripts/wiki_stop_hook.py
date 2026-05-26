#!/usr/bin/env python3
"""Keep Codex Stop hook non-blocking for wiki self-review.

Codex renders Stop hook blocks as visible Hook feedback and then asks the model
to add another response. That disrupts the previous assistant message in the UI,
which is worse than the wiki reminder it tries to enforce.

Wiki review is still requested through the SessionStart context. This hook stays
installed as an explicit no-op so the Codex hook chain does not produce visible
feedback at Stop time.
"""

import json
import sys


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass


if __name__ == "__main__":
    main()
