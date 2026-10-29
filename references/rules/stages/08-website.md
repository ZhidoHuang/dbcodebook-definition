# 8. 网站同步

## 本步输入与完成条件

- 输入为已授权同步的当前正式笔记、analysis_db、analysis_codebook及有效发布许可。
- 只同步时不重跑定义流程；权限见[写入边界](../write-boundaries.md#网站发布权限)，浏览器准备见[共用会话](../write-boundaries.md#浏览器会话)。

- 沿用当前Chrome/Edge及目标标签。
- 先检查文章身份、正文和附件，提交一次后以返回地址确认结果，随即停止浏览器工作，不再次审页或重开编辑器。
- 输出为原始同步结果和执行报告，完成后待用户检查。

## Website-Only Commands

在Skill根目录运行；路径、数据库、文章编号、标题、目录标签及会话参数均来自本任务记录。只保存完整命令结果，不修改其中的载荷。以下为既有文章；新建及改标题的差异见下一节。

### 1. 准备与预检

```powershell
& $Python scripts/execution_report.py website-prepare --process-dir $Process --database $Database --topic-id $Topic --topic-name $TopicName
```

- 在准备阶段运行网站准备入口，完成登录核对、文章身份确认、打开编辑页和等待内容加载。
- 把以下 JSON 保存为过程目录中的 `$WebsitePrepareAction`，地址和身份来自本任务记录：

```json
{"base_url":"http://localhost:8000","post_id":"local-395","identity_title_parts":["CHNS","人口学"],"open_login":true}
```

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode website-prepare --action $WebsitePrepareAction --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $WebsitePrepareResult
```

- 既有文章从实际“编辑”按钮取得编辑编号；返回 `WEBSITE_EDITOR_READY` 后，把返回的 `edit_id` 传给后面两次 verify-ready 的 `--edit-id`。
- 已在本任务编辑页时，准备 JSON 也传入此前核实的 `edit_id`，不重新加载。
- 新建时 JSON 使用 `{"base_url":"http://localhost:8000","create":true,"open_login":true}`，不传文章编号；固定入口打开 `/nodes/edit/` 并确认空白表单，不创建占位文章。

- `LOGIN_REQUIRED` 表示需要用户完成登录，之后重跑准备入口；其它失败先处理返回的具体原因。
- 已打开其它编辑页或新建页有内容时，保留现场，不覆盖或绕过。
- 网站准备只导航和读取，不填写、上传或提交。
- 不要把查询页专用的 login-status/login-open 用于文章页。

- 返回的 `fields` 已包含[当前标签选项](#下拉选项与填写)。
- 完成语义判断和选择后再生成预检载荷；这些均在准备计时内完成。
- 两次verify-ready使用同一份确定的选择，按下文传入标签参数或taxonomy-plan。

```powershell
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl --website-title $WebsiteTitle | Set-Content -Encoding utf8 $Preflight
```

准备计时从本地检查和登录核对前开始。网站准备成功后沿用同一 `$TabId`。以下预检只读，不导航、导入或提交：

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode preflight --action $Preflight --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $PreflightResult
```

### 2. 执行同步

本地与浏览器预检均通过后，启动提交计时，并立即执行固定入口，不再补查或改选标签：

```powershell
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --start-sync --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl --website-title $WebsiteTitle | Set-Content -Encoding utf8 $Action
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode sync --action $Action --preflight $Preflight --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $SyncResult
```

- 沿用同份预检、会话和标签，程序校验helper哈希及尝试身份。
- `--start-sync`自动结束准备并开始提交；缺准备计时会被拒绝。
- 分派有效期为启动后60秒，以首次进入固定浏览器动作为准。
- 同步按阶段限时，不共用60秒运行预算。正文等到内容匹配后继续；附件逐个等到读入完成后继续；提交等到返回文章地址后结束。完成即继续，不等满时限。
- 不手工建阶段、不重置计时，也不直接运行旧run_script。
- 固定入口失败时，先定位原因。可通过页面准备、会话恢复或配置修正解决的，自行处理后继续；需要修改工具时，按已授权的维护范围处理。保留身份、正文和附件检查，不临时绕过固定入口提交。

### 3. 导入结果与收口

仅同步成功、当前成果已经验证且没有仍阻断交付的 open 问题时，才执行以下成功收口命令。问题状态按[执行报告](../execution-report.md#bug-与异常)解释。

| 本次结果 | 收口状态 |
| --- | --- |
| 成功，且无问题记录 | `completed` |
| 成功，有 resolved 问题，或已验证恢复交付的 mitigated 问题 | `completed_with_issues`；mitigated 必须保留恢复证据和待修根因 |
| 失败、存在 open 问题、成果未验证或提交结果不明 | 不执行成功收口；记录 issue 和真实状态 |

下方命令使用 `completed`；存在 resolved 或 mitigated 问题时，按表替换状态：

```powershell
& $Python scripts/execution_report.py website-finish --process-dir $Process --result $SyncResult
& $Python scripts/execution_report.py finish --process-dir $Process --status completed --summary "网站已同步，待用户检查。"
```

保留原始 `$SyncResult`。正常成功、取回的原成功结果或固定入口生成的保存确认，由 `website-finish` 校验并写标准结果文件，不手工填报成功。保存确认使用 `--result $Confirmation`，原失败文件单独保留。
时间范围和汇报项见[执行报告](../execution-report.md#网站耗时)。

## 新建、改标题与附件

- 网站标题使用“数据库 — 中文（英文）”，例如“ELSA — 认知功能（Cognitive Function）”：数据库后用两侧各一个空格的长破折号，英文名称用中文全角括号，不带主题序号。
- 中英文含义一致且覆盖实际定义范围，采用主题已确定的英文名称，不由程序猜译。
- 新建和以后同步时，两次verify-ready（预检及--start-sync）均显式传入同一完整`--website-title`，不使用旧的仅中文默认标题。
- 序号只用于本地目录和内部记录；不因此批量改动未请求同步的旧文章。
- 程序兼容识别旧标题，以文章地址、数据库和主题名称核对身份。
- 新建文章在同一标签打开网站空白新建表单。
- 两个verify-ready命令均将post-id参数替换为 `--create --directory-tag $DirectoryTag`，保留上述完整标题参数；不先建占位文章取得ID，不用新建绕过既有文章身份检查。
- 文章编号支持正整数及 `local-正整数`，传入实际文章地址中的完整编号；程序将 `local-N` 的编辑入口映射为 `/nodes/edit/N/`。
- 更新返回允许同一编号的纯数字或 `local-` 地址，不接受另一编号；新建返回必须属于当前站点的文章路径。
- 原文章与本地编辑编号不同时，从原文章点击“编辑”核实对应地址；两次 verify-ready 均用 `--post-id <原文章编号> --edit-id <实际编辑编号>`。
- 编辑编号只指定操作页面，提交成功仍须返回原文章编号；不能猜测对应关系，也不能因此另建文章。
- 改既有标题时，两个命令都加同一 `--website-title`；先确认旧文章身份，再与正文附件同次提交。
- 目录标签与跨库主题（网页显示“主题标签”）均为单选：先读取当前下拉选项，优先选择含义匹配的已有项；检查同义、近义项后确无匹配才新建。
- 旧台账仅作线索，不能代替当前选项；不能把“搜索无结果”或“出现新建按钮”当成没有语义匹配。
- 更新时未要求调整的字段保留。
- KLoSA 发布按来源记录的 `language` 选择“KLoSA（韩文）”或“KLoSA（英文）”。数据库参数和标题仍用 KLoSA；来源语言未确认时停止准备，不猜选分类。
- 未变封面保留。
- 附件只有当前身份、名称、顺序及上次成功记录中的文件哈希吻合才保留，不凭同名认定未变。
- 只改第二份就替换第二份；第一份变更时从第一份起替换，保持analysis_db、analysis_codebook顺序。
- 各文件逐个上传至侧栏文档，不合并选择，不为测试重复删除上传；正文文档仅在正文含[DOCUMENTS]且任务另有规定时使用。
- 用户明确要求本次不上传数据表时，两次 `verify-ready` 均加 `--without-data-attachment`。仍核对本地数据表，侧栏只上传代码本；不修改或删除本地成果。

## 下拉选项与填写

- 使用网站准备结果的 `fields`，不重复读取；只有页面选项已变化时，才在同一已确认编辑页运行 `playwright_session_action.py --mode taxonomy-options --tab-id $TabId`（其余会话、配置、out参数同预检）。
- 主执行者结合本主题含义选择已有项；匹配有歧义时先查清，不让机械程序按字面猜含义。

- 已有项可通过 `--directory-tag`、`--cross-database-topic` 传入其原名；新建文章两项都要确定，未传跨库主题时程序只尝试匹配主题名称，不自动新建。
- 需要新建时，两个verify-ready命令均传同一 `--taxonomy-plan <本次选择JSON>`，字段为 `directory_tag` 和/或 `cross_database_topic`：

```json
{"directory_tag":{"value":"已有目录原名","mode":"existing"},"cross_database_topic":{"value":"新主题名称","mode":"create","options":["本次读取的全部已有选项"],"reason":"已比较哪些相近项及不匹配的具体原因"}}
```

- 选择记录保存在本次过程目录，不新增审批环节。
- 程序优先使用规范化后唯一匹配的已有项；没有匹配时，只有明确的新建选择且选项仍与读取时一致才点“使用…”；选项变化、同名歧义或控件不匹配时停止，返回选项判断。
- 通过按钮选择，不填隐藏字段、不直接回车。
- 选中后和提交前均核对两个目标值；仅准备或测试时不提交正式文章，不新建正式测试标签。

## 固定程序应完成的检查

1. 固定入口在浏览器操作前、上传前及提交前核对正文和附件与准备载荷中的文件哈希；缺失或变化时停止，回到受影响的本地验证后重新准备，不沿用旧载荷。
   - 页面实际就绪后确认目标URL、数据库、标题及编辑身份；新建须验证表单为空。
   - 身份未确认前不清正文或删附件。
   - 只返回必要身份与控件信息，不把全文输出到上下文。
2. 清空正文并确认空，再一次导入正式Markdown，不追加、分段拼接或重复导入。
3. 按上述规则保留或替换侧栏附件。**绑定标签页使用该页文件输入的setInputFiles，不等待系统文件选择窗口；旧未绑定入口使用CLI click/upload，仅限单任务独占会话。**两者不能混用，共享会话不得退回当前页或共享chooser。
4. 提交前核对正文UTF-16长度、LF换行下的首尾，与载荷body_check一致；核对身份及附件名称和顺序。已有载荷不再另算一份正文哈希。未替换附件不借机调整历史顺序。
5. 提交一次，等待导航返回正确文章URL，不等待文章页完整加载。记录实际返回地址和原始耗时。返回成功后不再读正文、附件或详情页，不重开编辑器。

## 失败怎样处理

| 状态 | 处理 |
| --- | --- |
| 预检失败、未确认文章身份 | 停止写入，报告具体问题；不自动清除身份不明的草稿 |
| 已进入确认的编辑页、尚未提交时发生非超时失败 | 先观察原动作；确认它已经结束且未请求提交后，才返回准备入口恢复本任务编辑页。动作仍在运行时，不重载或开始新尝试 |
| 同步超时（包括提交后等待超时） | 按下方“超时恢复”关闭本任务失效窗口，新窗口重新同步；不先核实保存状态 |
| 非超时的提交响应不明 | 保留SUBMISSION_UNCERTAIN，按固定观察入口处理具体回执错误 |
| 明确失败结束 | 保留失败证据。已授权的同步任务无需重新请示；处理失败原因、确认目标身份及重试条件后，沿用有效成果和检查结果，通过固定入口继续。条件未变时不反复重试 |

- 失败结果中的 `editor_page_restored` 只表示编辑页恢复，`content_rollback_status=NOT_VERIFIED` 表示正文和附件回滚未验证；兼容字段 `recovery_confirmed` 与前者同义。
- 页面恢复、内容回滚与同步成功分别判断，不能相互代替。

### 超时恢复

1. 保留原失败回执、目标文章身份和本次正式载荷；不运行 sync-observe 或 sync-confirm 作为超时重试前置。
2. 关闭本任务失效窗口，新开窗口并绑定新的 target ID，继续使用原登录配置及已确认目标。不得关闭其他线程窗口；共享窗口中仅关闭本任务标签。
3. 沿用未变的本地成果和有效验收，按固定准备入口创建新的同步尝试，再同步一遍。已有文章仍更新原文章；新建仍按原新建任务执行，不把前次超时记为保存成功。
4. 新尝试返回成功文章地址才登记同步完成。再次超时时保留两次失败记录，处理接口或配置原因，并继续其他可推进模块，不无限重试。

### 固定观察与保存确认

非超时失败需要调查原动作时，读取同次动作回执。沿用原载荷、会话和标签，不重新生成发布载荷：

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode sync-observe --action $Action --result $SyncResult --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $Observation
```

| 观察结果 | 下一步 |
| --- | --- |
| `ARTICLE_PAGE_RETURNED` | 已取回原成功结果，或同次回执核实延迟返回正确文章。延迟返回保留原失败状态，并核对既有提交前检查、当前文章身份、标题及附件顺序。用该结果执行website-finish；不再读取网站或提交 |
| `SYNC_ACTION_PENDING` | 原动作仍在运行。之后只观察同一回执，不重载、上传或提交 |
| `SYNC_NOT_SUBMITTED` | 原动作已结束，且未请求提交。记录失败，回准备入口恢复本任务页面，再按已授权范围继续 |
| `SYNC_SAVE_CHECK_REQUIRED` | 原动作已结束且请求过提交，用下方入口核对实际保存状态 |
| `SYNC_RECEIPT_UNAVAILABLE` | 回执不可用。不能据此认定没有保存；保留现场，说明缺少的回执，不自动重试或重启会话 |

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode sync-confirm --action $Action --result $SyncResult --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $Confirmation
```

- 原绑定标签已在本次目标文章地址时，确认入口直接读取该页，不重新导航或关闭它；否则使用临时只读标签核实原文章后关闭临时标签，保留原草稿。需要时正常展开延迟加载内容，并正常下载现有附件，与当前正式文件比较。
- `ARTICLE_SAVED_CONFIRMED`表示实际保存内容已核实；它不是补造的原提交成功回执。用该确认文件执行website-finish，按completed_with_issues收口。
- 确认失败时，按返回的身份、正文、附件或证据缺口处理。保留原失败和确认结果，不通过重新发布验证旧提交，不围绕同一未变条件反复排查。
- 接口、会话或网页结构确需修复时，结束本次同步诊断，转入已授权的独立维护；未受影响成果继续沿用。


- 文件为空、格式或读取失败、正文/附件不完整、连接中断和标签失效均不能带病提交。
- 正文完成等待最长30秒；附件完成等待最长60秒；提交返回等待最长30秒。CLI分别保留传输余量，不让前一步消耗下一步的等待时间。
- 超时按“超时恢复”执行；观察及保存确认工具保留用于非超时的具体诊断，不是超时重试前置。
- 重试成功只证明新尝试完成，原超时尝试仍如实记为结果不明。
- 人工点击没有系统弹窗不是绑定入口失败的判据。
- 禁止坐标猜测、另写上传器、切换共享当前页、临时API探索和绕过固定程序。


有限范围许可的提交参数与本地验收保持一致，按[验收范围](../validation.md#验收范围与沿用结论)核对；不通过同步扩大本次修改范围。
