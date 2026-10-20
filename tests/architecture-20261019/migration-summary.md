# 迁移追踪索引

逐条完整记录见 [migration.jsonl](migration.jsonl)，字段说明见[设计](design.md#迁移追踪办法)。原行号对应本轮本地基线，不对应Git HEAD。每个原条文都保留原文；下表聚焦实际移动、路由调整和保留待决项。

## 全文件覆盖

| 原文件 | 原文单元 | 本轮状态 |
| --- | --- | --- |
| `SKILL.md` | 100 | retained=99；routing_updated=1 |
| `references/rules/common-materials.md` | 16 | retained=16 |
| `references/rules/evidence-and-literature.md` | 65 | retained=65 |
| `references/rules/execution-report.md` | 91 | retained=91 |
| `references/rules/index.md` | 64 | retained=61；routing_updated=3 |
| `references/rules/local-source-evidence.md` | 19 | retained=19 |
| `references/rules/review-roles.md` | 75 | retained=75 |
| `references/rules/scoped-tasks.md` | 97 | retained=97 |
| `references/rules/stages/01-source-plan.md` | 178 | retained=177；pending_semantics=1 |
| `references/rules/stages/02-download.md` | 157 | retained=156；routing_updated=1 |
| `references/rules/stages/03-copy.md` | 318 | retained=298；routing_updated=4；moved=13；pending_semantics=3 |
| `references/rules/stages/04-public-r.md` | 138 | retained=138 |
| `references/rules/stages/05-generate.md` | 153 | retained=152；routing_updated=1 |
| `references/rules/stages/06-results.md` | 49 | retained=45；moved=3；routing_updated=1 |
| `references/rules/stages/07-review.md` | 21 | retained=21 |
| `references/rules/stages/08-website.md` | 101 | retained=101 |
| `references/rules/validation.md` | 74 | retained=64；routing_updated=10 |
| `references/rules/write-boundaries.md` | 100 | retained=100 |
| `references/databases/charls/profile.md` | 24 | retained=24 |
| `references/databases/charls/workflow.md` | 28 | retained=28 |
| `references/databases/chns/profile.md` | 28 | retained=28 |
| `references/databases/elsa/profile.md` | 56 | retained=56 |
| `references/databases/elsa/workflow.md` | 29 | retained=28；routing_updated=1 |
| `references/databases/hrs/profile.md` | 42 | retained=42 |
| `references/databases/hrs/workflow.md` | 22 | retained=22 |
| `references/databases/klosa/profile.md` | 13 | retained=13 |
| `references/databases/klosa/workflow.md` | 19 | retained=19 |
| `references/databases/knhanes/profile.md` | 11 | retained=11 |
| `references/databases/knhanes/workflow.md` | 26 | retained=26 |
| `references/databases/mhas/profile.md` | 8 | retained=8 |
| `references/databases/mhas/workflow.md` | 15 | retained=15 |
| `references/databases/nhanes/profile.md` | 8 | retained=8 |
| `references/databases/nhanes/workflow.md` | 10 | retained=10 |
| `references/databases/share/profile.md` | 17 | retained=17 |
| `references/databases/share/workflow.md` | 24 | retained=24 |
| `templates/change-impact.md` | 14 | retained=14 |
| `templates/definition-search-record.json` | 234 | retained=234 |
| `templates/exploration-record.md` | 39 | retained=39 |
| `templates/public-r-dictionary.R` | 52 | retained=52 |
| `templates/questionnaire-copy.md` | 3 | retained=3 |
| `templates/reader-copy.md` | 164 | retained=164 |

## 移动、路由与待决条目

| 原位置 | 原条文摘要 | 新归属 | 状态与原因 |
| --- | --- | --- |
| `SKILL.md:L57` | ／ 进入某一环节 ／ 读取本环节及有关数据库差异；按条件进入引用，不顺次通读全部规则 ／ | [SKILL.md](../../SKILL.md) 第73行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/index.md:L28` | ／ 01-source-plan ／ 用户约束与待探索问题 → 双路探索、主线程合并方案及来源清单 ／ 下载控件、公开代码、文案 ／ | [references/rules/index.md](../../references/rules/index.md) 第28行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/index.md:L29` | ／ 02-download ／ 方案与别名 → 本次已校验raw/codebook；下载失败找回也在此 ／ 发布、R实现和展示实现 ／ | [references/rules/index.md](../../references/rules/index.md) 第29行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/index.md:L33` | ／ 06-results ／ 当前产物 → 数据及显示一致性证据 ／ 重写文案、重新探索 ／ | [references/rules/index.md](../../references/rules/index.md) 第33行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/01-source-plan.md:L199` | ／ 从已完成模块中选取常用分析变量，组成“健康行为”等集合 ／ 被选入的变量使用 `A_`。这类变量一般覆盖完整调查周期，适合作为通用协变量。`A_` 专指常用分析 | [references/rules/stages/01-source-plan.md](../../references/rules/stages/01-source-plan.md) 第205行 | pending_semantics：原文保留；第一轮提出的语义问题本批不裁决 |
| `references/rules/stages/02-download.md:L213` | - 下载后、编写正式 R 前，完成［来源重叠核对］(06-results.md#来源重叠核对)中影响来源选择或合并的实际数据比较；未解释的差异先返回来源方案。 | [references/rules/stages/02-download.md](../../references/rules/stages/02-download.md) 第220行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/03-copy.md:L5` | - 完整写作前读取这两份文档；局部修改时读取两份文档中对应的部分。 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第5行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/03-copy.md:L9` | 按下表顺序填写`文案.md`。有条件的部分按实际情况写，不为凑齐栏目增加内容。 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第37行 | routing_updated：按用户要求区分编写顺序与展示顺序；组成及栏目条件不变 |
| `references/rules/stages/03-copy.md:L53` | ### 写作前先判断两件事 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第81行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/03-copy.md:L55` | 1. **判断结果关系。** 区分共同测量同一概念、多个结果并列，以及多个成分构成综合结果。    人口学的多个并列概念不因此成为综合指标；不能只按题目数量判断。  | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第83行 | routing_updated：按用户要求将关系确认移到来源阶段；文案复核，原并列/共同测量/综合区别原意保留 |
| `references/rules/stages/03-copy.md:L180` | 网站负责以下显示。根节点为第一级，第一层分支为第二级。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第242行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L182` | ／ 对象 ／ 颜色 ／ 大小或行距 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第244行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L184` | ／ 普通文字 ／ 前两级正文色；第三级起辅助灰 ／ 前两级基准字号；第三级起为基准的 0.85 倍 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第246行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L185` | ／ 最终变量名称 ／ 各层均为数据库主题色，优先于深层变浅 ／ 随所在行正文字号 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第247行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L186` | ／ meta ／ 各层均为辅助灰 ／ 所在行正文字号的 0.85 倍 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第248行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L187` | ／ 树线 ／ 各层均为正文色 ／ 第二级主干为基准字号；第三级及更深的分支和延续竖线为基准的 0.85 倍 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第249行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L188` | ／ 文字中的箭头 ／ 各层均为正文色 ／ 随所在行正文字号 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第250行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L189` | ／ 行距 ／ — ／ 前两级基准行距；第三级起为基准的 0.85 倍 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第251行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L191` | - 更深层不逐层累乘字号或行距，也不继续变浅。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第253行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L192` | - 外围主干按自身层级显示，不随所在行缩小。缩进和连接位置保持不变。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第254行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L193` | - 网站须核对实际行高，避免树线或 meta 撑大行距。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第255行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L194` | - 标签复用问卷的左侧时期标签，不用顶部话题标签。树内保留标题和必要说明。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第256行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L195` | - 未修改的旧树没有标签或语义标记时，仍可按原样显示；不将此兼容方式作为新稿模板。 | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第257行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/03-copy.md:L280` |    - 一个成分发生变化，不要求其他成分一起拆分。 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第300行 | pending_semantics：原文保留；第一轮提出的语义问题本批不裁决 |
| `references/rules/stages/03-copy.md:L377` |    ／ 实际处理 ／ 写什么 ／    ／ --- ／ --- ／    ／ 原有含义、分类或数值不变 ／ 说明保留什么 ／    ／ 重新分类 ／ 写清哪些回答 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第397行 | pending_semantics：原文保留；第一轮提出的语义问题本批不裁决 |
| `references/rules/stages/03-copy.md:L390` |    - 下载别名及其编程用的命名规律、后缀通常留在来源映射和 R 中。只有解释当前方法确有需要时，才在定义逻辑中提及。 | [references/rules/stages/03-copy.md](../../references/rules/stages/03-copy.md) 第410行 | pending_semantics：原文保留；第一轮提出的语义问题本批不裁决 |
| `references/rules/stages/05-generate.md:L222` | ／ 关系树 ／ 保留前导空格、树线和语义标记；由网站按［关系树规则］(03-copy.md#关系树)显示，不输出固定颜色 ／ | [references/rules/stages/05-generate.md](../../references/rules/stages/05-generate.md) 第222行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/06-results.md:L55` | - 多个来源在相同时期覆盖同一研究概念，且方案需要将它们视为等值替代或按优先级合并时，比较该时期对应记录的非空值与缺失模式，记录总行数、双方非空可比人数、双方均缺失 | [references/rules/stages/02-download.md](../../references/rules/stages/02-download.md) 第213行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/06-results.md:L56` | - 首次比较在下载后、正式 R 前完成；本步沿用仍有效的证据，核对实现是否遵循方案。 | [references/rules/stages/02-download.md](../../references/rules/stages/02-download.md) 第214行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/stages/06-results.md:L57` | - 结果符合已定方案时继续；发现方案未解释的差异时返回来源环节调查，不用合并优先级掩盖问题，也不因已解释的差异固定要求用户重新裁决。 | [references/rules/stages/02-download.md](../../references/rules/stages/02-download.md) 第215行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/stages/06-results.md:L58` | - 不同对象、不同含义的来源不作等值比较。 | [references/rules/stages/02-download.md](../../references/rules/stages/02-download.md) 第216行 | moved：完整条文移动到实际执行/显示负责阶段；旧入口保留引用 |
| `references/rules/validation.md:L13` | ／ 顺序 ／ 当前步骤及唯一规则 ／ 通过后交接 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第17行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L14` | ／ --- ／ --- ／ --- ／ | [references/rules/validation.md](../../references/rules/validation.md) 第18行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L15` | ／ 1 ／ ［选题与来源方案］(stages/01-source-plan.md) ／ 双路独立结果、主线程合并后的来源、定义、路径及候选取舍 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第19行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L16` | ／ 2 ／ ［选择与下载］(stages/02-download.md) ／ 本次完整原始包、raw/codebook 与真实取值 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第20行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L17` | ／ 3 ／ ［纯文案］(stages/03-copy.md) ／ 已定稿文案及已核对的变更影响 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第21行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L18` | ／ 4 ／ ［公开 R］(stages/04-public-r.md) ／ 预检及独立实现复核通过、符合当前合并方案的正式源 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第22行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L19` | ／ 5 ／ ［成果生成］(stages/05-generate.md) ／ 当前成果及明确退出码的运行日志 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第23行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L20` | ／ 6 ／ ［结果验证］(stages/06-results.md) ／ 当前版本、明确检查范围的结果证据 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第24行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L21` | ／ 7 ／ ［成品交接］(stages/07-review.md) ／ 执行结论汇总、生成一致性及当前发布许可 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第25行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |
| `references/rules/validation.md:L22` | ／ 8 ／ ［网站同步］(stages/08-website.md) ／ 提交结果、实际耗时和待用户检查状态 ／ | [references/rules/validation.md](../../references/rules/validation.md) 第26行 | routing_updated：人工对照：调整读取、归属或交接，原输入/输出/条件保留；不改业务算法与检查标准 |

| `references/databases/elsa/workflow.md:L38` | - 部分 Wave 来源重叠时，按［公共来源重叠核对］(../../rules/stages/06-results.md#来源重叠核对)处理，不另设一套暂停条件。 | [references/databases/elsa/workflow.md](../../references/databases/elsa/workflow.md) 第38行 | routing_updated：原条件不变；直接指向首次来源核对负责阶段，消除多余跳转 |

## 新增内容

新增读取表、优先级表、交接说明及新增标题见 [additions.jsonl](additions.jsonl)。它们以本轮六项架构要求为依据，不增加业务算法、阈值、下载或复核次数。

## 验收索引

- [原文覆盖与生产脚本哈希](coverage.json)
- [三类真实案例的逐文件读取范围与统计](path-comparison.json)
- [文件及标题锚点检查](link-check.json)
- [路径推演、回归结果与未覆盖范围](verification.md)
