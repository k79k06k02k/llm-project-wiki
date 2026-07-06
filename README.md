# LLM Project Wiki

<p align="center">
  <img src="docs/assets/llm-project-wiki-visual.png" alt="LLM Project Wiki workflow diagram" width="720">
</p>

A project-local LLM Wiki workflow with Claude Code and Codex hooks, human-approved updates, and git-tracked engineering memory.

This repository is a small, copyable example of the LLM Wiki pattern: keep durable project knowledge inside the repository, let an AI coding agent propose updates, and use hooks to make the agent evaluate whether a session produced knowledge worth saving.

The point is not to create another documentation folder. The point is to make project memory part of the agent workflow.

## What This Gives You

- A `wiki/` directory for git-tracked project knowledge.
- A `SessionStart` hook that loads the wiki index into Claude Code or Codex context.
- A Claude Code `Stop` hook that nudges the agent to evaluate whether the conversation produced wiki-worthy knowledge.
- A repo-scoped `wiki-review` skill for manual review and suggestion flow.
- A human approval rule so the agent proposes wiki updates instead of silently rewriting the knowledge base.
- A small install script for copying the template into another repository.

## Repository Layout

```text
.
├── .claude/
│   ├── hooks/scripts/wiki_stop_hook.py
│   ├── hooks/scripts/wiki_session_start.py
│   ├── rules/wiki-workflow.md
│   ├── settings.json
│   └── skills/wiki-review/SKILL.md
├── .codex/
│   └── hooks.json
├── .agents/
│   └── skills/wiki-review/
│       ├── SKILL.md
│       └── agents/openai.yaml
├── scripts/
│   ├── install.sh
│   └── smoke_test.sh
├── wiki/
│   ├── README.md
│   ├── index.md
│   ├── log.md
│   └── system-overview.md
└── wiki.config.json
```

## Quick Start

Clone this repository, then copy the template into a target project:

```bash
git clone https://github.com/k79k06k02k/llm-project-wiki.git
cd llm-project-wiki
./scripts/install.sh /path/to/your/project
```

## AI Agent Install Prompt

Copy this prompt into an AI coding agent while it is working inside the target project:

```text
Please integrate LLM Project Wiki into the current project: https://github.com/k79k06k02k/llm-project-wiki.git

Run `scripts/install.sh` from that repository.
```

Then open the target project with Claude Code or Codex. On session start, the agent should receive the wiki index as additional context. Claude Code uses a blocking stop hook for substantial responses; Codex registers no stop hook and relies on injected instructions so the transcript is not polluted by hook feedback. Both tools share one `wiki_session_start.py` script (under `.claude/hooks/scripts/`); the Codex hooks call it with a `codex` flavor argument.

The installer is designed for existing projects:

- It does not overwrite existing wiki, rule, hook, or skill files.
- If `.claude/settings.json` already exists, it merges the LLM Wiki hooks into the existing `hooks` object and writes a timestamped backup next to the original file.
- If `.codex/hooks.json` already exists, it does the same for Codex hooks.
- If a file path already exists, the installer skips that file and prints it. Review skipped paths manually.

Requirements: `bash`, `python3`, and `git`. The target should be a git repository so repo-local hooks can resolve the project root from subdirectories.

Codex discovers repository skills from `.agents/skills`. The checked-in `.agents/skills/wiki-review/SKILL.md` is intentionally a thin shim that points to the canonical workflow in `.claude/skills/wiki-review/SKILL.md`, so the Claude Code and Codex skill instructions do not drift apart.

## How The Workflow Works

1. `wiki/index.md` is loaded at the start of an agent session.
2. The agent reads relevant wiki pages before editing related code.
3. During work, the agent may propose a `Wiki suggestion` when it discovers durable knowledge.
4. At the end of substantial work, the agent evaluates whether the session produced wiki-worthy knowledge.
5. The agent proposes a `Wiki suggestion` when there is durable knowledge to record. In Codex, do not add no-op markers solely for the hook; keep the transcript clean.
6. Human approval is required before any wiki file is created, updated, or deleted (configurable, see below).

This keeps the system boring and auditable. Boring is good here. Unreviewed AI memory is just a more confident way to store mistakes.

## Write Policy Configuration

The root `wiki.config.json` controls how wiki writes are gated via a single `write_policy` value:

```json
{
  "write_policy": "require_approval"
}
```

- `require_approval` (default): the agent proposes a `Wiki suggestion` and waits for explicit approval before writing.
- `auto`: a deterministic `PreToolUse` gate (`wiki_write_gate.py`) decides per write. It judges each write by the resulting frontmatter `confidence`: `high` is allowed (and its diff is surfaced to you), while `medium` / `low` / missing confidence, deletes, and writes to the wrong location inside `wiki/` are blocked and must be proposed. This gate is Claude-only; Codex applies the same rules by instruction.
- `open`: the agent may create, update, or delete wiki pages directly, while still updating the index, appending to the log, and emitting a wiki evaluation marker.

**Migration**: the legacy boolean `require_human_approval` is still honored — `true` maps to `require_approval`, `false` maps to `open`. A valid `write_policy` value takes precedence.

The `SessionStart` hook reads this file and injects the active policy into Claude Code and Codex context at the start of every session, so a change takes effect on the next session. Resolution fails closed: a missing, unreadable, or invalid config is treated as `require_approval`.

## Wiki-Worthy Knowledge

Capture knowledge that saves future investigation:

- Cross-file architecture that is hard to reconstruct from code alone.
- Design decisions and the reasons behind them.
- API integration details that live between code and backend behavior.
- Bug roots and fixes other developers or QA may hit again.
- Project conventions not obvious from the style guide.

## What Not To Record

**If the code can tell you, don't write it down.** The wiki's value is in what
the code can't say, not in restating what the code does — a restatement only
drifts from the code over time and becomes a lying doc nobody maintains.

- Mechanics you get from reading a single file (what a method does, that a
  field exists, the steps of a flow). The code is the only source of truth.
- Structure you can derive straight from the code (class relationships, call
  chains, prefab hierarchies). The repo already records it.
- Anything `git log` can answer (when it changed, who changed it, what changed).

The test: ask "could I find this by reading the code?" If yes, don't write it.
Only write what the code can't reveal: **why** it was designed this way,
fail-silent couplings that span multiple files with no compile-time signal, and
traps others will step on repeatedly.

Even when a piece of knowledge spans several files, if one sentence plus a few
filename pointers is enough — and the details are more accurate read from the
code — write that one pointer (or a single gotcha), not a full page. Prefer few
but precise: one genuinely-uncoverable gotcha beats a page of explanation the
code could have given you.

## Hook Markers

The Claude Code stop hook looks for either marker in the final assistant response:

- `Wiki suggestion`
- `No wiki updates needed`

Codex does not block on missing markers. Codex renders stop-hook blocks as visible Hook feedback and can create marker-only follow-up messages, so Codex intentionally registers no stop hook and relies on the SessionStart instructions instead.

## Smoke Test

Run:

```bash
./scripts/smoke_test.sh
```

The smoke test verifies that:

- The Claude Code stop hook allows short responses.
- The Claude Code stop hook blocks substantial responses without a wiki marker.
- The Claude Code stop hook allows responses containing `Wiki suggestion`.
- The Claude Code stop hook allows responses containing `No wiki updates needed`.
- The installer creates Claude Code hooks, Codex hooks, and repo-scoped Codex skill files in a fresh target.
- Installed session hooks can load wiki and git context from a project subdirectory.
- Existing Claude Code and Codex hook configs are merged instead of overwritten.

## Design Notes

This example intentionally uses plain Markdown, git, and hooks.

No vector database. No dashboard. No fake "agent memory platform." Add those only when the boring version stops being enough.

## License

MIT
