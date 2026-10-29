# Scoped Tasks

Questionnaire-only 仅用于用户明确限定只改本地问卷、不生成或同步的任务；普通问卷修改按文案、生成和已授权同步的现有阶段执行。Offline-download 和 Historical-report 仅用于用户明确限定的任务。
路径和 Python 从任务配置取得；下方命令在 Skill 根目录运行。

## Questionnaire-only

1. 读取目标问卷部分，以及[通用表达](stages/03-copy.md#通用表达)、[通用格式](stages/03-copy.md#通用格式)和[问卷任务及基础模板](copy/questionnaire.md)。沿用本次未改变的展示决定；条件实例按问卷任务中的触发条件读取。
2. 按本次题组和时期定位用户提供的实际问卷及来源记录，再完整读取有关题文、选项、说明、进入条件和去向。大记录先定位字段或相关记录，不先整份输出。涉及上游题或跳转去向时补读相连内容；不把现有登记当作原问卷的完整范围。
3. 从原问卷逐题、逐选项核对文案，包含进入条件和去向；不以已记录项目限定检查范围。
4. 原文有记录未包含的路径时，保留该路径并报告记录遗漏。
5. 只有记录可写且修改在授权范围内时，才更新来源记录。
6. 保留其他章节、只读证据和既有展示，不为迎合检查器语法重写题块。
7. 运行检查，并确认差异只涉及指定部分：

```powershell
& $Python -X utf8 scripts/check_reader_copy.py --copy $Copy --record $SourceRecord
```

| 检查情况 | 处理 |
| --- | --- |
| 命令通过 | 只证明记录与文案一致；与原始材料的差异仍须单独报告 |
| 发现无关的既有缺陷 | 报告缺陷，不扩大修改范围 |
| 适用写法仍有具体疑问 | 定位对应条件实例；未决事实回来源，不启动完整生产流程 |

汇报实际修正及检查结果后结束。不生成 R、不发布、不创建复核角色或生产报告。

## Offline-download

`--prepare-download` 检查来源方案和选择清单，生成动作 JSON 及目录快照。
动作内包含浏览器指令，但准备过程不执行指令、不连接网址，不需要浏览器、登录或网络。

输入为过程目录中的已有方案和选择文件、数据库、网站地址、本地下载目录及正式目录。
使用提供的路径；输出目录缺失时可创建。

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --action-file "$Process/download_action.json" --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

| 情况 | 处理 |
| --- | --- |
| 命令成功，且两个 JSON 文件存在并可解析 | 汇报文件路径后结束；只有交接说明不算完成 |
| 已有下载尝试 | 保留原尝试，不覆盖它重新准备 |
| 准备失败 | 报告实际错误，不用尚未执行的命令冒充完成 |

本入口不执行浏览器动作、不等下载、不安装包，也不登记下载阶段已完成。
只有实际下载已获授权时，才继续第2步的 Download Commands 和浏览器会话准备。

## Historical-report

对已结束的完整定义报告运行：

```powershell
& $Python -X utf8 scripts/execution_report.py check --report $Report
```

- 命令复用完成检查，但不保存或更新报告。
- 如实报告缺失登记和失败检查。
- 通过只证明按当时策略登记完整，不证明历史研究、计算或复核内容正确。
- 不重跑生产，不补造耗时。
- 非完整定义报告或尚未结束的报告不在本入口范围内；说明限制，不代记完成。
