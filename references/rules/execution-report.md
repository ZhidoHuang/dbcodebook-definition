# 执行报告

只记录做了什么、真实耗时、问题和结束位置，不规定另一套验收流程。execution_report.json由脚本维护，执行报告.md由它生成；均放过程目录，不手填报告、不进入笔记或网站。

## 何时创建

| 本次任务 | 报告入口 |
| --- | --- |
| 完整新建或重做主题 | 首次实质操作前init --workflow full_definition |
| 局部返修或共享工具维护 | init --workflow general，只记录实际工作，不为凑完整流程重做 |
| 已有成果网站同步 | website-prepare自动管理website_only或沿用当前报告，后续按第8步 |
| 只回答、只读查看、简短审核 | 不建报告；只修问卷不生成、离线下载准备和历史登记检查按scoped-tasks |

```powershell
& $Python -X utf8 scripts/execution_report.py init --process-dir $Process `
  --database $Database --topic-id $TopicId --topic-name $TopicName `
  --task $Task --workflow full_definition
```

续办沿用正在执行的报告；确实新开运行须先如实结束旧报告，已结束报告由脚本归档，不静默覆盖。历史登记用 `execution_report.py check --report <报告>` 只读检查，不证明历史成果质量。返修与复核要求由[validation](validation.md)决定，不因报告格式增派角色。

## 必须记录的环节

完整流程按下表登记；局部任务只记实际涉及部分。阶段完成不是审核通过。

| stage_id | 工作 |
| --- | --- |
| locate | 任务定位及已有材料 |
| sources | 两路独立探索、权威材料、主线程比较及合并；实际数据核实及必要的定向返工 |
| download | 最终选择、导出、文件校验安装 |
| copy、public_r、generate | 文案；R编写预检及实现复核；生成。完整三段可替代旧formal_r，不另补总段 |
| results、review | 结果验证及成品交接。完整两段可替代旧validation，不代表另派角色 |
| website_preparation、website_sync及收口 | 由网站固定入口管理，不手动建网站阶段 |

完整流程未发生的固定环节记skipped及真实原因；缺环节或必要复核会阻止finish。旧formal_r/validation分段仍兼容，不改历史时间。只有实际发起的额外读者/异常复核才登记，角色操作见[review-roles](review-roles.md)。用户报告仍说明定位、探索、来源逻辑核对、下载、R/生成、实现复核、交接及额外读者、机器验证、网站这九类实际工作，不等于创建九次审核。

每段开始stage-start，结束stage-finish；work、wait、rework分别记录工作、外部等待、返工。性质改变时结束原段再开对应段，不能把排错全部称为机器运行。遗漏时间由timing_coverage.untracked_seconds如实披露；超过60秒标记覆盖不完整，但不阻止已完成成果收口，绝不补造瞬间阶段。

```powershell
& $Python -X utf8 scripts/execution_report.py stage-start --process-dir $Process --stage-id sources --name "来源探索" --role "主执行者" --mode work
& $Python -X utf8 scripts/execution_report.py stage-finish --process-dir $Process --stage-id sources --status completed --summary "本段实际完成的内容"
```

未传model时按CODEX_THREAD_ID读取本任务开始该段时的实际模型/档位并保留证据；不可核实时写未核实。明确指定的模型可用--model登记为显式声明，不从默认路由推测。init保存规则、模板、脚本及数据库配置的实际内容哈希，不以Git提交号代替工作树。

## 首稿与实际工作记录

copy首次形成完整稿时，按[文案程序操作](scoped-tasks.md#copy-operations)在机械检查前保存快照，不等检查成功。stage-finish传`--copy <文案.md> --summary <实际结论>`，失败状态也可保存明确提供的完整稿；同次同内容不重复保存。后续版本不覆盖首稿，漏记不能用修正版补称首次。快照、哈希和Skill版本仍在同一报告维护，不另建质量表，也不代表质量通过。

## Bug 与异常

发生问题立即issue记录，类别为bug（错误）、abnormal（流程/工具异常）或wait（外部等待），说明问题、影响、处理和状态：

| 状态 | 含义 |
| --- | --- |
| open | 仍阻断交付 |
| mitigated | 已验证交付恢复但根因待修；必须写恢复证据与剩余问题，计入未解决数，可completed_with_issues收口 |
| resolved | 有可核验的解决结果，不能仅凭重连或命令发出 |

保留已解决问题；误标用issue-amend留下更正原因。阻断下一步、需要用户动作或导致重复尝试时，立即说明卡点、成果是否改变和下一步，不等最终汇报；未变条件下不反复重试。

## 时间口径

- 阶段时间由实际起止计算，工作/等待/返工不混记。跨用户讨论或未分段排错须披露，不称纯操作耗时；并行角色时长不能简单相加作为总墙钟。
- 角色时间由review-import读取指定session日志，只统计本报告时间范围内的轮次；同一代理期间服务多个任务时，用重复的 `--turn-id` 明确本任务轮次。历史结论用沿用入口，不把旧任务计入本次耗时。按agent去重、turn分轮；轮间间隔不推定为等待或修改。定位、关闭登记及内容结论按review-roles，未完成角色不能收口。
- 报告结束不等于回复结束；轮次真正结束后才用 `turn-timing --process-dir $Process --log $TaskLog --turn-id $TurnId` 补该轮真实范围，当前轮只标“截至报告收口”。需要补报告开始用start-amend和同样日志参数，读取真实事件、保留更正，不接受手填估计时间。
- 没有日志或未单独计时的历史明确记缺失，不用零点、估计值或几秒钟阶段补齐；复盘写当前报告，保留原报告。
- 网站prepare开始准备，start-sync切换提交；website-finish校验原始结果的运行、尝试、开始时间、五项质量检查及耗时，以实际返回结束提交，延迟导入归收口；finish结束收口。旧运行、失败或无原始结果不能写成功。入口重复调用不重置计时，预检失败仍保留准备时间并登记issue。

## 完成条件

实际工作结束、成果为本次已验证文件、阶段有真实状态、所需角色完成并按review-roles关闭或披露关闭限制，才finish。正常完成用completed；有问题（包括已解决）用completed_with_issues，mitigated披露剩余根因；open不能标完成。失败或停止按实际状态记录。

报告仍执行中、成果未验证或新raw配旧结果时，不能宣布本次工作完成。报告收口不替代内容许可或用户验收；历史通过不得用于变化后的成果。

## 执行用量

```powershell
& $Python -X utf8 scripts/execution_report.py metrics-import --process-dir $Process --log $TaskLog --log $ReviewerLog
```

仅导入明确指定日志，按本报告开始至结束（运行中则截至导入时刻）截取；每个会话选一份完整日志，重复会话拒绝合计。重复导入更新统计，不累加旧导入。记录可用的累计用量差值、缓存输入、输出、最大单次请求输入、有用量事件的请求数、工具调用、相同调用重复数和最大工具输出字符数；计数重置分段处理。日志缺失的指标显示未提供，不能写成零或估算请求总数。

相同调用可能是合法轮询，不自动判为浪费。任意 shell 的文件重复读取与“因错误重跑”不能可靠从字符串推断；用既有 issue 和 mode=rework 记录原因与返工区间。不同供应商日志未提供兼容用量事件时保留未提供。缓存输入是总输入的子集，不与总输入相加，不直接换算价格或周额度。

没有同条件基线前不设武断调用配额。以对应阶段的真实返工和大输出定位问题；只有用户给出预算时才按预算管理。需要分段续办时保存稳定产物、已完成阶段和未决项，按原输入绑定接续，不重复下载或重新执行已验证阶段；不因分段自动创建新任务。

## 网站耗时

网站准备、固定提交和收口仍按上面的原始结果计时，不重复手记。汇报保留各浏览器步骤、浏览器总耗时、阶段开始到返回、阶段最终墙钟，不能只报最短值。登录等待单列。复用登录会话时，浏览器动作以30秒内、阶段到返回以90秒内为目标；动作超过60秒、阶段含收口超过2分钟仍未成功时停止继续尝试并如实报告。停止后的恢复或提交不确定按[网站失败处理](stages/08-website.md#失败怎样处理)，不为达到时限丢弃可能已提交的操作。

## 双路探索记录

新完整流程保留review_policy=execution_first_v1的R/读者兼容规则，另设exploration_policy=dual_exploration_v1。一般任务在实际exploration-start时启用，不因维护或纯文字返修强制探索。双路的登记、合并和只读检查命令见[探索交接](review-roles.md#双路探索交接)。

exploration保存共同输入、两路产出及当前合并；重复开始或更新结果保留历史，不能拿旧ready覆盖当前未完成。下载准备、公开R review-check和完整流程finish核对当前合并。没有新探索策略的历史报告继续原规则，不改写旧记录。报告展示两路登记和主线程合并状态；代理时长沿用真实日志，不能相加当作总墙钟。
