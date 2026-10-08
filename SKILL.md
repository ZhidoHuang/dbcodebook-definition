---
name: dbcodebook-definition
description: Run, revise, audit, or publish variable-definition topics built from dbCodeBook across CHARLS, ELSA, and configured databases. Use for source discovery, official-material and literature review, fresh downloads, formal R definitions, full 文案.md review, validation, and website inspection sync. Do not use for promotional assets, rich text, or website maintenance.
---

# dbCodeBook Definition

本仓库是规则、证据、程序和测试的正式来源。

- 从当前任务和配置确定数据库、主题、正式目录、过程目录、程序路径及网站地址。
- 这些信息未变时，沿用已有记录，不重复查找。
- 共享规则不写入本机路径。

## Choose The Entry

先按用户请求选择入口。用户限定的局部任务优先于完整流程。

| 用户请求 | 读取位置 | 执行范围 |
| --- | --- | --- |
| 解释或汇报状态 | 相关当前成果或执行报告 | 只回答；不生成、不上传、不创建生产报告 |
| 明确只修本地问卷、不生成或同步 | [问卷局部修正](references/rules/scoped-tasks.md#questionnaire-only) | 对照提供的证据，只改指定部分，运行对应检查后结束 |
| 离线准备下载文件 | [离线准备](references/rules/scoped-tasks.md#offline-download) | 生成本地动作和快照；不连接浏览器、不登录、不联网下载 |
| 检查历史阶段登记 | [历史报告检查](references/rules/scoped-tasks.md#historical-report) | 只读检查；不重跑生产、不改历史 |
| 新建、重做或改变来源 | [1. 选题与来源方案](references/rules/stages/01-source-plan.md) | 按完整流程执行；来源或别名变化时重新全量下载 |
| 审核或修改文案 | [3. 文案写作](references/rules/stages/03-copy.md)；既有主题只改表达或展示时用[局部更新](references/rules/scoped-tasks.md#copy-update) | 读取完整文案；重新生成并检查受影响成果，继续已授权的网站同步 |
| 修改 R 或计算 | [4. 公开 R](references/rules/stages/04-public-r.md) | 沿用未变来源；生成前同步修改受影响文案 |
| 上传已检查成果 | 只读[8. 网站同步](references/rules/stages/08-website.md) | 不加载探索、问卷、R 或写作规则，不重建主题 |
| 修改本 Skill | [规则归属](references/rules/index.md)及本次修改范围 | 不因维护 Skill 而运行主题或修改网站 |

主线程从已有上下文整理已确定要求、待探索问题和材料线索，不要求用户另填表。
提到某个来源或旧稿，不等于用户已确定采用它。
明确任务直接执行；只有未决研究问题进入双路探索。

局部任务只读取对应章节。遇到具体未决问题时，再读有关规则。
局部任务不自动启动完整流程或新生产报告；按该入口汇报实际工作和耗时。

## Stage Order

执行顺序及返修范围由 [validation.md](references/rules/validation.md)统一规定：

1. [选题与来源方案](references/rules/stages/01-source-plan.md)。
2. [选择与下载](references/rules/stages/02-download.md)。
3. [文案写作](references/rules/stages/03-copy.md)。
4. [公开 R](references/rules/stages/04-public-r.md)。
5. [成果生成](references/rules/stages/05-generate.md)。
6. [结果验证](references/rules/stages/06-results.md)。
7. [成品交接](references/rules/stages/07-review.md)。
8. [已授权的网站同步](references/rules/stages/08-website.md)。

### 准备与读取

| 情况 | 操作 |
| --- | --- |
| 新设备或运行环境有变化 | 生产前运行一次[环境检查](references/rules/stages/01-source-plan.md#新设备准备)，集中处理缺项 |
| 环境已验证且未变 | 不按变量或阶段重复检查 |
| 本地依赖检查通过 | 继续确认浏览器控制和登录；本地通过不证明这两项已通过 |
| 进入某一环节 | 读取本环节及有关数据库差异；按条件进入引用，不顺次通读全部规则 |
| 文档或工具结果很长 | 用 rg 定位标题后读取所需范围；每次通常不超过 200 行 |
| 需要完整证据或用户要求完整文案审核 | 读完所需内容；200 行是单次输出建议，不是删减证据的许可 |
| 材料已经读过且未变 | 直接沿用 |

各阶段文件规定输入、执行、产出、程序检查、模型判断和失败返回位置。
数据库 profile/workflow 只补充身份、时期、文件、编码、接口和已验证范围，不另设一套流程。

### 数据库材料与支持范围

从 [database-routing.json](references/database-routing.json)定位所选数据库规则。
参考材料从[材料索引](references/source-materials/材料索引.md)进入。

| 数据库 | 当前证据边界 |
| --- | --- |
| SHARE | 普通 Wave 1–9 人口学已完成真实完整流程；范围见该库 workflow |
| KNHANES | Core data 人口学的 1998、2001、2005、2007–2024 年已完成真实下载、生成、独立复算和发布；范围见该库 workflow |
| KLoSA、CHNS | 以各自 workflow/profile 的当前验证范围为准 |
| HRS | 正式路线为 `/home/hrs/` 的 Full HRS 原始库；真实下载及完整流程验证范围以该库规则为准 |

RAND HRS 和 Harmonized HRS 是独立产品，只能作为明确标注的辅助证据。
材料可读、配置存在、完整流程通过是三种不同证据，不能互相替代。
公共生成器的数据库支持范围见第5步；路由存在不证明完整流程通过。

遇到具体下载或生成入口不支持时：

1. 说明缺少哪项能力，只暂停依赖它的操作。
2. 继续能完成的目录、变量、问卷和方法探索。
3. 公共适配已获授权时，在授权范围内处理。
4. 公共适配未获授权时，提出具体修改范围，继续不受影响的工作。

### 执行记录与角色

执行者负责内容完整、表达易读。

- 实质生产或共享工具修改开始前，创建既有[执行报告](references/rules/execution-report.md)。不另建计时或审核体系。
- 当前任务负责合并方案和后续执行，不把整个生产流程交给代理。
- 未决研究问题按第1步交给两个独立探索代理，再由主线程根据证据合并。
- 完整主题在稳定 R 稿及预检完成后，保留一次独立 R 实现复核，核对已定方案和计算。
- 需要只读复核时，按[角色交接](references/rules/review-roles.md)在输入稳定后创建角色。受影响返修复用该角色，完成后关闭。
- 不为拆分工作而创建可见任务，也不为每个环节或写作要求创建审核者。
- 普通读者复核只在具体理解问题未解决或用户明确要求时发起。
- 不要求固定写作自查、逐栏目 PASS 或作者通读声明。保留必要程序检查、独立 R 实现复核和真实证据。

## Global Boundaries

| 情况或对象 | 要求 |
| --- | --- |
| 已有明确规则 | 按规则执行，不自行改设计 |
| 规则不清、冲突或需要偏离 | 改动前报告具体疑点和影响；不限于来源映射 |
| 已授权生成、检查及网站同步 | 连续执行，不逐步重复请示 |
| 明确要求“只审核、不执行” | 在文案审核结束，不继续生成或同步 |
| 未决研究选择、必要来源缺口、外部写入结果不明 | 暂停依赖该问题的操作 |
| 写入范围 | 不扩展到无关主题、网站源码、账号或宣传材料；见[写入边界](references/rules/write-boundaries.md) |
| 浏览器 | dbCodeBook 只用无扩展的 Playwright CLI 控制 Chrome 或 Edge；不用 ChatGPT 扩展或内置浏览器 |
| 会话与固定动作 | 按[会话规则](references/rules/write-boundaries.md#浏览器会话)复用有名称的持久会话，通过固定入口下载和同步 |
| 来源身份 | 完整原始身份与下载别名分开保存；不改下载 CSV 表头，不用展示缩写替代正式来源 |
| 检查结论 | 程序通过只证明实际比较过的内容；未执行不能记通过，存在、长度或哈希不证明内容正确易读 |
| 网站提交 | 必要本地检查通过后才提交；返回文章地址后停止浏览器操作，不再次审页 |
| 正式 R | 保留独立运行入口，读者从头运行即可生成完整笔记 |
| 最终数据 | 按[第5步](references/rules/stages/05-generate.md#正式输出与图表)统一为每人每期一行的长表；原始来源可以是其他结构 |
| 主题事实 | 不把单主题选择变成公共规则，不套用其他数据库的身份或时期假设 |
| 颜色与宣传 | 数据库颜色由[主题配置](references/database-themes.json)维护；宣传材料使用对应专用 Skill |

## Progress And Finish

向用户直接用中文说明进展、发现、需要决定的事项和最终结果。
用户不应依赖打开文件才能知道结论。

- 请用户审阅文案时，在对话中展示实际文字。
- 文案较长时，分成标识清楚的部分展示，不省略内容。
- 文件、链接和附件用于佐证，不代替汇报。
- 用户未要求时，原始数据、完整代码和详细日志留在文件中。

| 当前状态 | 怎样汇报和继续 |
| --- | --- |
| 无需用户决定，仍有已授权工作 | 用进度消息说明下一步，并在同一轮继续；不因阶段结束而等待“继续” |
| 确实需要用户决定 | 在汇报末尾提出具体问题，说明可选方案及影响，再给推荐和依据；缺证据时明确缺什么 |
| 只有部分工作依赖用户答复 | 暂停该部分，继续其他已授权工作 |
| 请求范围已完成，或确需用户/外部条件才能推进 | 给出最终答复 |

完成前结束执行报告。汇报实际改动、检查及结果、总耗时和各阶段耗时、异常及未完成工作。
网站提交成功不等于用户验收通过。

共享机制修改或仓库发布时，运行 `tests/run_all.ps1`，使用本机配置的程序及已安装 skill-creator 的 `quick_validate.py`（通过 `-SkillValidator` 传入）。
将实际覆盖和未验证范围记入[验收矩阵](tests/acceptance-matrix.md)，不把某库通过推广为其他库通过。
