# KLoSA 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 以下仅列 KLoSA 的接口差异；正式来源记录带`database=KLoSA`、`language=en`或`ko`，本任务不自动切换语言。
- 材料、身份和文件区别见[profile](profile.md)。

1. 固定选择准备使用`prepare_source_selection.py --database klosa --language <已定语言>`；来源记录必须READY，来源为已确认的实际波次字段。
   - 选择及登录使用公共浏览器入口、同一语言和原绑定标签，不依赖当前页。
2. 下载准备和恢复显式传`--database klosa --language <已定语言>`。
   - 固定快照与动作保留语言，变更语言或数据库时拒绝续用旧尝试。
   - 一次提交、新鲜文件和失败处理遵循第2步，不新增审批点。
3. `klosa_adapter_contract.py`按普通、Exit和插补文件分别检查字典、别名、身份和记录键。
   - Exit独立文件按字典中的`KLoSA_Exit`来源归属检查；完整成果清单保留实际下载的各原文件，结果检查覆盖其身份及列集合。不把死亡访谈强接到同波存活访谈；连接或合并方式由已核实的记录关系决定。
   - 当前字典不再单列 `Wave`；按已核实的实际 `wNN… (File)` 身份核对时期及非空值所在期。旧包保留其原有 `Wave` 列契约，不改写原始文件。
   - 包没有语言标记，离线校验不能单凭ZIP证明来源语言；真实网页动作与下载回执须一同保留。
4. 公开R在读取时保留字符型`ID`、`Harmonized_id`、`Wave_id`，实际包带有默认`pid`时也按字符原样保留。
   - 普通个人结果用`render_definition_bundle(database="KLOSA", language=chosen_language, cycle_order=verified_waves, ...)`。
   - 时期为有证据的有序子集，不从非缺失行反推。
   - 生成器只在工作副本投影时期，不改raw。
5. 结果检查使用`check_definition_output.py --db klosa --language <已定语言>`。
   - 普通与Exit来源支持多文件契约及成果身份检查；生成前仍须形成身份唯一的个人—时期表。接口通过不代替主题的实际生成和完整验收；插补包仅支持结构校验。

- 英文入口的完整主题流程仍未验证；插补包的结构校验不涵盖插补分析或多文件主题生成。
