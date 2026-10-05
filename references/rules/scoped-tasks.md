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


## Copy-update

已有主题只改措辞或展示时，先保存修改前的有效依据，再改文案。不重新探索或重审未变的R。来源、补值条件、公式、变量范围或R需要变化时，返回对应环节，不使用这个入口。

```powershell
# 修改文件前运行；程序核对当前成果和既有研究、R复核，保存原稿及数据基线。
& $Python -X utf8 scripts/update_reader_copy.py prepare --formal-dir $Formal --process-dir $Process --reason "本次具体修改内容，以及研究方案和计算保持不变的范围"
# 修改文案.md；需要改问卷译文或位置时同步相应展示字段。
& $Python -X utf8 scripts/update_reader_copy.py run --formal-dir $Formal --process-dir $Process --config $Config
```

已按用户要求删除整节问卷时，第二条加 `--omit-questionnaire "本主题省略问卷展示的具体原因，研究证据和必要定义条件仍保留"`，程序同步展示标记及变更范围。局部题目取舍仍按下方Copy-operations登记。PowerShell 7不在PATH时传入实际 `--pwsh` 路径。

程序沿用修改前已核实的研究及R结论，运行正式生成、核对数据未变、保留内容未变的工作簿并取得当前发布许可；记录在原过程目录，不创建另一套审核。它只完成本地更新，不下载或发布。已授权同步时接第8步；失败保留日志，按具体问题修正，不用重派代理或重建记录绕过失败。已修改而没有修改前基线时，先核实已有版本，不能把当前稿冒充修改前稿。

## Copy-operations

问卷展示取舍按第3步。现有questionnaire_evidence中，不展示的题目填写display_required=false、display_omission_reason（本题为何无需展示），rendered_in_copy=false，copy_locator写“不展示：”及理由；原题证据、来源覆盖和路径核验仍保留。需要展示的沿用原字段，缺省display_required=true以兼容旧记录。检查器只跳过明确省略项的正文匹配，不跳过其研究证据校验，也不替执行者判断省略是否合理。

程序兼容：`chinese_v1` 可选登记 `display.options`（原编码及顺序不变，仅译标签）和 `display.skip_logic`（完整唯一 `source_index`、原触发代码及目的题号不变），缺省保持旧检查行为；两个问卷检查入口统一核验，并支持同题明确引用先前内容一致的 Wave 选项，选项引用不继承跳转，原文与 `routing_verbatim` 保留。

本节是文案阶段的程序操作，正文写法与模板统一见[03-copy](stages/03-copy.md)。不安排固定内容自查，不填写逐栏目PASS或通读声明。

1. **确定修改范围。** 新主题或定义事实变化时，在正式R前按[变更范围](../../templates/change-impact.md)填写已有definition_change_impact.json。只改表达则沿用未变的方案、来源和R复核；只改某栏不顺手修改其它内容。未决事实回来源方案；主题过大时按独立研究问题拆分，不拆散同一变量链或删掉必要原题。
2. **登记问卷展示。** 来源记录question_text保留原文，逐期证据不因合并展示而删除。原问卷题号与变量名不同时，question_id保留题号，question_variable登记已核实的原始变量名，locator注明对应依据；对应随时期变化时分期登记。两个问卷检查入口据此匹配正文标题，不从下载别名或题义猜测对应。写作时设置questionnaire_display_policy="chinese_v1"；需要展示的证据用display.question_text填完整中文题干，display.instructions填必要中文访员/测验说明，无则空列表。共同说明可以放在该组设计段。原始选项编码与标签保留；数据解码方式只在影响对应关系时说明。原文、题意或时期有缺口，回到实际材料解决，不反向编造证据。
3. **保存完整稿并运行机械检查。** 执行`check_reader_copy.py --copy <文案> --record <来源记录> --process-dir <过程目录>`；当前copy环节须在运行中，程序先保存完整稿，再检查，即使失败也保留真正首稿。未启动报告的只读检查省略process-dir。处理结构、变量顺序、题文与格式差异；程序不判断表达质量、翻译准确或官方证据是否完整。
4. **交接。** 使用`stage-finish --stage-id copy --copy <文案.md> --summary <实际完成内容>`记录真实结果，同次同内容不重复保存快照。事实缺口回方案，发现表达错误直接修；不把保存快照当作质量通过。生成器读取这份文案，R不另写一份正文。结果检查后按[成品交接](stages/07-review.md)取得机械发布许可。

目录入口由第5步生成，不手写进文案。单目录使用完整路径；分散来源的主要路径与说明分开传入，见[生成接口](stages/05-generate.md#文案读取与展示)。
