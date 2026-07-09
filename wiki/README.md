# LLM Self-Learning Wiki

This wiki is a git-tracked knowledge base maintained by AI agents and reviewed by humans.

It is inspired by the LLM Wiki pattern: keep project knowledge close to the code, then make the agent consult and update that knowledge during normal development.

## Layers

```text
Source material: code, git history, specs
        ↓
Project wiki: wiki/
        ↓
Agent rules and hooks: .claude/
```

## Core Files

- `index.md` - top-level index: one row per category (page count, sub-index link, keywords).
- `index-<slug>.md` - per-category sub-index listing that category's pages.
- `README.md` - explains how this wiki works.

All other Markdown files are knowledge pages, kept flat under `wiki/`. There is
no tracked change log — read a page's history from git (`git log wiki/<page>.md`).

## Rules

See `.claude/rules/wiki-workflow.md` for the write policy, hook markers, and review flow.
