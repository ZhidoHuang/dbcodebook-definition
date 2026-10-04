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
| Only correct questionnaire text | [Scoped tasks](references/rules/scoped-tasks.md#questionnaire-only) | Compare supplied evidence, edit only the requested section, run its checker, then stop |
| Prepare download files offline | [Scoped tasks](references/rules/scoped-tasks.md#offline-download) | Generate the local action and snapshot; no browser, login, network or download |
| Check historical stage registration | [Scoped tasks](references/rules/scoped-tasks.md#historical-report) | Run the read-only report check; do not recreate production or alter history |
| Create, remake, or change sources | [1. Source plan](references/rules/stages/01-source-plan.md) | Follow the stages below; source or alias changes require a fresh full download |
| Review or change copy | [3. Reader copy](references/rules/stages/03-copy.md) | Read the complete 文案.md; regenerate and validate affected outputs, then perform authorized sync |
| Change R or calculation | [4. Public R](references/rules/stages/04-public-r.md) | Reuse unchanged sources; revise affected copy before generation |
| Upload reviewed outputs | [8. Website sync](references/rules/stages/08-website.md) only | Do not load discovery, questionnaire, R or writing rules; do not rebuild the topic |
| Edit this Skill | [Rule ownership](references/rules/index.md) and the requested scope | Do not run a topic or change the website merely to maintain the Skill |

明确用户已确定的要求、待探索问题及材料线索；由主线程从现有上下文整理，不要求用户填表，不把提到的来源或旧稿当作已决定的范围。明确任务直接执行；只有未决研究问题进入双路探索。

## Stage Order

The scoped entries above take precedence when the user limits the task. They do not start the full stage sequence or a new production report. Read their linked section only; load additional rules only for a concrete unresolved question. Report actual work and timing in the requested output instead.

On a new device or after runtime changes, run the [environment check](references/rules/stages/01-source-plan.md#新设备准备) once before production. Resolve all reported missing dependencies together; do not repeat unchanged checks per variable or stage. A local dependency pass does not establish browser control or website login.

[validation.md](references/rules/validation.md) owns stage order and correction scope. Each stage document contains its input, necessary additional reading, execution, output, machine checks, model judgement, and return point. Read the current stage and its relevant database sections, not all stages or both database workflows. Use the reading instructions and links in the current stage to locate the required rules and database sections; follow conditional links only when their condition holds. For long rules or tool outputs, locate headings with rg and read the relevant range (normally at most 200 lines per call); this is an output-size default, not permission to truncate required evidence or a requested full-copy review. Reuse unchanged material already read instead of reopening it at each stage.

1. [Source plan](references/rules/stages/01-source-plan.md).
2. [Selection and download](references/rules/stages/02-download.md).
3. [Reader copy](references/rules/stages/03-copy.md).
4. [Public R](references/rules/stages/04-public-r.md).
5. [Generation](references/rules/stages/05-generate.md).
6. [Result verification](references/rules/stages/06-results.md).
7. [Delivery check](references/rules/stages/07-review.md).
8. [Authorized website sync](references/rules/stages/08-website.md).

Resolve database-specific materials from [database-routing.json](references/database-routing.json). For reference documents, start with the [database material index](references/source-materials/材料索引.md); SHARE, KLoSA, KNHANES and CHNS currently provide materials only, not an accepted full-definition workflow. HRS routes to the Full HRS raw workflow at `/home/hrs/`; RAND HRS and Harmonized HRS are separate products and may be used only as explicitly labelled auxiliary evidence. HRS remains subject to its stated real-download and end-to-end acceptance boundary. A route is not evidence that a database has passed end-to-end testing. The generation stage states the current shared renderer's database boundary.

Before substantive production or shared-tool modification, start the existing [execution report](references/rules/execution-report.md); do not create parallel timing or audit systems. The current task owns the merged plan and subsequent execution. For unresolved research work, use two independent exploration agents as specified in stage 1; do not delegate the entire production workflow. When a stage calls for a read-only reviewer, use [review roles](references/rules/review-roles.md), create it only when input is stable, reuse it for affected rechecks, and close it afterward. Do not create visible tasks merely to split work.

## Global Boundaries

Execution owns completeness and readability. Do not create reviewers for each stage or writing requirement. Research uses two independent explorations followed by the primary agent’s evidence-based merge. A full topic retains one independent R implementation review against that settled plan after the stable R draft. Ordinary-reader review is optional for a specific unresolved readability concern or an explicit user request. Do not require a fixed writing self-review, per-section PASS statements, or an author reading declaration. Preserve deterministic checks, independent R implementation review, and truthful evidence.

- Clear rules are requirements, not invitations to redesign. If any rule is unclear, conflicts with another, or appears to require a departure, report the exact uncertainty and impact before changing it. This applies to all rules, not only source mapping.
- Keep authorized scope: no unrelated topics, website source changes, account changes, or promotional assets. Detailed write boundaries are in [write-boundaries.md](references/rules/write-boundaries.md).
- Use extension-free Playwright CLI with Chrome or Edge for dbCodeBook; no ChatGPT extension or Codex in-app browser. Follow [browser session setup](references/rules/write-boundaries.md#浏览器会话), reuse the named persistent session, and run the fixed download and website actions through its documented CLI entry.
- Continue through authorized generation, verification and website sync without asking at every step. Stop at copy only for explicit “只审核、不执行”; pause for an unresolved research decision, required source gap, or uncertain external write.
- Keep full original identity and actual download alias distinct; do not rename downloaded CSV headers or replace formal sources with display abbreviations.
- A script pass proves only what it actually compared. Do not mark unexecuted checks passed or use presence, length, or hashes as proof of readable or correct content.
- Submit only after required local checks. After website submission returns the article URL, stop browser work; do not audit the page again.
- Follow the established standalone R entry: a user can run the formal R from start to finish to generate the complete note.
- Do not turn a topic decision into a common rule, or borrow another database's identity/period assumptions.
- Database colors remain in [database-themes.json](references/database-themes.json). Promotional assets use their dedicated skills.

## Progress And Finish

Report progress, findings, decisions needing user input, and final results directly in the conversation in plain Chinese. The user must be able to understand the work and its outcome without locating or opening a file. When asking the user to review copy, present the actual text being reviewed in the conversation; for long copy, split it into clearly identified sections without silently omitting content. File paths, links, and attachments provide supporting detail and traceability, not a substitute for the report or review text. Keep raw data, full code, and detailed execution logs in their files unless the user requests them.

Stage reports are progress updates, not turn-ending handoffs. When no user decision is needed and authorized work remains, report in commentary, state the next action, and execute it in the same turn; do not send a final response or wait for “continue” merely because a stage finished. When a genuine decision is required, end the report with the concrete question, viable options and their material consequences, then give a recommendation and its evidence-based reason; identify any missing evidence that prevents a sound recommendation. Do not leave the user to infer the decision from findings or file links. Pause only the work that depends on the answer and continue independent authorized work. Use a final response when the requested scope is complete or progress truly requires user input or resolution of an external blocker. This reporting requirement does not create a new approval gate at every stage.

Close the execution report before claiming completion. In plain Chinese report actual changes, checks and results, total/per-stage time, bugs or abnormal events, and unfinished work. Website submission is not user acceptance.

For a shared-mechanism change or repository release, locate the installed skill-creator's quick_validate.py and run tests/run_all.ps1 with the configured executables and -SkillValidator. Record observed coverage and untested boundaries in [tests/acceptance-matrix.md](tests/acceptance-matrix.md). Do not infer one database's acceptance from another database's tests.
