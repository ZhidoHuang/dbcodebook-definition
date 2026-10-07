# HRS 数据库 profile

版本日期：2026-09-26

适用范围：记录本 Skill 中 Full HRS 原始库的稳定身份、文件族、分析单位和时期边界。本文件不替代真实 dbCodeBook 页面、官方代码本、`raw_codebook.csv` 或本轮主题裁决。

## 1. 路线与产品身份

| 项目 | 稳定规则 |
| --- | --- |
| 正式数据库 | Full HRS 原始库 |
| dbCodeBook 路径 | `/home/hrs/` |
| 页面数据库类型 | `RAW_HRS` |
| 常用文件族 | Tracker、各波次 Core、Cross-Wave Geographic 等官方原始/跨波次文件 |
| 个人键 | 通常为字符型 `HHID` + `PN`；不得数值化后丢失前导零 |
| 稳定变量单位 | Tracker 为一人一行 |
| 时变变量单位 | 各波次 Core 或从 Tracker 宽表显式转换的个人-时期长表 |

- `/home/hrs/`、`/home/harmonized/randhrs/` 与 `/home/harmonized/hrs/` 是不同产品路线，不能互换来源、变量名、版本、下载记录或验收结论。
- 本 profile 只把 Full HRS 原始库作为正式数据源。RAND HRS 可用于追溯构造思路和原始字段映射，但必须标为辅助证据，并在 Full HRS 页面及官方原始代码本中重新核实。

## 2. 文件族与变量身份

- Tracker 提供跨期稳定信息和逐波次状态，常见字段包括 `BIRTHYR`、`BIRTHMO`、`GENDER`、`RACE`、`HISPANIC`、`SCHLYRS`、`DEGREE`、`USBORN`、`xAGE`、`xIWMONTH`、`xIWYEAR`、`xCOUPLE`。
- Core 原始变量的前缀和名称随波次变化；2004 年以后常见波次前缀为 `J` 至 `S`。必须保存网页显示的 `Base_Variable`、`File` 和各时期实际变量名，不能仅凭前缀推断。
- Cross-Wave Geographic 提供 `REGIONxx`、`REGIONB` 和不同年份版本的 `BEALEyyyy_xx`。地理文件的最新时期可能落后于 Tracker；这是结构性覆盖差异，不得用后续时期值填补。
- 同名变量可能出现在 Core、Exit、Internet Survey 等不同文件。正式选择必须使用完整的 `Variable (File)` 身份，不能只按变量 token 选择。

## 3. 时期与分析单位

- HRS 核心访谈年份不等于网站展示的所有年份。实际核心时期由所选 Tracker/Core 变量的非空时期列确定。
- 将 Tracker 宽表转换成长表时，必须使用显式的前缀—年份映射，并保留 `HHID`、`PN` 和时期列。
- 稳定变量可以按个人键合并到个人-时期长表，但笔记应说明其跨时期重复。
- Exit、配偶、家庭成员和 household 记录不是 respondent core 记录的同义替代，纳入前必须单独裁决对象和连接键。

## 4. 日期与缺失边界

- `BIRTHYR` 与 `BIRTHMO` 是出生年、月；Full HRS Tracker 不提供可直接解释为真实出生日的稳定“日”字段。
- 需要从出生年、月构造日期时，具体取日方法属于主题定义方案，不由本 profile 规定；构造日期不能称为原始记录的真实出生日。
- 原始文件的特殊缺失、合法值和标签按具体变量、文件和发布版本逐项核对；不得套用 RAND HRS、CHARLS 或 ELSA 的缺失规则。

## 5. 主题事实边界

- 具体变量、别名、公式、分类、时期覆盖和结构性缺失由本轮真实页面探索、实际下载、当前官方代码本、正式 R 和用户裁决确定。
- 单主题事实不回填 profile；只有经真实任务验证的跨主题稳定规律才更新本文件。
