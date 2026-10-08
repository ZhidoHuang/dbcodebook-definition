# KNHANES 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 下方只列 KNHANES 的接口差异及验证范围，调查设计和身份结构见 [profile](profile.md)。

## 选择和下载

- 本轮合并READY来源记录通过原来源检查器后，用prepare_source_selection.py --database knhanes生成原固定selection动作，再以固定标签调用playwright_session_action.py --mode select。
- 下载恢复器显式--database knhanes，不借其它库。
- 新鲜下载、快照、一次UI导出、真实浏览器原始回执及包验收沿用公共规则，不能以本地旧文件或合成fixture替代。

- 网站预期ZIP名KNHANESWithDict.zip：普通文件合并raw_data.csv；重复文件raw_data_<英文文件名空格改下划线>.csv；raw_codebook.csv含Variable、Label原文、Label中文、File type、newname。
- File type区分uniqID/reID。
- 各别名须只在正确文件出现一次；不清除RowIndex后伪装个人表。

## 公开R与生成

- 公开读取：dt <- read.csv("raw_data.csv", colClasses = c(id = "character"))；name_z <- read.csv("raw_codebook.csv")。
- ID有下划线通常自动字符，后台仍校验类型与ID=year_id；必要时允许身份列ID/id/year按字符读，不增加其他读取参数。

- render_definition_bundle(..., database="KNHANES", cycle_order=<来源方案明确年份>)。
- 数据、db_data、analysis_data均保留ID/id/year、唯一个人年；不根据非缺失输出反推时期。
- 重复文件可下载验证，进入个人级主题生成前须研究裁决并显式聚合，当前renderer拒绝重复个人年。

- check_definition_output.py --db knhanes当前生成验收范围仅为单一raw_data.csv个人年表：所有raw_vars必须来自该唯一表。
- 包含重复来源的合法分文件包只支持下载结构验证；由于当前输出检查仍要求主raw包含全部raw_vars，不能把重复包声明为已支持全层级生成。
- 若主题需重复来源，必须先裁决聚合及正式raw/来源关系/验收接口，此候选没有实现该扩展。
- 源码字段不代表真包已验收。

## 已验收范围与限制

- 2026-10-06，Core data 人口学已完成1998、2001、2005、2007–2024共21期真实下载：16来源、251455条个人年记录、15个结果。
- 唯一正式R完整生成，独立R复核及结果逐记录对照通过（含id/year共4274735单元、0差异）；正文与两份分析附件一次提交返回文章地址。
- 问卷显示与当前文案逐项核对通过。

- 本结论仅适用于本次普通个人年Core data人口学流程；不代表重复文件、其他主题、其他年份或新模型首次写作已通过。
- 固定 source-read 的当前支持范围见[来源读取](../../rules/stages/01-source-plan.md)；KNHANES 尚未接入，使用绑定 tab-code 只读。
