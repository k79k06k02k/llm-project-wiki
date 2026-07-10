"""Tests for wiki_lint: structural invariants over a temp wiki fixture."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "hooks"
    / "scripts"
    / "wiki_lint.py"
)

spec = importlib.util.spec_from_file_location("wiki_lint", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def page(confidence="high", related=()):
    related_block = (
        "related_pages:\n" + "".join(f"  - {r}\n" for r in related)
        if related
        else "related_pages: []\n"
    )
    return (
        f"---\ntitle: T\ntags: [x]\nlast_updated: 2026-07-10\n"
        f"confidence: {confidence}\nsources:\n  - src\n{related_block}---\n\n# T\n"
    )


class WikiLintTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.wiki = self.root / "wiki"
        self.wiki.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def build(self, count=2, entries=("a.md", "b.md"), files=None):
        """Consistent-by-default fixture: one category, N entries, N files."""
        (self.wiki / "index.md").write_text(
            "# Wiki Index\n\n| Category | Pages | Directory | Keywords |\n|---|---|---|---|\n"
            f"| Architecture | {count} | [index-architecture.md](index-architecture.md) | arch |\n",
            encoding="utf-8",
        )
        (self.wiki / "index-architecture.md").write_text(
            "".join(f"- [{e[:-3]}]({e}) — desc\n" for e in entries), encoding="utf-8"
        )
        for name in files if files is not None else entries:
            (self.wiki / name).write_text(page(), encoding="utf-8")

    def test_consistent_wiki_is_clean(self):
        self.build()
        self.assertEqual(mod.lint_wiki(self.root), [])

    def test_missing_index_reported(self):
        self.assertEqual(mod.lint_wiki(self.root), ["wiki/index.md does not exist"])

    # The English `| Category |` header is skipped structurally (separator-based),
    # not by a hardcoded label — it must not be mistaken for a data row.
    def test_english_header_not_treated_as_data(self):
        self.build()
        self.assertEqual(mod.lint_wiki(self.root), [])

    def test_count_mismatch_reported(self):
        self.build(count=3)
        self.assertTrue(any("but it lists 2" in p for p in mod.lint_wiki(self.root)))

    def test_dead_index_entry_reported(self):
        self.build(entries=("a.md", "b.md"), files=("a.md",))
        problems = mod.lint_wiki(self.root)
        self.assertTrue(
            any("does not exist: b.md" in p for p in problems), problems
        )

    def test_orphan_page_reported(self):
        self.build()
        (self.wiki / "c.md").write_text(page(), encoding="utf-8")
        self.assertTrue(
            any("c.md is an orphan page" in p for p in mod.lint_wiki(self.root))
        )

    def test_illegal_confidence_reported(self):
        self.build()
        (self.wiki / "a.md").write_text(page(confidence="medium-high"), encoding="utf-8")
        problems = mod.lint_wiki(self.root)
        self.assertTrue(
            any("invalid or missing confidence" in p and "a.md" in p for p in problems)
        )

    def test_legal_confidence_values_pass(self):
        for value in ("high", "medium", "low"):
            self.build()
            (self.wiki / "a.md").write_text(page(confidence=value), encoding="utf-8")
            self.assertEqual(mod.lint_wiki(self.root), [], value)

    def test_dead_related_link_reported(self):
        self.build()
        (self.wiki / "a.md").write_text(page(related=("ghost.md",)), encoding="utf-8")
        problems = mod.lint_wiki(self.root)
        self.assertTrue(
            any("related_pages link to a missing ghost.md" in p for p in problems)
        )

    def test_valid_related_link_passes(self):
        self.build()
        (self.wiki / "a.md").write_text(page(related=("b.md",)), encoding="utf-8")
        self.assertEqual(mod.lint_wiki(self.root), [])

    def test_duplicate_listing_reported(self):
        self.build()
        (self.wiki / "index.md").write_text(
            "# Wiki Index\n\n| Category | Pages | Directory | Keywords |\n|---|---|---|---|\n"
            "| Architecture | 2 | [index-architecture.md](index-architecture.md) | arch |\n"
            "| Debugging | 1 | [index-debugging.md](index-debugging.md) | bug |\n",
            encoding="utf-8",
        )
        (self.wiki / "index-debugging.md").write_text(
            "- [a](a.md) — dup\n", encoding="utf-8"
        )
        problems = mod.lint_wiki(self.root)
        self.assertTrue(
            any("a.md is listed by more than one index" in p for p in problems)
        )

    def test_missing_frontmatter_reported(self):
        self.build()
        (self.wiki / "a.md").write_text("# no frontmatter\n", encoding="utf-8")
        self.assertTrue(
            any("a.md is missing frontmatter" in p for p in mod.lint_wiki(self.root))
        )


if __name__ == "__main__":
    unittest.main()
