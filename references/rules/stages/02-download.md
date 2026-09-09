# 2. 选择与下载

## 本步执行与验收

- 输入：已复核的来源方案、完整身份和别名清单
- 另读：所选数据库 workflow 的选择、预览、落盘部分；[写入边界](../write-boundaries.md) 中下载与来源缺口部分
- 执行：按共同浏览器规则连接 Chrome 或 Edge，确认登录、选择和实际下载目录，再执行下方固定下载动作一次；核对本次包和 raw
- 交付：当前下载包、原样 raw/codebook、下载凭据和实际取值/路径记录
- 程序检查：prepare-download 直接检查选择；恢复与正式 R 前来源检查对账清单、包内原文件和实际路径人数
- 模型判断：原始取值是否与问卷含义相符；数据异常是否要求修订方案
- 未通过：来源或别名变更回到方案并重新全量下载；下载失败查同次尝试，不重复点击

进入下载前，用 `execution_report.py review-check --process-dir $Process --role "定义逻辑复核"` 核对当前或可沿用的来源复核；prepare-download 随后检查已登记结论，缺失或过期时不生成浏览器写入动作。

通过本步才交接给下一步；一次命令或点击不是一个独立验收环节。只读复核者接收本步稳定输入、对应标准及具体问题，不接收整个历史对话。

## 来源命名

### 1.1 通用命名

- 变量名在含义清楚的前提下保持简短，优先使用领域内稳定、容易辨认的共同前缀和词干。
- 命名前检查已有正式变量系列；存在明确系列关系时复用共同前缀，并一次性确认相关变量是否需要同步命名。
- 不把处理步骤或解释性长句塞进变量名，也不能删掉区分即时/延迟、状态/数量、单项/汇总等含义所需的核心维度。
- 数据库或主题已经裁决的前缀可以继续使用，不机械复制到其它数据库。

### 1.2 来源别名必须在下载前确定

- 先确认来源身份和研究关系，再决定别名。只有题义、编码和适用对象一致，并且在不同调查时期互相补充的直接来源，才使用同一词干和 `_1`、`_2` 等顺序后缀。顺序同时表示正式合并时的优先级，必须在下载前写清。
- 预载、上一轮回答、代理回答、补充模块、外部派生或其它身份不同的来源使用能说明身份的语义后缀，不混入直接来源的顺序组。不同文件或模块中的同名变量必须设置能够区分来源的唯一别名；当前来源清单中没有重名冲突的变量保留原变量名，不额外添加文件或模块后缀。
- 按成员编号重复展开的变量按完整变量族处理。只要其中一个成员需要调查时期、模块或来源后缀，整组成员都使用同一后缀；不得只给发生重名的个别成员改名。完整别名模式和编号范围写入 `definition_search_record.json` 的 `alias_families`。
- 最终别名在 dbCodeBook 页面选择变量时设置。重新下载后的 `raw_data.csv` 和 `raw_codebook.csv` 必须直接带有这些别名；不得下载后修改 CSV 表头，也不得在正式 R 中复制、改名或按列位置制造别名。
- 正式 raw、codebook、公开 R、mapping 和完整定义链路保留每个来源的完整别名。面向读者的紧凑来源图可以把已经核实属于同一组的重复成员合并成范围标签，但该标签只用于展示，不能反向改变正式来源清单。
- `definition_search_record.json` 记录来源关系、最终别名和变量族；数据库专属流程负责规定页面选择清单、预览检查、下载与恢复方法。记录模板和任务卡只保存本次事实，不另立命名规则。
- 最终手动选择的来源字段必须至少承担一种明确作用：参与定义、作为辅助判定条件，或执行本主题实际需要并会报告结论的验证。仅用于“顺便保留”“可能链接”“标记来源版本”而未在当前主题使用的字段不得纳入。平台自动提供且正式输出必需的记录键单独管理，不用无关业务字段代替记录键。

#### 先按出现位置区分三种变量关系

本流程有三种外观相近但用途不同的变量关系。读到“原始变量名映射”“来源映射”或“变量对应”时，先确认它出现在下面哪一个位置，再读取和修改；不能把一种关系的格式或取舍套到另一种关系上。

| 出现位置 | 它解决什么问题 | 必须怎样写 |
| --- | --- | --- |
| `材料 → 1-提取变量` | 生成可以直接粘贴到 dbCodeBook 网站批量输入框的选项 | 每个来源写成 `网站完整原始变量身份=下载别名`。左侧逐字取自 `raw_codebook.csv` 的 `Variable`，保留模块或文件括号；右侧逐字取自 `newname`。没有改名时左右仍各写一次。每项完整列出并用逗号分隔，不使用范围标签或解释性文字 |
| 正式 R 的 `add_mapping()`、`analysis_codebook` | 说明一个分析变量实际由哪些来源构成 | 追溯到全部参与赋值、路由、补值或完整性判断的原始变量；中间变量可以同时保留，但不能替代最初来源。只做独立验证而没有参与该变量生成的变量不写成其定义来源 |
| 定义卡变量名右侧的 `←` 来源 | 让读者查看该变量的完整定义来源 | 来源范围必须与正式 R 的 `add_mapping()` 完全一致，包括参与赋值、补零、缺失判定、路由和完整性判断的来源。公共渲染器直接读取 `analysis_codebook$processed_vars`，并从 `raw_codebook$Variable` 和 `raw_codebook$newname` 的同一行生成逐项完整的 `网站完整原始变量身份=下载别名`。正式 R 不得再为定义卡另设来源子集或展示文本 |

网站批量输入示例：

```text
da040 (health status and functioning)=da040,
zda040 (health status and functioning)=zda040,
ztooth (health status and functioning)=ztooth
```

上例左侧的括号属于网站原始变量身份，不能省略；右侧才是下载后的列名。生成时固定使用 `paste0(raw_codebook$Variable, "=", raw_codebook$newname)`，不从 `add_mapping()` 或定义卡来源文字反推。

## Download Commands

Read [browser session setup](../write-boundaries.md#浏览器会话) and [download execution](../write-boundaries.md#下载结果与找回). Bind the chosen connection as `dbCodeBookBrowser`, verify the source list and final download control in its logged-in tab, and set `$Downloads` to that browser's actual download directory. Then prepare the local observer:

Treat the variable-selection page's normal export as the primary download path. A test of recovery cannot substitute for a forward test of that normal export.

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

The command checks inputs and the output boundary before spending points, records the current files, assigns one attempt ID, and returns one `browser_action.run_script`. Run that script unchanged once through the browser skill's execution tool with its declared timeout. It uses the selected matching variable-selection page within `dbCodeBookBrowser`, otherwise locates the unique matching tab in that same connection, verifies the selected count, starts waiting for that tab's download, and clicks the final control once. An exclusive local attempt file beside the snapshot prevents a second click after a runtime reset without modifying the page. When it returns `DOWNLOAD_FILE_READY`, pass its `download_path` unchanged to `recover_dbcodebook_export.py --archive <download_path>` with the same database, output directory, selection file, and intentional `--overwrite` setting. A browser without a download-path interface returns `next_action: run_watch_command`; run the prepared observer rather than guessing a file API. If neither route verifies a file, inspect the existing paid record; never run the browser action again. Use `--overwrite` only for an intentional replacement of existing formal raw.
