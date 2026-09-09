---
name: dbcodebook-definition
description: Run, revise, audit, or publish variable-definition topics built from dbCodeBook across CHARLS, ELSA, and configured databases. Use for source discovery, official-material and literature review, fresh downloads, formal R definitions, full 文案.md review, validation, and website inspection sync. Do not use for promotional assets, rich text, or website maintenance.
---

# dbCodeBook Definition

This repository is the canonical source for rules, evidence, scripts, and tests. Resolve the database, topic, formal/process directories, executables, and website address once from the current task and configuration. Never put machine paths in shared rules or rediscover unchanged task context.

## Choose The Entry

| Request | Start here | Scope |
| --- | --- | --- |
| Explain or report status | Relevant current artifact or execution report only | Answer without generating, uploading, or starting a production report |
| Create, remake, or change sources | [1. Source plan](references/rules/stages/01-source-plan.md) | Follow the stages below; source or alias changes require a fresh full download |
| Review or change copy | [3. Reader copy](references/rules/stages/03-copy.md) | Read the complete 文案.md; regenerate and validate affected outputs, then perform authorized sync |
| Change R or calculation | [4. Public R](references/rules/stages/04-public-r.md) | Reuse unchanged sources; revise affected copy before generation |
| Upload reviewed outputs | [8. Website sync](references/rules/stages/08-website.md) only | Do not load discovery, questionnaire, R or writing rules; do not rebuild the topic |
| Edit this Skill | [Rule ownership](references/rules/index.md) and the requested scope | Do not run a topic or change the website merely to maintain the Skill |

## Stage Order

[validation.md](references/rules/validation.md) owns stage order and correction scope. Each stage document contains its input, necessary additional reading, execution, output, machine checks, model judgement, and return point. Read the current stage and its relevant database sections, not all stages or both database workflows.

1. [Source plan](references/rules/stages/01-source-plan.md).
2. [Selection and download](references/rules/stages/02-download.md).
3. [Reader copy](references/rules/stages/03-copy.md).
4. [Public R](references/rules/stages/04-public-r.md).
5. [Generation](references/rules/stages/05-generate.md).
6. [Result verification](references/rules/stages/06-results.md).
7. [Author and ordinary-reader review](references/rules/stages/07-review.md).
8. [Authorized website sync](references/rules/stages/08-website.md).

Resolve database-specific materials from [database-routing.json](references/database-routing.json). A route is not evidence that a database has passed end-to-end testing. The generation stage states the current shared renderer's database boundary.

Before substantive production or shared-tool modification, start the existing [execution report](references/rules/execution-report.md); do not create parallel timing or audit systems. Use one primary writer. When a stage calls for a read-only reviewer, use [review roles](references/rules/review-roles.md), create it only when input is stable, reuse it for affected rechecks, and close it afterward. Do not create visible tasks merely to split work.

## Global Boundaries

- Clear rules are requirements, not invitations to redesign. If any rule is unclear, conflicts with another, or appears to require a departure, report the exact uncertainty and impact before changing it. This applies to all rules, not only source mapping.
- Keep authorized scope: no unrelated topics, website source changes, account changes, or promotional assets. Detailed write boundaries are in [write-boundaries.md](references/rules/write-boundaries.md).
- Use only Chrome or Edge for dbCodeBook; do not use the Codex in-app browser, even if its page is already open. Follow [browser session setup](references/rules/write-boundaries.md#浏览器会话), reuse the chosen logged-in session throughout the task, and pass it to the fixed download and website programs.
- Continue through authorized generation, verification and website sync without asking at every step. Stop at copy only for explicit “只审核、不执行”; pause for an unresolved research decision, required source gap, or uncertain external write.
- Keep full original identity and actual download alias distinct; do not rename downloaded CSV headers or replace formal sources with display abbreviations.
- A script pass proves only what it actually compared. Do not mark unexecuted checks passed or use presence, length, or hashes as proof of readable or correct content.
- Submit only after required local checks. After website submission returns the article URL, stop browser work; do not audit the page again.
- Follow the established standalone R entry: a user can run the formal R from start to finish to generate the complete note.
- Do not turn a topic decision into a common rule, or borrow another database's identity/period assumptions.
- Database colors remain in [database-themes.json](references/database-themes.json). Promotional assets use their dedicated skills.

## Finish

Close the execution report before claiming completion. In plain Chinese report actual changes, checks and results, total/per-stage time, bugs or abnormal events, and unfinished work. Website submission is not user acceptance.

For a shared-mechanism change or repository release, locate the installed skill-creator's quick_validate.py and run tests/run_all.ps1 with the configured executables and -SkillValidator. Record observed coverage and untested boundaries in [tests/acceptance-matrix.md](tests/acceptance-matrix.md). Do not infer ELSA acceptance from CHARLS tests.
