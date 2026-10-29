# KNHANES 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 下方只列 KNHANES 的接口差异及验证范围，调查设计和身份结构见 [profile](profile.md)。
- 目录、搜索和详情使用[固定来源读取入口](../../rules/stages/01-source-plan.md#网页取证固定入口)，传 `--database knhanes`。

## 选择和下载

- 本轮合并READY来源记录通过原来源检查器后，用prepare_source_selection.py --database knhanes生成原固定selection动作，再以固定标签调用playwright_session_action.py --mode select。
- 下载恢复器显式--database knhanes，不借其它库。
- 新鲜下载、快照、一次UI导出、真实浏览器原始回执及包验收沿用公共规则，不能以本地旧文件或合成fixture替代。

- 网站预期ZIP名KNHANESWithDict.zip：普通文件合并raw_data.csv；重复文件及profile所列独立专项输出raw_data_<英文文件名空格改下划线>.csv；raw_codebook.csv含Variable、Label原文、Label中文、File type、newname。
- File type区分uniqID/reID。
- 各别名须只在正确文件出现一次；不清除RowIndex后伪装个人表。
- 独立专项按字典完整来源核对原名、别名归属及ID/id/year唯一性，保留原文件名。
- Core data 与 Indoor air quality special release 可以在同一主题中交付。两份原始文件分别验收；工作表按行合并，不按编号连接。其他专项混合组合仍不支持。普通表加 reID 分文件的下载校验不代表可以进入个人定义；第二访次饮食四题须满足下方有界聚合契约。

## 公开R与生成

- 公开读取：dt <- read.csv("raw_data.csv", colClasses = c(id = "character"))；name_z <- read.csv("raw_codebook.csv")。
- 单一独立uniqID专项直接读取字典对应的原名CSV，例如 `dt <- read.csv("raw_data_Indoor_air_quality_special_release.csv", colClasses = c(ID = "character", id = "character", year = "character"))`。公开读检查用正式目录字典绑定文件名。
- 同时使用 Core 和室内空气专项时，分别读入 `dt_core` 和 `dt_special`。两份读取均保留字符身份列。在工作表和分析表增加字符列 `sample_source`，分别填写 `Core data`、`Indoor air quality special release`。原始 ID/id/year 不改写；每个样本内每人每期一行。合并后以 sample_source、id、year 区分记录。不得将两个样本的指标填到同一行。
- ID有下划线通常自动字符，后台仍校验类型与ID=year_id；必要时允许身份列ID/id/year按字符读，不增加其他读取参数。

- render_definition_bundle(..., database="KNHANES", cycle_order=<来源方案明确年份>)。
- 数据、db_data、analysis_data均保留ID/id/year及来源内唯一记录；专项时期标记按profile解释，不将其当核心人年或建立跨Core连接。不根据非缺失输出反推时期。
- 重复文件可下载验证。进入个人级主题生成前须研究裁决并显式聚合；renderer仍拒绝把重复食品行当作个人年输入。

- check_definition_output.py --db knhanes 按字典验收单一普通个人表、单一独立专项，或上述 Core 与室内空气专项组合。所有原始文件均列入完整产物范围；分析身份按各自原始文件核对。
- 除下方第二访次饮食四题的显式聚合契约外，包含重复来源的合法分文件包只支持下载结构验证；其他 reID 不能进入个人主题生成验收，不以文件后缀猜测记录类型。
- 若主题需其他重复来源，必须先裁决聚合及正式raw/来源关系/验收接口；不得把下方四题支持泛化到其他重复文件或食品条目。
- 源码字段不代表真包已验收。

## 第二访次饮食四题的有界个人聚合

- 仅支持常规 `raw_data.csv` 与原名 `raw_data_Dietary_recall_second_day.csv`，重复来源限 `n_diet`、`n_diet_why`、`n_dt_ds`、`n_dt_etc` 四题；其他重复族仍拒绝。原始CSV、RowIndex和字典不改写。
- 来源记录须声明 `knhanes_person_aggregation`：版本1、上述原文件、ID/id/year分组、2009/2019原生访次、`constant_within_person_visit`、`single_known_or_all_missing`、`group_na_and_report`、`left_to_primary`、`orphan_rule=stop`。每个原字段须声明唯一来源别名、独立ASCII汇总变量和numeric_code/text类型；汇总变量不得占用原始字段、身份或结果名。
- 同人同访次只有一个已知答值时保留，全部普通缺失则缺失。数值编码按有限数值等价比较，疾病名/其他说明按原文字面比较。一个已知答值夹普通缺失不抹掉该答值；8、9及条件标签不是普通缺失。
- 任一题有多个不一致已知答值时，仅该人访次的四个相关汇总值暂缓为NA。独立验收保留冲突原值和原始RowIndex记录；不取首条、不按频次投票。无法对应主表的人或意外年份直接停止。
- 公开R分别直接读取原名文件到 `dt` 和 `dt_day2`，只准身份列字符类型参数。保留未改动原始帧；显式聚合后按原主表左连接，全部主表人年及其顺序保留。工作表用四个汇总字段承接重复来源，原始重复别名不伪装成个人原答列；字典逐项记录汇总至原始来源的关系。
- 输出检查独立从未改动的重复文件重算四题汇总，逐格核对完整工作表；分析表须保留全部主表身份和顺序，四表共享结果、来源关系及原始文件范围继续按公共检查。该聚合检查不裁决糖尿病、高血压等疾病文本的临床含义。
- 仅合成数据接口回归通过不证明本次网站真包或主题验收通过。新鲜下载、来源绑定、实际原答分布、正式R与成品检查仍须逐题完成；2009四题是否有实值及结果采用哪些年份由本主题证据决定。
