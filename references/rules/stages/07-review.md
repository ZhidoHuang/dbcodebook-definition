# 7. 成品交接

本步stage_id为review，由主执行者完成，不等于另派审核者。输入为已通过结果验证的当前成果、完整文案和各步实际结论；输出为readability_audit.json及当前发布许可。

## 执行结论归位

核对生成物与已完成文案/R一致及整篇衔接，沿用以下八项scope，不把它们当作八轮审核：

| 记录 | 结论来自哪里 |
| --- | --- |
| title_summary、definition_logic、criteria、insight_card、references | 第3步写作：对象、时间、判定、分类及必要限制清楚；依据与项目处理分开 |
| public_r_comments | 第4步编写及实现复核：按实际表达式解释输入、计算和结果；沿用该步骤的 code_walkthrough，不重新逐块审核 |
| labels_charts | 第5、6步：来源、标签、类别、图表和附件与定义一致 |
| full_note_flow | 本步：生成后核对段落衔接和遗漏，记录实际查看范围及必要过渡 |

每项依据指向实际内容及判定，发现和解决结果保留在现有evidence/findings。五项写作结论沿用第3步对具体内容及栏目职责的判断；完成摘要只有题数、变量数或检查通过时，不足以据此填写写作pass，应返回[写作步骤](03-copy.md#7-参考资料与交接)补核。不能用栏目存在、数量或程序PASS代替；有新生成内容须读取，用户要求全文审核时读全文。没有问题可通过，不制造发现。

失败只返回受影响文案、代码或生成部分，按[返修范围](../validation.md#修正后的复核范围)更新；不重开无关来源或固定再做两轮全文审核。

## 生成发布许可

绑定当前文件，在生成的记录中归入真实结论和unresolved_issues，再运行check：

```powershell
& $Python -X utf8 scripts/check_definition_readability.py init `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId `
  --note $Note --r-script $RScript --analysis-db $AnalysisDb --analysis-codebook $AnalysisCodebook
# 在生成的 readability_audit.json 中汇总执行结论，不填虚构 PASS。
& $Python -X utf8 scripts/check_definition_readability.py check `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId
```

init同时生成author_review_input.md，保留当前正文、参考链接及代码，移除HTML样式和脚本。本步用它看全文衔接，不反复读取整份HTML；它不替代图表/文件检查，成果变更后重建视图。

新记录的review_scope写实际查看的文件和段落范围、沿用哪些未变结论及未查看部分，不要求填写“完整通读”声明。各scope的evidence仍负责具体内容判断；记录范围不证明内容合格。check自动写入发布许可的checked_at，表示程序核验时间，不冒充人工阅读时间；不手填audited_at。历史第5版记录按原字段只读校验，不改写其声明或时间。

init带入同报告中与当前文案哈希一致的copy_execution_conclusions，但不自动判pass。重新生成时，仅已明确通过且文案、来源、数据、代码、写作规则绑定未变的五项写作scope可以保留；缺绑定或改变时pending。公开R、图表和全文衔接不由此自动通过。

新记录使用execution_first_v1；旧记录按原要求校验，不改旧记录免除未完成工作。check验证当前文件、结果证据、问卷和文案一致性，不证明语言好懂；发布前网站入口仍须verify-ready。状态含义见[验收流程](../validation.md#4-状态与入账)。

## 按需普通读者复核

仅按[触发条件](../validation.md#普通读者复核)使用init-reader。只读角色看ordinary_reader_input.md，在reader_comprehension_review.json记录原文、复述、疑问及真实结论；未发起不生成记录。

已发起则必须完成并解决疑问，过期或失败不能忽略。返修复用角色，只复核受影响内容；相同笔记的合格记录可用 `init --overwrite --preserve-reader` 验证保留。哈希、状态或逐块证据不符时失败，不自动补成通过；最后仍运行check取得当前许可。
