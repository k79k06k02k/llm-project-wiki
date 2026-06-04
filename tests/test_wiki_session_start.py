"""Tests for write-policy resolution in the SessionStart hook."""

import importlib.util
import json
import shutil
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


if __name__ == "__main__":
    unittest.main()
