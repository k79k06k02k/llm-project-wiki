#!/usr/bin/env python3
"""Load project wiki context at session start.

Shared by Claude Code and Codex: the second argv selects the flavor
("claude" default, "codex"), which only changes the injected wording.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)

    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if output:
            return Path(output)
    except Exception:
        pass

    return Path.cwd()


VALID_POLICIES = {"require_approval", "auto", "open"}


def resolve_write_policy(root: Path) -> str:
    """Resolve the active write policy. Fail closed: default to require_approval.

    Resolution order:
      1. A valid `write_policy` enum value.
      2. Legacy `require_human_approval` boolean (true -> require_approval,
         false -> open).
      3. require_approval (fail-closed: missing/unreadable/invalid config).
    """
    try:
        config = json.loads((root / "wiki.config.json").read_text(encoding="utf-8-sig"))
        if isinstance(config, dict):
            policy = config.get("write_policy")
            if policy in VALID_POLICIES:
                return policy
            if "require_human_approval" in config:
                return "require_approval" if config.get("require_human_approval") else "open"
    except Exception:
        pass

    return "require_approval"


def write_policy_text(policy: str, flavor: str = "claude") -> str:
    if policy == "open":
        return (
            "Wiki write policy (wiki.config.json): human approval NOT required "
            "(open). When you find durable knowledge, you may write the wiki page "
            "directly without waiting for approval — still maintain the two-level "
            "index (wiki/index.md + wiki/index-<slug>.md) and output a wiki "
            'evaluation marker (e.g. "Wiki suggestion") so the Stop hook passes. '
            "Change history lives in git, so there is no log file to update."
        )
    if policy == "auto":
        if flavor == "codex":
            return (
                "Wiki write policy (wiki.config.json): auto. NOTE: the deterministic "
                "PreToolUse gate is Claude-only; Codex does not enforce it, so apply "
                "these rules by self-discipline. You may write a wiki page directly "
                "only when its resulting frontmatter confidence is `high`, and you must "
                "then disclose the diff. If the resulting confidence would be `medium`, "
                "`low`, or missing — or for any delete or wrong-location write — do not "
                'write; propose it with the "Wiki suggestion" format instead. Still '
                "maintain the two-level index and emit a wiki evaluation marker."
            )
        return (
            "Wiki write policy (wiki.config.json): auto. You may write a wiki page "
            "directly only when its resulting frontmatter confidence is `high`. A "
            "PreToolUse gate enforces this deterministically: writes whose "
            "resulting confidence is `medium`, `low`, or missing — plus deletes and "
            "writes to the wrong location inside wiki/ — are blocked and must be "
            'proposed with the "Wiki suggestion" format instead. High-confidence '
            "writes are allowed, but the gate surfaces their diff to the human, so "
            "set confidence honestly. Still maintain the two-level index "
            "(wiki/index.md + wiki/index-<slug>.md) and output a wiki evaluation "
            "marker so the Stop hook passes. Change history lives in git, so there "
            "is no log file to update."
        )
    return (
        "Wiki write policy (wiki.config.json): human approval REQUIRED. "
        'Propose updates with the "Wiki suggestion" format and wait for '
        "explicit approval before creating, updating, or deleting any wiki page."
    )


def emit_context(text: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                }
            }
        )
    )


def lint_warning(root: Path) -> str:
    """Warning block for wiki structural problems, or "" when clean.

    Fail-soft: a broken lint must never break session start.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from wiki_lint import lint_wiki

        problems = lint_wiki(root)
    except Exception:
        return ""
    if not problems:
        return ""
    shown = problems[:10]
    more = f"\n  …and {len(problems)} problems in total" if len(problems) > 10 else ""
    return (
        "\n\n⚠ Wiki lint found structural problems (index/confidence/related_pages "
        "invariants broken). When this session touches the wiki, fix these first:\n"
        + "\n".join(f"  - {p}" for p in shown)
        + more
    )


def git_output(root: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).rstrip()
    except Exception:
        return ""


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    flavor = sys.argv[2] if len(sys.argv) > 2 else "claude"
    root = project_root()

    if mode == "wiki-index":
        index_path = root / "wiki" / "index.md"
        if not index_path.is_file():
            print("{}")
            return
        codex_rule = (
            "Codex wiki review rule: every substantial final response must "
            "evaluate whether the conversation produced durable project "
            "knowledge. If yes, include a visible `Wiki suggestion`. If no, "
            "do not add a visible no-op marker; keep the transcript clean.\n\n"
            if flavor == "codex"
            else ""
        )
        policy_text = write_policy_text(resolve_write_policy(root), flavor)

        # Summarize the category table instead of injecting the full index:
        # rows are (category, page count, sub-index link, keywords). The header
        # is skipped structurally (everything up to the |---| separator row),
        # so it works for any header language.
        text = index_path.read_text(encoding="utf-8")
        rows = []
        seen_separator = False
        for line in text.splitlines():
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
            cat, cnt, link = cells[0], cells[1], cells[2]
            keywords = cells[3] if len(cells) >= 4 else ""
            rows.append((cat, cnt, link, keywords))

        if not rows:
            # No category table (e.g. a legacy flat index): inject it verbatim.
            emit_context(
                f"Project wiki index:\n\n{text}\n\n{codex_rule}{policy_text}"
            )
            return

        lines_out = []
        for cat, cnt, link, keywords in rows:
            head = f"- {cat} ({cnt} pages) → {link}"
            lines_out.append(f"{head}\n  keywords: {keywords}" if keywords else head)
        summary = "\n".join(lines_out)

        emit_context(
            "Project wiki categories (top-level index; details lazy-load):\n\n"
            f"{summary}\n\n"
            "Lookup workflow:\n"
            "1. Match the topic against the categories above. Category names are "
            "descriptive labels and users often use aliases, so match against the "
            "keywords column semantically; only fall back to step 3 when nothing "
            "matches.\n"
            "2. Read wiki/index-<slug>.md for that category's full page list.\n"
            "3. Otherwise grep: rg \"<keyword>\" wiki/ -g '!index*.md'\n"
            "4. Tag filter: .claude/scripts/wiki-search.sh -t <tag> (or: "
            "rg \"^tags:.*<tag>\" wiki/ -g '!index*.md')\n"
            "Do not Read the full wiki/index.md (this summary already covers it). "
            "For a page's change history, use git log wiki/<page>.md.\n\n"
            f"{codex_rule}{policy_text}{lint_warning(root)}"
        )
        return

    if mode == "git-context":
        status = git_output(root, ["status", "-s"])
        latest_commit = git_output(root, ["log", "-1", "--format=%h %s (%cr)"])
        emit_context(f"Git status:\n{status}\n\nLatest commit:\n{latest_commit}\n")
        return

    print("{}")


if __name__ == "__main__":
    main()
