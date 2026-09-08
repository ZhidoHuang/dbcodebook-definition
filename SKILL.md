---
name: dbcodebook-definition
description: Run, revise, audit, or publish variable-definition topics built from dbCodeBook across CHARLS, ELSA, and configured databases. Use for source discovery, official-material and literature review, fresh downloads, formal R definitions, full 文案.md review, validation, and website inspection sync. Do not use for promotional assets, rich text, or website maintenance.
---

# dbCodeBook Definition

Use this repository as the canonical rule, evidence, script, and test source. Resolve machine-specific paths and website addresses from `config.local.json`, a file passed to the relevant script, or explicit task context; never write them into shared rules.

## Choose The Requested Work First

Resolve the database, topic, formal directory, process directory, and configuration once from the current task. Continue from those known values after a context transition; do not search for them again unless a file is missing or the user changes the target.

| Request | Read now | Execute |
| --- | --- | --- |
| Explain or report status | Only the relevant current artifact or execution report | Answer; do not regenerate, publish, or start a production report |
| Upload already-reviewed outputs | [write-boundaries.md](references/rules/write-boundaries.md) and the sync commands below | Check local readiness and run the fixed preflight in the existing edit or article page. Then start sync timing and immediately run the short returned program. Do not load questionnaire, database workflow, or common copy rules |
| Review or change copy | Relevant writing sections of [common-materials.md](references/rules/common-materials.md) and correction scope in [validation.md](references/rules/validation.md) | Review the complete `文案.md`, regenerate, renew affected evidence, and perform authorized sync |
| Change R or calculation | Relevant R sections of [common-materials.md](references/rules/common-materials.md) and [validation.md](references/rules/validation.md) | Inspect current inputs, change R, rerun and validate; unchanged sources do not require another download |
| Create, remake, or change sources | [database-routing.json](references/database-routing.json), the selected workflow/profile, [common-materials.md](references/rules/common-materials.md), and [evidence-and-literature.md](references/rules/evidence-and-literature.md) | Follow the complete definition workflow and refresh the full download when sources change |

Use [rules/index.md](references/rules/index.md) to resolve ownership when editing rules, not as a mandatory prelude to every upload. Read [execution-report.md](references/rules/execution-report.md) before a production run; use its existing script for timing and status. Website-only runs use `website-prepare`, then `--start-sync` below instead of manually creating timing stages.

Work on one topic at a time and retain authorization already given. Pause only for an unresolved research decision, a required source gap, or an uncertain external write. Do not treat a requested upload as permission to rebuild the topic.

Every rule in this skill is an execution requirement, not an invitation to redesign it. Apply a clear rule directly without adding interpretations, exceptions, or alternative schemes. If a rule cannot be understood, two rules genuinely conflict, or a different approach appears necessary, report the exact uncertainty or proposed departure and its impact before making changes; do not change first and explain afterward.

## Website-Only Commands

Run from this skill root, using the configured Python executable and the current task's values for `$Formal`, `$Process`, `$Topic`, `$Database`, `$TopicName`, `$PostId`, and `$BaseUrl`. This is local preparation, not an uploader; it does not open a browser or submit anything.

Start the preparation clock before local checks or browser setup, then run the readiness check without `--start-sync`. Reuse the current task's matching in-app-browser tab and confirm that it still shows the expected article and the logged-in edit control. Preparation is part of the website total, separate from fixed-submit timing.

```powershell
& $Python scripts/execution_report.py website-prepare --process-dir $Process --database $Database --topic-id $Topic --topic-name $TopicName
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl
```

Confirm that the required article or edit page is already open and logged in, then run the returned `browser_action.preload_script` once. The program uses the selected Codex in-app-browser tab when it matches, otherwise locates the unique matching tab itself, and loads the fixed helper functions; it does not navigate, edit, upload, or submit.

For a genuinely new article, open the site's new-article form in that same tab and verify it is blank. In both commands replace `--post-id $PostId` with `--create --website-title $WebsiteTitle --directory-tag $DirectoryTag`, using a directory tag verified on the website. The same helper sets the database and title, imports the body, uploads the two sidebar files in order, and submits once. It returns the actual newly assigned post URL; never create a placeholder article just to obtain an ID.

Only after both preflight checks pass, run the measured command below and execute the returned CUA program immediately:

```powershell
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --start-sync --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl
```

After local and browser preparation, `--start-sync` closes `website_preparation` and starts `website_sync` automatically. Missing preparation timing blocks dispatch; do not manually create either stage.

When the existing article also needs a new title, add the same
`--website-title $WebsiteTitle` to both commands. The fixed browser program
verifies the existing article identity first and changes the title in the same
single submission as the body and sidebar attachments.

The command rechecks current readiness and starts or resumes `website_sync` only after every local check passes. `website-prepare` archives a finished previous run. The dispatch command returns the fixed payload, helper hash, report identity, attempt, sync start time, and a short `browser_action.run_script`. A failed preflight leaves preparation time running; record and resolve that failure before dispatch.

Confirm that `browser_action.preload_sha256` matches the preflight output, then run `browser_action.run_script` unchanged in the very next CUA call. The program resolves the unique matching in-app-browser tab again; do not add a binding call, parse the script through another shell, rediscover browser methods, split it into manual steps, or substitute another upload implementation. The preloaded helper refuses to write if it was not dispatched within 60 seconds of the measured stage starting. It opens the exact edit page, verifies article identity before writing, imports the body once, uploads the two sidebar attachments one at a time in the declared order, checks body and attachment order, and submits once. Its result includes dispatch latency, total browser time, elapsed time since the website stage began, five step timings, and five explicit quality checks. If it fails before submission it reloads the same edit page to discard unsaved form changes and stops without retrying.

Complete every body, attachment, structure, and identity check before submission. After the article page returns, use its URL only to confirm that submission succeeded, then stop browser work: do not read or audit the returned page, reopen the editor, or submit again. Keep the unchanged browser result JSON as `$SyncResult` and import it directly. `website-finish` validates it and writes the standard `website_sync_result.json` itself; do not manually create that file. Submission time comes from that result; subsequent bookkeeping is recorded separately and ends with `finish`:

```powershell
& $Python scripts/execution_report.py website-finish --process-dir $Process --result-json $SyncResult
& $Python scripts/execution_report.py finish --process-dir $Process --status completed --summary "网站已同步，待用户检查。"
```

Use the report's actual issue status: resolved problems require `completed_with_issues`; failure requires recording the cause and stopping, not these success commands. An active timer is not restarted by another readiness check. Do not manually patch report JSON or Markdown to bypass its lifecycle.

## Execution Roles And Model Routing

Keep one primary writer for the entire topic. Use internal read-only subagents for the required reviews; do not create separate visible task threads merely to divide stages. Reviewers report findings to the primary writer and never edit files, rerun the production workflow, operate the website, or create competing versions.

Create a reviewer when its input is ready, not at the start of the topic. Retain its agent ID and use `send_input` for that topic's focused rechecks. Do not create another reviewer for a small correction. After the final affected review passes, close the agent with `close_agent`; an agent that has returned a result is still open until explicitly closed. Preserve its evidence and record its actual rounds using the report's `review-import` command. A later new topic gets its own scoped review context.

Use the following current defaults when the host offers these models. If a named model is unavailable, preserve the role by choosing the strongest available flagship model for quality-first review, a balanced agentic model for ordinary execution, and an efficient model only for bounded mechanical work. Do not weaken a role merely to preserve an exact model name.

| Role | Current default | Reasoning | Scope |
| --- | --- | --- | --- |
| Primary writer | `gpt-5.6-terra` | `high` | Ordinary source discovery, definition, download, R, generation, revision, and authorized website sync |
| Complex-topic primary writer | `gpt-5.6-sol` | `high` | Multiple periods or files, complex questionnaire paths, long-to-wide outcomes, official derived indicators, or unresolved source inconsistencies |
| Definition-logic reviewer | `gpt-5.6-sol` | `xhigh` | Read-only review of source completeness, questionnaire-path closure, definition breadth, period, population, unit, keys, and each source variable's purpose |
| Public-R reviewer | `gpt-5.6-sol` | `high` | Read-only review of final aliases, fixed header, observed-value checks, beginner-readable execution order, missing handling, mapping, and output boundary |
| Ordinary-reader reviewer | `gpt-5.6-terra` | `medium` | Read only the final reader copy and test whether each part can be understood and restated without technical context |
| Mechanical website operation | `gpt-5.6-luna` | `low` | Optional per-stage override for the already-authorized fixed upload action; keep the primary writer when switching would require another writer or task |
| Exceptional independent validation | `gpt-5.6-sol` | `max` | Only for the unresolved evidence, research, or high-impact shared-mechanism cases defined in the validation rules |

Machine checks use deterministic scripts rather than a model. The report reads the primary model from this task's session log at stage start; an unavailable record is marked unverified, never filled from this routing table. Do not use `max` for routine work, and do not create a separate visible task or browser session only to change models. Keep reviewer inputs narrow and bind each review to the current artifacts so long primary-thread context does not contaminate the independent pass.

For a full topic run, the definition-logic reviewer is required after the source plan is settled and before the final download or formal R. The Public-R reviewer is required after the R draft is complete and before it is accepted as the production script. The ordinary-reader reviewer is required after the reader artifacts are regenerated. The primary writer resolves every finding and reruns the affected review. Website work stays with the primary writer in the one existing in-app-browser session.

Schedule reviews at these dependency boundaries, not while their inputs are still changing. While a reviewer works, the primary writer may prepare a disjoint part of the deliverable, but must not rewrite the reviewer's inputs or repeat its review. Finish machine validation before final reading; use the change scope in the validation rules to decide which evidence needs renewal.

Submit the complete source plan and evidence together. Ask the reviewer to collect all findings in one pass; the primary writer resolves the batch before requesting a focused recheck of the changed branches and their dependents. Preserve unaffected findings instead of restarting discovery or whole-topic review. If the same gap recurs, resolve its missing evidence before another review request. Do not start a production stage merely to fill review waiting time; start it when its prerequisites and actual work are ready.

Before the first Public-R review, use the existing runner's `-PreflightOnly` mode to catch fixed-header, source, environment and syntax errors without producing outputs. Send the stable draft after fixing that batch. Do not send progress-only messages to a waiting reviewer; send the completed correction and affected scope together. The later production run still checks its actual inputs; do not insert another standalone preflight immediately before it.

## Complete Definition Workflow

Only creation, remake, or source-changing work needs this whole path:

Before the first substantive action, initialize the truthful execution report with `scripts/execution_report.py init --workflow full_definition`. Use the fixed stage IDs and review role names in [execution-report.md](references/rules/execution-report.md); an inapplicable stage must be recorded as skipped with its actual reason. The report cannot finish when a required stage or review is absent, a skipped stage is unexplained, or more than 60 seconds of wall-clock time is left outside every recorded work, wait, or rework stage.

1. Discover candidates in dbCodeBook; use local official materials before online research. Verify full original questions, options and real skip destinations for every period in the source evidence; present the reader-facing questionnaire using [common-materials.md, section 6.2](references/rules/common-materials.md).
2. Settle topic breadth and each variable's source, population, unit, missing handling and questionnaire paths; run the definition-logic review in [validation.md](references/rules/validation.md).
3. Download the full settled list when a source variable, period, file, identity or alias changes. Never rebuild raw from old packages. Use [Download Commands](#download-commands) for every export or recovery, not only after an event timeout. Inspect actual values before adding any cleaning.
4. Write beginner-readable R using established helpers and the fixed header. Run the existing runner with `-PreflightOnly` before the first Public-R review, resolve its findings, then complete Public-R review. Run `scripts/run_r_definition.ps1` in PowerShell 7 with the actual formal/process directories to produce the outputs.
5. Validate results, review the complete `文案.md`, and finish ordinary-reader review against stable final artifacts. `scripts/check_definition_readability.py check` binds the current evidence and outputs; correction scope is defined in [validation.md](references/rules/validation.md).
6. When website sync is authorized, use the website-only commands and [write-boundaries.md](references/rules/write-boundaries.md). Stop at copy only for an explicit `只审核、不执行` request.

Use the existing execution components for the mechanical parts:

| Step | Reusable entry |
| --- | --- |
| Runtime and R invocation | Resolve configured executables once. In PowerShell 7: `./scripts/run_r_definition.ps1 -WorkDir $Formal -Script $RFile -LogPrefix $LogPrefix -ProcessDir $Process -Config $Config -Database $Database -PreflightOnly`; after Public-R review, use the same command without `-PreflightOnly`. Pass paths as parameters, not inside a temporary `Rscript -e` string. |
| Public R structure | Start from [the fixed header](references/rules/common-materials.md#22-头部模板) and [dictionary template](templates/public-r-dictionary.R); fill the current sources/results rather than redesigning these components. |
| Independent workbook verification | Import `read_xlsx_rows` from `scripts/check_definition_output.py`; it reads actual cells, including workbooks with an incorrect `A1` dimension. Keep the independent definition calculation separate from file reading. |
| Reader review | `check_definition_readability.py init-reader` produces a DRAFT plus `ordinary_reader_input.md`, an allowlist containing that file alone, and the exact reviewer prompt. Give the reviewer only the returned input file and prompt; do not add the formal directory, public R, data, exploration record, or author review. Preserve the reader's returned wording when recording the review. The reader still supplies the interpretation and findings; the draft cannot pass by itself. |

## Download Commands

Read [download execution](references/rules/write-boundaries.md#下载结果与找回). Once the source list and the final download control are verified in the existing logged-in in-app-browser tab, prepare the local observer:

Treat the variable-selection page's normal export as the primary download path. A test of recovery cannot substitute for a forward test of that normal export.

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

The command checks inputs and the output boundary before spending points, records the current files, assigns one attempt ID, and returns one `browser_action.run_script`. Run that script unchanged once in the next CUA call with its declared timeout. It uses the selected matching variable-selection page, otherwise locates the unique matching Codex in-app-browser tab, verifies the selected count, starts waiting for that tab's download, and clicks the final control once. The same attempt ID is stored in both the browser-control runtime and the variable-selection page session, so a runtime reset cannot authorize a second click. When it returns `DOWNLOAD_FILE_READY`, pass its `download_path` unchanged to `recover_dbcodebook_export.py --archive <download_path>` with the same database, output directory, selection file, and intentional `--overwrite` setting. Run the prepared `watch_command` only when the browser result says `next_action: run_watch_command`. If neither route verifies a file, inspect the existing paid record; never run the browser action again. Use `--overwrite` only for an intentional replacement of existing formal raw.

## Boundaries

- Promotional SVG, rich text, covers, Xiaohongshu assets, and other campaign materials belong to their dedicated skills. Definition facts may feed those tasks only after validation.
- Database-level user-facing colors live in [database-themes.json](references/database-themes.json). Definition renderers and downstream promotional skills read this shared identity file instead of maintaining another copy.
- Do not turn a topic-specific decision into a common rule.
- Do not silently borrow another database's profile. Configure a workflow, profile, source-material route, and identity rules before formal work on a new database.
- Do not treat the example configuration as a user's actual configuration.

## Finish

Finish the execution report before claiming completion. Report in plain Chinese: what was checked, what changed, the concrete result, the total and per-stage time, any Bug or abnormal event, and what remains for user inspection. Do not lead with internal status labels or call a website update user acceptance.

For repository release or a shared-mechanism change, locate the installed `skill-creator`'s `quick_validate.py` as `$Validator`, then run `tests/run_all.ps1 -Config $Config -SkillValidator $Validator`. Both tests and structure validation use the configured Python. Record only observed results in [tests/acceptance-matrix.md](tests/acceptance-matrix.md); a database without a real forward test must remain explicitly marked as not yet tested rather than being inferred from another database.
