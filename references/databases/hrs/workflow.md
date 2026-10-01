# HRS 变量定义标准流程

版本日期：2026-09-26

适用范围：通过 dbCodeBook 的 Full HRS 原始库入口发现候选、裁决口径、下载 raw、编写正式 R，并完成正式成果与机器闭环。

## 1. 先锁定正式产品

正式页面由外部配置解析，必须为 `/home/hrs/`，页面数据库类型必须为 `RAW_HRS`。开始探索时同时确认登录状态、页面产品、可用时期和一次无写入目录读取成功。若进入 RAND HRS 或 Harmonized HRS，停止并纠正路由，不沿用其下载清单。

## 2. 候选发现与来源裁决

1. 在 Full HRS 页面按完整来源身份检索，记录 `Base_Variable`、`File`、Label、各时期实际变量名、对象层级和覆盖期。
2. 优先选择能直接支持主题概念的官方原始/跨波次文件：稳定信息通常来自 Tracker，时变回答来自 Core，地区与城乡来自 Cross-Wave Geographic。
3. 同名变量跨 Core、Exit、Internet Survey 等文件时，按 `Variable (File)` 排除错误对象。
4. RAND HRS 或 Harmonized HRS 仅可作为辅助映射证据；所有正式 raw 必须回到 Full HRS 页面与官方原始代码本核实。
5. 文件的最新时期不一致时明确记录结构性缺失，不得向前或向后填补。

从第一次网页操作起同步维护 `探索记录.md` 与 schema v7 `definition_search_record.json`。网页尚未实际读取或结果只来自本地代码本时，必须写明限制。

## 3. 下载与恢复

1. 下载前固定完整变量身份、时期、别名、对象、分析单位和预期文件组。
2. 用[固定选择入口](../../rules/stages/02-download.md#固定选择与别名输入)在 Full HRS 页面输入已定来源和别名，再按本节查看预览、文件分组、header 与记录数。
3. 使用公共下载准备与命名流程；最终下载按钮只触发一次。
4. 下载包经 transaction、ZIP 成员、raw header、codebook、别名和变量全集验证后才能进入正式目录。
5. 变量、时期、来源文件或别名发生变化时重新形成完整清单；不从旧包拼接正式 raw。

## 4. 正式 R 与分析单位

- raw 保持网站下载原貌，不改列名、不预先转成长表。
- 以字符型 `HHID`、`PN` 为个人键；若实际包提供平台 `ID`，先核对含义再使用。
- Tracker 波次变量通过显式 mapping 转为个人-时期长表；不得从列位置猜测年份。
- Core 与 Geographic 按实际个人键和时期连接；每个时期映射必须列出原始变量、来源文件与定义变量。
- 稳定 Tracker 变量按个人键合并并在各时期重复，笔记说明其稳定变量身份。
- 公开代码不得依赖本机绝对路径、Skill 内部材料路径或未公开对象。

## 5. HRS 专项验收

- 页面与下载包确为 Full HRS 原始库，`db_type=RAW_HRS`。
- 所选变量的完整 `Variable (File)` 身份与网页、raw header、codebook 一致。
- `HHID`、`PN` 字符身份和前导零未丢失，个人-时期键符合声明。
- Tracker、Core、Geographic 的时期映射完整，未混入 Exit、配偶或 household 变量。
- 结构性缺失、特殊缺失、分类标签和构造规则逐变量可追溯。
- 每个分析变量均能回到网页选择、官方材料、raw 列和正式 R。

生成器、恢复工具和输出检查器只有在 HRS fixture 与一次真实 Full HRS 主题通过后才算完成适配；其它数据库回归通过不能替代 HRS 验收。
