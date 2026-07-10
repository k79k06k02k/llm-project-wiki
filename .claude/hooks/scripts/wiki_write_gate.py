#!/usr/bin/env python3
"""PreToolUse gate for wiki writes under the `auto` write policy.

This hook is the deterministic enforcement layer for `write_policy: auto`. It
only governs the `wiki/` tree and only acts when the policy is `auto`; in every
other case it exits silently (allow).

The index is two-level (index.md + index-<slug>.md) and the wiki is otherwise
flat: change history lives in git (`git log wiki/<page>.md`), not in a tracked
log file, so the gate only knows about knowledge pages and the index.

Classification (first match wins):
  1. Bash rm/git rm/mv referencing wiki                -> deny
  2. Write/Edit to a non-flat or non-.md wiki path     -> deny
  3. index*.md / README.md maintenance                 -> allow (no confidence)
  4. resulting confidence == high                      -> allow + surface diff
  5. resulting confidence == medium / low              -> deny
  6. resulting confidence missing / unparseable        -> deny (fail-closed)
"""

import difflib
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_session_start import project_root, resolve_write_policy

CONFIDENCE_RE = re.compile(r"^confidence:\s*(\S+)\s*$", re.MULTILINE)


def is_maintenance(name: str, root: Path) -> bool:
    """Top-level index/README files carry no confidence frontmatter.

    `index-<slug>.md` is exempt only when the slug is actually listed in the
    directory column of wiki/index.md — otherwise any knowledge page could
    dodge the confidence check by taking an index- prefix (fail-closed: if
    index.md is missing or unreadable, no index-* file is exempt).
    """
    if name in {"README.md", "index.md"}:
        return True
    if not name.startswith("index-"):
        return False
    try:
        index_text = (root / "wiki" / "index.md").read_text(encoding="utf-8")
    except Exception:
        return False
    return name in re.findall(r"index-[a-z0-9-]+\.md", index_text)


def parse_confidence(text: str) -> str | None:
    """Pull the frontmatter confidence value (lowercased) or None."""
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    front = text[3:end]
    match = CONFIDENCE_RE.search(front)
    if not match:
        return None
    value = match.group(1).strip().lower()
    return value if value in {"high", "medium", "low"} else None


def wiki_relative(path: Path, root: Path) -> Path | None:
    """Return the path relative to root if it is under wiki/, else None."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return None
    parts = rel.parts
    # APFS is case-insensitive but case-preserving: resolve() does not
    # normalize WIKI/ back to wiki/, so the comparison must ignore case or the
    # whole gate can be bypassed with a case variant.
    if not parts or parts[0].lower() != "wiki":
        return None
    return rel


def allow_silent() -> None:
    sys.exit(0)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{reason}. This is a high-risk wiki operation. Propose it "
                        'with the "Wiki suggestion" format and wait for approval; '
                        "do not write directly."
                    ),
                }
            }
        )
    )
    sys.exit(0)


def allow_with_message(message: str) -> None:
    print(
        json.dumps(
            {
                "systemMessage": message,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                },
            }
        )
    )
    sys.exit(0)


def _strip_heredocs(command: str) -> str:
    """Strip heredoc bodies (<<EOF … EOF) — the body is stdin data, not command.

    Leaving it in lets bare `rm` / `wiki` tokens inside the body leak out (a
    `git commit -F-` heredoc message false-positived in practice). When the
    terminator is missing, strip to end of string (everything after an
    unterminated heredoc is body anyway).
    """
    return re.sub(
        r"<<-?\s*(['\"]?)(\w+)\1.*?(?:\n\2(?=\s|$)|\Z)",
        " ",
        command,
        flags=re.DOTALL,
    )


def _bash_tokens(command: str) -> list[str] | None:
    """shlex tokenization (posix + punctuation_chars); None on parse failure.

    posix mode is the crux: quoted arguments collapse into a *single* token, so
    `-m "message mentioning rm and wiki/"` cannot be confused with real command
    tokens; meanwhile wi"ki" / wi\\ki style quoting confusion normalizes back to
    wiki, so obfuscated bypasses are still caught.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return None


def _has_wiki_segment(token: str) -> bool:
    """Whether any `/`-delimited path segment of the token is wiki.

    Case-insensitive: APFS is case-insensitive, so a WIKI/ variant must match.
    """
    return any(segment.lower() == "wiki" for segment in token.split("/"))


def handle_bash(command: str, root: Path) -> None:
    # Join backslash line-continuations (`\` + newline) first: `rm -rf \<newline>wiki`
    # is a single action.
    command = re.sub(r"\\\r?\n", " ", command)
    command = _strip_heredocs(command)

    tokens = _bash_tokens(command)
    if tokens is None:
        _fallback_scan(command)
        return

    # Token-level "delete/move targeting wiki": rm/mv must be a whole token
    # (quoted prose collapses into one long token and cannot match; `git rm`
    # carries its own standalone rm token), and wiki must be a path segment of
    # some token (/tmp/wiki-notes.txt does not match). Still an AND over the
    # whole command, not per segment: cross-segment bypasses (find wiki | xargs
    # rm) that split verb and target are still caught. To genuinely mix them,
    # split into two Bash calls.
    destructive = any(token in {"rm", "mv"} for token in tokens)
    references_wiki = any(_has_wiki_segment(token) for token in tokens)
    if destructive and references_wiki:
        deny(
            "delete or move of a wiki directory or page (if the rm/mv is "
            "unrelated to the wiki and just clears a temp file on the same line, "
            "split it into a separate Bash call)"
        )
    # Bash writes (redirect / tee / python -c …) are intentionally NOT detected:
    # a blacklist regex can never enumerate them all, so the old >/>>/tee
    # detection and its adversarial hardening were removed. "Write the wiki only
    # via Write/Edit" is an instruction-layer obligation (see wiki-workflow.md,
    # "Bash detection is not exhaustive"); do not grow write-detection regex back
    # in here.
    allow_silent()


def _fallback_scan(command: str) -> None:
    # Reached only when shlex cannot parse: the old whole-string regex (strip
    # quotes + backslashes, then match). It cannot separate quoted prose and
    # will over-deny — a safe direction for a backstop; fix the quoting or split
    # the command to get unstuck.
    command = command.replace('"', "").replace("'", "").replace("\\", "")
    destructive = re.search(r"\b(rm|git\s+rm|mv)\b", command, re.IGNORECASE)
    references_wiki = re.search(r"(?<![\w.-])wiki(?=/|['\"\s]|$)", command, re.IGNORECASE)
    if destructive and references_wiki:
        deny(
            "delete or move of a wiki directory or page (the command has "
            "unbalanced quotes, so the whole line is judged conservatively; fix "
            "the quoting or split into two calls)"
        )
    allow_silent()


def resulting_content(tool_name: str, tool_input: dict, target: Path) -> str | None:
    """The full page text after the operation, or None if it cannot be derived."""
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name == "Edit":
        try:
            current = target.read_text(encoding="utf-8")
        except Exception:
            return None
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        if old and old in current:
            if tool_input.get("replace_all"):
                return current.replace(old, new)
            return current.replace(old, new, 1)
        return current
    return None


def change_message(rel: Path, tool_name: str, tool_input: dict, target: Path) -> str:
    name = rel.name
    if tool_name == "Edit":
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        body = f"- {old}\n+ {new}"
        return f"Wiki: high-confidence write to {name}. Change:\n{body}"
    # Write
    new_content = tool_input.get("content", "")
    if target.exists():
        try:
            old_content = target.read_text(encoding="utf-8")
        except Exception:
            old_content = ""
        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=name,
                tofile=name,
            )
        )
        return f"Wiki: high-confidence write to {name}. Change:\n{diff}"
    preview = "\n".join(new_content.splitlines()[:12])
    return f"Wiki: new high-confidence page {name}. Content preview:\n{preview}"


def handle_write_edit(tool_name: str, tool_input: dict, root: Path) -> None:
    file_path = tool_input.get("file_path")
    if not file_path or not isinstance(file_path, (str, Path)):
        allow_silent()

    # Resolve relative paths against the project root, not the cwd (the hook may
    # run from a subdirectory). An absolute file_path is unchanged by this join.
    target = (root / Path(file_path)).resolve()
    rel = wiki_relative(target, root)
    if rel is None:
        allow_silent()  # not a wiki path -> gate is inert

    # Rule 2: knowledge pages must be flat wiki/<name>.md
    if len(rel.parts) != 2 or rel.suffix != ".md":
        deny("write to a disallowed location inside the wiki/ tree (must be a flat wiki/<name>.md)")

    # Rule 3: maintenance files carry no confidence
    if is_maintenance(rel.name, root):
        allow_silent()

    content = resulting_content(tool_name, tool_input, target)
    if content is None:
        deny("cannot determine the resulting page content")

    confidence = parse_confidence(content)
    if confidence == "high":
        allow_with_message(change_message(rel, tool_name, tool_input, target))
    if confidence in {"medium", "low"}:
        deny(f"resulting page confidence is {confidence}")
    deny("resulting page confidence is missing or unparseable")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not isinstance(data, dict):
        sys.exit(0)

    root = project_root()
    if resolve_write_policy(root) != "auto":
        sys.exit(0)  # gate inert outside auto mode

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input") or {}

    if tool_name == "Bash":
        handle_bash(tool_input.get("command", ""), root)
    elif tool_name in {"Write", "Edit"}:
        handle_write_edit(tool_name, tool_input, root)

    sys.exit(0)


if __name__ == "__main__":
    main()
