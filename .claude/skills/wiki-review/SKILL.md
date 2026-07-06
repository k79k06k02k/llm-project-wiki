---
name: wiki-review
description: Review the current conversation and propose project wiki updates when durable knowledge was discovered. Use before ending a substantial task, after solving a cross-file bug, after implementation work, or when the user asks what should be recorded.
---

# Wiki Review

Use this skill to extract durable project knowledge from a conversation and propose updates to the project wiki.

The core question:

> If someone hits this problem again three months from now, should the wiki contain something that would save them time?

## Step 1: Establish Scope

Check what pages already exist before proposing anything new:

1. Start from the category summary of `wiki/index.md` (already in context from session start if this is a live session, or read the file directly otherwise).
2. Read the `wiki/index-<slug>.md` for any category the conversation plausibly touched, to see its full page list.
3. If a topic doesn't map cleanly to a category, run `.claude/scripts/wiki-search.sh "<keyword>"` instead of guessing.

Then review the conversation and identify:

- Which systems, modules, scenes, or services were touched.
- What problem was solved.
- What design decisions were made.
- What limitations or hidden assumptions were found.
- Whether understanding required reading multiple files.

## Step 2: Filter

Suggest a wiki update when the knowledge is durable:

| Type | Example |
| --- | --- |
| Cross-file architecture | A flow spans several managers and no single file explains it. |
| Design reason | A workaround exists because a platform or backend behaves in a specific way. |
| API integration | A payload field or call order is required but not obvious from the local code. |
| Bug root | A failure mode will probably affect future developers or QA. |
| Project convention | A recurring pattern is not documented in style rules. |

Do not suggest updates for:

- Facts obvious from one file.
- Temporary debugging details.
- Changes already documented during the same task.
- Low-confidence guesses.

## Judgment Principles

- **Few but precise.** One well-grounded, specific suggestion beats five vague ones.
- **Don't force it.** If the conversation genuinely produced nothing wiki-worthy, say so plainly — do not pad the review to look productive.
- **Check before proposing an update.** Confirm the target page is actually missing the information before suggesting a change to it, so you don't propose a duplicate.
- **This review only proposes.** The actual write follows whatever `write_policy` is active in `wiki.config.json` — see "Step 4" below.

## Step 3: Produce The Review

Use this format:

```text
Wiki self-review

Topics covered: [one sentence]

Suggested wiki updates:

1. page-name.md (new/update) - [what should be recorded]
   - Confidence: high/medium/low
   - Source: [conversation step, code path, or investigation result]
   - Expected content: [2-3 sentences]

No wiki updates needed: [explain when there are no suggestions]

Should I apply these suggestions?
```

## Step 4: Writing Follows The Active Policy

This review proposes work; it does not perform the write itself. What happens
next depends on the `write_policy` in `wiki.config.json` (default:
`require_approval`, meaning every write waits for explicit user approval). See
`.claude/rules/wiki-workflow.md` for the full write policy, including what the
`auto` and `open` policies allow the agent to do without waiting.
