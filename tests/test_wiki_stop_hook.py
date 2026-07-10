"""Tests for the wiki_stop_hook Stop + PostToolUse pair.

Both modes are pure stdin->stdout JSON programs. Tests feed payloads on stdin
and assert whether the stop is blocked. State lives in the temp dir keyed by a
hash of the session id; tests use unique ids and clean up after themselves.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HOOK = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "hooks"
    / "scripts"
    / "wiki_stop_hook.py"
)

spec = importlib.util.spec_from_file_location("wiki_stop_hook", HOOK)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

COMMIT_COMMAND = "git add file.py && git commit -m 'feat: x'"
# A long reply that *mentions* commits/hashes — the removed prose regex used to
# false-positive on exactly this.
PROSE_MSG = (
    "Design note: we could switch the message to git commit -F, like commit "
    "0818bf74 did before. " + "Here are the details. " * 200
)


def run_hook(payload, mode=None, raw_stdin=None):
    argv = [sys.executable, str(HOOK)] + ([mode] if mode else [])
    proc = subprocess.run(
        argv,
        input=raw_stdin if raw_stdin is not None else json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"hook exited {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


class StopHookTestCase(unittest.TestCase):
    def setUp(self):
        self.session = f"test-{uuid.uuid4()}"

    def tearDown(self):
        try:
            os.unlink(mod.state_file({"session_id": self.session}))
        except FileNotFoundError:
            pass

    def mark(self, command=COMMIT_COMMAND, tool_name="Bash"):
        return run_hook(
            {
                "session_id": self.session,
                "tool_name": tool_name,
                "tool_input": {"command": command},
            },
            mode="mark-commit",
        )

    def stop(self, msg):
        return run_hook({"session_id": self.session, "last_assistant_message": msg})

    # a real commit ran + no marker -> block
    def test_pending_commit_without_marker_blocks(self):
        self.mark()
        self.assertEqual(self.stop("Done, committed.").get("decision"), "block")

    # regression lock: prose that merely *mentions* commits/hashes must never
    # block when no commit actually ran this session.
    def test_prose_commit_mention_never_blocks(self):
        self.assertEqual(self.stop(PROSE_MSG), {})

    # either marker satisfies the evaluation and clears the pending flag
    def test_marker_allows_and_clears_pending(self):
        self.mark()
        self.assertEqual(self.stop("Committed.\n\nNo wiki updates needed"), {})
        self.assertEqual(self.stop("A later ordinary reply."), {})  # flag cleared

    def test_wiki_suggestion_marker_allows(self):
        self.mark()
        self.assertEqual(self.stop("Committed.\n\n**Wiki suggestion**: ..."), {})

    # non-commit bash commands do not set the flag
    def test_non_commit_command_not_marked(self):
        self.mark(command="git log --oneline | head")
        self.assertEqual(self.stop("Finished reading history."), {})

    # non-Bash tools are ignored by mark-commit
    def test_non_bash_tool_ignored(self):
        self.mark(tool_name="Write")
        self.assertEqual(self.stop("Wrote the file."), {})

    # anti-loop: block, block, then allow — and the pass-through clears the flag
    def test_antiloop_allows_after_two_blocks_and_clears(self):
        self.mark()
        self.assertEqual(self.stop("done").get("decision"), "block")
        self.assertEqual(self.stop("done").get("decision"), "block")
        self.assertEqual(self.stop("done"), {})
        self.assertEqual(self.stop("done"), {})  # flag cleared, no re-block

    # pending survives across turns until a marker (or pass-through) clears it
    def test_pending_persists_until_marker(self):
        self.mark()
        self.assertEqual(self.stop("First reply after commit").get("decision"), "block")
        self.assertEqual(self.stop("Adding the evaluation. No wiki updates needed"), {})

    # malformed stdin must not crash or block
    def test_non_dict_stdin_allows(self):
        self.assertEqual(run_hook(None, raw_stdin="[]"), {})
        self.assertEqual(run_hook(None, raw_stdin="not json"), {})
        self.assertEqual(run_hook(None, mode="mark-commit", raw_stdin="[]"), {})


class StateFileTestCase(unittest.TestCase):
    """state_file is a pure function: keying and path-safety invariants."""

    def test_distinct_sessions_get_distinct_files(self):
        a = mod.state_file({"session_id": "aaa"})
        b = mod.state_file({"session_id": "bbb"})
        self.assertNotEqual(a, b)

    # missing session_id falls back to transcript_path, so two concurrent
    # sessions without ids do not share (and cross-pollute) one counter
    def test_missing_session_id_falls_back_to_transcript(self):
        a = mod.state_file({"transcript_path": "/x/a.jsonl"})
        b = mod.state_file({"transcript_path": "/x/b.jsonl"})
        self.assertNotEqual(a, b)

    # the key is hashed: hostile ids cannot escape the temp dir or inject path
    # parts. The prefix is the platform temp dir (not hardcoded /tmp).
    def test_weird_session_id_stays_in_tempdir(self):
        path = mod.state_file({"session_id": "../../etc/passwd"})
        self.assertTrue(path.startswith(tempfile.gettempdir()))
        self.assertRegex(Path(path).name, r"^wiki-stop-[0-9a-f]{16}\.json$")


if __name__ == "__main__":
    unittest.main()
