#!/usr/bin/env python3
"""Deterministic checks for the wiki's structural invariants.

Guards what the agent workflow otherwise maintains by discipline alone:
  1. index.md's per-category page count == the entry count of its
     index-<slug>.md
  2. every index entry points to a file that exists; no page is listed under
     more than one category
  3. every knowledge page is listed by some index-<slug>.md (no orphans)
  4. every page's frontmatter confidence is one of {high, medium, low}
  5. related_pages targets exist (no dead links)

Used by wiki_session_start.py (which injects a warning at session start when
problems exist) and as a CLI: `python3 wiki_lint.py [project-root]` prints the
problems and exits 1 when any are found.
"""

import re
import sys
from pathlib import Path

INDEX_LINK_RE = re.compile(r"\[(index-[a-z0-9-]+\.md)\]")
ENTRY_RE = re.compile(r"^- \[[^\]]+\]\(([^)]+\.md)\)", re.MULTILINE)
CONFIDENCE_RE = re.compile(r"^confidence:\s*(\S+)\s*$", re.MULTILINE)
MD_TOKEN_RE = re.compile(r"([A-Za-z0-9._-]+\.md)")

VALID_CONFIDENCE = {"high", "medium", "low"}


def _frontmatter(text: str) -> str | None:
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


def _related_targets(front: str) -> list[str]:
    """.md tokens inside the related_pages block (inline list or dash list)."""
    targets: list[str] = []
    active = False
    for line in front.splitlines():
        if line.startswith("related_pages:"):
            active = True
            targets += MD_TOKEN_RE.findall(line)
            continue
        if active:
            if line[:1] in (" ", "\t") and line.lstrip().startswith("-"):
                targets += MD_TOKEN_RE.findall(line)
            elif line[:1] not in (" ", "\t"):
                active = False  # next top-level key ends the block
    return targets


def _index_rows(index_text: str) -> list[list[str]]:
    """Category-table data rows as cell lists.

    Header handling is language-neutral: skip every table line up to and
    including the |---| separator row (mirrors wiki_session_start.py), so an
    English `| Category |` header is not mistaken for a data row.
    """
    rows: list[list[str]] = []
    seen_separator = False
    for line in index_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if not seen_separator:
            if set(stripped) <= {"|", "-", ":", " "}:
                seen_separator = True
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        rows.append(cells)
    return rows


def lint_wiki(root: Path) -> list[str]:
    wiki = Path(root) / "wiki"
    index_path = wiki / "index.md"
    if not index_path.is_file():
        return ["wiki/index.md does not exist"]

    problems: list[str] = []
    pages = sorted(
        p.name
        for p in wiki.glob("*.md")
        if p.name != "README.md" and not p.name.startswith("index")
    )

    # Level-1 index: | Category | Pages | [index-<slug>.md](...) | keywords |
    declared_counts: dict[str, int | None] = {}
    for cells in _index_rows(index_path.read_text(encoding="utf-8")):
        match = INDEX_LINK_RE.search(cells[2])
        if not match:
            problems.append(
                f"index.md row \"{cells[0]}\" has no index-<slug>.md link in its "
                "directory column"
            )
            continue
        try:
            declared_counts[match.group(1)] = int(cells[1])
        except ValueError:
            declared_counts[match.group(1)] = None
            problems.append(
                f"index.md row \"{cells[0]}\" page count is not a number: {cells[1]!r}"
            )

    # Level-2 entries vs declared counts vs actual files
    entry_owners: dict[str, list[str]] = {}
    for slug_file, declared in declared_counts.items():
        slug_path = wiki / slug_file
        if not slug_path.is_file():
            problems.append(f"{slug_file} is listed in index.md but the file is missing")
            continue
        entries = ENTRY_RE.findall(slug_path.read_text(encoding="utf-8"))
        if declared is not None and len(entries) != declared:
            problems.append(
                f"index.md records {declared} pages for {slug_file}, "
                f"but it lists {len(entries)}"
            )
        for entry in entries:
            entry_owners.setdefault(entry, []).append(slug_file)

    for page, owners in entry_owners.items():
        if not (wiki / page).is_file():
            problems.append(f"{owners[0]} lists a page that does not exist: {page}")
        if len(owners) > 1:
            problems.append(f"{page} is listed by more than one index: {', '.join(owners)}")

    for page in pages:
        if page not in entry_owners:
            problems.append(f"{page} is an orphan page: no index-<slug>.md lists it")

    # Per-page frontmatter
    for page in pages:
        front = _frontmatter((wiki / page).read_text(encoding="utf-8"))
        if front is None:
            problems.append(f"{page} is missing frontmatter")
            continue
        match = CONFIDENCE_RE.search(front)
        value = match.group(1).strip().lower() if match else None
        if value not in VALID_CONFIDENCE:
            problems.append(f"{page} has an invalid or missing confidence: {value!r}")
        for target in _related_targets(front):
            if not (wiki / target).is_file():
                problems.append(f"{page} has a related_pages link to a missing {target}")

    return problems


def main() -> None:
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from wiki_session_start import project_root

        root = project_root()
    problems = lint_wiki(root)
    for problem in problems:
        print(problem)
    if problems:
        sys.exit(1)
    print("wiki lint: OK")


if __name__ == "__main__":
    main()
