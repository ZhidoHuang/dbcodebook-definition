# ELSA 变量定义标准流程

版本日期：2026-08-27

适用范围：通过 dbCodeBook 为 ELSA 发现候选、裁决研究口径、下载 raw、编写正式 R，并完成正式成果与机器闭环。

本文件只保留 ELSA 特有规则。跨数据库的命名、公开 R、`Criteria`、摘要导读、小book提示、输出合同和机器检查，按 [共同规则索引](../../rules/common-materials.md) 进入对应环节，不重复定义；数据库身份和文件族见 [profile.md](profile.md)。不得从 CHARLS 流程复制题号、波次、编码、前缀或主题经验。

## 1. 任务与目录

- 正式数据库根：外部配置中的 `paths.formal_root/ELSA`。
- 过程证据根：外部配置中的 `paths.process_root/ELSA`。
- 正式主题目录：`paths.formal_root/ELSA/<编号_主题>`，只在候选和口径确认后创建。
- ELSA 在本数据库内独立连续编号；开始前先查正式目录、主题索引和验收台账。
- 过程目录只保存本轮确有用途的截图、检索记录、recover 报告、核对报告和机器闭环 JSON；不强制创建 `current_task.md`、复盘包或重复叙述型过程卡。
- 新主题或改变 raw、`Variable (File)`、文件族、分析单位、权重、编码、Wave 含义、transaction 时，走完整流程。只改文字或展示且正式事实不变时，可从当前正式 R、raw、codebook 和已确认裁决重建；发现证据不足时立即回到候选阶段。

## 2. 候选发现与研究口径

### 2.1 从真实页面开始

页面：外部配置中的 `website.base_url + website.database_paths.elsa`。

1. 先从目录进入相关节点；目录面板筛选词只用于定位目录。
2. 需要发现跨目录候选时，再做普通检索，并分别记录关键词、结果和后续决定；0 结果也是证据。
3. 启用页面 `Label`，核对题目、Wave、取值和适用对象；Easy label 只作入口。
4. 每个候选记录完整 `Variable (File)`、Wave、目录或数据家族、题义、取值、适用对象、raw/derived、跨 Wave 差异和纳入或排除理由。
5. 不用旧代码、本地导出、底层数据库、Parquet、历史笔记或最终变量名反推候选和探索路径。

从第一次网页操作起同时建立 `探索记录.md` 和 schema v7 `definition_search_record.json`，分别使用 [exploration-record.md](../../../templates/exploration-record.md) 和 [definition-search-record.json](../../../templates/definition-search-record.json)。前者用大白话同步记录每一步“做了什么、看到了什么、这说明什么、下一步为什么这样走”，直接供用户和后续复查者阅读；后者记录同一步骤的结构化身份，供机器对账。两者来自同一次真实探索，JSON 不高于、不替代大白话记录，也不能用于事后生成探索故事：

- `exploration_log` 按实际发生顺序记录目录进入、普通检索、页面观察、官方材料、Harmonised ELSA 和文献核对、下一步决定及理由，并用 `human_step_id` 指向 `探索记录.md` 中同号步骤。
- `evidence_reviews` 记录实际查阅材料的标题、可定位位置、明确支持内容、没有说明的内容、对本轮决定的影响和对应探索步骤。
- `questionnaire_evidence` 逐题记录各 Wave 正文实际呈现的官方题号、完整题干、完整选项、跳题条件与真实去向，以及本地材料路径和定位；`questionnaire_coverage` 必须覆盖每个来源组的每个 Wave。非问卷构造来源要明确标为不适用并说明理由。本地缺件时先记录实际查找范围和缺口，才能补用官方网站。
- `candidate_decisions` 记录每个候选的纳入、排除及对应发现步骤。
- 每个最终 raw 必须能回到真实页面来源和纳入理由；记录不完整时不得下载。

### 2.2 文献与官方材料

完成页面探索和官方题目详情核对后、下载前，进行与研究概念相称的定向调研：

1. dbCodeBook 题目详情、实际 raw 和 `raw_codebook.csv`。
2. ELSA 官方问卷、用户指南、技术文档、派生变量说明和可定位构造过程的 Harmonised ELSA 代码本。
3. 原始量表、方法文献、正式指南、共识或主管机构文件。
4. 明确报告 ELSA 题项、Wave、raw、公式或计分的高质量同行评议研究。
5. 一般应用研究只作使用实例，不替代直接证据。

简单单题至少确认是否存在不同常见口径；量表、认知测验、指数、总分、复合变量、跨 Wave 项目变化或计分歧义必须实质调研。记录来源明确说了什么、可直接核实什么、本轮拟采用什么；未报告的细节写“未报告”，不得反推。证据冲突或存在多个合理口径时，形成候选方案交用户裁决。

每次官方材料、Harmonised ELSA 或文献核对都作为真实探索步骤，按发生顺序写入 `探索记录.md` 的 `Sxxx`，并在 `definition_search_record.json.evidence_reviews` 登记同号步骤。记录直接说明“材料写了什么、没有写什么、因此本轮怎样决定”，不能在笔记完成后根据最终文案反向补造调研记录。

### 2.3 研究性与 Wave 完整性

正式命名和下载前必须完成：

- **成果查重**：比较研究含义、`Variable (File)`、构造和实际取值；同义等值变量复用，简单重分组优先并回原主题。
- **主题边界**：一个候选包含多个独立概念时，说明合并或拆分理由。
- **命名系列**：遵守通用命名规则并检查 ELSA 既有系列；不机械套用 CHARLS 前缀或历史名称。
- **Wave 完整性**：列出预期 Wave、实际来源和题义。前后有来源而中间断开，必须回到目录和普通检索核查；不得用 `coalesce` 掩盖未解释断层。
- **逐 Wave 可用性**：报告适用对象、非缺失人数和覆盖率，不用合并后总人次代替。

候选结论使用 `NEW`、`MERGE`、`REUSE` 或 `DEFER`。只有 `NEW` 且口径已确认，才进入正式下载。

### 2.4 ELSA 身份闸门

- 候选、判重、mapping、下载和 QA 的身份键是 `Variable + File`。
- 同名 Variable 跨 File 必须拆开，例如 `palevel (Core data)` 与 `palevel (Derived Variables)`。
- Core、COVID、Wave 0、Nurse、Life History、End of Life、HCAP、Nutrition、Pension Grid 和 Harmonised ELSA 不能只按裸 Variable 拼接。
- 出现 raw 与官方 derived 二选一、core member/partner/proxy/copied value/refreshment sample、非个人-Wave单位、同一 `idauniq` 多行、权重或负值编码歧义、特殊文件族是否纳入等问题时，必须先裁决。

候选审核包只需包含：`探索记录.md`、`definition_search_record.json`、候选矩阵、关键官方或文献证据、主题与命名判断、Wave 完整性和逐 Wave 可用性、方案比较及待裁决问题。未裁决前不下载 raw、不创建正式主题目录、不写正式 R。

## 3. 下载与恢复

收到明确裁决后：

1. 固定 `Variable (File)`、分析对象、Wave、权重和编码边界；来源别名、周期互补组和完整变量族按公共规范第 1.2 节确定，并写入 `definition_search_record.json`。
2. 在页面设置已经确定的最终别名，再核对标签、预览、header、记录数和文件分组；正式 raw 和 codebook 必须直接带有最终别名。
3. 保存本轮确有判定价值的选择列表、File/Wave 覆盖和预览证据；截图必须真实存在、非空且可解码。
4. 页面下载生成本次 transaction。
5. 下载完成后，使用 `<skill-root>/scripts/recover_dbcodebook_export.py --archive <本次下载包> --database elsa --out <正式主题目录> --expect-vars-file <download_selection.txt>` 保存并核对本次 zip/raw。
6. recover 必须拆分并保留 `Variable (File)` 的 variable 与 file；核对 transaction、header、codebook 和文件列表。
7. raw header 按 `ID, idauniq, <selected variables...>` 精确核验，不伪造 CHARLS 的 `id/year`。
8. codebook 同时核验 `Variable (File)` 和 `newname`；不得去掉 File 后用裸 Variable 对账。
9. `newname` 为空、重复、缺少预期变量或出现意外变量时，恢复失败。

只要最终来源清单中的变量、Wave、File、来源身份或最终别名发生变化，就必须按改变后的完整清单重新从网站一次下载；不得筛选旧包或拼接补充下载。来源清单没有变化时，不因文案、展示、注释、主题编号或同一批 raw 上的实现调整重复下载。

确认以上事实后，才创建正式主题目录、写唯一正式 R 并运行。

## 4. 分析单位与来源一致性

正式定义前确认：

- `idauniq` 是否唯一；不唯一时写清附加 key 及每行代表什么。
- 正式 db/analysis 身份列为 `ID, idauniq, Wave`；raw 保持下载原貌。
- `Wave` 从 `ID` 提取并保留 `Wave 1`、`Wave 2`……文本；所有 ID 均须成功解析，正式范围按本轮来源核对。
- `idauniq` 可跨 Wave 重复，这是纵向记录，不按 `idauniq` 去重。
- 是否混入 COVID、Wave 0、2023 等特殊期。
- household id 是否波次化，以及 core member、partner、proxy/copy、访谈 outcome、refreshment sample 的角色。
- Nutrition detail、Pension Grid、respondent/informant 等文件是否造成一人多行。
- 权重对应的对象、Wave、横断面或纵向用途。
- 每个 raw 的全部负值及官方解释；不套用 CHARLS 特殊码。

任一项会改变研究对象或口径时，暂停裁决。

当多个 `Variable (File)` 在部分 Wave 重叠而正式路线只采用一个来源时，必须在重叠 Wave 逐项逐行比较。每项记录总行数、双方非空可比行、双方同时缺失、缺失模式 mismatch、有效值 mismatch 和来源选择理由。mismatch 大于 0 时暂停裁决，不用优先级或 `coalesce` 静默覆盖。

## 5. 正式 R 与用户材料

- 通用包头、公开代码、mapping、xlsx、QA、runner、`Criteria`、摘要导读和小book提示均执行 [common-materials.md](../../rules/common-materials.md)；ELSA 不维护第二套语言或代码模板。
- 正式 R 只补 ELSA 必需背景：`Variable (File)` 身份、Wave、文件族、官方负值编码和本主题实际跨 Wave 变化。
- mapping 必须追溯到完整 `Variable (File)`；内部证据和 QA 不得丢失 File。
- 正式分类变量默认保留规范化英文或 ASCII 标签；只有 YES/NO 二分类默认使用 `1/0`。频率、等级和状态等多分类不为排序便利擅自改成数值等级。
- 用户可见主题色从 [database-themes.json](../../database-themes.json) 的 ELSA 配置读取，不逐主题手填。
- detail 或组分概览的周期列显式命名为 `Wave 1`、`Wave 2`……，再交给生成器。
- 用户材料只写研究对象、变量语义、来源或 Wave 变化及分析影响，不写 transaction、recover、检查器或内部执行史。

## 6. 正式输出与机器闭环

正式目录只保留标准成果：

- 唯一正式 R 和唯一成功日志。
- raw 三件套。
- db、codebook、analysis_db、analysis_codebook 四表。
- QA、definition HTML、detail HTML 和定义笔记。

通用执行、审核、返修范围和发布状态统一见 [验收流程](../../rules/validation.md)。ELSA 的结果检查显式使用 --db elsa；不能继承 CHARLS 的默认参数。

ELSA 另需保留已有证据清单和机器闭环记录：实际引用的截图、原始包恢复报告、成功日志、关键核对报告的存在与可读性；transaction、raw/analysis 行数、变量顺序、完整 File 身份、Wave 覆盖、负值和重叠来源比较。结果不明时回到对应研究口径，不强行合并。

生成器适配边界见 [成果生成](../../rules/stages/05-generate.md#数据库适配边界)。最终笔记未变时是否保留读者审核，完全按共同修正规则；不因附件或 R 后台变化无条件重做两轮。

机器闭环只报告真实证据，不要求另写叙述型过程卡或历史复盘。具体主题问题不自动写成公共规则。
