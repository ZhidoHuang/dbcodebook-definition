# ELSA 数据库 profile

版本日期：2026-08-14

适用范围：记录 ELSA 的稳定身份、文件族、分析单位、Wave、样本和编码边界。本文件不替代真实 dbCodeBook 页面、官方题目、`raw_codebook.csv` 或本轮裁决。

正式源：本文件是 Skill 仓库中的 ELSA profile；机器路径和网站域名由外部配置提供。

## 1. 基本身份

| 项目 | 稳定规则 |
| --- | --- |
| 数据库 | ELSA（English Longitudinal Study of Ageing） |
| dbCodeBook 页面 | 外部配置中的 `website.base_url + website.database_paths.elsa` |
| 主个人标识 | `idauniq`，跨 Wave 的个人入口 |
| 下载行键 | `ID`，通常表示个人-Wave记录 |
| household 标识 | 按 Wave 识别，例如 `idahhw10`、`idahhw11` 或 `hhidw*`，不能当稳定跨 Wave 家庭 ID |
| raw 来源身份 | `Variable (File)`，不得只用裸 `Variable` |

- ELSA raw header 通常为 `ID, idauniq, <selected variables...>`；不得套用 CHARLS 的 `id/year` 身份结构。
- 正式 db/analysis 使用 `ID, idauniq, Wave`。`Wave` 从 `ID` 解析，保留 `Wave 1`、`Wave 2`……文本；raw 不改写。
- 同一 `idauniq` 可跨 Wave 重复，这是纵向记录，不按 `idauniq` 去重。

## 2. `Variable (File)` 身份

- 候选、判重、页面选择、下载记录、mapping 和 QA 都使用 `Variable + File`。
- 同名 Variable 跨 File 不自动视为同一来源，不自动拼接，也不因覆盖更多就优先采用。
- 例如 `palevel (Core data)` 与 `palevel (Derived Variables)` 必须分别核对；Core 与 COVID 中的同名变量也必须拆开。
- `raw_codebook.csv` 同时保留 `Variable (File)` 的来源身份和 `newname` 的导出列身份；二者不可互相替代。

## 3. 文件族边界

| 文件族 | 主要边界 |
| --- | --- |
| Core data | 主纵向访谈入口；仍需核对适用对象、访谈结果和 copied/derived 身份 |
| Self-completion | 发放与回收机制不同，缺失不能直接解释为主访谈未回答 |
| Nurse data / health visit | 仅特定 Wave 和访视成功对象，不能用 Core 全体作分母 |
| Derived / IFS / Financial Derived | 官方或外部整理来源；需追溯公式、复制关系、Wave 和对象，不因“派生”自动采用 |
| Harmonised ELSA | 跨数据库协调口径，不等于原始 ELSA；只有明确选择 harmonised 路线时使用 |
| Wave 0 | HSE 前身或基线补充，题期与 ELSA Wave 1+ 不同，不自动拼入主线 |
| COVID-19 | 专题 Wave；与 Core 同名变量仍是独立来源 |
| Life History | 回顾性生命历程，不是常规当期测量 |
| End of Life | 已故样本的代理或末期访谈，记录对象与答题人可能不同 |
| HCAP Respondent / Informant | 受访者与知情人分开，不能因同一 `idauniq` 当作同一答题人 |
| Nutrition detail | 可能一人多行，先确认 detail key 和行级单位 |
| Pension Grid | 一人可有多条养老金记录，分析单位通常是 pension record |
| Index file | 用于 outcome、issued/productive 和跨 Wave 索引，不自动当主题测量值 |

## 4. 对象与重复记录

- “有该 Wave 记录”“属于 core member”“属于 partner”“来自 refreshment sample”“有可用权重”是不同判断。
- proxy、partner 回答、household 共享值、官方 copied value 和本人回答是不同证据层级；是否纳入取决于研究问题。
- Nutrition detail、Pension Grid、HCAP Informant、End of Life 和其它专题文件必须实际检查 `idauniq` 重复与附加 key。
- 不用 `distinct(idauniq, .keep_all = TRUE)` 处理一人多行；先定义每行代表什么以及聚合或保留规则。

## 5. 编码、Wave 与权重

- 负值编码按 `Variable (File)`、Wave 和官方 codebook 逐项解释；ELSA 没有可套用到全库的统一负值字典。
- 数值、日期、时长、频率、总分和权重在解释全部负值前不得进入计算。
- 波次覆盖、题目适用对象、refreshment sample 和权重用途是四件事，不能互相替代。
- 权重必须说明对象、Wave、横断面或纵向用途；权重选择属于研究口径裁决。
- 不把 CHARLS 的特殊码、前缀、题号或主题经验带入 ELSA。

## 6. 主题事实边界

- 具体 raw、变量名、公式、Wave 拼接、分类和缺失由本轮真实探索、官方材料、实际 raw、正式 R 和用户裁决确定。
- `探索记录.md` 用大白话同步保存真实发现与判断过程；`definition_search_record.json` 保存同一步骤的结构化来源身份和候选取舍；recover、来源重叠核对和 machine closure 保存机器证据。
- 单主题事实不回填 profile；只有用户确认的跨主题稳定规律才更新本文件。
