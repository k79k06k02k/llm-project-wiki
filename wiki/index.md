# Wiki Index

Flat markdown wiki with a two-level index: this file lists only the categories; for the pages in a category, read the matching `index-<slug>.md`.

This index is maintained by the AI agent after human approval. See [README](README.md) for how this wiki works; agent write rules live in [`.claude/rules/wiki-workflow.md`](../.claude/rules/wiki-workflow.md).

The "Keywords" column helps the agent match user vocabulary to a category (a user saying "bug" should land on "Debugging"). It is required when adding a category; see Write Scenario 2 in [`.claude/rules/wiki-workflow.md`](../.claude/rules/wiki-workflow.md).

| Category | Pages | Directory | Keywords |
|---|---|---|---|
| Architecture | 1 | [index-architecture.md](index-architecture.md) | architecture, system, module, overview, structure |
| Integrations | 0 | [index-integrations.md](index-integrations.md) | integration, api, backend, service, data, third-party |
| Debugging | 0 | [index-debugging.md](index-debugging.md) | debug, gotcha, troubleshoot, bug, root cause |
| Decisions | 0 | [index-decisions.md](index-decisions.md) | decision, design, rationale, trade-off, adr |
