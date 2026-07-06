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
- `log/` - wiki change log, split into weekly files (named after the week's Monday) grouped by year; `log/index.md` lists them.
- `README.md` - explains how this wiki works.

All other Markdown files are knowledge pages, kept flat under `wiki/`.

## Rules

See `.claude/rules/wiki-workflow.md` for the write policy, hook markers, and review flow.
