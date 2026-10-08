# 定义变更范围

使用现有definition_change_impact.json，init-impact创建第3版记录，不另建表。它记录要改什么，用于确定后续执行范围，不评价文案质量。

- change_summary：本次新增、删除或改变什么；只改表达时直接说明，不能写成定义事实变化。
- changed_dimensions：实际改变的部分，如variable_set、questionnaire_scope、public_r或copy。
- question_groups：涉及的题组，保留名称、时期、对象、官方材料位置、代表性中文题文、用于什么结果及文案位置。
- 已核实中文原题用verified_quote；外文的完整中文翻译用verified_translation，来源原文留在来源证据；已满足题意概括证据条件时用plain_paraphrase并填paraphrase_reason；来源记录的对应项同时使用question_text_mode=plain_paraphrase、question_text_complete=false，并按证据规则登记对象、回顾期及原题缺失原因。
- 没有涉及题组时填question_groups_not_applicable_reason。
- unresolved_issues：尚未解决、会影响实施的问题。解决前不能进入正式生成；重新初始化不会清空已有问题。

- 不填写审核人、审核时间、题组PASS或逐项surface评语。
- 程序保留CHANGE_SCOPE_RECORDED状态，检查必要信息及代表性题文是否在文案中；这不是内容质量结论。
- 第2版历史记录继续按原版本只读验证。
