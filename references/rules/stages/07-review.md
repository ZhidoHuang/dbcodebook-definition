# 7. 成品交接

- 本步stage_id为review。
- 输入为当前文案、生成物和结果检查报告；输出为当前发布许可。
- 执行者先完成本次范围的内容整理、结果核对和常规程序检查，再做下方补充审核，通过后生成发布许可。审核不代替执行，也不重新开展全面研究。
- 不填写八项scope、逐项PASS、全文通读声明或代码复述。程序检查与代理的内容判断分别报告。

## 成品补充审核

- 新稿和整篇更新审当前成果；局部修改只审受影响内容及衔接。纯同步沿用未变且有效的结论，不借机重审旧稿或补造历史审核。
- 同一主题复用独立 R 复核代理；本次没有该代理时再创建。审核者只读，不代写成果、不修改已确认方案、不操作网站。
- 提供本次范围、对应栏目规则、已确认方案和必要证据、当前成稿及结果、结构等常规检查报告。代码或结果受影响时再提供相应实现和复算证据，不交整个历史对话。
- 审核者核对实际内容是否落实相应规则。解释性文案按[信息取舍](03-copy.md#解释性文案的信息取舍)审核：核心定义是否清楚，定义依据是否满足展示条件，数据处理细节及常规局限是否留在 R 注释；不要求将这些说明补回正文。来源、计算或关键条件存在疑点时定位到具体证据；已验证且未变的部分沿用，不重复逐格比较或重跑整套程序。
- 事实错误、计算错误、遗漏明确要求或妨碍正确理解的问题，写明位置、问题及依据，作为待解决发现。表达偏好和可选优化单列为建议，不列入阻断发现，不要求执行者全部采纳。
- 执行者根据证据修正；意见与既有证据不符时说明依据。研究取舍未定则返回来源阶段。修正后复用原代理，只复核受影响部分，不以固定轮数或发现数量评判质量。

复用现有执行报告，角色名为“成品补充审核”，不创建第二套审核表：

```powershell
& $Python scripts/execution_report.py review-start --process-dir $Process --role "成品补充审核" --input $Note --input $SourceRecord
# 本次实际使用的规则、证据和常规检查报告同样追加 --input；纯文案修改不补做 R 前审。
& $Python scripts/execution_report.py review-result --process-dir $Process --role "成品补充审核" --result pass --agent-id $ReviewerId --output $ReviewOutput --evidence $Conclusion
& $Python scripts/execution_report.py review-check --process-dir $Process --role "成品补充审核" --read-only
```

`review-result` 保存审核者真实交付；有未解决问题时用 blocked。审核输入不包含随后生成的 `publish_readiness.json`，也不包含随审核登记变化的 `execution_report.json`，以免形成循环。发现登记及返修见[角色交接](../review-roles.md#输入可见性日志定位与发现记录)。建议留在原始交付中，不要求另建文件。

## 生成发布许可

```powershell
& $Python -X utf8 scripts/check_definition_readability.py init `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId `
  --note $Note --r-script $RScript --analysis-db $AnalysisDb --analysis-codebook $AnalysisCodebook
& $Python -X utf8 scripts/check_definition_readability.py check `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId
```

- 为兼容现有入口，文件仍叫readability_audit.json。
- 新版记录（格式版本7）由程序生成ARTIFACTS_BOUND状态，绑定当前文件及证据，不含写作自评项，不需要手动修改。
- 成果变化后使用init --overwrite重新绑定，再check。

- 程序检查结果报告、文件身份、文案与生成内容一致性、已登记问卷展示和未解决问题；writing_quality=NOT_ASSESSED表示程序不判断写作质量。已登记的成品补充审核单独核对当前输入和真实结论，待审、过期或未解决发现不能忽略。未登记的历史审核不伪装成已通过。
- 正式生成前的独立R实现复核保持原要求；不在这里重复审核。
- 历史格式版本5、6的记录按原版本只读验证，不改写旧结论。
- 旧局部验收中的程序版本和生成环境只用于追溯。当前程序仍核对原始基线、来源、允许的改动及保留证据；缺失或不一致时停止该项验收，补核对受影响部分，不重建当时环境。沿用旧结论不表示重新验证过历史计算。

- 失败按报错返回对应文件、生成或结果检查，只重做受影响部分，见[返修范围](../validation.md#修正后的复核范围)。
- 已有unresolved_issues在重新初始化时保留，实际解决后记录处理依据再移除，不能靠重新初始化抹去。
- 发布前网站入口仍运行verify-ready。

## 按需普通读者复核

仅按[盲读触发条件](../validation.md#普通读者复核)使用init-reader。普通可读性已由成品补充审核覆盖，不重复启动此入口；未发起不生成记录。

- 只读角色看ordinary_reader_input.md，在reader_comprehension_review.json记录真实结论；一旦发起，未完成、未解决或已过期就不能发布。
- 返修复用角色，只复核受影响内容；相同笔记的有效记录可用 `init --overwrite --preserve-reader` 保留。
- 最后运行check取得当前许可。

