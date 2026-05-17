---
name: wiki-review
description: Review the current conversation and propose project wiki updates when durable knowledge was discovered. Use before ending a substantial task, after solving a cross-file bug, after implementation work, or when the user asks what should be recorded.
---

# Wiki Review

Use this skill to extract durable project knowledge from a conversation and propose updates to the project wiki.

The core question:

> If someone hits this problem again three months from now, should the wiki contain something that would save them time?

## Step 1: Establish Scope

Read `wiki/index.md` to see what pages already exist.

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

All writes require explicit user approval. This review proposes work; it does not perform the write.
