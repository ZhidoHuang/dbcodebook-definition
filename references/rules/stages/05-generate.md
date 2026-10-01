# 5. 成果生成

## 1. 准备、运行与交接

本步stage_id为generate。输入为已通过预检及公开R复核的唯一正式脚本、当前raw、定稿文案和变更影响；只读所选数据库workflow的正式输出部分。保持已经裁决的定义，不在生成时重新研究或改写文案。

先按下方“文案读取与展示”接入输入、确认数据库参数，再在Skill根目录运行：

```powershell
./scripts/run_r_definition.ps1 -WorkDir $Formal -Script $RFile -LogPrefix $LogPrefix -ProcessDir $Process -Config $Config -Database $Database
```

从头运行同一正式脚本，不另建第二份脚本或手改产物。检查退出码和唯一最终日志。公共生成器在生成前比较实际文案输入，生成后自动提取摘要、问卷、Criteria、小book和参考说明核对文字一致性，不另做一轮人工全文比对。文本不一致不交付，需改字先回文案。来源卡由正式来源关系生成。文字一致不代表定义正确；计算、数据及整套产物的完整性由下一步结果验证负责。

通过后将当前产物和日志交[结果验证](06-results.md)。失败只返回出错的输入、代码或生成部分，不重做无关探索下载。下列接口、安装定位和样式用于接入或排查相应问题，不作为额外执行阶段。

## 文案读取与展示

后台调用 `copy <- read_definition_copy(analysis_vars)`，把criteria、summary_entry、summary_insight_items、reference_lines、summary_selection传给现有生成器。definition_data$Criteria、定义HTML和笔记使用同份文案，不能另写一份或覆盖copy$summary_selection。

新主题或本次修改问卷展示时，将问卷迁入文案并删除R中的重复文字；旧主题仅改其它内容、问卷未变时允许沿用既有R问卷。无原题不传问卷展示。输入格式使用[文案模板](../../../templates/reader-copy.md)与[问卷模板](../../../templates/questionnaire-copy.md)，内容要求由[写作环节](03-copy.md)负责。

## 数据库适配边界

ELSA调用公共render_definition_bundle并设置database="ELSA"、cycle_order为已核实时期顺序，输入保留ID/idauniq/Wave。Full HRS用database="HRS"及本轮核实年份，保留字符型HHID/PN和year；不在主题复制渲染器。顺序取自证据，不从非缺失行反推；概览和文件前缀随参数生成。

summary_source只在此生成目录入口，不在文案摘要重复。单目录传纯路径字符串；需要附加说明时传 `list(path = "已核实的完整目录", note = "；其它来源说明。")`，链接仅使用path，note显示在链接外。不要把说明句拼进路径。带lines的既有结构仍兼容。下面仅示范参数，不替代完整业务定义及正式生成调用：

```r
# 名称逐项对应 analysis_vars；含义与分组取自本主题已核对的定义。
summary_meanings <- c(defined_a = "第一项定义变量的具体含义", defined_b = "第二项定义变量的具体含义")
summary_groups <- c(defined_a = "研究概念一", defined_b = "研究概念二")
# 按需传给 render_definition_bundle：
# summary_meanings = summary_meanings, summary_groups = summary_groups,
# summary_selection = copy$summary_selection,
# hist_mode = "linear"（默认）或有依据的 "zero_plus_log"
# hist_binwidth = 1，或按变量命名的已裁决分组宽度
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

公共组件负责下列样式，主题只提供文案和语义标记，不复制CSS。文案输入格式在[文案模板](../../../templates/reader-copy.md)和[问卷模板](../../../templates/questionnaire-copy.md)，本节不重复内容取舍。

| 内容 | 展示要求 |
| --- | --- |
| 摘要结果、共享维度及数量 | 保留名称的中文双引号；只有引号内概念和数字使用主题色，不染整句、连接词及标点。核对实际名称与标记，不用固定高亮数验收 |
| 时期正文与设计说明 | 时期内容统一为正文0.92em；问卷设计首段顶格，其后自然段首行缩进。说明中引号内核心问题用主题色，引号及其它文字普通色 |
| 原题题块 | 分组标题主题色加粗，题号加粗；标题、题号和问题顶格。中文题干不加引号；题号、题干、填写及访员说明继承正文颜色 |
| 选项与跳转 | 逐行缩进；选项独立0.8em、#888888；题干后进入条件用全角括号，条件及跳转独立0.72em、正文深色。同一行选项与跳转为同级元素，不嵌套相乘字号，外层只管换行缩进 |
| 间距 | 时期首个分组标题无额外上间距；后续题组及相邻问题保留轻量间距 |
| Criteria | 结构、颜色和缩进由公共helper生成；仅多条判定共同依赖的跨期组成、适用对象或解释前提使用criteria_context()浅底背景，普通含义、清单、赋值及公式不加底色 |
| 小book | 正文外层14px；首段顶格，其后自然段首行缩进2em；编号项不缩进，不在子段重复缩放 |
| 其它 | dbCodeBook普通样式，完整目录使用目录标记；数字与量词使用不可断开容器，百分号紧贴数字；关系树保留前导空格和树线 |

问卷沿用 `summary_questionnaire_line()`。语义标记对应：设计问题为 `.summary-period-question[data-summary-period-question="true"]`；原题为 `.summary-question[data-summary-question="true"]`；进入条件为 `.summary-question-condition[data-summary-question-condition="true"]` 或结构化题块的 `[data-summary-question-detail-role="instruction"][data-summary-question-position="before"]`；选项为 `[data-summary-question-option="true"]` 或 `[data-summary-question-detail-role="option"]`；选项后跳转为 `[data-summary-question-instruction="true"]`。结构化题块使用 `.summary-questionnaire-line`。变量代码由成对反引号转换，不手写code标签。

### 时期分组与全文保留

`.raw-source-structure` 包含完整来源说明；按真实调查顺序建立 `.raw-source-period`，`data-label` 保存读者可见时期名，`.raw-source-period-label` 使用普通文本容器而非Markdown或HTML标题。

前端负责标签页及展开收起；主题不写按钮、隐藏逻辑、高度、边框或网站样式。无脚本、复制、打印和导出时，所有时期名与全文仍须存在。正文不靠删减来适应折叠。

摘要整节总述首段顶格，后续自然段由展示端缩进；问卷设计与小book按上表的专门规则。参考资料位于完整定义表之后、材料之前。定义表覆盖全部分析变量，与analysis_vars、analysis_db、analysis_codebook顺序相同，综合主题先组成变量后综合变量，不再生成摘要五列表。
