# 8. 网站同步

## 本步输入与完成条件

输入为已授权同步的当前正式笔记、analysis_db、analysis_codebook及有效发布许可。只同步时不重跑定义流程；权限见[写入边界](../write-boundaries.md#网站发布权限)，浏览器准备见[共用会话](../write-boundaries.md#浏览器会话)。

沿用当前Chrome/Edge及目标标签。先检查文章身份、正文和附件，提交一次后以返回地址确认结果，随即停止浏览器工作，不再次审页或重开编辑器。输出为原始同步结果和执行报告，完成后待用户检查。

## Website-Only Commands

在Skill根目录运行；路径、数据库、文章编号、标题、目录标签及会话参数均来自本任务记录。只保存完整命令结果，不修改其中的载荷。以下为既有文章；新建及改标题的差异见下一节。

### 1. 准备与预检

```powershell
& $Python scripts/execution_report.py website-prepare --process-dir $Process --database $Database --topic-id $Topic --topic-name $TopicName
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl | Set-Content -Encoding utf8 $Preflight
```

准备计时从本地检查和登录核对前开始。确认目标页已打开且登录有效，沿用该任务观察并绑定的 `$TabId`。未登录时在尚未改动的页面完成登录后继续。预检只读，不导航、导入或提交：

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode preflight --action $Preflight --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $PreflightResult
```

### 2. 执行同步

本地与浏览器预检均通过后，启动提交计时，并立即执行固定入口：

```powershell
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --start-sync --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl | Set-Content -Encoding utf8 $Action
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode sync --action $Action --preflight $Preflight --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $SyncResult
```

沿用同份预检、会话和标签，程序校验helper哈希及尝试身份。`--start-sync`自动结束准备并开始提交；缺准备计时或启动后超过60秒才分派会被拒绝。不手工建阶段、不重置计时，也不直接运行旧run_script。固定入口不适用时停止报告，另修工具，不临场拼调用或改走粘贴。

### 3. 导入结果与收口

仅成功时执行：

```powershell
& $Python scripts/execution_report.py website-finish --process-dir $Process --result $SyncResult
& $Python scripts/execution_report.py finish --process-dir $Process --status completed --summary "网站已同步，待用户检查。"
```

保留原始 `$SyncResult`，由website-finish校验并写标准结果文件，不手工填报成功。过程中有已解决问题仍用completed_with_issues；失败记issue及真实失败状态，不运行成功收口。时间范围和汇报项见[执行报告](../execution-report.md#网站耗时)。

## 新建、改标题与附件

- 网站标题使用“数据库 主题名称”，不带主题序号，例如“ELSA 孤独感”；序号只用于本地目录和内部记录。新建和以后同步时按此执行，不因此批量改动未请求同步的旧文章。程序兼容识别带序号的旧标题，以文章地址、数据库和主题名称核对身份。
- 新建文章在同一标签打开网站空白新建表单。两个verify-ready命令均将post-id参数替换为 `--create --website-title $WebsiteTitle --directory-tag $DirectoryTag`；不先建占位文章取得ID，不用新建绕过既有文章身份检查。
- 文章编号支持正整数及 `local-正整数`，传入实际文章地址中的完整编号；程序将 `local-N` 的编辑入口映射为 `/nodes/edit/N/`。更新返回允许同一编号的纯数字或 `local-` 地址，不接受另一编号；新建返回必须属于当前站点的文章路径。
- 改既有标题时，两个命令都加同一 `--website-title`；先确认旧文章身份，再与正文附件同次提交。
- 目录标签沿用已核实的主题索引、台账或同组文章登记值，不根据主题名造标签。文章身份、正文路径及附件未确定时不开始写入。
- 未变封面保留。附件只有当前身份、名称、顺序及上次成功记录中的文件哈希吻合才保留，不凭同名认定未变。只改第二份就替换第二份；第一份变更时从第一份起替换，保持analysis_db、analysis_codebook顺序。各文件逐个上传至侧栏文档，不合并选择，不为测试重复删除上传；正文文档仅在正文含[DOCUMENTS]且任务另有规定时使用。

## 固定程序应完成的检查

1. 固定入口在浏览器操作前、上传前及提交前核对正文和附件与准备载荷中的文件哈希；缺失或变化时停止，回到受影响的本地验证后重新准备，不沿用旧载荷。页面实际就绪后确认目标URL、数据库、标题及编辑身份；新建须验证表单为空。身份未确认前不清正文或删附件。只返回必要身份与控件信息，不把全文输出到上下文。
2. 清空正文并确认空，再一次导入正式Markdown，不追加、分段拼接或重复导入。
3. 按上述规则保留或替换侧栏附件。**绑定标签页使用该页文件输入的setInputFiles，不等待系统文件选择窗口；旧未绑定入口使用CLI click/upload，仅限单任务独占会话。**两者不能混用，共享会话不得退回当前页或共享chooser。
4. 提交前核对正文UTF-16长度、LF换行下的首尾，与载荷body_check一致；核对身份及附件名称和顺序。已有载荷不再另算一份正文哈希。未替换附件不借机调整历史顺序。
5. 提交一次，记录实际返回文章URL和原始耗时。返回成功后不再读正文、附件或详情页，不重开编辑器。

## 失败怎样处理

| 状态 | 处理 |
| --- | --- |
| 预检失败、未确认文章身份 | 停止写入，报告具体问题；不自动清除身份不明的草稿 |
| 已进入确认的编辑页、尚未提交时失败 | 固定程序恢复本任务编辑页；记录是否尝试、是否确认恢复，未确认不能写恢复成功 |
| 提交已开始但响应不明 | 保留SUBMISSION_UNCERTAIN；不重载、不丢弃、不自动再次提交，先核对同次结果 |
| 明确失败结束 | 保留失败证据；新一次同步须有用户指令，不循环重连或消耗尝试 |

用户授权核对不确定提交时，只读检查同次返回文章的身份、已保存正文和实际附件，另存确认依据；保留原始失败结果，不补造成功回执，也不通过重新发布来确认旧提交。

文件为空、格式或读取失败、正文/附件不完整、连接中断和标签失效均不能带病提交。固定动作有60秒运行限时；耗时目标不能代替成功检查，也不能因超时在可能已提交后重新操作。人工点击没有系统弹窗不是绑定入口失败的判据。禁止坐标猜测、另写上传器、切换共享当前页、临时API探索和绕过固定程序。
