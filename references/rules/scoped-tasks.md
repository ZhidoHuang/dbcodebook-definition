# Scoped Tasks

Questionnaire-only, Offline-download and Historical-report apply only to explicitly limited work. Copy-operations contains the shared mechanical steps for the writing stage. Resolve paths and Python from the task configuration; commands below use the Skill root as working directory.

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


## Copy-operations

本节是文案阶段的程序操作，正文写法与模板统一见[03-copy](stages/03-copy.md)。不安排固定内容自查，不填写逐栏目PASS或通读声明。

1. **确定修改范围。** 新主题或定义事实变化时，在正式R前按[变更范围](../../templates/change-impact.md)填写已有definition_change_impact.json。只改表达则沿用未变的方案、来源和R复核；只改某栏不顺手修改其它内容。未决事实回来源方案；主题过大时按独立研究问题拆分，不拆散同一变量链或删掉必要原题。
2. **登记问卷展示。** 来源记录question_text保留原文，逐期证据不因合并展示而删除。写作时设置questionnaire_display_policy="chinese_v1"；每条证据的display.question_text填完整中文题干，display.instructions填必要中文访员/测验说明，无则空列表。共同说明可以放在该组设计段。原始选项编码与标签保留；数据解码方式只在影响对应关系时说明。原文、题意或时期有缺口，回到实际材料解决，不反向编造证据。
3. **运行机械检查。** 执行`check_reader_copy.py --copy <文案> --record <来源记录>`，处理它报告的结构、变量顺序、题文与格式差异。它不判断表达质量、翻译准确或官方证据是否完整。
4. **保存首稿并交接。** 已启动执行报告时，使用`stage-finish --stage-id copy --copy <文案.md> --summary <实际完成内容>`保存首次完整产出。事实缺口回方案，发现表达错误直接修；不把保存快照当作质量通过。生成器读取这份文案，R不另写一份正文。结果检查后按[成品交接](stages/07-review.md)取得机械发布许可。

目录入口由第5步生成，不手写进文案。单目录使用完整路径；分散来源的主要路径与说明分开传入，见[生成接口](stages/05-generate.md#文案读取与展示)。
