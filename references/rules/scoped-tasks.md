# Scoped Tasks

These entries apply only to explicitly limited work. They do not replace the full production workflow. Resolve paths and Python from the task configuration; commands below use the Skill root as working directory.

## Questionnaire-only

Read the target questionnaire section, the actual supplied questionnaire and its source record. Work from each original question and each option to the copy, including entry conditions and destinations; do not use the record's list as the limit of what to check. If the original has a route absent from the record, retain it in the copy and report the record omission. Update the record only when it is writable and within scope. Preserve other sections, read-only evidence and existing presentation; do not rewrite a question block merely to match the checker's syntax.

```powershell
& $Python -X utf8 scripts/check_reader_copy.py --copy $Copy --record $SourceRecord
```

Check the resulting diff is limited to the requested section. This command compares the record with the copy, not the original material. Report original-material discrepancies separately even if the command passes. If the checker reports an unrelated existing defect, report it without expanding the edit. Finish with the actual corrections and check result; do not generate R, publish, create reviewers or start a production report for this scoped task. For an unresolved presentation question consult only the relevant section of stage 3, not its full production procedure.

## Offline-download

`--prepare-download` is a local file-generation command. It checks the supplied selection/source plan and writes an action JSON and a directory snapshot. The action contains browser instructions, but preparation does not execute them or connect to the URL. No browser, login or network is required for this step.

Inputs: existing source plan and selection file in the process directory, database, base URL, local downloads and formal directories. Use the supplied paths, creating missing output directories if needed.

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --action-file "$Process/download_action.json" --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

Success means the command succeeded and both JSON files exist and can be parsed. A handoff paragraph alone is not the deliverable. Report their paths and stop. Do not run the browser action, wait for a download, install a package or register a completed download stage. Preserve an existing attempt instead of rerunning preparation over it. If preparation fails, report its actual error; do not substitute an unexecuted command for completed work.

Only when actual downloading is authorized, continue at stage 2's Download Commands and browser-session setup.

## Historical-report

For a finished full-definition report, run:

```powershell
& $Python -X utf8 scripts/execution_report.py check --report $Report
```

This reuses the completion checks without saving or updating the report. Report missing registration or failed checks as found. A pass establishes registration completeness under the recorded policy, not that historical research, calculations or reviews were substantively correct. No production rerun or fabricated timing is needed. Non-full-definition or unfinished reports are outside this command's scope; report that limitation rather than assigning completion.
