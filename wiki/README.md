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

- `index.md` - wiki table of contents.
- `log.md` - append-only wiki change log.
- `README.md` - explains how this wiki works.

All other Markdown files are knowledge pages.

## Rules

See `.claude/rules/wiki-workflow.md` for the write policy, hook markers, and review flow.
