# Wiki Workflow

The project keeps a shared, git-tracked wiki in `wiki/`. The AI agent may propose updates; the human developer approves writes.

## Conversation Lifecycle

1. **Session start**: `wiki/index.md` is loaded through the `SessionStart` hook. When working on a topic, read relevant wiki pages before editing code.
2. **During work**: Pause and consider a wiki suggestion when the conversation uncovers durable knowledge:
   - A cross-file system relationship.
   - A non-obvious bug root.
   - An answer to "why" that lives across several files.
   - A convention that future agents or developers will need.
3. **Commit or PR work**: Before finishing substantial commit or PR work, evaluate whether the change should update the wiki.
   - Multi-file or cross-system changes usually deserve evaluation.
   - Small one-file edits usually do not.
4. **Manual trigger**: When the user asks for `wiki-review`, run the full wiki self-review flow.

## Codex Support

Codex can run the same wiki flow through `.codex/hooks.json`.
The Codex implementation uses `SessionStart` to load `wiki/index.md` and git context,
then leaves `Stop` non-blocking. Codex Stop hook blocks are rendered as visible
Hook feedback and can create marker-only follow-up messages, so wiki self-review
is handled through instructions instead of a Stop-time gate.

Codex-specific details:

- Project-local hooks only run when the project `.codex/` layer is trusted.
- Hook `timeout` values are seconds, not milliseconds.
- Repo-local commands should resolve paths from `git rev-parse --show-toplevel`, because Codex may start from a subdirectory.
- Use `/hooks` in Codex to inspect, trust, or disable non-managed hooks.

## What To Record

- Architecture explanations that require reading several files.
- Design decisions and the reasons behind them.
- API integration details discovered from code or backend behavior.
- Bug roots and fixes that future developers or QA may hit again.
- Project conventions that are not already obvious from style rules.

## Write Policy

All wiki writes require explicit human approval.

When you find knowledge worth saving, propose it in the conversation:

```text
Wiki suggestion: I found that the checkout flow uses a two-stage loading pattern that is not documented.
- Target page: checkout-flow.md
- Confidence: high
- Approval? If approved, I will write the wiki update.
```

Do not create, update, or delete wiki pages until the user approves.

## Stop Hook Markers

The Claude Stop hook checks whether wiki evaluation happened by scanning for one of these markers:

- `Wiki suggestion`
- `No wiki updates needed`

Use `Wiki suggestion` when proposing an update. Use `No wiki updates needed` when the session produced no durable wiki-worthy knowledge. In Codex, do not add no-op markers solely for the hook; keep the transcript clean.

## Page Format

Each wiki page should use YAML frontmatter:

```yaml
---
title: Page Title
tags: [architecture]
last_updated: YYYY-MM-DD
confidence: medium
sources:
  - path/to/source.file
related_pages:
  - other-page.md
---
```

## Maintenance Rules

- Update `wiki/index.md` when creating or deleting a page.
- Append to `wiki/log.md` after every approved wiki change.
- Keep wiki files flat under `wiki/`; do not create nested folders.
- Prefer fewer high-confidence pages over many vague pages.
- If an existing wiki page conflicts with code, propose a correction instead of silently rewriting it.

## Wiki Self-Review

When asked to perform a wiki review:

1. Read `wiki/index.md`.
2. Review what the conversation touched: systems, bugs, design decisions, and cross-file discoveries.
3. Compare the discoveries against existing wiki pages.
4. Suggest new or updated pages only when they would save future investigation.

Output:

```text
Wiki self-review

Topics covered: ...

Suggested wiki updates:
1. page-name.md (new/update) - what should be recorded
   - Confidence: high/medium/low
   - Source: where this was discovered

No wiki updates needed: ...

Should I apply these suggestions?
```
