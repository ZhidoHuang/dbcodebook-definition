# 定义规则材料索引

版本日期：2026-09-09

本文件只回答“某类要求应该去哪里找、以后应该写到哪里”，不新增、不复制具体规则。遇到同一要求出现在两份材料中时，应把完整条文保留在唯一负责该事项的文件，其他文件只保留引用，不能按文件日期自行挑一版执行。

## 正式规则

| 材料 | 唯一职责 | 不负责 |
| --- | --- | --- |
| [common-materials.md](common-materials.md) | 历史规则入口，指向各环节的唯一条文 | 不复制细则或主流程 |
| [stages/](stages/01-source-plan.md) | 八个环节各自的执行、验收、范例和失败返回范围；按 validation 表读取对应文件 | 其他环节的完整规则、数据库专门事实 |
| [evidence-and-literature.md](evidence-and-literature.md) | 权威材料使用、文献支持与方法依据 | 主题裁决、下载操作 |
| [review-roles.md](review-roles.md) | 只读角色生命周期与模型配置 | 代替各环节的具体验收标准 |
| [CHARLS workflow](../databases/charls/workflow.md) | CHARLS 特有的网页探索、年份、来源身份、选择与下载、特殊编码及输出事实 | 重新定义跨数据库命名、文案、函数或网站发布操作 |
| [ELSA workflow](../databases/elsa/workflow.md) | ELSA 特有的 `Variable (File)`、Wave、文件族、选择与恢复、负值和分析单位 | 复制 CHARLS 规则或另写一套共同文案和代码规范 |
| [write-boundaries.md](write-boundaries.md) | 任务能写什么、不能改什么、来源缺口怎样停止，以及网站发布任务的唯一操作规则 | 变量怎样定义、文案怎样写、何时需要独立验收 |
| [validation.md](validation.md) | 唯一环节顺序、修正后的复核范围、独立验收触发条件和状态含义 | 网站控件操作、数据库特有事实、主题公式 |
| [execution-report.md](execution-report.md) | 主题执行过程、环节耗时、角色、模型、Bug 与异常的自动记录 | 主题定义、读者文案和网站正文 |

## 数据库事实与配置

| 材料 | 唯一职责 | 不负责 |
| --- | --- | --- |
| [CHARLS profile](../databases/charls/profile.md) | CHARLS 稳定入口、身份结构和数据库级核验事实 | 流程步骤、主题定义和主题经验 |
| [ELSA profile](../databases/elsa/profile.md) | ELSA 稳定身份、文件族、Wave、分析单位和编码边界 | 流程步骤和主题裁决 |

## 记录模板

下面这些文件只规定本次任务要记录哪些事实，不是新的规则来源。填写时必须依据上面的正式规则和本次真实探索，不能从模板占位文字反推研究口径。

| 材料 | 用途 |
| --- | --- |
| [exploration-record.md](../../templates/exploration-record.md) | 从第一次探索开始，用大白话按时间记录做了什么、看到了什么、说明什么和下一步 |
| [definition-search-record.json](../../templates/definition-search-record.json) | 保存与同一次探索对应的结构化来源、证据、别名、候选和定义方案，供机器对账 |
| [reader-copy.md](../../templates/reader-copy.md) | 摘要、Criteria、小book与参考说明的可编辑输入 |
| [questionnaire-copy.md](../../templates/questionnaire-copy.md) | 按时期、题文、适用对象与选项填写问卷的范例 |
| [public-r-dictionary.R](../../templates/public-r-dictionary.R) | 正式变量对照表的可执行范例 |
| [change-impact.md](../../templates/change-impact.md) | 说明如何填写机器生成的变更影响检查表；不代替公共文案和生成规则 |

## 新要求怎样归位

1. 多个数据库都适用的代码、命名或读者材料要求，写入负责该事项的环节文件，公共入口只链接。
2. 只与某个数据库的网页、身份、周期、文件或编码有关，写入该数据库标准流程；稳定事实写入该数据库 profile。
3. 任务权限、网站发布和源端保护，写入写入边界规则。
4. 是否需要独立验收、机器闭环和状态含义，写入风险触发验收规则。
5. 执行环节、耗时、Bug 和异常怎样记录，写入执行报告规则。
6. 主题自身的来源、公式、结果、例外和用户裁决，只留在主题成果与过程证据，不回填公共规则。
7. 模板只在正式规则已经确定需要记录某项事实后增加对应字段，不在模板里另写判断标准。

每次整理规则时都要检查：是否已有唯一负责文件、是否只是本主题个例、是否造成两份完整条文并存。若答案不清楚，先停止新增条文，回到本索引确定归属。
