# HRS 数据库差异说明

通用流程按[公共规则](../../rules/validation.md)执行。本页只补充 Full HRS 的来源、下载、R及验证差异，产品身份、文件族和分析单位见 [profile](profile.md)。

## 来源探索

- 正式入口为 `/home/hrs/`，页面数据库类型为 `RAW_HRS`；RAND HRS、Harmonized HRS 不是这一路线。
- 记录 `Base_Variable`、`File`、Label、各时期实际变量名及对象层级。稳定信息通常来自 Tracker，时变回答来自 Core，地区与城乡来自 Cross-Wave Geographic；仍按主题需要核实，不把这些例子当固定清单。
- RAND HRS 或 Harmonized HRS 仅作明确标注的辅助方法与映射证据，正式来源回到 Full HRS 页面和官方原始代码本核实。
- Core、Exit、Internet Survey、配偶或 household 来源分清对象。文件最新时期不一致时记录实际覆盖，不用其它时期值擅自补齐。

## 选择与下载

按[第2步](../../rules/stages/02-download.md)执行，数据库参数为 `hrs`。预览与包校验确认 Full HRS 产品身份、完整 `Variable (File)`、各期字段、实际文件分组及身份列，不套用 RAND/Harmonized 的下载清单。

## R 与生成

- 个人键 `HHID`、`PN` 按字符读取，保留前导零；平台 `ID` 如存在，先核对含义。
- Tracker 波次字段通过显式“变量—年份”映射转换为个人—时期工作表，原始下载文件不变。
- Core、Geographic 按实际个人键和时期连接；稳定 Tracker 信息按个人键接入各期，保留其稳定来源身份。
- 公共生成器使用 `database="HRS"` 和本次核实的 `cycle_order`，输入保留 `HHID`、`PN`、`year`。调用及公开代码要求按[第4步](../../rules/stages/04-public-r.md)和[第5步](../../rules/stages/05-generate.md)。

## 结果验证与支持范围

在[第6步](../../rules/stages/06-results.md)中核对 `RAW_HRS` 产品身份、完整 File、字符型个人键及前导零、个人—时期唯一性和显式时期映射，核实未误用不同对象的文件。

Full HRS 已有本地端到端验证，具体主题、时期及是否包含网站发布以[验收矩阵](../../../tests/acceptance-matrix.md)为准，不把其它数据库或合成测试当作本库生产证据。