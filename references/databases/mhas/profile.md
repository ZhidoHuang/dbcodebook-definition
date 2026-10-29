# MHAS 数据库差异

- 原始库入口为 `/home/mhas/`，不与 Harmonized MHAS 混用。
- 字典用 `Base_Variable` 和 `File` 标识来源，各期实际变量名见对应 `_variable` 字段。使用固定来源读取入口。
- 当前接收范围如下。主题实际采用时期由来源方案确定，不能把文件的全部时期当成业务范围。

  | 文件 | 文件时期 | 可组合范围 |
  | --- | --- | --- |
  | `MHAS_SURVEY_CORE_RESPONDENT` | 2001、2003、2012、2015、2018、2021、2024 | 单独接收，或与 NOK、Mex-Cog 问卷文件共同接收 |
  | `MHAS_SURVEY_NEXT_OF_KIN` | 2003、2012、2015、2018、2021、2024 | 单独接收，或与 Core、Mex-Cog 问卷文件共同接收 |
  | `MHAS_MEXCOG_COGNITIVE_ASSESSMENT` | 2016、2021 | 单独接收，或与 Core、NOK、Mex-Cog Informant 共同接收 |
  | `MHAS_MEXCOG_INFORMANT_INTERVIEW` | 2016、2021 | 单独接收，或与 Core、NOK、Mex-Cog Cognitive 共同接收 |
  | `MHAS_ANCILLARY_ANTHROPOMETRICS_BIOMARKERS` | 2001、2003、2012、2016 | 单独接收，或与下列金属文件共同接收 |
  | `MHAS_ANCILLARY_HEAVY_METALS` | 2018 | 单独接收，或与上述体测及生物标志物文件共同接收 |

- 网站按文件导出 `raw_data_<文件>.csv`，保留各自原文件名，不复制或改成 `raw_data.csv`。上述四类问卷文件不与体测、生物标志物或金属文件混包。
- `ID` 是网站记录标识。Core个人—时期检查使用 `ID`、`Wave_id`，两列按字符读取。`ID` 包含时期和该期身份分量；逐行核对其与默认导出分量一致。Core不默认提供 `UNHHIDNP`，不能宣称这些ID已建立跨期同人对应。默认身份分量及来源定位列保留在工作表，不计作定义结果或重复选择。
- Core 行存在不代表完成访谈。本人、代理、已故封面与未访谈记录按本主题核实的问卷及状态字段处理，不能依据ADL空白推断身份。
- Ancillary同样保留字符型`ID`、`Wave_id`和实际默认身份组件。体测及生物标志物文件：2001年为`unhhid/ps3`，2003年为`cunicah/acthog/ent2`，2012、2016年为`cunicah/np`；金属文件2018年为`cunicah/np`。接收器逐行核对ID与该期组件。只保留实际存在的来源定位列，不要求补造`source_file/source_row`。
- 多文件检查分别核对每个物理文件及字典身份，再核对最终表是否来自这些文件的身份并集。导出和堆叠不证明跨期同人已连接。
- 其他模块、家庭或重复明细、跨模块及跨期桥接不在本次接入范围。需要时先核实对应来源和连接契约；不得直接套用Core身份规则。

## Core、Next-of-Kin 与 Mex-Cog 问卷文件接口

- `MHAS_SURVEY_NEXT_OF_KIN` 文件可单独接收或与 Core、Mex-Cog 问卷文件接收；不得与体测、生物标志物或金属文件混包。物理时期为 2003、2012、2015、2018、2021、2024。
- NOK 2003 身份为 `cunicah/acthog/ent2`；2012、2015、2021 为 `cunicah/np`；2018、2024 为 `UNHHIDNP`。逐期核验，不套用 Core 或建立跨模块桥接。
- Mex-Cog 两个文件的 2016 身份组件为小写 `cunicah/np`，2021 为大写 `CUNICAH/NP`。保留真实大小写、前导零及各列，不把同名大小写变体互换。Informant 的键指其报告的目标受访者，不是知情人本人。
- 采用 NOK、Mex-Cog 或显式 `mhas_analysis_scope` 时，最终表保留 `source_module,ID,Wave_id`；同号人物在不同文件仍为不同来源行。不得据这些键声称跨文件或跨期同人已连接。各文件实际默认身份列逐值保留。
- 来源记录必须声明 `mhas_analysis_scope`，键为实际文件模块名，值包含 `analysis_periods`（字符串数组）与 `result_variables`（结果列数组）。所有声明时期的原始行都须保留；其他物理时期只留在原始文件。各结果在其他模块必须为空。
- 接口合成测试不代表真实下载包已验收；真实文件身份、附带行和所选列可用时期仍需逐包核对。
