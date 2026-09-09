# 复核角色与模型

只在需要调度对应角色时读取；角色输入和通过条件由各环节规定。模型名称沿用现有配置，记录实际可用模型，不因改规则重选模型。

## 稳定输入到复核结论

定义逻辑和公开 R 的复核交接记录在现有 execution_report.json 中，不另建审核报告。发给角色前运行 review-start，重复 --input 指定本轮要读的准确文件。来源方案至少包括探索记录和 definition_search_record.json；公开 R 至少包括正式 R、raw_codebook.csv 和定义方案。单纯表达变化由文案和全文环节检查，不把文案的措辞修改自动算成代码复核失效。

返修先运行 review-check；本轮没有新复核记录时，它可检查同一过程目录最近的归档结论。所有绑定输入均未变才沿用，并披露沿用来源；当前已有待处理或失败结论时不退回旧通过记录。没有合格结论或输入变化时，才创建本次需要的只读复核。

```powershell
& $Python scripts/execution_report.py review-start --process-dir $Process --role $Role --input $InputFile
```

新发起的复核收到具体发现后，先用 review-import 登记对应 agent 日志；解决发现后，用 review-result --role $Role --agent-id $AgentId --result pass|blocked --evidence $ActualFindings 保存实际结论。新复核要求当前输入未变、该角色最新一轮确已完成且结论通过；沿用归档复核时则检查原轮次证据和当前输入，不要求再开本轮审核。两种情况均用 review-check 交接。保存字段不证明判断正确，具体标准仍按当前环节逐条核对。不得把没有完成的审核填成通过。

环境确实无法建立独立角色时，采用隔离上下文自查，使用 review-result 的 --isolated-reason 写明限制并保留具体发现，不传虚构 agent ID。报告明确显示“隔离自查（非独立复核）”，不冒充独立角色，也不为满足计数创建无关角色。此例外不改变普通读者已有的输入隔离和逐块审核要求。

## Execution Roles And Model Routing

Keep one primary writer for the entire topic. Use internal read-only subagents for the required reviews; do not create separate visible task threads merely to divide stages. Reviewers report findings to the primary writer and never edit files, rerun the production workflow, operate the website, or create competing versions.

Create a reviewer when its input is ready, not at the start of the topic. Retain its agent ID and use `send_input` for that topic's focused rechecks. Do not create another reviewer for a small correction. After the final affected review passes, close the agent with `close_agent`; an agent that has returned a result is still open until explicitly closed. Preserve its evidence and record its actual rounds using the report's `review-import` command. A later new topic gets its own scoped review context.

Use the following current defaults when the host offers these models. If a named model is unavailable, preserve the role by choosing the strongest available flagship model for quality-first review, a balanced agentic model for ordinary execution, and an efficient model only for bounded mechanical work. Do not weaken a role merely to preserve an exact model name.

| Role | Current default | Reasoning | Scope |
| --- | --- | --- | --- |
| Primary writer | `gpt-5.6-terra` | `high` | Ordinary source discovery, definition, download, R, generation, revision, and authorized website sync |
| Complex-topic primary writer | `gpt-5.6-sol` | `high` | Multiple periods or files, complex questionnaire paths, long-to-wide outcomes, official derived indicators, or unresolved source inconsistencies |
| Definition-logic reviewer | `gpt-5.6-sol` | `xhigh` | Read-only review of source completeness, questionnaire-path closure, definition breadth, period, population, unit, keys, and each source variable's purpose |
| Public-R reviewer | `gpt-5.6-sol` | `high` | Read-only review of final aliases, fixed header, observed-value checks, beginner-readable execution order, missing handling, mapping, and output boundary |
| Ordinary-reader reviewer | `gpt-5.6-terra` | `medium` | Read only the final reader copy and test whether each part can be understood and restated without technical context |
| Mechanical website operation | `gpt-5.6-luna` | `low` | Optional per-stage override for the already-authorized fixed upload action; keep the primary writer when switching would require another writer or task |
| Exceptional independent validation | `gpt-5.6-sol` | `max` | Only for the unresolved evidence, research, or high-impact shared-mechanism cases defined in the validation rules |

Machine checks use deterministic scripts rather than a model. The report reads the primary model from this task's session log at stage start; an unavailable record is marked unverified, never filled from this routing table. Do not use `max` for routine work, and do not create a separate visible task or browser session only to change models. Keep reviewer inputs narrow and bind each review to the current artifacts so long primary-thread context does not contaminate the independent pass.

For a full topic run, the definition-logic reviewer is required after the source plan is settled and before the final download or formal R. The Public-R reviewer is required after the R draft is complete and before it is accepted as the production script. The ordinary-reader reviewer is required after the reader artifacts are regenerated. The primary writer resolves every finding and reruns the affected review. Website work stays with the primary writer in the one existing in-app-browser session.

Schedule reviews at these dependency boundaries, not while their inputs are still changing. While a reviewer works, the primary writer may prepare a disjoint part of the deliverable, but must not rewrite the reviewer's inputs or repeat its review. Finish machine validation before final reading; use the change scope in the validation rules to decide which evidence needs renewal.

Submit the complete source plan and evidence together. Ask the reviewer to collect all findings in one pass; the primary writer resolves the batch before requesting a focused recheck of the changed branches and their dependents. Preserve unaffected findings instead of restarting discovery or whole-topic review. If the same gap recurs, resolve its missing evidence before another review request. Do not start a production stage merely to fill review waiting time; start it when its prerequisites and actual work are ready.

Before the first Public-R review, use the existing runner's `-PreflightOnly` mode to catch fixed-header, source, environment and syntax errors without producing outputs. Send the stable draft after fixing that batch. Do not send progress-only messages to a waiting reviewer; send the completed correction and affected scope together. The later production run still checks its actual inputs; do not insert another standalone preflight immediately before it.
