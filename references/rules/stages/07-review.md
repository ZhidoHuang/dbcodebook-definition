# 7. 成品交接

本步stage_id为review。输入为当前文案、生成物和结果检查报告；输出为当前发布许可。常规交接使用下面两条命令；若触发普通读者复核，须按后文完成对应流程，再运行最终check取得当前许可。不安排固定内容自查，不填写八项scope、逐项PASS、全文通读声明或代码复述。

## 生成发布许可

```powershell
& $Python -X utf8 scripts/check_definition_readability.py init `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId `
  --note $Note --r-script $RScript --analysis-db $AnalysisDb --analysis-codebook $AnalysisCodebook
& $Python -X utf8 scripts/check_definition_readability.py check `
  --formal-dir $Formal --process-dir $Process --topic-id $TopicId
```

为兼容现有入口，文件仍叫readability_audit.json。新版记录（格式版本7）由程序生成ARTIFACTS_BOUND状态，绑定当前文件及证据，不含写作自评项，不需要手动修改。成果变化后使用init --overwrite重新绑定，再check。

程序检查结果报告、文件身份、文案与生成内容一致性、已登记问卷展示和未解决问题；PUBLISH_READY仅表示这些发布条件成立，writing_quality=NOT_ASSESSED，不表示写作质量通过。正式生成前的独立R实现复核保持原要求；不在这里重复审核。历史格式版本5、6的记录按原版本只读验证，不改写旧结论。

失败按报错返回对应文件、生成或结果检查，只重做受影响部分，见[返修范围](../validation.md#修正后的复核范围)。已有unresolved_issues在重新初始化时保留，实际解决后记录处理依据再移除，不能靠重新初始化抹去。发布前网站入口仍运行verify-ready。

## 按需普通读者复核

仅按[触发条件](../validation.md#普通读者复核)使用init-reader。它是有具体需要时的独立复核，不是每次写作的自查替代品。未发起不生成记录。

只读角色看ordinary_reader_input.md，在reader_comprehension_review.json记录真实结论；一旦发起，未完成、未解决或已过期就不能发布。返修复用角色，只复核受影响内容；相同笔记的有效记录可用 `init --overwrite --preserve-reader` 保留。最后运行check取得当前许可。
