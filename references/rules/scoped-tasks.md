# Scoped Tasks

Questionnaire-only 仅用于用户明确限定只改本地问卷、不生成或同步的任务；普通问卷修改完成后接 Copy-update 和网站同步。Offline-download 和 Historical-report 仅用于用户明确限定的任务。
Copy-operations 保存文案阶段共用的程序操作。
路径和 Python 从任务配置取得；下方命令在 Skill 根目录运行。

## Questionnaire-only

1. 读取目标问卷部分、用户提供的实际问卷及来源记录。
2. 从原问卷逐题、逐选项核对文案，包含进入条件和去向；不以已记录项目限定检查范围。
3. 原文有记录未包含的路径时，保留该路径并报告记录遗漏。
4. 只有记录可写且修改在授权范围内时，才更新来源记录。
5. 保留其他章节、只读证据和既有展示，不为迎合检查器语法重写题块。
6. 运行检查，并确认差异只涉及指定部分：

```powershell
& $Python -X utf8 scripts/check_reader_copy.py --copy $Copy --record $SourceRecord
```

| 检查情况 | 处理 |
| --- | --- |
| 命令通过 | 只证明记录与文案一致；与原始材料的差异仍须单独报告 |
| 发现无关的既有缺陷 | 报告缺陷，不扩大修改范围 |
| 展示方式仍有具体疑问 | 只读第3步有关部分，不启动完整生产流程 |

汇报实际修正及检查结果后结束。不生成 R、不发布、不创建复核角色或生产报告。

## Offline-download

`--prepare-download` 检查来源方案和选择清单，生成动作 JSON 及目录快照。
动作内包含浏览器指令，但准备过程不执行指令、不连接网址，不需要浏览器、登录或网络。

输入为过程目录中的已有方案和选择文件、数据库、网站地址、本地下载目录及正式目录。
使用提供的路径；输出目录缺失时可创建。

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --action-file "$Process/download_action.json" --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

| 情况 | 处理 |
| --- | --- |
| 命令成功，且两个 JSON 文件存在并可解析 | 汇报文件路径后结束；只有交接说明不算完成 |
| 已有下载尝试 | 保留原尝试，不覆盖它重新准备 |
| 准备失败 | 报告实际错误，不用尚未执行的命令冒充完成 |

本入口不执行浏览器动作、不等下载、不安装包，也不登记下载阶段已完成。
只有实际下载已获授权时，才继续第2步的 Download Commands 和浏览器会话准备。

## Historical-report

对已结束的完整定义报告运行：

```powershell
& $Python -X utf8 scripts/execution_report.py check --report $Report
```

- 命令复用完成检查，但不保存或更新报告。
- 如实报告缺失登记和失败检查。
- 通过只证明按当时策略登记完整，不证明历史研究、计算或复核内容正确。
- 不重跑生产，不补造耗时。
- 非完整定义报告或尚未结束的报告不在本入口范围内；说明限制，不代记完成。

## Copy-update

已有主题只改措辞或展示时，先保存修改前的有效依据，再改文案。不重新探索或重审未变的R。来源、补值条件、公式、变量范围或R需要变化时，返回对应环节，不使用这个入口。

```powershell
# 修改文件前运行；程序核对当前成果和既有研究、R复核，保存原稿及数据基线。
& $Python -X utf8 scripts/update_reader_copy.py prepare --formal-dir $Formal --process-dir $Process --reason "本次具体修改内容，以及研究方案和计算保持不变的范围"
# 修改文案.md；需要改问卷译文或位置时同步相应展示字段。
& $Python -X utf8 scripts/update_reader_copy.py run --formal-dir $Formal --process-dir $Process --config $Config
```

- 已按用户要求删除整节问卷时，第二条加 `--omit-questionnaire "本主题省略问卷展示的具体原因，研究证据和必要定义条件仍保留"`，程序同步展示标记及变更范围。
- 局部题目取舍仍按下方Copy-operations登记。
- PowerShell 7不在PATH时传入实际 `--pwsh` 路径。

- 程序沿用修改前已核实的研究及R结论，运行正式生成、核对数据未变、保留内容未变的工作簿并取得当前发布许可；记录在原过程目录，不创建另一套审核。
- 它只完成本地更新，不下载或发布。
- 本地更新完成后接第8步同步，用户明确限定本地时除外。失败保留日志，按具体问题修正，不用重派代理或重建记录绕过失败。

| 固定入口返回 | 下一步 |
| --- | --- |
| `LOCAL_UPDATE_COMPLETE` | 本地成果已验证，接第8步；不代表已提交网站 |
| `READER_REVIEW_REQUIRED` | 旧读者结论不能用于新稿；按第7步复用角色复核受影响内容。通过后运行 `finish`；仍需改稿时，修正后用 `retry` 重新生成，不重做研究 |
| 执行失败且已保存失败现场 | 修正具体问题后运行下方 `retry`；原基线、失败日志和问题记录继续保留 |
| 研究、R、raw或本入口以外成果发生变化 | 返回实际受影响环节；不能用 `retry` 掩盖变化 |

```powershell
& $Python -X utf8 scripts/update_reader_copy.py retry --formal-dir $Formal --process-dir $Process --config $Config --reason "实际失败原因、已经修正的内容，以及研究与计算未变的依据"
# 已完成要求的读者复核后，只核对当前许可并收口。
& $Python -X utf8 scripts/update_reader_copy.py finish --formal-dir $Formal --process-dir $Process
```

旧失败记录没有失败现场指纹时，入口会说明限制；先核实原基线和当前文件，不手改状态强行重试。
- 已修改而没有修改前基线时，先核实已有版本，不能把当前稿冒充修改前稿。

## Copy-operations

问卷是否展示按第3步判断。已有 `questionnaire_evidence` 的展示字段按下表登记：

| 情况 | 字段 |
| --- | --- |
| 不展示本题 | `display_required=false`；`display_omission_reason` 写具体理由；`rendered_in_copy=false`；`copy_locator` 写“不展示：”及理由 |
| 需要展示 | 沿用原字段；缺省 `display_required=true`，兼容旧记录 |

不展示时仍保留原题证据、来源覆盖和路径核验。
检查器只跳过明确省略项的正文匹配，不跳过研究证据，也不判断省略是否合理。

`chinese_v1` 兼容字段：

| 可选字段 | 保留要求 |
| --- | --- |
| `display.options` | 原编码和顺序不变，只译标签 |
| `display.skip_logic` | `source_index` 完整且唯一；原触发代码及目的题号不变 |

不提供这些字段时，保持旧检查行为。
两个问卷检查入口使用同一核验规则，并支持同题明确引用先前内容一致的 Wave 选项。
选项引用不继承跳转；原文及 `routing_verbatim` 保留。

本节是文案阶段的程序操作，正文写法与模板统一见[03-copy](stages/03-copy.md)。不安排固定内容自查，不填写逐栏目PASS或通读声明。

1. **确定修改范围。**
   - 新主题或定义事实变化时，在正式R前按[变更范围](../../templates/change-impact.md)填写已有definition_change_impact.json。
   - 只改表达则沿用未变的方案、来源和R复核；只改某栏不顺手修改其它内容。
   - 未决事实回来源方案；主题过大时按独立研究问题拆分，不拆散同一变量链或删掉必要原题。
2. **登记问卷展示。**
   - 来源记录question_text保留原文，逐期证据不因合并展示而删除。
   - 原问卷题号与变量名不同时，question_id保留题号，question_variable登记已核实的原始变量名，locator注明对应依据；对应随时期变化时分期登记。
   - 两个问卷检查入口据此匹配正文标题，不从下载别名或题义猜测对应。
   - 写作时设置questionnaire_display_policy="chinese_v1"；需要展示的证据用display.question_text填完整中文题干，display.instructions填必要中文访员/测验说明，无则空列表。
   - 共同说明可以放在该组设计段。
   - 原始选项编码与标签保留；数据解码方式只在影响对应关系时说明。
   - 原文、题意或时期有缺口，回到实际材料解决，不反向编造证据。
3. **保存完整稿并运行机械检查。**
   - 执行`check_reader_copy.py --copy <文案> --record <来源记录> --process-dir <过程目录>`；当前copy环节须在运行中，程序先保存完整稿，再检查，即使失败也保留真正首稿。
   - 未启动报告的只读检查省略process-dir。
   - 处理结构、变量顺序、题文与格式差异；程序不判断表达质量、翻译准确或官方证据是否完整。
4. **交接。**
   - 使用`stage-finish --stage-id copy --copy <文案.md> --summary <实际完成内容>`记录真实结果，同次同内容不重复保存快照。
   - 事实缺口回方案，发现表达错误直接修；不把保存快照当作质量通过。
   - 生成器读取这份文案，R不另写一份正文。
   - 结果检查后按[成品交接](stages/07-review.md)取得机械发布许可。

目录入口由第5步生成，不手写进文案。单目录使用完整路径；分散来源的主要路径与说明分开传入，见[生成接口](stages/05-generate.md#文案读取与展示)。
