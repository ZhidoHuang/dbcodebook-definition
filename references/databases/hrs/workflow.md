# HRS 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 本页只补充 Full HRS 的来源、下载、R及验证差异，产品身份、文件族和分析单位见 [profile](profile.md)。

## 来源探索

- 目录、搜索和详情使用[固定来源读取入口](../../rules/stages/01-source-plan.md#网页取证固定入口)，传 `--database hrs`；详情动作使用 `base_variable`，结果保留各时期实际变量名。
- 正式入口为 `/home/hrs/`，页面数据库类型为 `RAW_HRS`；RAND HRS、Harmonized HRS 不是这一路线。
- 记录 `Base_Variable`、`File`、Label、各时期实际变量名及对象层级。
- 稳定信息通常来自 Tracker，时变回答来自 Core，地区与城乡来自 Cross-Wave Geographic；仍按主题需要核实，不把这些例子当固定清单。
- RAND HRS 或 Harmonized HRS 仅作明确标注的辅助方法与映射证据，正式来源回到 Full HRS 页面和官方原始代码本核实。
- Core、Exit、Internet Survey、配偶或 household 来源分清对象。文件最新时期不一致时记录实际覆盖，不用其它时期值擅自补齐。

## 选择与下载

- 按[第2步](../../rules/stages/02-download.md)执行，数据库参数为 `hrs`。
- 预览与包校验确认 Full HRS 产品身份、完整 `Variable (File)`、各期字段、实际文件分组及身份列，不套用 RAND/Harmonized 的下载清单。

## R 与生成

- 个人键 `HHID`、`PN` 按字符读取，保留前导零；平台 `ID` 如存在，先核对含义。
- 统一 `HHID/PN` 为空、同包连接说明明确声明该期 `ID = Wave_id | hhid | pn` 时，在 R 工作对象中按声明恢复字符键。核对时期、六位家庭号、三位个人号及唯一性；原始 CSV 不变。没有这项声明、只有一个键为空或 ID 结构不符时，返回来源身份核实。
- Tracker 波次字段通过显式“变量—年份”映射转换为个人—时期工作表，原始下载文件不变。
- Core、Geographic 按实际个人键和时期连接；稳定 Tracker 信息按个人键接入各期，保留其稳定来源身份。
- 公共生成器使用 `database="HRS"` 和本次核实的 `cycle_order`，输入保留 `HHID`、`PN`、`year`。`year` 保存来源的真实时期：常规四位年份、多年度区间或带 Spring/Summer/Fall/Winter 的项目时期均按原值保留；不能将区间或季节擅自压成四位年份。`cycle_order` 无重复并按起始年及季节顺序排列；输入时期必须属于声明清单。同一时期内的不同项目、访视或表式仍须在方案和结果列中明确身份，不能靠时期校验授权覆盖。
- 调用及公开代码要求按[第4步](../../rules/stages/04-public-r.md)和[第5步](../../rules/stages/05-generate.md)。

## 结果验证与支持范围

在[第6步](../../rules/stages/06-results.md)中核对 `RAW_HRS` 产品身份、完整 File、字符型个人键及前导零、个人—时期唯一性和显式时期映射，核实未误用不同对象的文件。

当前生成接口接收 Full HRS 的 `HHID`、`PN`、`year` 个人—时期对象；其他对象层级不能直接套用该接口。生成接口及边界见[第5步](../../rules/stages/05-generate.md#数据库适配边界)。

## ADAMS 条件明细导出接口

- 完整文件 `ADAMS_MEDICAL_CONDITIONS_INITIAL_VISIT_CONDITION` 与 `ADAMS_MEDICAL_CONDITIONS_FOLLOW_UP_VISIT_CONDITION` 以 `raw_data_repeat_<完整文件>.csv` 导出；字典须为对应完整来源且 `File type=rePersonID`。自动 `RowIndex`、`source_file`、`source_row` 是来源定位列，不是额外选择变量。
- 包校验核对字符人键、`ID=Wave_id|HHID|PN`、原始访视时期和 `ADAMS1AH_C/BH_C/CH_C/DH_C`，并核对 RowIndex 以及原文件内 source_row 唯一。个人键允许重复；先按个人和时期汇总，再与主表连接，不能拿 RowIndex/source_row 跨文件连接。
- 公开 R 允许分别直接读取上述两张明细，保留 HHID/PN。条件文件 HCODE 及 `ADAMS_MEDICAL_HISTORY_INITIAL_VISIT_RESPONDENT`、`ADAMS_MEDICAL_HISTORY_FOLLOW_UP_VISIT_RESPONDENT` 的 M251A–H/J/K 为官方 Character 型 ICD 字段；由当前来源记录、完整文件、字典和所在表头共同匹配后允许字符读取，防止前导零、点号和尾零丢失。该许可不扩展至 TYPE、SUBCODE 或其他文件/业务字段。

- 摘要事实生成由HRS渲染入口显式指定 `period_mode="hrs_original"`，实际与预期时期以字符校验并保留多年度/季节标签；摘要覆盖范围及对象提示不能把这些时期转为整数。其他数据库沿用原周期模式。该事实适配不授权把同年不同项目互相覆盖。

- 成品检查复用已支持ADAMS两张条件明细的同一原包校验：主表保持四个人期身份列，两张明细由完整文件族与同包rePersonID字典核实，自动定位列/来源时期及行号继续检查。全部选择列须在主表和明细合计恰好覆盖一次；完整交付清单不得漏明细。不能为了满足主表表头检查拼平明细或删来源。


## Internet 问卷重复记录接口

- 完整 `INTERNET_SURVEY_INTERNET_QUESTIONNAIRE_RESPONDENT` 的 `rePersonID` 来源可由 `raw_data_repeat_<完整文件>.csv` 原样交付。仅此完整文件新增支持；三个来源定位列仍须原文件/时期、正整数行号及定位唯一性验证，全部业务列与同包字典精确对应。未知文件和额外业务列仍拒绝。
- 同包该文件连接说明明确2011使用 `ID=Wave_id|hhid|PN` 时，导出HHID空白可从完整ID恢复，但必须与原PN及时期一致。没有该文件自身声明、ID形状不符或现有键冲突时拒绝；不能用来源行号造个人身份。
- 公开R保留HHID/PN字符读取，且须与当前来源记录及同包完整rePersonID字典匹配。原始重复记录保留，正式输出仍为每人每期一行。重复问卷回答的合并、冲突及缺失规则由具体主题方案依据实际记录决定，接口不替主题选第一/最后一条或认定阳性。
- 成品入口复用同一原包契约，完整交付清单须包含该明细。不修改原CSV头、不将多对多连接当作个人长表。
- 成品个人身份核验纳入上述已通过完整原包契约的重复表，允许合法受访者仅见于该来源。未知重复文件、未核实字典或连接声明、身份冲突均不能扩大可接受人键集合；个人时期唯一性仍由长表检查核对。
