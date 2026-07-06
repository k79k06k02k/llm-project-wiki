"""Tests for the wiki_write_gate PreToolUse hook.

The gate is a pure stdin->stdout JSON program. Each test feeds a PreToolUse
payload on stdin (with CLAUDE_PROJECT_DIR pointing at a temp repo) and asserts
the resulting decision.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / ".claude" / "hooks" / "scripts" / "wiki_write_gate.py"


def page(confidence="high", body="# Title\n\nSome body text.\n", title="X"):
    """Build a wiki page with optional confidence frontmatter."""
    if confidence is None:
        front = f"---\ntitle: {title}\n---\n"
    else:
        front = f"---\ntitle: {title}\nconfidence: {confidence}\n---\n"
    return front + body


def run_gate(payload, root, cwd=None, raw_stdin=None):
    proc = subprocess.run(
        [sys.executable, str(GATE)],
        input=raw_stdin if raw_stdin is not None else json.dumps(payload),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert proc.returncode == 0, f"gate exited {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def decision(out):
    """'deny' / 'allow' from the hook output; None means silent-allow."""
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "wiki").mkdir()
        # Top-level index lists the valid index-<slug> pages; this is the
        # allowlist source for the index-* maintenance exemption below.
        (self.root / "wiki" / "index.md").write_text(
            "# Wiki Index\n\n| Category | Pages | Directory | Keywords |\n|---|---|---|---|\n"
            "| Architecture | 1 | [index-architecture.md](index-architecture.md) | architecture |\n",
            encoding="utf-8",
        )
        self.set_policy("auto")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def set_policy(self, policy):
        (self.root / "wiki.config.json").write_text(
            json.dumps({"write_policy": policy}), encoding="utf-8"
        )

    def write_page(self, name, **kw):
        (self.root / "wiki" / name).write_text(page(**kw), encoding="utf-8")

    def Write(self, rel, content):
        return {"tool_name": "Write", "tool_input": {"file_path": str(self.root / rel), "content": content}}

    def Edit(self, rel, old, new):
        return {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.root / rel),
                "old_string": old,
                "new_string": new,
            },
        }

    def Bash(self, command):
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    # 1. new page with confidence: high -> allow + summary
    def test_new_page_high_allows_with_message(self):
        out = run_gate(self.Write("wiki/new.md", page("high")), self.root)
        self.assertEqual(decision(out), "allow")
        self.assertIn("new.md", out.get("systemMessage", ""))

    # 2. new page with confidence: medium / low -> deny
    def test_new_page_medium_denies(self):
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertEqual(decision(out), "deny")

    def test_new_page_low_denies(self):
        out = run_gate(self.Write("wiki/new.md", page("low")), self.root)
        self.assertEqual(decision(out), "deny")

    # 3. log.md append / index.md edit -> allow (rule 3)
    def test_index_edit_allows(self):
        self.write_page("index.md", confidence=None)
        out = run_gate(self.Edit("wiki/index.md", "Some body text.", "New body."), self.root)
        self.assertIsNone(decision(out))

    # Legacy back-compat regression test: the gate still exempts a flat
    # wiki/log.md even though the log has moved to a weekly wiki/log/ tree,
    # so downstream projects installed before that migration keep working.
    def test_legacy_log_md_write_still_allows(self):
        out = run_gate(self.Write("wiki/log.md", "# Log\n\n- entry\n"), self.root)
        self.assertIsNone(decision(out))

    # 4. Write rewrite, resulting high -> allow + diff
    def test_rewrite_high_allows_with_diff(self):
        self.write_page("p.md", confidence="high", body="# P\n\nold line\n")
        out = run_gate(self.Write("wiki/p.md", page("high", body="# P\n\nnew line\n")), self.root)
        self.assertEqual(decision(out), "allow")
        self.assertIn("new line", out.get("systemMessage", ""))

    # 5. Write rewrite, resulting medium / low -> deny
    def test_rewrite_medium_denies(self):
        self.write_page("p.md", confidence="high")
        out = run_gate(self.Write("wiki/p.md", page("medium")), self.root)
        self.assertEqual(decision(out), "deny")

    # 6. Edit leaving resulting high (edit does not touch frontmatter) -> allow + diff
    def test_edit_keeps_high_allows(self):
        self.write_page("p.md", confidence="high", body="# P\n\noriginal body\n")
        out = run_gate(self.Edit("wiki/p.md", "original body", "edited body"), self.root)
        self.assertEqual(decision(out), "allow")
        self.assertIn("edited body", out.get("systemMessage", ""))

    # 7. Edit lowering resulting confidence to medium -> deny
    def test_edit_lowers_to_medium_denies(self):
        self.write_page("p.md", confidence="high", body="# P\n\nbody\n")
        out = run_gate(self.Edit("wiki/p.md", "confidence: high", "confidence: medium"), self.root)
        self.assertEqual(decision(out), "deny")

    # 8. resulting frontmatter has no / garbled confidence -> deny
    def test_missing_confidence_denies(self):
        out = run_gate(self.Write("wiki/new.md", page(None)), self.root)
        self.assertEqual(decision(out), "deny")

    # 9. Bash rm / git rm / mv out of wiki -> deny
    def test_bash_rm_denies(self):
        self.write_page("p.md")
        out = run_gate(self.Bash("rm wiki/p.md"), self.root)
        self.assertEqual(decision(out), "deny")

    def test_bash_git_rm_denies(self):
        self.write_page("p.md")
        out = run_gate(self.Bash("git rm wiki/p.md"), self.root)
        self.assertEqual(decision(out), "deny")

    def test_bash_mv_out_denies(self):
        self.write_page("p.md")
        out = run_gate(self.Bash("mv wiki/p.md /tmp/p.md"), self.root)
        self.assertEqual(decision(out), "deny")

    # 10. write to nested folder / non-.md inside wiki -> deny
    def test_nested_path_denies(self):
        out = run_gate(self.Write("wiki/sub/page.md", page("high")), self.root)
        self.assertEqual(decision(out), "deny")

    def test_non_md_in_wiki_denies(self):
        out = run_gate(self.Write("wiki/page.txt", "data"), self.root)
        self.assertEqual(decision(out), "deny")

    # 11. non-wiki path -> allow (inert)
    def test_non_wiki_path_inert(self):
        out = run_gate(self.Write("src/foo.py", "print(1)"), self.root)
        self.assertIsNone(decision(out))

    def test_bash_non_wiki_inert(self):
        out = run_gate(self.Bash("rm src/foo.py"), self.root)
        self.assertIsNone(decision(out))

    # 12. require_approval and open -> gate inert
    def test_require_approval_inert(self):
        self.set_policy("require_approval")
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertIsNone(decision(out))

    def test_open_inert(self):
        self.set_policy("open")
        out = run_gate(self.Bash("rm wiki/p.md"), self.root)
        self.assertIsNone(decision(out))

    # 13a. legacy boolean: require_human_approval true -> behaves as require_approval (inert)
    def test_legacy_true_inert(self):
        (self.root / "wiki.config.json").write_text(
            json.dumps({"require_human_approval": True}), encoding="utf-8"
        )
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertIsNone(decision(out))

    # 13b. legacy boolean false -> open (inert)
    def test_legacy_false_inert(self):
        (self.root / "wiki.config.json").write_text(
            json.dumps({"require_human_approval": False}), encoding="utf-8"
        )
        out = run_gate(self.Bash("rm wiki/p.md"), self.root)
        self.assertIsNone(decision(out))

    # 13c. missing config -> fail-closed to require_approval (inert)
    def test_missing_config_inert(self):
        (self.root / "wiki.config.json").unlink()
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertIsNone(decision(out))

    # 13d. invalid policy value -> fail-closed to require_approval (inert)
    def test_invalid_policy_inert(self):
        self.set_policy("banana")
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertIsNone(decision(out))

    # --- Robustness fixes from code review ---

    # Bash bypasses that the narrow `wiki/...\.md` regex missed.
    def test_bash_rm_rf_whole_dir_denies(self):
        out = run_gate(self.Bash("rm -rf wiki"), self.root)
        self.assertEqual(decision(out), "deny")

    def test_bash_rm_glob_denies(self):
        out = run_gate(self.Bash("rm wiki/*"), self.root)
        self.assertEqual(decision(out), "deny")

    def test_bash_mv_dir_denies(self):
        out = run_gate(self.Bash("mv wiki/ /tmp/"), self.root)
        self.assertEqual(decision(out), "deny")

    # Must not false-positive on an unrelated path that merely contains "wiki".
    def test_bash_unrelated_wiki_substring_inert(self):
        out = run_gate(self.Bash("rm /tmp/wiki-notes.txt"), self.root)
        self.assertIsNone(decision(out))

    # Non-dict config root must not crash the gate (fail-closed -> inert).
    def test_non_dict_config_inert(self):
        (self.root / "wiki.config.json").write_text("[]", encoding="utf-8")
        out = run_gate(self.Write("wiki/new.md", page("medium")), self.root)
        self.assertIsNone(decision(out))

    # Non-dict stdin payload must not crash the gate.
    def test_non_dict_stdin_inert(self):
        out = run_gate(None, self.root, raw_stdin="[]")
        self.assertIsNone(decision(out))

    # Relative file_path resolves against the project root, not the cwd.
    def test_relative_path_resolves_against_root(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "wiki/new.md", "content": page("medium")},
        }
        out = run_gate(payload, self.root, cwd="/tmp")
        self.assertEqual(decision(out), "deny")

    # Non-string file_path must not crash (inert).
    def test_non_string_file_path_inert(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": 42, "content": "x"}}
        out = run_gate(payload, self.root)
        self.assertIsNone(decision(out))

    # UTF-8 BOM prefix must not break frontmatter confidence parsing.
    def test_bom_prefix_high_allows(self):
        self.write_page("p.md", confidence="high")
        out = run_gate(self.Write("wiki/p.md", "﻿" + page("high")), self.root)
        self.assertEqual(decision(out), "allow")

    # --- Two-level index + weekly wiki/log/ tree ---

    # index-<slug>.md is a second-level index; maintenance writes to it need
    # no confidence frontmatter -> allow.
    def test_index_slug_write_allows(self):
        out = run_gate(
            self.Write("wiki/index-architecture.md", "- [a](a.md) — desc\n"), self.root
        )
        self.assertIsNone(decision(out))

    # README.md is the entry-point doc, no confidence frontmatter expected -> allow.
    def test_readme_write_allows(self):
        out = run_gate(self.Write("wiki/README.md", "# Wiki\n"), self.root)
        self.assertIsNone(decision(out))

    # Weekly log file wiki/log/<year>/<monday>.md -> allow (maintenance, no
    # confidence check).
    def test_weekly_log_write_allows(self):
        out = run_gate(
            self.Write("wiki/log/2026/2026-07-06.md", "# Log\n\n## entry\n"), self.root
        )
        self.assertIsNone(decision(out))

    # The log tree's own index wiki/log/index.md -> allow.
    def test_log_index_write_allows(self):
        out = run_gate(self.Write("wiki/log/index.md", "# Log index\n"), self.root)
        self.assertIsNone(decision(out))

    # Non-.md file inside the log tree -> deny.
    def test_log_non_md_denies(self):
        out = run_gate(self.Write("wiki/log/2026/data.json", "{}"), self.root)
        self.assertEqual(decision(out), "deny")

    # A nested path outside the log tree is still denied (a deeper case beyond
    # test_nested_path_denies above).
    def test_deep_non_log_nested_denies(self):
        out = run_gate(self.Write("wiki/notes/2026/x.md", page("high")), self.root)
        self.assertEqual(decision(out), "deny")

    # --- Adversarial regression: filename spoofing / shell redirects / case bypass ---

    # The index-<slug>.md exemption only recognizes slugs actually listed in
    # wiki/index.md's directory column; a spoofed index-<fake>.md with no
    # frontmatter must still be denied.
    def test_fake_index_slug_denies(self):
        out = run_gate(
            self.Write("wiki/index-totally-fake.md", "smuggled knowledge, no frontmatter\n"),
            self.root,
        )
        self.assertEqual(decision(out), "deny")

    # When wiki/index.md itself is missing, the index-* exemption fails closed
    # (only the fixed names index.md/README.md/log.md stay exempt).
    def test_index_slug_fails_closed_without_index(self):
        (self.root / "wiki" / "index.md").unlink()
        out = run_gate(
            self.Write("wiki/index-architecture.md", "- [a](a.md) — desc\n"), self.root
        )
        self.assertEqual(decision(out), "deny")

    # Shell redirect / tee into wiki -> deny (>, >>, tee, tee -a).
    def test_bash_redirect_into_wiki_denies(self):
        for cmd in (
            "cat > wiki/sneaky.md",
            "echo x >> wiki/sneaky.md",
            "tee wiki/sneaky.md",
            "sort input | tee -a wiki/sneaky.md",
        ):
            out = run_gate(self.Bash(cmd), self.root)
            self.assertEqual(decision(out), "deny", f"cmd not denied: {cmd}")

    # A redirect that reads out of wiki (target is outside wiki/) must not be
    # falsely denied.
    def test_bash_redirect_out_of_wiki_inert(self):
        out = run_gate(self.Bash("cat wiki/p.md > /tmp/out.md"), self.root)
        self.assertIsNone(decision(out))

    # macOS APFS is case-insensitive: a WIKI/ path must be treated the same as
    # wiki/ and must not bypass the confidence check.
    def test_uppercase_wiki_write_denies(self):
        out = run_gate(self.Write("WIKI/new.md", page("medium")), self.root)
        self.assertEqual(decision(out), "deny")

    def test_uppercase_wiki_bash_rm_denies(self):
        out = run_gate(self.Bash("rm WIKI/p.md"), self.root)
        self.assertEqual(decision(out), "deny")

    # Shell quoting / backslash-escaping bypasses: the command is normalized
    # (quotes and backslashes stripped) before matching.
    def test_bash_quoted_wiki_segment_denies(self):
        for cmd in (
            'echo x > "wiki"/new.md',
            "echo x > 'wiki'/new.md",
            '"tee" wiki/new.md',
            'rm -rf wi"ki"',
            "rm -rf wi\\ki",
        ):
            out = run_gate(self.Bash(cmd), self.root)
            self.assertEqual(decision(out), "deny", f"cmd not denied: {cmd}")


if __name__ == "__main__":
    unittest.main()
