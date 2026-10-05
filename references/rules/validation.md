# 执行顺序与复核条件

本文件决定什么时候前进、返回或增加复核。各环节负责具体质量标准；[review-roles](review-roles.md)负责角色交接，[成品交接](stages/07-review.md)负责发布许可，[execution-report](execution-report.md)负责如实记录。

## 1. 默认路径：执行任务机器闭环

研究问题按第1步双路探索，由主线程比较并合并；明确执行由执行者按规则做好，机械操作走固定入口。完整主题在R预检后保留一次独立实现复核，沿用角色名“公开 R 复核”，检查是否忠实于已确定方案及计算正确性，不重新完整探索来源。不另设固定文案审核。下方入口不替代必要的双路探索或R实现复核。

| 顺序 | 当前步骤及唯一规则 | 通过后交接 |
| --- | --- | --- |
| 1 | [选题与来源方案](stages/01-source-plan.md) | 双路独立结果、主线程合并后的来源、定义、路径及候选取舍 |
| 2 | [选择与下载](stages/02-download.md) | 本次完整原始包、raw/codebook 与真实取值 |
| 3 | [纯文案](stages/03-copy.md) | 已定稿文案及已核对的变更影响 |
| 4 | [公开 R](stages/04-public-r.md) | 预检及独立实现复核通过、符合当前合并方案的正式源 |
| 5 | [成果生成](stages/05-generate.md) | 当前成果及明确退出码的运行日志 |
| 6 | [结果验证](stages/06-results.md) | 当前版本、明确检查范围的结果证据 |
| 7 | [成品交接](stages/07-review.md) | 执行结论汇总、生成一致性及当前发布许可 |
| 8 | [网站同步](stages/08-website.md) | 提交结果、实际耗时和待用户检查状态 |

每步使用稳定输入，失败只返回出错环节或受影响上游。命令成功不等于内容通过，也不为每条命令创建审核角色。

### 修正后的复核范围

| 改动 | 返回与核对范围 |
| --- | --- |
| 来源或别名变化 | 按完整新清单重新下载、从头运行，更新受影响证据 |
| 计算逻辑变化 | 复核受影响实现及上下游，从头运行并验证结果 |
| 仅表达变化 | 改文案、重新生成并核对文字及结果未变，不重开探索下载或未变R复核 |
| 仅后台展示或附件变化 | 核对受影响成果与正文；后台若改变数据、来源、公式或影响不能证明，仍须针对性独立复核 |

修改任何绑定成果后，重新绑定当前文件并记录影响，旧发布许可失效。输入未变的合格结论可沿用；笔记改动读受影响段落及衔接，不重读无关材料。公开R绑定与角色复查按review-roles，读者结论保留及重新取得许可按第7步；当前失败或待处理结论不能被历史通过覆盖。

### 定义变更影响

新主题，或新增、删除、重命名变量、改变对象、周期、问法、组成或缺失处理时，正式R前运行 `check_definition_readability.py init-impact` 并完成 `definition_change_impact.json`。按[填写说明](../../templates/change-impact.md)记录真实变更范围、题组证据及未决问题，不逐栏评价写作质量，不事后根据成品补写。记录未完成、必要题文未进入文案或定义未决时不得生成。

只改表达时使用[局部文案更新入口](scoped-tasks.md#copy-update)，不写成定义事实变化；方案与R未变则保留原有效R复核。首次预检和R复核不等于每次改字都重做。

### 原始回答冲突

专项扫描仅在用户明确要求时执行，正常执行已发现的矛盾仍须处理。各变量按直接原始题目分别生成；未经用户裁决，不用筛选题优先、金额优先、补零、改缺失、删记录或其它方式强制一致。

在现有过程证据保存身份键、周期、题目与回答、来源组、冲突方向和最终保留/裁决结果，不能把派生关系或正式覆盖误写为原始冲突。读者陈述按[Criteria与小book](stages/03-copy.md#5-criteria每个变量怎样得到)的职责。能按直接来源生成时报告后继续；单个变量的生成规则不明、来源不明、重复计入或覆盖顺序未定时，按下述研究判断入口处理。

## 2. 独立验收仅有四个入口

本节只指默认R实现复核以外的额外验收：

| 触发情况 | 只复核什么 |
| --- | --- |
| 机器证据缺失、失败、矛盾或执行者不能解释差异 | 冲突字段及生成链 |
| 现有规则和用户裁决不能解决的研究判断 | 返回第1步针对具体问题双路调查、主线程合并；不替用户作尚未明确的研究取舍 |
| 公共核心机制高影响修改且现有测试不足 | 受影响机制及代表性回归 |
| 用户或主任务明确要求独立验收 | 指定范围 |

新主题、数据库、变量、编码、mapping或工具变化本身不自动增加验收。原始回答矛盾按上节处理；能按直接来源忠实生成则继续，不自动进入RESULT_REVIEW_REQUIRED。不按任务数量随机抽查，也不让额外验收重跑生产或重复已证明的文件、日志、目录及常规读取检查。

## 普通读者复核

仅用户要求，或执行者仍无法消除具体理解歧义时发起。角色只看普通读者视图，不查代码或重新调查。操作见[第7步](stages/07-review.md#按需普通读者复核)。未发起不补记录；一旦发起，未完成、未解决或过期输入仍阻止发布，不能忽略失败继续。

## 4. 状态与入账

- 默认：`GENERATED -> MACHINE_CHECK_PASS -> DELIVERY_CHECK -> PUBLISH_READY -> USER_REVIEW_PENDING -> COMPLETE`。
- 额外验收：`GENERATED -> MACHINE_CHECK_PASS/BLOCKED -> SENT_FOR_VALIDATION -> VALIDATION_PASS -> DELIVERY_CHECK -> PUBLISH_READY -> USER_REVIEW_PENDING -> COMPLETE`。
- machine closure登记机器报告及是否需额外验收；无额外验收写independent_validation_required=false，不另建过程卡。
- MACHINE_CHECK_PASS仅表示机器检查；PUBLISH_READY表示当前成果通过规定的机械检查且无阻断，可提交，不代表写作质量通过；USER_REVIEW_PENDING表示已同步待用户阅读；只有用户确认才为COMPLETE。报告的completed不等于用户已验收，不把这些状态记成同一时点。

## 5. 机器产物与写入入口

| 产物 | 状态或有效性 | 生成/验证命令 | 下游 |
| --- | --- | --- | --- |
| definition_change_impact.json | init-impact 创建CHANGE_SCOPE_RECORDED；填写实际变更范围与题组依据，再由check-impact验证，不填自评PASS | check_definition_readability.py init-impact / check-impact | 正式生成 |
| result_check.json | ok=true、scope=complete 且绑定当前文件 | check_definition_output.py --complete；默认位于 --process-dir | 成品交接初始化 |
| readability_audit.json | 新版由init自动绑定文件为ARTIFACTS_BOUND；check核验机械条件，不填自评PASS | check_definition_readability.py init / check | 当前发布许可 |
| reader_comprehension_review.json | 仅实际发起时要求完整独立结论 | init-reader 后填写实际结论，再 check | 已发起的读者复核不得忽略 |
| execution_report.json | running 到 completed / completed_with_issues / failed / stopped | execution_report.py init / stage-start / stage-finish / finish | 执行报告；不代替内容通过 |

变更范围记录实际事实与未决问题；交接绑定由程序生成。两者均不要求写作自评或修改状态来声称合格。历史记录按原版本验证，不改写历史结论。

结果检查失败时可用 `check_definition_readability.py preview --note <完整笔记路径>` 只读定位问题，不生成许可。不提供绕过数据、身份或来源失败的accept-known-issue通道。
