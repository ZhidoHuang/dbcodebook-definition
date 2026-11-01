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
- Core data 与 Indoor air quality special release 可以在同一主题中交付。两份原始文件分别验收；工作表按行合并，不按编号连接。其他专项混合组合仍不支持。普通表加 reID 分文件的下载校验不代表可以进入个人定义；个人聚合的现有支持范围见下方。

## 公开R与生成

- 公开读取：dt <- read.csv("raw_data.csv", colClasses = c(id = "character"))；name_z <- read.csv("raw_codebook.csv")。
- 单一独立uniqID专项直接读取字典对应的原名CSV，例如 `dt <- read.csv("raw_data_Indoor_air_quality_special_release.csv", colClasses = c(ID = "character", id = "character", year = "character"))`。公开读检查用正式目录字典绑定文件名。
- 同时使用 Core 和室内空气专项时，分别读入 `dt_core` 和 `dt_special`。两份读取均保留字符身份列。在工作表和分析表增加字符列 `sample_source`，分别填写 `Core data`、`Indoor air quality special release`。原始 ID/id/year 不改写；每个样本内每人每期一行。合并后以 sample_source、id、year 区分记录。不得将两个样本的指标填到同一行。
- ID有下划线通常自动字符，后台仍校验类型与ID=year_id；必要时允许身份列ID/id/year按字符读，不增加其他读取参数。

- render_definition_bundle(..., database="KNHANES", cycle_order=<来源方案明确年份>)。
- 数据、db_data、analysis_data均保留ID/id/year及来源内唯一记录；专项时期标记按profile解释，不将其当核心人年或建立跨Core连接。不根据非缺失输出反推时期。
- 重复文件可下载验证。进入个人级主题生成前须研究裁决并显式聚合；renderer仍拒绝把重复食品行当作个人年输入。

- check_definition_output.py --db knhanes 按字典验收单一普通个人表、单一独立专项，或上述 Core 与室内空气专项组合。所有原始文件均列入完整产物范围；分析身份按各自原始文件核对。
- 当前个人聚合接口只支持下方列出的输入和方法；其他 reID 包只支持下载结构验证，不以文件后缀猜测记录类型。
- 已确认的主题方案超出接口范围时，先处理缺少的接口能力。不得为了通过检查，改用下方的方法或改变主题的字段、时期和缺失处理。
- 源码字段不代表真包已验收。

## 第二访次个人聚合接口

先在主题方案中确定字段、时期、聚合及缺失处理，再核对接口是否支持。下面说明现有程序能力，不是 KNHANES 主题统一采用的计算规则。主题的选择和依据保存在其来源记录与公开 R 中。

### 当前支持范围

- 输入：`raw_data.csv` 与 `raw_data_Dietary_recall_second_day.csv`；重复来源为 `n_diet`、`n_diet_why`、`n_dt_ds`、`n_dt_etc` 四题，原生访次为2009、2019。这里只限定接口接收范围，不规定最终结果采用哪些年份。
- 启用：主题明确采用下表方法时，在来源记录填写 `knhanes_person_aggregation`，版本为1，按 ID/id/year 分组。缺少声明时不启用；不从其他主题复制方案。
- 映射：每个原字段声明来源别名、独立ASCII汇总变量和 `numeric_code` 或 `text` 类型。汇总变量不得占用原始字段、身份或结果名。

| 接口选项 | 已实现的方法 |
| --- | --- |
| `constant_within_person_visit`、`single_known_or_all_missing` | 同人同访次只有一个已知答值时保留，包括夹有普通缺失的情况；全部普通缺失则为缺失。数值编码按有限数值等价比较，文本按原文比较；8、9及条件标签不当作普通缺失。 |
| `group_na_and_report` | 任一题有多个不一致已知答值时，该人访次的四个汇总值均为NA，并记录冲突原值及RowIndex；不取首条或按频次投票。 |
| `left_to_primary`、`orphan_rule=stop` | 左连接至原主表，保留全部主表人年及顺序；重复记录无法对应主表或出现未声明年份时停止。 |

### 读取与检查

- 公开R分别读取原名文件到 `dt` 和 `dt_day2`，只准身份列字符类型参数。原始CSV、RowIndex、字典和读入帧不改写。工作表用汇总字段承接重复来源，字典记录其原始来源。
- 程序按主题声明的方法，从原始重复文件重算汇总，逐格核对工作表及主表身份顺序。它不判断该方法是否适合主题，也不判断疾病文本的临床含义。
- 新鲜下载、来源绑定、实际原答分布、公开R及成品检查仍按公共流程完成。接口回归通过不等于真实主题已验收。
