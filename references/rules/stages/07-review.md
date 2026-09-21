# 7. 成品交接

## 本步执行与验收

- 输入：已通过结果验证的当前成果、完整文案和执行时留下的检查结论。
- 另读：只在发生返修时读 [修正范围](../validation.md#修正后的复核范围)。
- 执行：主执行者核对生成物与已完成的文案、R 是否一致，检查整篇衔接；汇总各步骤已有结论，不重新开展两轮全文审核。
- 交付：现有 readability_audit.json 和当前发布许可；普通读者记录不再是固定交付物。
- 程序检查：check_definition_readability.py check 核对当前文件、结果证据、问卷呈现和文案一致性；它不证明语言好懂。
- 未通过：只回到受影响的文案、代码或生成步骤，集中修正后重生，不重查无关来源。

## 执行结论归位

沿用现有八项 scope，避免新增一套报告。它们是执行覆盖范围，不是八轮审核：

| 记录 | 结论来自哪里 |
| --- | --- |
| title_summary、definition_logic、criteria、insight_card、references | 第3步写作：对象、时间、判定、分类及必要限制清楚；依据与项目处理分开 |
| public_r_comments | 第4步编写及合并复核：按实际表达式解释输入、计算和结果；沿用该步骤的 code_walkthrough，不重新逐块审核 |
| labels_charts | 第5、6步：来源、标签、类别、图表和附件与定义一致 |
| full_note_flow | 本步：生成后核对段落衔接和遗漏，记录实际查看范围及必要过渡 |

每项保存实际依据、发现及解决结果，未发现问题可以通过，不要求为了证明审核有用而制造发现。不得把只完成格式检查写成语义检查通过。生成后若出现此前未读的新内容，必须读该内容；用户明确要求全文文案审核时仍从头读完整文案。

## 生成发布许可

先绑定当前文件，再汇总上述真实结论。未解决问题保留在 unresolved_issues；程序不能自动代填语言质量结论。

```powershell
& $Python -X utf8 scripts/check_definition_readability.py init `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId `
  --note $Note --r-script $RScript --analysis-db $AnalysisDb --analysis-codebook $AnalysisCodebook
# 在生成的 readability_audit.json 中汇总执行结论，不填虚构 PASS。
& $Python -X utf8 scripts/check_definition_readability.py check `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId
```

新记录标记 execution_first_v1；旧记录继续按其原有要求校验，不能编辑旧记录来免除未完成审核。PUBLISH_READY 表示当前文件可提交，不表示用户验收。网站入口仍运行 verify-ready，提交成功后不再审核页面。

## 按需普通读者复核

仅在用户要求，或执行者无法消除具体理解歧义时使用 init-reader。另一个只读角色只看生成的 ordinary_reader_input.md，按现有记录说明原文、复述和疑问；不查代码或重新调查来源。没有这项任务时不生成 reader_comprehension_review.json，也不登记“读者审核通过”。

一旦发起，这项审核的未完成、未解决问题或过期输入仍阻止发布；不能通过忽略失败记录继续。返修使用同一角色，只复核受影响内容，未变记录可按 --preserve-reader 保留。
