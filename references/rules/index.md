# 定义规则材料索引

版本日期：2026-09-30

本文件只回答“某类要求应该去哪里找、以后应该写到哪里”，不新增、不复制具体规则。遇到同一要求出现在两份材料中时，应把完整条文保留在唯一负责该事项的文件，其他文件只保留引用，不能按文件日期自行挑一版执行。

## 正式规则

| 材料 | 唯一职责 | 不负责 |
| --- | --- | --- |
| [common-materials.md](common-materials.md) | 历史规则入口，指向各环节的唯一条文 | 不复制细则或主流程 |
| [stages/](stages/01-source-plan.md) | 八个环节各自的探索/明确执行/机械操作、交接和失败返回范围；按 validation 表读取对应文件 | 其他环节的完整规则、数据库专门事实 |
| [evidence-and-literature.md](evidence-and-literature.md) | 权威材料使用、文献支持与方法依据 | 主题裁决、下载操作 |
| [review-roles.md](review-roles.md) | 只读角色生命周期与模型配置 | 代替各环节的具体验收标准 |
| [CHARLS 差异说明](../databases/charls/workflow.md) | CHARLS 特有的网页探索、年份、来源身份、选择与下载、特殊编码及输出事实 | 重新定义跨数据库命名、文案、函数或网站发布操作 |
| [ELSA 差异说明](../databases/elsa/workflow.md) | ELSA 特有的 `Variable (File)`、Wave、文件族、选择与恢复、负值和分析单位 | 复制 CHARLS 规则或另写一套共同文案和代码规范 |
| [HRS 差异说明](../databases/hrs/workflow.md) | Full HRS 原始库的 Tracker、Core、Cross-Wave 文件、时期映射、选择和下载验收边界 | 把 RAND HRS/Harmonized HRS 当作正式 raw 或混用数据库身份 |
| [write-boundaries.md](write-boundaries.md) | 任务权限、来源缺口和共用浏览器会话 | 下载或发布的逐步操作、变量定义、独立验收触发 |
| [validation.md](validation.md) | 唯一环节顺序、修正后的复核范围、独立验收触发条件和状态含义 | 网站控件操作、数据库特有事实、主题公式 |
| [execution-report.md](execution-report.md) | 主题执行过程、环节耗时、角色、模型、Bug 与异常的自动记录 | 主题定义、读者文案和网站正文 |

## 环节之间的分工

| 文件 | 接收与完成 | 不在这里重复 |
| --- | --- | --- |
| 01-source-plan | 用户约束与待探索问题 → 双路探索、主线程合并方案及来源清单 | 下载控件、公开代码、文案 |
| 02-download | 方案与别名 → 本次已校验raw/codebook；下载失败找回也在此 | 发布、R实现和展示实现 |
| 03-copy | 方案与实际事实 → 完整文案及首稿快照 | 生成接口、CSS、网站操作 |
| 04-public-r | 方案与文案 → 实现、预检及实现复核 | 摘要写法、发布步骤 |
| 05-generate | 稳定源和文案 → 数据、笔记、附件；接口和展示由此负责 | 重新裁决研究事实 |
| 06-results | 当前产物 → 数据及显示一致性证据 | 重写文案、重新探索 |
| 07-review | 各步结论与当前产物 → 机械一致性检查及发布许可 | 重新安排全流程审核 |
| 08-website | 已授权成果及许可 → 单次同步结果 | 研究、写作、数据修复 |

validation负责何时返回或复核及状态含义；review-roles负责复核角色与证据交接；execution-report负责记录和耗时，不各自再规定一套主题操作。此表说明职责，不表示每份旧文件已经完成精简；整理进度留在维护记录。

## 数据库事实与配置

`databases/<数据库>/`只保存数据库事实、接口差异及验证范围，不另写完整流程。现有 `profile.md` 保存稳定事实，`workflow.md` 保存各环节如何使用这些差异；保留原文件名以兼容路由，CHNS沿用一份profile。公共流程要求由 stages、validation、write-boundaries 等负责，数据库文件只引用；`source-materials/<数据库>/`保存问卷、指南等原始材料，统一从[材料索引](../source-materials/材料索引.md)进入。[database-routing.json](../database-routing.json)指定各库规则和材料路径，程序读取同一份路由，不另维护材料位置。

| 材料 | 唯一职责 | 不负责 |
| --- | --- | --- |
| [CHARLS profile](../databases/charls/profile.md) | CHARLS 稳定入口、身份结构和数据库级核验事实 | 流程步骤、主题定义和主题经验 |
| [ELSA profile](../databases/elsa/profile.md) | ELSA 稳定身份、文件族、Wave、分析单位和编码边界 | 流程步骤和主题裁决 |
| [HRS profile](../databases/hrs/profile.md) | Full HRS 原始产品身份、文件族、变量命名、分析单位和时期边界 | RAND HRS/Harmonized HRS 事实、流程步骤和主题裁决 |

各库差异说明中的接口及验证范围见[SHARE](../databases/share/workflow.md)、[KLoSA](../databases/klosa/workflow.md)、[KNHANES](../databases/knhanes/workflow.md)及[CHNS](../databases/chns/profile.md)。CHNS十期人口学已完成真实下载、完整生成、独立复算及发布；其它来源层级和主题不据此视为通过。材料存在或接口测试通过，不代表真实主题已验收。

## 记录模板

下面的模板保存录入格式和可执行示例；内容取舍仍由对应环节决定。填写依据本次真实事实，不能从占位文字反推研究口径。

| 材料 | 用途 |
| --- | --- |
| [exploration-record.md](../../templates/exploration-record.md) | 从第一次探索开始，用大白话按时间记录做了什么、看到了什么、说明什么和下一步 |
| [definition-search-record.json](../../templates/definition-search-record.json) | 保存与同一次探索对应的结构化来源、证据、别名、候选和定义方案，供机器对账 |
| [reader-copy.md](../../templates/reader-copy.md) | 文案各部分的模板与实例；与03-copy顺序一致，不另设规则 |
| [questionnaire-copy.md](../../templates/questionnaire-copy.md) | 旧入口，指向问卷要求及reader-copy中的对应实例 |
| [public-r-dictionary.R](../../templates/public-r-dictionary.R) | 正式变量对照表的可执行范例 |
| [change-impact.md](../../templates/change-impact.md) | 说明如何填写机器生成的变更影响检查表；不代替公共文案和生成规则 |

## 新要求怎样归位

1. 多个数据库都适用的代码、命名或读者材料要求，写入负责该事项的环节文件，公共入口只链接。
2. 只与某个数据库的网页、身份、周期、文件或编码有关，写入该数据库标准流程；稳定事实写入该数据库 profile。
3. 任务权限、网站发布和源端保护，写入写入边界规则。
4. 是否需要独立验收、机器闭环和状态含义，写入风险触发验收规则。
5. 执行环节、耗时、Bug 和异常怎样记录，写入执行报告规则。
6. 主题自身的来源、公式、结果、例外和用户裁决，只留在主题成果与过程证据，不回填公共规则。
7. 文案的目的、内容和格式统一在03-copy；模板与实例集中在reader-copy，questionnaire-copy只保留跳转。其它模板不另写内容标准；显示样式和生成接口归第5步，机器验收与状态归validation。

每次整理规则时都要检查：是否已有唯一负责文件、是否只是本主题个例、是否造成两份完整条文并存。若答案不清楚，先停止新增条文，回到本索引确定归属。
