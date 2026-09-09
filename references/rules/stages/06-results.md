# 6. 结果验证

## 本步执行与验收

- 输入：当前生成成果、来源方案及实际路径统计
- 另读：所选数据库 workflow 的业务 QA 部分
- 执行：按确定变量和身份键核对完整交付物，按风险复算结果及分支统计；记录实际执行范围
- 交付：当前版本的输出检查报告、主题复算/回归证据
- 程序检查：check_definition_output.py 的完整检查模式检查必需项；局部检查的 ok 只代表列出的检查，不代表完整成果通过
- 模型判断：未解释缺失、冲突、值域、单位和路径人数是否都有根据；不能用运行成功代替复算
- 未通过：退回出错的来源、R 或生成环节；变化后更新受影响证据，不交全文审核代为排错

## 完整检查入口

```powershell
& $Python scripts/check_definition_output.py --complete --db $Database --formal-dir $Formal --process-dir $Process --expected-files $ExpectedFiles --raw-vars $RawVars --analysis-db $AnalysisDb --analysis-columns $AnalysisColumns --analysis-codebook $AnalysisCodebook --analysis-vars $AnalysisVars --check-summary-facts --require-log-exit-code --report "$Process/result_check.json"
```

参数来自已定方案，不重新手写一份变量口径。ExpectedFiles 包含 raw、正式 R、笔记、四张工作簿及正式 HTML/QA 等本次交付物。报告绑定当前来源方案、检查程序和实际文件。进入作者审核前会核对它，文件改变后只重做受影响的结果核对，不重新探索。

不加 --complete 可做局部诊断，返回 PARTIAL_CHECK_PASS；不能用于发布许可。完整检查通过也不代替下面要求的业务复算与解释。

通过本步才交接给下一步；一次命令或点击不是一个独立验收环节。只读复核者接收本步稳定输入、对应标准及具体问题，不接收整个历史对话。

1. 正式 runner 成功，唯一最终日志含明确退出码 0。
2. 固定检查器使用正确数据库参数运行并为 `ok: true`。
3. 正式目录、raw/header/codebook、analysis、mapping、禁止变量、唯一日志和用户材料结构检查通过。问卷展示在已有全文审核中按 [问卷展示](03-copy.md#62-再说明调查原来怎样提问) 中的模板核对，确保题前条件、完整选项及跳转说明清楚且与原问卷一致。
4. 按实际改动完成足够的回归或独立复算，能够证明变量值、缺失、覆盖、来源身份和输出结构符合当前裁决；已发现的原始题目间矛盾必须证明各变量按直接来源分别保留，未经用户裁决没有发生静默协调。对每个定义变量和调查时期，还必须把进入条件、直接回答、预载信息、确认与更新、跳题方向及最终出口逐条连接到定义结果和所需原始变量，并用实际数据统计每条路径。存在未处理的观察路径、无法解释的结构性缺失或尚未提取的必要字段时，机器闸门不得通过。
5. 新增或修改公共机制时，相关 fixture、专项扫描和既有主题回归通过。
6. 过程证据存在、非空、可读；正式目录不混入过程材料。

机器闸门任一失败时，执行任务必须自行修正或向大脑报告阻断。不得把未闭环成果转交验收任务代为排错。

独立读取工作簿使用 scripts/check_definition_output.py 的 read_xlsx_rows；它读取实际单元格，不能依赖可能错误的 A1 维度。复算业务算法须与文件读取分开。
