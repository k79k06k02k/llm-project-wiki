"""Tests for write-policy resolution and index summarization in the
SessionStart hook.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / ".claude" / "hooks" / "scripts" / "wiki_session_start.py"

spec = importlib.util.spec_from_file_location("wiki_session_start", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ResolveWritePolicyTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_config(self, obj):
        (self.root / "wiki.config.json").write_text(json.dumps(obj), encoding="utf-8")

    def test_enum_values(self):
        for value in ("require_approval", "auto", "open"):
            self.write_config({"write_policy": value})
            self.assertEqual(mod.resolve_write_policy(self.root), value)

    def test_legacy_true_maps_to_require_approval(self):
        self.write_config({"require_human_approval": True})
        self.assertEqual(mod.resolve_write_policy(self.root), "require_approval")

    def test_legacy_false_maps_to_open(self):
        self.write_config({"require_human_approval": False})
        self.assertEqual(mod.resolve_write_policy(self.root), "open")

    def test_enum_takes_precedence_over_legacy(self):
        self.write_config({"write_policy": "open", "require_human_approval": True})
        self.assertEqual(mod.resolve_write_policy(self.root), "open")

    def test_missing_config_fails_closed(self):
        self.assertEqual(mod.resolve_write_policy(self.root), "require_approval")

    def test_invalid_value_fails_closed(self):
        self.write_config({"write_policy": "banana"})
        self.assertEqual(mod.resolve_write_policy(self.root), "require_approval")

    def test_non_dict_config_fails_closed(self):
        (self.root / "wiki.config.json").write_text("[]", encoding="utf-8")
        self.assertEqual(mod.resolve_write_policy(self.root), "require_approval")

    # A BOM-prefixed config (as saved by some editors) must not fail JSON
    # parsing and silently fall back to require_approval.
    def test_bom_prefixed_config_reads_policy(self):
        (self.root / "wiki.config.json").write_text(
            '﻿{"write_policy": "auto"}', encoding="utf-8"
        )
        self.assertEqual(mod.resolve_write_policy(self.root), "auto")


class WritePolicyTextTestCase(unittest.TestCase):
    def test_require_approval_text(self):
        text = mod.write_policy_text("require_approval")
        self.assertIn("approval REQUIRED", text)

    def test_open_text(self):
        text = mod.write_policy_text("open")
        self.assertIn("NOT required", text)

    def test_auto_text_mentions_confidence_and_gate(self):
        text = mod.write_policy_text("auto")
        self.assertIn("auto", text.lower())
        self.assertIn("confidence", text.lower())

    # The log moved from a single wiki/log.md to a weekly wiki/log/ tree; the
    # open/auto policy text must point at the weekly file, not the old path.
    def test_policy_text_references_weekly_log_not_log_md(self):
        for policy in ("open", "auto"):
            for flavor in ("claude", "codex"):
                text = mod.write_policy_text(policy, flavor)
                self.assertNotIn("wiki/log.md", text)
                self.assertIn("current week's log file under wiki/log/", text)


class MainFlavorTestCase(unittest.TestCase):
    """Subprocess-level checks for the CLI entry (mode + flavor argv parsing,
    the index category-table parser, and its fallback branch)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "wiki").mkdir()
        (self.root / "wiki" / "index.md").write_text(
            "# Wiki Index\n\n| Category | Pages | Directory | Keywords |\n|---|---|---|---|\n"
            "| Architecture | 1 | [index-architecture.md](index-architecture.md) | "
            "architecture, system, module |\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_hook(self, *args):
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), *args],
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_claude_flavor_has_policy_without_codex_rule(self):
        ctx = self.run_hook("wiki-index")
        self.assertIn("Wiki write policy", ctx)
        self.assertNotIn("Codex wiki review rule", ctx)

    def test_codex_flavor_appends_codex_rule(self):
        ctx = self.run_hook("wiki-index", "codex")
        self.assertIn("Codex wiki review rule", ctx)
        self.assertIn("Wiki write policy", ctx)

    def test_summary_parses_index_table(self):
        ctx = self.run_hook("wiki-index")
        self.assertIn("Architecture (1 pages)", ctx)
        self.assertIn("index-architecture.md", ctx)

    # The parser skips the header structurally (everything up to the |---|
    # separator row), so it must work regardless of the header's language.
    def test_summary_parses_index_table_with_non_english_header(self):
        (self.root / "wiki" / "index.md").write_text(
            "# Wiki\n\n| Catégorie | Pages | Répertoire | Mots-clés |\n|---|---|---|---|\n"
            "| Général | 1 | [index-architecture.md](index-architecture.md) | divers |\n",
            encoding="utf-8",
        )
        ctx = self.run_hook("wiki-index")
        self.assertIn("Général (1 pages)", ctx)
        self.assertIn("index-architecture.md", ctx)

    # A flat index.md with no category table (no |---| separator row) has no
    # rows to summarize, so the hook falls back to injecting the file verbatim.
    def test_flat_index_without_table_falls_back_to_full_text(self):
        (self.root / "wiki" / "index.md").write_text(
            "# Wiki\n\nJust a flat list of pages, no category table here.\n",
            encoding="utf-8",
        )
        ctx = self.run_hook("wiki-index")
        self.assertIn("Project wiki index:", ctx)
        self.assertIn("Just a flat list of pages, no category table here.", ctx)


if __name__ == "__main__":
    unittest.main()
