# 5. 成果生成

## 1. 准备、运行与交接

本步stage_id为generate。输入为已通过预检及公开R复核的唯一正式脚本、当前raw、定稿文案和变更影响；只读所选数据库差异说明中与本次生成有关的接口和支持范围。保持已经裁决的定义，不在生成时重新研究或改写文案。

先按下方“文案读取与展示”接入输入、确认数据库参数。新库首次接入或修改公共生成接口时，先在过程目录用覆盖实际时期、身份和结果类型的小样本及定稿文案，调用同一个公共生成器，确认笔记、定义表、图表和QA都能完整产出，再运行全量。样本不替换正式raw或成果，不另写业务算法；已有适用的完整生成证据时沿用，不要求每个普通主题重复。小样本只验证生成衔接，全量结果仍按第6步验证。

在Skill根目录运行：

```powershell
./scripts/run_r_definition.ps1 -WorkDir $Formal -Script $RFile -LogPrefix $LogPrefix -ProcessDir $Process -Config $Config -Database $Database
```

从头运行同一正式脚本，不另建第二份脚本或手改产物。检查退出码和唯一最终日志。公共生成器在生成前比较实际文案输入，生成后自动提取摘要、问卷、Criteria、小book和参考说明核对文字一致性，不另做一轮人工全文比对。文本不一致不交付，需改字先回文案。来源卡由正式来源关系生成。文字一致不代表定义正确；计算、数据及整套产物的完整性由下一步结果验证负责。

通过后将当前产物和日志交[结果验证](06-results.md)。失败只返回出错的输入、代码或生成部分，不重做无关探索下载。下列接口、安装定位和样式用于接入或排查相应问题，不作为额外执行阶段。

正式目录保留本次下载包及原始 CSV、定稿文案、唯一正式 R、四张工作簿、QA、definition/detail HTML、完整笔记和唯一成功日志；过程记录放过程目录。不另生成 README、重复报告或定义表中转文件。正式 runner 默认限时 30 分钟，失败或超时后先查明原因，不自动重跑。

## 文案读取与展示

第3步规定了独立“定义依据”及“题组 → 时期”问卷结构。使用这些结构前，确认文案读取器保留定义依据的全部内容，生成器为每个题组分别生成时期标签，问卷检查按题组和时期定位证据。旧的全局时期结构通过回归不证明新结构可用；不得把成分名称当作时期、静默丢弃定义依据，或为了适配旧程序把文稿改回整篇合并时期。同一时期的题号在多个题组重复时，在对应questionnaire_evidence中用questionnaire_module填写文案题组名称；无歧义的旧记录可省略。不能由检查器猜选其中一组。当前已测范围见[验收矩阵](../../../tests/acceptance-matrix.md)。

后台调用 `copy <- read_definition_copy(analysis_vars)`，把criteria、criteria_intro、summary_entry、summary_insight_items、reference_lines、summary_selection、definition_basis传给现有生成器。新文案从首个变量直接开始，criteria_intro为空，不生成定义表前的共同说明；该参数仅保留旧稿兼容。没有参考资料时reference_lines为空，不生成空标题。definition_data$Criteria、定义HTML和笔记使用同份文案，不能另写一份或覆盖copy$summary_selection。

新主题或本次修改问卷展示时，按第3步选定需要展示的题组，写入文案并删除R中的重复文字；不需要展示时，summary_selection为空，不生成空问卷块。旧主题仅改其它内容、问卷未变时允许沿用既有R问卷。仅核实题意、未取得完整原题且确需展示时，保留已明确标注的题意概括和原因说明。内容要求和输入格式见[文案写作](03-copy.md)，模板与实例见[reader-copy](../../../templates/reader-copy.md)。

没有问卷展示时，目录衔接句由生成器改为“本主题在数据中对应 N 个原始变量，可从 dbCodeBook 的目录［目录路径］进入检索和查看。”有问卷时保持下述原句，数量和链接样式不变。

## 数据库适配边界

ELSA调用公共render_definition_bundle并设置database="ELSA"、cycle_order为已核实时期顺序，输入保留ID/idauniq/Wave。Full HRS用database="HRS"及本轮核实年份，保留字符型HHID/PN和year；不在主题复制渲染器。顺序取自证据，不从非缺失行反推；概览和文件前缀随参数生成。

SHARE、KLoSA与KNHANES的生成接口须显式指定database及cycle_order，身份与文件层级按[SHARE流程](../../databases/share/workflow.md)、[KLoSA流程](../../databases/klosa/workflow.md)、[KNHANES流程](../../databases/knhanes/workflow.md)执行。SHARE普通Wave1–9人口学已完成真实完整流程；KNHANES的Core data人口学21期已完成真实完整流程，其它来源和主题不据此视为通过；KLoSA仍按其workflow所列边界。KLoSA还须显式传入与来源方案相同的language，目录入口沿用该语言。程序可运行不代表所有来源或主题已验收。

CHNS同样须显式指定database及cycle_order；静态来源已由网站并入主表时直接使用；仍为独立文件时，生成前在公开R工作对象中接入，生成器只检查个人—年身份并投影WAVE为本地年份。分文件完整检查与当前候选验收边界见[CHNS接口](../../databases/chns/profile.md)。

summary_source提供已核实的目录路径，生成器从正式来源清单自动取得原始变量数量，衔接为：“以上问卷问题在数据中对应 N 个原始变量，可从 dbCodeBook 的目录［目录路径］进入检索和查看。”数量取raw_vars在raw_codebook中的完整来源身份，按数据库、文件及原变量名去重；包含必要前置题，同一来源跨期不重复计数，不统计最终变量、下载别名数量或网页搜索结果总数。来源身份缺失或无法对应时返回来源清单修正，不省略数量或猜数。

目录只写上述衔接句，数字用普通正文，不加粗或单独强调；目录链接保留现有斜体样式。不另加“本次使用”“还可查找”等解释。优先传一个已核实的主题目录路径；确需多个入口时可传路径向量，不重复总数。旧note、lines输入保持兼容，新主题及本次更新不为目录另写说明段。旧variable_count参数仅作兼容核对，与自动统计不一致时报错。

下面仅示范参数，不替代完整业务定义及正式生成调用：

```r
# 名称逐项对应 analysis_vars；含义与分组取自本主题已核对的定义。
summary_meanings <- c(defined_a = "第一项定义变量的具体含义", defined_b = "第二项定义变量的具体含义")
summary_groups <- c(defined_a = "研究概念一", defined_b = "研究概念二")
# 按需传给 render_definition_bundle：
# summary_meanings = summary_meanings, summary_groups = summary_groups,
# summary_selection = copy$summary_selection,
# definition_basis = copy$definition_basis,
# hist_mode = "linear"（默认）或有依据的 "zero_plus_log"
# hist_binwidth：仅在正式业务分组宽度已明确时传入；
# 未明确时省略，使用自动分箱。宽度已确定为1时才传入1；
# 不同变量使用不同宽度时，传按变量命名的向量。
```

CHARLS 五期是当前共同覆盖契约，不能依据本主题恰好出现的年份缩减。Full HRS 的年份覆盖由本轮实际选择的 Tracker、Core 与跨波次文件共同确定；地理等文件落后于 Tracker 时按结构性缺失处理，不把 RAND Wave 契约套到原始库。升级新波次时先核实正式来源，再同步 renderer 契约与对应测试，运行完整回归后发布；ELSA 与 HRS 的已测范围以 tests/acceptance-matrix.md 为准，不据此宣称其它文件族、产品路线或未来波次均已验收。

## 正式输出与图表

- `### 1-提取变量` 必须包含非空、可直接粘贴到网站批量输入框的 `网站完整原始变量身份=下载别名` 列表和一个 `Go to 提取变量` 按钮；左右两侧来源、括号保留和逐项格式按 [来源关系](02-download.md#先按出现位置区分三种变量关系) 执行。
- detail/组分概览按真实研究概念分组，每组先显示 `source variables`，再显示 `defined variables`。分组名称使用普通读者能理解的业务概念；source variable 的 Easy.label 说明原题，defined variable 的显示标签说明分析变量。正式 R 显式设置 factor levels；未匹配变量进入 `Other / check` 并触发 warning 或 QA。
- detail 片段自行提供 `## 定义的组分概览` 和 `## 定义的组分详情`；笔记拼装器不得再额外添加“定义的组分详情”。最终笔记各保留一个标题，不能形成“详情 → 概览 → 详情”的重复结构。
- 周期热图文字始终使用深色。周期不超过 6 个时单行显示；超过 6 个时按原顺序分两行，两行仍溢出才使用横向滑动与箭头。
- 连续变量默认自动选择自然刻度，使柱数约为 12–16 根；横轴显示分组起点，完整区间留在悬停提示中。
- 非负金额正值跨度很大、线性图会挤压主要分布时，直接使用 `hist_mode = "zero_plus_log"`：`0` 单独展示，正值按对数分档。存在负值、`0` 含义特殊或口径不明确时才需裁决。
- 只有正式业务分组宽度已经明确时才设置 `hist_binwidth`；不同变量需要不同宽度时使用命名向量。


保持完整生成调用；四份write.xlsx在唯一 `# 输出` 前，后台QA和渲染在后，写法见[字典模板](../../../templates/public-r-dictionary.R)。四份文件依次命名为 `db_<主题>.xlsx`、`codebook_<主题>.xlsx`、`analysis_db_<主题>.xlsx`、`analysis_codebook_<主题>.xlsx`，只替换主题部分，不调整前缀顺序。生成器对公开代码以空编号标题结束发出警告。

定义笔记公开R不显示raw获取提示；`# raw_data.csv从网站dbcodebook.cn对应笔记，go to提取变量获得`只由公众号SVG/富文本工具注入。宣传材料不作定义措辞底稿；定义事实变化后，由独立宣传任务评估更新。用户材料不显示工具、版本史、验收或过程证据。

## 安装定位与独立运行

主题 R 无论通过正式 runner 运行，还是在 RStudio 中直接全选运行，都必须继续生成完整笔记。正式 runner 会把当前 Skill 根目录写入环境变量 `DBCODEBOOK_DEFINITION_SKILL_ROOT`；直接全选时，R 自动从当前 `CODEX_HOME` 或用户目录下的 `.codex/skills/dbcodebook-definition` 查找已经安装的 Skill。不按成果目录层级寻找 `_工具`，也不写死作者电脑路径：

```r
skill_root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
if (!nzchar(skill_root)) {
  codex_home <- Sys.getenv("CODEX_HOME")
  if (!nzchar(codex_home)) {
    user_home <- Sys.getenv("USERPROFILE")
    if (!nzchar(user_home)) user_home <- path.expand("~")
    codex_home <- file.path(user_home, ".codex")
  }
  skill_root <- file.path(codex_home, "skills", "dbcodebook-definition")
}
helper_files <- file.path(
  skill_root,
  "scripts",
  c("summary_fact_helpers.R", "render_definition_bundle.R")
)
if (!all(file.exists(helper_files))) {
  stop("未找到 dbcodebook-definition Skill。请先安装该 Skill。")
}
eval(parse(
  file = helper_files[1],
  encoding = "UTF-8"
))
eval(parse(
  file = helper_files[2],
  encoding = "UTF-8"
))
```

这一段属于正式输出机制，不放进公开 R。既有主题在下次实质修改或重新生成时改用该入口；在完成迁移前，不提前删除仍被旧主题引用的兼容文件。正式检查必须拒绝只能由 runner 运行、无法在 RStudio 中全选生成完整笔记的脚本。

## 展示标准

公共组件负责下列样式，主题只提供文案和语义标记，不复制CSS。文案输入格式见[文案写作](03-copy.md)，本节只规定生成样式。

| 内容 | 展示要求 |
| --- | --- |
| 摘要结果、共享维度及数量 | 保留名称的中文双引号；只有引号内概念和数字使用主题色，不染整句、连接词及标点。核对实际名称与标记，不用固定高亮数验收 |
| 问卷主题标签 | 一个题组也显示话题标签，不省略。各模块的名称（如握力、视力，网站称 questionnaire-topic）使用普通文本容器，继承正文字号、正常字重，不使用 h1–h6 或标题样式。保留 data-questionnaire-module-title 标记、模块分组和各自的时期标签。文案中的三级题组标题仍用于结构解析，不代表生成后采用标题外观；文章标题、问卷内的题目标题不受此要求影响 |
| 题目分组与选项引用 | 按文案显示题目分组标题，包括上游／原始问题及实际模块名称；共用选项只展开一次并保留适用题号说明。各题跳转保留在对应题目下，整组检查点保留在组末；不因选项相同而复制跳转，不把跳转移到首题或设计说明中 |
| 时期正文与设计说明 | 时期内容统一为正文0.92em；问卷设计首段顶格，其后自然段首行缩进。说明中引号内核心问题用主题色，引号及其它文字普通色 |
| 原题题块 | 分组标题主题色加粗，题目标题（原问卷变量名或题号）加粗且不用行内代码样式；标题和问题顶格。中文题干不加引号；题目标题、题干、填写及访员说明继承正文颜色 |
| 选项与跳转 | 逐行缩进；选项独立0.8em、#888888；题干后进入条件用全角括号，条件及跳转独立0.72em、正文深色。同一行选项与跳转为同级元素，不嵌套相乘字号，外层只管换行缩进 |
| 间距 | 时期首个分组标题无额外上间距；后续题组及相邻问题保留轻量间距 |
| Criteria | 结构、颜色和缩进由公共helper生成；仅多条判定共同依赖的跨期组成、适用对象或解释前提使用criteria_context()浅底背景，普通含义、清单、赋值及公式不加底色 |
| 小book | 正文外层14px；每条首句用数据库主题色，不加粗，解释用正文色。每条均显示编号，只有一条也显示；编号与正文分列，续行与正文起点对齐。不在子段重复缩放 |
| 其它 | dbCodeBook普通样式，完整目录使用目录标记；数字与量词使用不可断开容器，百分号紧贴数字；关系树保留前导空格和树线 |

问卷沿用 `summary_questionnaire_line()`。语义标记对应：设计问题为 `.summary-period-question[data-summary-period-question="true"]`；原题为 `.summary-question[data-summary-question="true"]`；进入条件为 `.summary-question-condition[data-summary-question-condition="true"]` 或结构化题块的 `[data-summary-question-detail-role="instruction"][data-summary-question-position="before"]`；选项为 `[data-summary-question-option="true"]` 或 `[data-summary-question-detail-role="option"]`；选项后跳转为 `[data-summary-question-instruction="true"]`。结构化题块使用 `.summary-questionnaire-line`。变量代码由成对反引号转换，不手写code标签。

### 时期分组与全文保留

`.raw-source-structure` 包含完整来源说明；按真实调查顺序建立 `.raw-source-period`，`data-label` 保存读者可见时期名，`.raw-source-period-label` 使用普通文本容器而非Markdown或HTML标题。

前端负责标签页及展开收起；主题不写按钮、隐藏逻辑、高度、边框或网站样式。无脚本、复制、打印和导出时，所有时期名与全文仍须存在。正文不靠删减来适应折叠。

摘要整节总述首段顶格，后续自然段由展示端缩进；问卷设计与小book按上表的专门规则。参考资料位于完整定义表之后、材料之前。定义表覆盖全部分析变量，与analysis_vars、analysis_db、analysis_codebook顺序相同，综合主题先组成变量后综合变量，不再生成摘要五列表。
