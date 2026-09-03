---
name: dbcodebook-definition
description: Run, revise, audit, or publish variable-definition topics built from dbCodeBook across CHARLS, ELSA, and configured databases. Use for source discovery, official-material and literature review, fresh downloads, formal R definitions, full 文案.md review, validation, and website inspection sync. Do not use for promotional assets, rich text, or website maintenance.
---

# dbCodeBook Definition

Use this repository as the canonical rule, evidence, script, and test source. Resolve machine-specific paths and website addresses from `config.local.json`, a file passed to the relevant script, or explicit task context; never write them into shared rules.

## Start

1. Read [references/rules/index.md](references/rules/index.md), then load the common rule files it routes to.
2. Read [references/database-routing.json](references/database-routing.json). Identify the database, topic, formal directory, process directory, and requested stage.
3. Read only the selected database's workflow and profile. Never apply one database's periods, keys, files, codes, or questionnaire facts to another.
4. Work on one topic at a time. Continue through the requested stages without asking for confirmation already given. Pause only for an unresolved research decision, a required source gap, or an uncertain external write that the user has not authorized.

## Workflow

### 1. Discover Sources And Evidence

Discover candidates in dbCodeBook and inspect actual variable details and values. After candidate discovery, use the repository's official-material library before searching online. For every period shown as original-question content, record the question id, full question text, complete options when applicable, population, reference period, coding, and actual skip destination.

Read [references/rules/evidence-and-literature.md](references/rules/evidence-and-literature.md) for questionnaire, Harmonized, technical-document, and literature decisions.

### 2. Settle The Definition

Before formal R, settle every analysis variable's meaning, source groups, construction, missing handling, skip handling, period coverage, and cross-period decision. Check whether the proposal is narrower than the questionnaire, official construction, Harmonized counterpart, or authoritative method. Present a real unresolved research choice to the user; do not manufacture choices after the direction is already clear.

### 3. Download And Protect Sources

If any final source variable, period, file, source identity, or alias changes, download the complete changed list again from dbCodeBook. Never create formal raw data by filtering, splitting, supplementing, or joining an older package. Validate numbered variable families as complete families.

### 4. Write R And Generate Outputs

Inspect actual values before converting, cleaning, or recoding. Formal R implements the settled plan; it does not discover the plan. Prefer code a beginner can follow in execution order, use the project's established helpers for simple recurring operations, and add a transformation only when observed data require it.

Use the scripts under `scripts/` for source, output, and readability checks. When public R changes, review every meaningful block's input, action, output, and plain-language meaning; rewrite code that cannot be explained clearly in its actual order.

### 5. Review The Complete Copy

A request for “文案审核” means reading the deliverable-directory `文案.md` from beginning to end, editing it, synchronizing the formal generation source, regenerating, validating, and preparing the website inspection update. Stop at copy only when the user explicitly says `只审核、不执行`.

Review factual support, ordinary-language clarity, continuity, original-question fidelity, and duplication across the complete file. Website placement is for inspection, not acceptance.

### 6. Sync For Website Inspection

Immediately before browser work, read [references/rules/write-boundaries.md](references/rules/write-boundaries.md). Use one existing edit page, registered tags, one full body import, and the prescribed attachment location and order. Submit once and stop when the article page returns. Do not modify website code, databases, or upstream data.

## Boundaries

- Promotional SVG, rich text, covers, Xiaohongshu assets, and other campaign materials belong to their dedicated skills. Definition facts may feed those tasks only after validation.
- Do not turn a topic-specific decision into a common rule.
- Do not silently borrow another database's profile. Configure a workflow, profile, source-material route, and identity rules before formal work on a new database.
- Do not treat the example configuration as a user's actual configuration.

## Finish

Report in plain Chinese: what was checked, what changed, the concrete result, and what remains for user inspection. Do not lead with internal status labels or call a website update user acceptance.

For repository release or a shared-mechanism change, run `tests/run_all.ps1` and the `skill-creator` quick validator. Record only observed results in [tests/acceptance-matrix.md](tests/acceptance-matrix.md); a database without a real forward test must remain explicitly marked as not yet tested rather than being inferred from another database.
