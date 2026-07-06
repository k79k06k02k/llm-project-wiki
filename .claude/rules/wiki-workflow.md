# Wiki Workflow

The project keeps a shared, git-tracked wiki in `wiki/`. The AI agent may propose updates; the human developer approves writes.

## Conversation Lifecycle

1. **Session start**: the `SessionStart` hook injects a summary of `wiki/index.md`'s category table (category, page count, sub-index link, keywords) into context — not the raw file. Look up a topic in this order:
   1. Match the topic against the injected categories. Category names are descriptive labels and users often use aliases (for example "web" or "browser" might map to a "WebGL Platform" category), so match semantically against each category's `keywords` column before falling back to search.
   2. Read the matching `wiki/index-<slug>.md` for that category's full page list.
   3. Still not found? Run `.claude/scripts/wiki-search.sh "<keyword>"` (it excludes `index*.md`, `log/`, and `README.md`, and prints title + tags + the matching line).
   4. Filter by tag with `.claude/scripts/wiki-search.sh -t <tag>` (combine with a query: `-t <tag> "<keyword>"`).
   5. As a last resort, raw ripgrep: `rg "<keyword>" wiki/ -g '!index*.md' -g '!log'`.
   - Do not proactively read the full `wiki/index.md` — the injected summary already covers the category layer.
   - Do not read `wiki/log/` by default. When you need wiki change history, `rg "<keyword>" wiki/log/` (grep returns only matching lines), scope to one weekly file, or use `git log wiki/<page>.md` for the git-native view.
2. **During work**: Pause and consider a wiki suggestion when the conversation uncovers durable knowledge:
   - A cross-file system relationship.
   - A non-obvious bug root.
   - An answer to "why" that lives across several files.
   - A convention that future agents or developers will need.
3. **Commit or PR work**: Before finishing substantial commit or PR work, evaluate whether the change should update the wiki.
   - Multi-file or cross-system changes usually deserve evaluation.
   - Small one-file edits usually do not.
4. **Manual trigger**: When the user asks for `wiki-review`, run the full wiki self-review flow.

## Index Structure

The index is two-level:

```text
wiki/
├── index.md              # top-level: one row per category (page count, sub-index link, keywords)
├── index-<slug>.md        # per-category: full list of that category's pages
├── log/                    # weekly change log (see "Weekly Log" below)
├── README.md               # human-facing entry point
└── <page>.md                # knowledge pages (flat, one per topic)
```

- `wiki/index.md` lists categories only, one row per category: `| Category | Pages | Directory | Keywords |`. This template ships four starting categories (`Architecture`, `Integrations`, `Debugging`, `Decisions`, with slugs `architecture`, `integrations`, `debugging`, `decisions`) — rename or add categories as the project's knowledge grows.
- `index-<slug>.md` holds the full page list for one category. Entry format: `- [page-slug](page-slug.md) — one-sentence description`, sorted alphabetically within the category, description under roughly 80 characters.
- The **Keywords** column on `wiki/index.md` maps a category's descriptive label to the vocabulary a user or agent is likely to type. Category names are labels, not guaranteed to match user phrasing — the SessionStart hook injects the keywords column so the agent can do semantic matching before falling back to search. Keywords must not contain `|` (it would break the table's cell boundaries and misparse the SessionStart hook).

## Weekly Log

The change log is a weekly file tree instead of a single growing file:

```text
wiki/log/
├── index.md                # lists every weekly file
└── <year>/
    └── YYYY-MM-DD.md        # one file per week, named after that week's Monday
```

- One file per week, named after the ISO week's Monday (Mon = weekday 0). Example: entries for the week of May 18–24 all go into `wiki/log/2026/2026-05-18.md`.
- Files are grouped into per-year subfolders; create the year folder the first time an entry lands in a new year.
- New entries go at the **top** of the current week's file, directly under the file header (reverse chronological).
- File header format: `# Log YYYY-MM-DD ~ YYYY-MM-DD` (week start ~ week end) plus a one-line description.
- `wiki/log/index.md` is maintained alongside: append one line per new weekly file, e.g. `- [YYYY-MM-DD.md](YYYY/YYYY-MM-DD.md) — M/D ~ M/D`.
- **Relative link depth from inside a weekly file**: a weekly file lives at `wiki/log/<year>/`, two levels deeper than the wiki root.
  - Link to another wiki page: `[xxx](../../xxx.md)`
  - Link to a file elsewhere in the repo: `[path](../../../path/to/file)`
  - Link to `.claude/...`: `[...](../../../.claude/...)`
  - External URLs, absolute paths, and anchors are unchanged.
- `wiki/log/` (including its year subfolders) is **not read proactively** — the SessionStart hook does not inject it, and the agent should not `Read` it wholesale. Look up history with `rg "<keyword>" wiki/log/` (full-text, matching lines only), scope to one file with `rg "<keyword>" wiki/log/2026/2026-05-18.md`, or use `git log wiki/<page>.md` for the git-native view.
- **Cross-year housekeeping**: this is a suggestion, not automation. If `wiki/log/` accumulates past roughly 200 files (about 4 years at one file per week), consider manually collapsing older years into a single archive file — nothing in the hooks or gate does this automatically.

## Codex Support

Codex can run the same wiki flow through `.codex/hooks.json`.
The Codex hooks call the shared `.claude/hooks/scripts/wiki_session_start.py`
(with a `codex` flavor argument) to load the `wiki/index.md` category summary
and git context, and register no `Stop` hook. Codex renders Stop hook blocks as
visible Hook feedback and can create marker-only follow-up messages, so wiki
self-review is handled through instructions instead of a Stop-time gate.

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

## What Not To Record

**Security red line (hard rule, overrides everything below).** Never write any
secret value read from code, logs, environment variables, config files, or
command output into the wiki — credentials/passwords, session tokens, API keys,
private keys/certificates, internal URLs or IPs, personal data, DB connection
strings, and the like. When you must refer to one, write only the file path or a
placeholder; **never reproduce the actual value**. This is a different axis from
"if the code can tell you, don't write it" below: the red line is a prohibition
(never transcribe it into the wiki even if the code reveals it), whereas the rest
of this section is a value judgment about what is worth recording. This mirrors
the path & privacy rule in CLAUDE.md ("secrets never land"). Under the `auto`
write policy the agent writes directly with no human in the loop, so this rule
matters most there.

**If the code can tell you, don't write it down.** The wiki's value is in what
the code can't say, not in restating what the code does — a restatement only
drifts from the code over time and becomes a lying doc that nobody maintains.

- **Mechanics you get from reading a single file** (what a method does, that a
  field exists, the steps of a flow) → don't write it; the code is the only
  source of truth.
- **Structure you can derive straight from the code** (class relationships, call
  chains, prefab hierarchies) → don't write it; the repo already records it.
- **Anything `git log` can answer** (when it changed, who changed it, what
  changed) → don't write it; use `git log`.

**The test**: ask "could I find this by reading the code?" If yes → don't write
it. Only write what the code *can't* reveal: **why** it was designed this way,
**fail-silent couplings** that span multiple files with no compile-time signal
and can only be reconstructed by piecing them together, and traps others will
**step on repeatedly**.

Even when a piece of knowledge spans several files, if condensing it into "one
sentence plus a few filename pointers" is enough — and the details are more
accurate read from the code — then **write that one pointer** (or a single
gotcha), don't copy the code's content into a full page. Prefer "few but
precise": one genuinely-uncoverable gotcha beats a page of explanation the code
could have given you.

## Write Policy

The write policy is controlled by `write_policy` in the root
`wiki.config.json`. The SessionStart hook reads this file and injects the
active policy into context at the start of every session. The default is
`require_approval`, and resolution fails closed: if the config is missing,
unreadable, or holds an invalid value, approval is required.

`write_policy` takes one of three values:

- **`require_approval`** (default): all wiki writes require explicit human
  approval. When you find knowledge worth saving, propose it in the conversation
  and wait for approval before writing.
- **`auto`**: a PreToolUse gate (`wiki_write_gate.py`) decides per write,
  deterministically. See "Auto Mode Gate" below.
- **`open`**: you may create, update, or delete wiki pages directly without
  waiting for approval. Still update `wiki/index.md`, append to the current
  week's log file under `wiki/log/`, and emit a wiki evaluation marker so the
  Stop hook passes.

**Migration**: the legacy boolean `require_human_approval` is still honored —
`true` maps to `require_approval`, `false` maps to `open`. A valid `write_policy`
value takes precedence over the legacy key.

### Auto Mode Gate

Under `auto`, the `PreToolUse` gate (`wiki_write_gate.py`) governs the `wiki/`
tree only (writes elsewhere are untouched) and applies these rules in order,
first match wins:

1. **Bash `rm` / `git rm` / `mv`, or a shell redirect / `tee` into `wiki/`** → denied. Propose the change instead of deleting, moving, or redirecting into the wiki from a shell command.
2. **Write/Edit inside the `wiki/log/` tree** (`wiki/log/index.md`, `wiki/log/<year>/<monday>.md`) → allowed without a confidence check, as long as the target is a `.md` file. The weekly log is maintenance, not a knowledge page, so it carries no `confidence` frontmatter.
3. **Write/Edit to a non-flat or non-`.md` path inside `wiki/`** (a nested folder outside `wiki/log/`, or a non-Markdown file) → denied.
4. **Write/Edit to `index*.md`, `README.md`, or the legacy `log.md`** → allowed without a confidence check. `index-<slug>.md` is only exempt when that exact filename is listed in the directory column of `wiki/index.md` — otherwise any knowledge page could dodge the confidence check just by taking an `index-` prefix. If `wiki/index.md` is missing or unreadable, no `index-*` file is exempt (fail-closed). `log.md` stays exempt for projects installed before the log moved to the weekly `wiki/log/` tree.
5. **Resulting frontmatter `confidence: high`** → allowed; the gate surfaces the diff (or, for a new page, a content preview) to the human.
6. **Resulting frontmatter `confidence: medium` or `low`** → denied; propose instead.
7. **Resulting frontmatter `confidence` missing or unparseable** → denied (fail-closed).

"Resulting" means the gate reconstructs the page content after the edit — for
`Write`, the new content; for `Edit`, the current file with `old_string`
replaced by `new_string` — and reads `confidence` from the YAML frontmatter of
that reconstructed content, not the confidence stated in conversation.

**Bash detection is not exhaustive.** The gate only recognizes `rm`, `git rm`,
`mv`, and shell redirects/`tee` (`>`, `>>`, `tee`) targeting a `wiki/` path.
Other ways to write a file from a shell command — `python -c`, `curl -o`, and
similar — are not covered; regex cannot enumerate every file-writing pattern.
The gate is a backstop, not a complete guarantee: honest `confidence` labeling
under `auto` remains an instruction-level obligation, not just a mechanical one.

This gate is Claude-specific; the Codex layer has no PreToolUse mechanism, so
it applies the same rules by self-discipline through the SessionStart-injected
instructions instead.

Because the gate keys on the confidence you write, **set `confidence` honestly**.
The diff surfacing is the backstop: a high-confidence write is allowed but never
silent.

When approval is required (or the gate blocks a write), propose updates in this
format:

```text
Wiki suggestion: I found that the checkout flow uses a two-stage loading pattern that is not documented.
- Target page: checkout-flow.md
- Confidence: high
- Approval? If approved, I will write the wiki update.
```

When approval is required, do not create, update, or delete wiki pages until
the user approves.

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

### Tag Vocabulary

- Naming convention: lowercase, hyphen-separated, no uppercase, no spaces, no
  underscores (e.g. `webgl`, `addressables`, `oauth-setup`).
- Before adding a new tag, check whether an existing one already covers the
  concept and reuse it — don't introduce a synonym that splits the vocabulary.
- List the tags currently in use:
  ```bash
  rg "^tags:" wiki/ -g '!index*.md' | grep -oE '\[[^]]+\]' | tr ',' '\n' | tr -d '[] ' | sort -u
  ```
  Check this project's actual output before picking a tag; do not assume any
  specific tag list — a fresh project starts with none.

## Maintenance Rules

Each wiki write falls into one of five scenarios. Follow the matching
checklist so the index and log stay in sync — the gate (under `auto`) only
checks frontmatter confidence and file location, not index/log consistency, so
keeping them in sync is on the agent regardless of write policy.

- Keep wiki files flat under `wiki/`; the only subfolder is `wiki/log/`.
- Prefer fewer high-confidence pages over many vague pages.
- If an existing wiki page conflicts with code, propose a correction instead of silently rewriting it.

### Write Scenario 1: Add A New Page

0. **Check for an existing page first.** Run `.claude/scripts/wiki-search.sh "<keyword>"` and check the relevant `index-<slug>.md` for topic overlap. If a page already covers the topic, extend it instead (add a section, bump `last_updated`, update `related_pages`) rather than creating a new page. Only create a new page when the content is genuinely a separate topic and folding it into an existing page would dilute that page's focus. This step matters most under `auto`, since the gate cannot judge topical overlap — preventing page fragmentation depends entirely on this step.
1. Decide which existing category the page belongs to (check the table in `wiki/index.md`).
   - No fitting category exists → do Write Scenario 2 first.
2. Create the file with complete frontmatter (`title`, `tags`, `last_updated`, `confidence`, `sources`; `related_pages` optional).
3. Add one line to the matching `wiki/index-<slug>.md`, inserted in alphabetical order.
4. Update the `Pages` count for that category in `wiki/index.md` (+1).
5. Write a log entry (Write Scenario 5).

### Write Scenario 2: Add A New Category

1. Agree on a category name and a kebab-case slug.
2. Agree on a keyword list (6–10 terms) for semantic matching — this is what lets the SessionStart hook map a user's phrasing onto the category. Keywords must not contain `|` (it breaks the table's cell boundaries in `wiki/index.md` and can misparse the SessionStart hook).
3. Create `wiki/index-<slug>.md` with a heading, e.g. `# <Category Name> — Wiki Sub-Index`.
4. Add a row to the table in `wiki/index.md`: `| <Category> | 0 | [index-<slug>.md](index-<slug>.md) | <keywords> |`.
5. Continue with Write Scenario 1 to add the first page.
6. Note "added category <name>" in the log entry.

Keywords are not optional: a category name is a label, and users rarely type the label verbatim. Without keywords, the category is invisible to the agent's semantic matching at session start.

### Write Scenario 3: Delete A Page

1. Delete the file.
2. Remove its line from the matching `wiki/index-<slug>.md`.
3. Decrement the `Pages` count for that category in `wiki/index.md` (-1).
4. If the count reaches zero, ask the human whether to also delete `index-<slug>.md` — do not delete it automatically.
5. Write a log entry.

### Write Scenario 4: Recategorize A Page

1. Remove the entry from the old `index-<slug-old>.md`.
2. Add the entry to the new `index-<slug-new>.md`.
3. Adjust the `Pages` count for both categories in `wiki/index.md`.
4. Write a log entry.

### Write Scenario 5: Write A Log Entry

1. **Compute this week's log path**: take today's date minus its ISO weekday (Mon = 0 … Sun = 6) to get that week's Monday, then the file is `wiki/log/<YYYY>/<YYYY-MM-DD>.md` (using the Monday's year).
2. **Create the weekly file if it doesn't exist yet**:
   - Also create the `<YYYY>/` folder if this is the first entry of a new year.
   - Write the file header: `# Log YYYY-MM-DD ~ YYYY-MM-DD` followed by a one-line description and the weekly-split-rule link.
   - Also append a line to `wiki/log/index.md` under the matching year: `- [YYYY-MM-DD.md](YYYY/YYYY-MM-DD.md) — M/D ~ M/D`.
3. **Add the entry** at the top of that week's file, right below the header: `## YYYY-MM-DD` + `### <topic>` + details (reverse chronological — newest entry on top).

There is no sliding-window trimming to worry about — crossing a week boundary
just computes a new file path in step 1; older weekly files stay where they are.

## Wiki Self-Review

When asked to perform a wiki review:

1. Start from the category summary of `wiki/index.md` (already in context from session start, or read the file directly if reviewing outside a session).
2. Review what the conversation touched: systems, bugs, design decisions, and cross-file discoveries.
3. Check for overlap with existing pages: read the relevant `wiki/index-<slug>.md` for the touched categories, or run `.claude/scripts/wiki-search.sh "<keyword>"` when the category is unclear.
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
