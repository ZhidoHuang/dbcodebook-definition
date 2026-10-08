# 复核角色交接

是否发起及返修范围由[验收流程](validation.md)决定。本文件只规定已需要的角色怎样接收材料、复查和留下真实结论，不增加角色。

只读复核者接收稳定输入、对应标准及具体问题，不接收整个历史对话。

## 稳定输入到复核结论

1. **准备稳定输入。** 先完成双路探索合并、文案和 R 预检。
   - 一次交付正式 R、raw_codebook、来源记录、探索记录及有关权威证据。
   - 确认准确路径可访问，再绑定输入。
2. **开展只读复核。** 对照当前合并方案判断实现和计算是否正确。
   - 新发现研究缺口时，只返回有关探索问题。
   - 集中返回具体发现、未决问题和结论。
   - 不修改成果、不重跑生产、不操作网站，也不代主执行者补基本材料。
3. **集中修正后复查。** 主执行者解决一批发现和程序差异，再提交受影响分支及修改依据。
   - 复用同一角色，不每改一项就重新派发。
   - 复核期间不修改绑定文件。
   - 新增实质问题仍须解决，不以固定轮数强制通过。
4. **记录实际结论。** 导入角色日志，保存结论，再检查绑定。
   - 未读到材料、任务未送达、中止或宿主不能提供独立角色时，记为未完成。
   - 不用隔离自查替代独立复核；可继续不依赖结论的准备工作。

```powershell
& $Python -X utf8 scripts/execution_report.py review-start --process-dir $Process `
  --role "公开 R 复核" --r-scope public --input $RScript --input $RawCodebook --input $SourceRecord --input $Exploration
```

- 相关权威证据同样逐项追加--input。
- 新来源绑定保留官方题文、题号与变量对应、跳题、来源、定义和实际数据核实；不绑定译文、展示位置、是否展示及省略原因，这些由文案和生成检查负责。
- 实现复核的r-scope public只绑定唯一 `# 输出` 前的计算、mapping、字典和写出。
- 后台与文案可供阅读，不因此扩大绑定；不能把计算移到后台规避复核。
- 旧记录按原范围校验；局部更新入口在修改前核实其仍有效后，才保存沿用依据，不事后放宽旧结论。

- 返修先review-check；输入未变且当前合格才沿用，否则复查受影响部分。
- review-import登记实际会话，review-result登记内容结论，二者不互相代替。
- 没有发现也可通过，但必须实际完成判断。

## 角色生命周期

- 当前任务自己主执行，不另派代理承担整个主题，不为环节创建可见任务。
- 探索使用下面的两个独立角色；R复核在输入稳定后创建，同主题返修复用。
- 完成后实际关闭再用review-import --closed登记；宿主无关闭工具时，仅最后轮已完成才能登记--close-unavailable及限制，不冒充已关闭。

沿用任务当前模型及用户已授权配置，不为切换模型创建新任务。
以下是既有默认路由，不表示已经切换模型或获得新的授权：

| 用途 | 既有默认模型与推理档位 |
| --- | --- |
| 普通执行 | gpt-5.6-terra / high |
| 复杂主题执行 | gpt-5.6-sol / high |
| 合并独立复核 | gpt-5.6-sol / high |
| 按需普通读者 | gpt-5.6-terra / medium |
| 异常独立验收 | gpt-5.6-sol / max |

只有调度工具允许且用户已授权时，才传入模型参数。可见任务默认沿用用户设置。
宿主不提供上述模型时，质量判断用可用的强模型，普通执行用均衡模型；不能因此削弱复核职责。
报告从实际日志记录模型和推理档位。无法核实就写“未核实”，不从默认表推测。

## 输入可见性、日志定位与发现记录

原目录不可访问时复制所需文件到可访问工作区，记录原路径和副本并核对SHA-256；绑定原件、读取一致副本。派发自包含任务，确认收到且能读取；送达失败重发本任务，不能把空回复当结论。

```powershell
& $Python -X utf8 scripts/execution_report.py find-log --sessions-root $SessionsRoot --agent-id $AgentId --parent-id $ParentId
& $Python -X utf8 scripts/execution_report.py review-import --process-dir $Process --log $AgentLog --role "公开 R 复核"
& $Python -X utf8 scripts/execution_report.py review-check --process-dir $Process --role "公开 R 复核" --read-only
```

- 只定位明确agent的日志并验证身份；多个续写文件选含本次完整轮次的日志，不猜最新文件或扫描整段历史。
- fork日志需独立会话身份、forked_from_id及真实起止事件；控制台JSONL不能替代session日志。
- 定位或导入失败修交接，不重做内容审核；绑定必须早于实际复核。

--read-only不登记复用或修改报告。R预检可先通过并提示复核未就绪，这不表示正式生成已获准。计时及用量含义按[执行报告](execution-report.md#时间口径)。

- review-result 可加 `--findings-file <JSON文件>`，内容为实际发现数组；每项包含 category、location、problem、evidence（非空文本）、changed_artifact、resolved（布尔值）。
- 无发现填 `[]`；没提供数组显示“未结构化登记”，不推测为零。
- 仍有 unresolved 发现时不得 pass。
- 发现数量不是质量分数，不要求每轮必须找出问题。

- 重新绑定或更新结论时，程序在同一执行报告内保留此前输入版本、发现及结论；末轮空数组不覆盖历史。
- 报告分别显示当前未解决与累计结构化发现条次，同一问题跨轮重复出现不算不同问题；绑定/结论记录数不冒充子智能体日志的实际轮数。
- 旧报告未保存的前轮发现显示未知，不用末轮零发现反推全过程质量。

## 双路探索交接

- 共同任务说明包含已确定要求、待探索问题和材料入口；若本轮只调查局部问题，写清不变方案约束。
- 先保存该说明并登记exploration-start，再以不带父对话历史的两个独立subagent发送相同说明和只读材料入口。
- A/B输出分开，禁止读取另一分支；不得把共享的可变来源记录作为共同输入。
- 真实独立性由派发与材料访问控制，哈希不能证明思想独立。

```powershell
& $Python scripts/execution_report.py exploration-start --process-dir $Process --input <共同任务说明文件>
# 两个代理分别探索并交付后，用各自真实日志登记；下面A，B同样执行。
& $Python scripts/execution_report.py review-import --process-dir $Process --role "独立探索 A" --log <A真实日志> --close-unavailable <确无关闭工具时的真实限制>
& $Python scripts/execution_report.py exploration-result --process-dir $Process --branch a --agent-id <A真实身份> --output <A独立结果文件> --evidence <实际交付范围及未决问题>
# 主线程在既有探索记录中保存比较、取舍、共同缺口、依据性质和下游方案，不要求两路一致。
& $Python scripts/execution_report.py exploration-merge --process-dir $Process --record <definition_search_record.json> --decision <本轮合并结论文件> --result ready
& $Python scripts/execution_report.py exploration-check --process-dir $Process --record <definition_search_record.json>
```

- 当前报告已结束时，先在同一过程目录执行init，保留原workflow并自动归档旧报告，建立本次running记录；不改旧报告的状态或时间。
- 分段续办且共同输入、两路产出未变时，使用 `exploration-reuse --process-dir $Process --from-report <原execution_report.json> --input <原共同任务说明文件>`，不要先用exploration-start把历史完成时间变成本轮绑定。
- 入口核验原报告、输入、产出、不同代理身份及完成证据，保留原时间，记录原报告路径/哈希和本次reused_at；当前主线程必须独立于历史两路。
- 原合并不沿用，主线程仍须保存本次比较判断并执行exploration-merge。
- 已有当前探索只允许同输入、没有结果/合并且未启动新代理轮次的空pending登记，加 `--replace-reason <失败登记的实际替换理由>` 后替换并留存history；其它冲突拒绝替换。
- 原报告随后变化会使沿用失效。

- 有关闭工具时实际关闭后用--closed，不照抄关闭限制；代理日志读取、身份与结束状态沿用本页规则。
- exploration-result只登记实际探索完成，不认可该路方案。
- 两路都须独立完成；主线程比较后才可ready。
- 有影响当前方案的未决问题使用--result blocked并逐项--unresolved，不能用两路相同结论掩盖共同缺口。

- 合并结论文件属于本次探索记录，可引用既有证据，不新建审核表；保存后不把后续无关流水写入该绑定文件。
- 程序绑定共同输入、两份输出、合并结论和方案；身份必须不同，隔离自查不可替代。
- 程序只证明记录和输入有效，不能判断研究结论充分。
- 来源/定义实质变更要更新受影响的探索与合并；仅补实际路径人数、展示定位不使方案失效。
- 局部调查重新exploration-start时保留历史，说明影响范围与沿用决定，不要求重查整个主题。

- 新full_definition报告要求有效的双路探索绑定；分段续办可按上面的显式入口沿用未变证据，并重新合并。
- 一般返修只有存在研究问题时才exploration-start；只改表达、生成或同步沿用已有已确定方案，不自动增派探索。
- 旧报告不回填虚构代理。
- R实现复核仍沿用“公开 R 复核”接口；新报告在调用它的review-check时同时检查探索合并有效性，不能靠更新R复核绕过失效方案。
