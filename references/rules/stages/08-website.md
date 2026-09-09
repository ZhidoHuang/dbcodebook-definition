# 8. 网站同步

## 本步执行与验收

- 输入：已验收且已授权同步的当前笔记、两份附件和发布许可
- 另读：[写入边界](../write-boundaries.md) 的网站固定步骤；[执行报告](../execution-report.md) 的网站计时与异常处理
- 执行：复用任务已选定的 Chrome 或 Edge 会话，执行下方唯一命令路径；提交前检查，提交后只确认返回地址
- 交付：原始同步结果及执行报告
- 程序检查：verify-ready 检查许可仍对应当前文件；提交前检查文章身份、正文、附件与顺序
- 模型判断：没有新的研究判断；只有身份不明、写入不确定或授权不足才停止反馈
- 未通过：提交前失败丢弃未保存改动并报告；提交结果不确定先查同次结果，不重新提交，不改网站源码

通过本步才交接给下一步；一次命令或点击不是一个独立验收环节。只读复核者接收本步稳定输入、对应标准及具体问题，不接收整个历史对话。

## Website-Only Commands

Run from this skill root, using the configured Python executable and the current task's values for `$Formal`, `$Process`, `$Topic`, `$Database`, `$TopicName`, `$PostId`, and `$BaseUrl`. This is local preparation, not an uploader; it does not open a browser or submit anything.

Start the preparation clock before local checks or browser setup, then run the readiness check without `--start-sync`. Follow [browser session setup](../write-boundaries.md#浏览器会话) and reuse the matching tab in `dbCodeBookBrowser`; confirm that it still shows the expected article and the logged-in edit control. Preparation is part of the website total, separate from fixed-submit timing.

```powershell
& $Python scripts/execution_report.py website-prepare --process-dir $Process --database $Database --topic-id $Topic --topic-name $TopicName
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl
```

Confirm that the required article or edit page is already open and logged in. Save the complete readiness JSON as `$Preflight`, then run `playwright_session_action.py --mode preflight` using the recorded CLI session/workdir (full command in the linked browser-session section). This checks the matching tab without navigating, editing, uploading or submitting. Keep that same preflight JSON for the submission command; no extension connection or manual browser binding is needed.

For a genuinely new article, open the site's new-article form in that same tab and verify it is blank. In both commands replace `--post-id $PostId` with `--create --website-title $WebsiteTitle --directory-tag $DirectoryTag`, using a directory tag verified on the website. The same helper sets the database and title, imports the body, uploads the two sidebar files in order, and submits once. It returns the actual newly assigned post URL; never create a placeholder article just to obtain an ID.

Only after both preflight checks pass, run the measured command below, save its complete JSON as `$Action`, and immediately execute `playwright_session_action.py --mode sync --action $Action --preflight $Preflight` with the same session/workdir and result path:

```powershell
& $Python scripts/check_definition_readability.py verify-ready --formal-dir $Formal --process-dir $Process --topic-id $Topic --start-sync --database $Database --topic-name $TopicName --post-id $PostId --base-url $BaseUrl
```

After local and browser preparation, `--start-sync` closes `website_preparation` and starts `website_sync` automatically. Missing preparation timing blocks dispatch; do not manually create either stage.

When the existing article also needs a new title, add the same
`--website-title $WebsiteTitle` to both commands. The fixed browser program
verifies the existing article identity first and changes the title in the same
single submission as the body and sidebar attachments.

The command rechecks current readiness and starts or resumes `website_sync` only after every local check passes. `website-prepare` archives a finished previous run. The dispatch command returns the fixed payload, helper hash, report identity, attempt, sync start time, and a short `browser_action.run_script`. A failed preflight leaves preparation time running; record and resolve that failure before dispatch.

Immediately run the fixed `playwright_session_action.py --mode sync` command with the unchanged action and preflight JSON. It verifies their helper hash and starts within 60 seconds of the measured stage. Internally it executes the prepared identity checks, CLI `click` then `upload` for the body, body verification and attachment preparation, CLI upload of each changed attachment, and the final checks and single submission. These are one measured operation, not model-directed retries. Do not execute the old monolithic `run_script` directly: the CLI owns file-chooser state, which must be cleared by its `upload` command. Keep the existing identity, body, attachment-order and return-URL checks. On a pre-submit upload failure, the runner records the error, opens a replacement editor tab in the same browser before closing the stuck tab, and verifies recovery. It does not close the only tab first. Unconfirmed recovery stays unconfirmed. Once submission begins, an uncertain response never triggers discard or automatic resubmission.

Complete every body, attachment, structure, and identity check before submission. After the article page returns, use its URL only to confirm that submission succeeded, then stop browser work: do not read or audit the returned page, reopen the editor, or submit again. Keep the unchanged browser result JSON as `$SyncResult` and import it directly. `website-finish` validates it and writes the standard `website_sync_result.json` itself; do not manually create that file. Submission time comes from that result; subsequent bookkeeping is recorded separately and ends with `finish`:

```powershell
& $Python scripts/execution_report.py website-finish --process-dir $Process --result $SyncResult
& $Python scripts/execution_report.py finish --process-dir $Process --status completed --summary "网站已同步，待用户检查。"
```

Use the report's actual issue status: resolved problems require `completed_with_issues`; failure requires recording the cause and stopping, not these success commands. An active timer is not restarted by another readiness check. Do not manually patch report JSON or Markdown to bypass its lifecycle.
