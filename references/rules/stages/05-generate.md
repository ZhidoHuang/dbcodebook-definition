# 5. 成果生成

## 本步执行与验收

- 输入：已通过预检及公开 R 复核的脚本、当前 raw、定稿文案和变更影响
- 另读：数据库 workflow 的正式输出部分；既有生成脚本 API 按需要查看
- 执行：用现有 runner 从头运行一次；公开 R 全选运行仍可生成完整笔记，不能事后手改产物
- 交付：当前数据、字典、HTML、笔记和唯一运行日志
- 程序检查：生成前比较实际传入文案，生成后从笔记反向比较；检查退出码；来源卡从正式来源关系生成
- 模型判断：本步不重新发明研究口径；生成顺序、图表与文本必须忠于已验收输入
- 未通过：定位生成或输入问题，仅返回受影响步骤，不重复探索和下载

在 Skill 根目录运行，使用本次任务既定路径和数据库，不另建第二份正式脚本：

```powershell
./scripts/run_r_definition.ps1 -WorkDir $Formal -Script $RFile -LogPrefix $LogPrefix -ProcessDir $Process -Config $Config -Database $Database
```

通过本步才交接给下一步；一次命令或点击不是一个独立验收环节。只读复核者接收本步稳定输入、对应标准及具体问题，不接收整个历史对话。

### 3.4 `generate_var_details()`

- 周期热图文字始终使用深色。周期不超过 6 个时单行显示；超过 6 个时按原顺序分两行，两行仍溢出才使用横向滑动与箭头。
- 连续变量默认自动选择自然刻度，使柱数约为 12–16 根；横轴显示分组起点，完整区间留在悬停提示中。
- 非负金额正值跨度很大、线性图会挤压主要分布时，直接使用 `hist_mode = "zero_plus_log"`：`0` 单独展示，正值按对数分档。存在负值、`0` 含义特殊或口径不明确时才需裁决。
- 只有正式业务分组宽度已经明确时才设置 `hist_binwidth`；不同变量需要不同宽度时使用命名向量。

### 3.5 宣传代码提示边界

定义笔记公开 R 与正式业务 R 保持一致，不显示 raw 获取提示。`# raw_data.csv从网站dbcodebook.cn对应笔记，go to提取变量获得` 只由公众号 SVG/富文本渲染工具注入，不写回正式 R 或定义笔记。

### 3.6 公共生成脚本的定位

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

#### 6.2.1 调查时期分组的笔记生成规则

调查时期分组用于按年份、Wave、调查阶段或问卷版本分别保存完整说明，CHARLS、ELSA 及其它数据库共用同一套笔记结构。

1. 主题生成源使用 `.raw-source-structure` 包住整个来源说明，按真实调查顺序为每个时期建立 `.raw-source-period`，并用 `data-label` 保存该时期的读者可见名称。
2. `.raw-source-period-label` 只保存无脚本环境需要显示的时期名称，必须使用普通文本容器，不得使用 Markdown 标题或 `h1` 至 `h6`。
3. 每个时期的正文必须完整保留在对应分组中。主题脚本不得生成标签按钮、展开收起逻辑、内容高度、边框、间距或其它网站样式。
4. 没有网站脚本、打印、复制全文或导出时，所有时期正文和时期名称仍须完整显示，不能因网站采用标签页而丢失内容。

网站识别上述语义结构后，由公共前端自动完成标签显示和交互；主题生成源不得重复实现网站渲染逻辑。

- “摘要导读”只有整节最开头的总述首段顶格；后续自然段由网站统一设置缩进。笔记正文不手写空格或 HTML 空格模拟缩进。
- 来源组成之后，用一句单独成行的简短文字说明可从 dbCodeBook 的哪个真实完整目录进入。多个来源共享父目录时优先展示一次稳定父目录；来源分散时展示最能说明主题的入口，并中性说明还有其它来源。目录记录数只有帮助理解且能对应紧邻展示的同一实际目录时才保留。
- 普通检索关键词、翻页、排除候选和其它探索过程不进入摘要。真实发现路径、页面观察和判断过程同步保留在数据库流程规定的 `探索记录.md`；`definition_search_record.json` 只保存与同号步骤对应的机器对账信息。
- 摘要和时期标签不展开逐变量赋值、特殊编码、公式、补零、缺失、QA、下载、验收和制作过程，也不另设“定义处理”块。影响单个变量的判定写入 `Criteria`；影响多个变量或整个主题使用的边界写入小book提示。

## 7. 其它用户材料与同步

- `### 1-提取变量` 必须包含非空、可直接粘贴到网站批量输入框的 `网站完整原始变量身份=下载别名` 列表和一个 `Go to 提取变量` 按钮；左右两侧来源、括号保留和逐项格式按 [来源关系](02-download.md#先按出现位置区分三种变量关系) 执行。
- detail/组分概览按真实研究概念分组，每组先显示 `source variables`，再显示 `defined variables`。分组名称使用普通读者能理解的业务概念；source variable 的 Easy.label 说明原题，defined variable 的显示标签说明分析变量。正式 R 显式设置 factor levels；未匹配变量进入 `Other / check` 并触发 warning 或 QA。
- detail 片段自行提供 `## 定义的组分概览` 和 `## 定义的组分详情`；笔记拼装器不得再额外添加“定义的组分详情”。最终笔记各保留一个标题，不能形成“详情 → 概览 → 详情”的重复结构。
- 用户材料只解释数据对象、变量语义、周期逻辑、必要来源差异和研究使用影响；工具、版本史、验收状态和过程证据留在机器报告或内部证据。
- 定义笔记摘要负责“定义结果、变量关系、来源组成和目录入口”；`Criteria` 负责逐变量判定；小book提示负责主题级边界；公开 R 负责解释并实现定义过程；宣传材料负责把已确认事实重新组织成适合相应平台阅读的内容。
- 摘要、`Criteria`、detail 分组和公开 R 分别从各自正式生成源同步。正式定义事实变化后，再由独立的宣传任务评估并刷新需要更新的宣传材料；宣传材料不作为定义笔记或正式 R 的措辞底稿。

## 数据库适配边界

read_definition_copy() 返回 summary_selection 时，直接使用该值，勿在调用之后覆盖。问卷文字只改文案.md 的“原始问卷”，程序负责转成既有展示结构并检查一致。

当前 render_definition_bundle() 包含 CHARLS 五期、year 与文件名假设。ELSA 及新数据库在实际采用这条生成路径前必须完成相应适配；有 profile 或路由不代表生成器已经验收。本轮不以 CHARLS 测试代替 ELSA 实题验收。
