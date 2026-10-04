# 2. 选择与下载

执行记录：本步 `stage_id` 为 `download`。

若任务仅要求离线准备交接文件，直接使用 [离线准备](../scoped-tasks.md#offline-download)，不要连接浏览器或执行下方完整下载流程。`--prepare-download` 只生成本地动作和快照；生成的动作交给浏览器执行才会联网下载。

## 本步执行与验收

- 输入：执行者已核对的来源方案、完整身份和别名清单
- 另读：所选数据库 workflow 的选择、预览、落盘部分；[共用浏览器会话](../write-boundaries.md#浏览器会话)和[来源缺口](../write-boundaries.md#来源缺口)
- 执行：按共同浏览器规则连接 Chrome 或 Edge，确认登录、选择和实际下载目录，再执行下方固定下载动作一次；核对本次包和 raw
- 交付：当前下载包、原样 raw/codebook、下载凭据和实际取值/路径记录
- 程序检查：prepare-download 直接检查选择；恢复与正式 R 前来源检查对账清单、包内原文件和实际路径人数
- 模型判断：原始取值是否与问卷含义相符；数据异常是否要求修订方案
- 未通过：来源或别名变更回到方案并重新全量下载；下载失败查同次尝试，不重复点击

进入下载前由 prepare-download 校验来源方案、用途、别名和未解决问题。新流程在下载前验证双路探索及主线程合并已完成，不另派下载前审核；第4步复核实现是否符合合并方案。旧执行报告仍按原有要求校验，不手改历史记录跳过审核。

通过本步才交接给下一步；一次命令或点击不是一个独立验收环节。只读复核者接收本步稳定输入、对应标准及具体问题，不接收整个历史对话。

## 来源命名

### 1.1 通用命名

- 变量名在含义清楚的前提下保持简短，优先使用领域内稳定、容易辨认的共同前缀和词干。
- 命名前检查已有正式变量系列；存在明确系列关系时复用共同前缀，并一次性确认相关变量是否需要同步命名。
- 不把处理步骤或解释性长句塞进变量名，也不能删掉区分即时/延迟、状态/数量、单项/汇总等含义所需的核心维度。
- 数据库或主题已经裁决的前缀可以继续使用，不机械复制到其它数据库。

### 1.2 来源别名必须在下载前确定

- 先确认来源身份和研究关系，再决定别名。只有题义和适用对象一致、合并时使用相同编码表达相同含义，并且在不同调查时期互相补充的直接来源，才使用同一词干和 `_1`、`_2` 等顺序后缀。原始编码不同时，在来源探索阶段确定能否统一及对应关系，R按方案重编码后再合并。顺序同时表示正式合并时的优先级，必须在下载前写清。
- 预载、上一轮回答、代理回答、补充模块、外部派生或其它身份不同的来源使用能说明身份的语义后缀，不混入直接来源的顺序组。不同文件或模块中的同名变量必须设置能够区分来源的唯一别名；无需额外区分来源身份、且不受变量族统一命名约束的无重名变量，保留原变量名，不额外添加文件或模块后缀。
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

### 固定选择与别名输入

从主线程已合并的 `READY` 来源记录生成选择清单：每个来源组的 `source_identities` 保存网站完整 `Variable (File)`，与 `raw_variables` 中的最终下载别名逐项对应。同一来源可被多个概念引用，程序按完整身份去重；同一身份出现不同别名、不同身份共用别名或对应项缺失时停止，不替执行者猜测。旧记录只有文件名时，先依据已取得的证据补全身份。

先离线生成动作及下载别名清单，两者来自同一输入，不从网页再抄一份：

```powershell
& $Python -X utf8 "$Skill/scripts/prepare_source_selection.py" --config $Config --database $Database --record "$Process/definition_search_record.json" --action-file "$Process/selection_action.json" --expect-vars-file "$Process/download_selection.txt"
& $Python -X utf8 "$Skill/scripts/playwright_session_action.py" --config $Config --mode select --database $Database --action "$Process/selection_action.json" --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out "$Process/selection_result.json"
```

固定动作只操作绑定页：检查页面和登录，打开批量输入框，填入完整清单，点击一次确认，核对网站返回的无效项，并确认页面最终已选来源的完整身份、别名及数量与本任务清单一致，且加载已经结束；不能仅凭数量相等认定选择完成。别名由网站原有输入功能设置；不另写 `addTag`、直接请求验证接口或修改页面 DOM 的脚本，不预先清空旧选择，不逐项重复探索已确定的来源。

| 返回 | 处理 |
| --- | --- |
| `SELECTION_READY` | 选择完成，继续已有下载步骤；仍须通过原有包内来源核对 |
| `LOGIN_REQUIRED` | 按共用登录步骤交还用户，登录后再执行选择 |
| `SOURCE_REJECTED` / `SELECTION_COUNT_MISMATCH` / `SELECTION_CONTENT_MISMATCH` | 不下载；只调查返回的缺项、身份、别名或数量差异，需要修改方案时返回来源探索 |
| `INPUT_DIALOG_ALREADY_OPEN` | 保留现场，确认是本任务未提交的输入后关闭，再运行固定动作 |
| `WRONG_PAGE` / 控件变化 / 登录状态未知 | 核实绑定页或页面结构，不换页猜选项 |
| `SELECTION_UNCERTAIN` / `SESSION_UNAVAILABLE_OR_UNCERTAIN` | 保存结果并检查原页是否仍在处理；未确认结束前不重发。已结束但状态不明时重新按完整清单选择，不触发下载 |

此入口适用于 CHARLS、ELSA、Full HRS 的现有批量输入页面。已有独立 `Variable (File)=alias` 清单仍可用兼容参数 `--input`，新流程不再另抄一份。来源含输入分隔符或页面不再支持此格式时明确报告，不静默删改身份。离线生成成功只证明输入格式成立，不证明来源存在、已登录或获准下载；原下载准备检查仍须通过。

复用已记录的Chrome/Edge会话和本任务标签页，确认登录、来源清单和最终下载控件。`$Downloads`是执行入口保存动作结果及ZIP的目录，不猜测系统Downloads。新设备与绑定方法见[浏览器会话](../write-boundaries.md#浏览器会话)。

1. 运行一次本地准备，建立快照和唯一尝试。成功后直接使用生成的动作文件，不复制脚本或重复准备：

```powershell
$Action = "$Process/download_action.json"
& $Python -X utf8 scripts/recover_dbcodebook_export.py --prepare-download $Downloads --snapshot-file "$Process/download_before.json" --action-file $Action --database $Database --base-url $BaseUrl --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

2. 同一会话执行一次动作。入口在最终点击前建立下载事件监听，点击后等待事件、保存文件并返回实际路径；分派前原子登记尝试，连接丢失不允许重新分派同次付费动作：

```powershell
& $Python -X utf8 scripts/playwright_session_action.py --config $Config --mode download --action $Action --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out $Result
```

3. 返回 `DOWNLOAD_FILE_READY` 时将 `download_path` 原样作为 `$Archive`，校验并安装：

```powershell
& $Python -X utf8 scripts/recover_dbcodebook_export.py --archive $Archive --database $Database --out $Formal --expect-vars-file "$Process/download_selection.txt"
```

有意替换现有正式raw时才加 `--overwrite`。返回 `run_watch_command` 时运行原快照对应的观察命令；观察器已安装文件则不重复安装。变量清单及包内CSV通过校验才算成功，点击返回或尝试已登记不等于文件已到达。

正常导出验收必须证明本次选择页的新包完整落盘，不能用找回测试替代。包安装核验结束下载计时；下载后实际取值、路径人数与方案修订另记sources工作或返工段。

## 下载结果与找回

| 结果 | 下一步 |
| --- | --- |
| 本次新包已校验安装 | 继续定义，不再等事件、找回或重下 |
| 临时文件仍在下载 | 保留原页和原快照继续观察，不重新准备 |
| 没有匹配文件 | 查看同次下载记录，不据此认定未生成或再次付费 |
| 多个匹配文件 | 辨明本次文件，不自动选最新一个 |

仅接受相对快照新增或变化、稳定且完整校验的包；旧包、临时文件及来源不符的包不作结果。分派前认领不能证明已点击，失败需根据原动作结果区分未点击、已提交和文件未取得。

固定入口返回 `DOWNLOAD_NOT_CLICKED` 且 `operation_completed=true`、`click_requested=false` 时，表示本次动作已结束且尚未调用最终下载点击。保留原动作、快照、尝试记录和返回结果，修复原因后，在原有下载授权范围内以新的动作、快照和结果文件名重新运行第1步准备，建立新尝试；不重发原动作，不覆盖旧文件。已经调用点击、已提交或提交状态不明时，按观察、找回及付费重试规则处理；超时、连接中断或未发现文件不证明没有点击。

没有文件时，在原浏览器按本次时间、数据库、来源及别名核对下载记录。已有对应记录且下载环境可用时才使用其找回入口，不重新导出。直接下载链接先建立 `page.waitForEvent("download")` 再点击已核实链接，以 `saveAs` 保存到本次目录，再走同一archive校验。页面显示“已找回”不代表落盘；仍无文件时保留事实，不消耗其它找回机会。

只有确证浏览器关闭或崩溃导致失败时，先用 `tests/probe_browser_download.py --browser msedge --config $Config --out <独立测试目录>`（Chrome用chrome）做免费本地19MB下载测试；它仅关闭自己的临时会话，不访问网站。测试通过只证明测试环境可落盘，不证明生产会话恢复。生产会话确已关闭才用原配置恢复并重新绑定；不凭saveAs错误断言崩溃，不新建登录挤掉其它任务。

观察或找回均不授权重新付费导出。重试前说明已有记录及文件状态；不明确或仍在下载时停止重试。用户已授权付费复测时，在确认前次未成功且无进行中的下载后沿用授权，不重复确认；该授权不包括改网站、重启服务或切换浏览器。

## 记录字段的阶段边界

下载后某个实际取值涉及哪些时期，直接从逐期统计提取，再用于探索记录和R注释，不手写另一份时期清单。可运行 `scripts/observed_value_periods.py --raw <raw_data.csv> --variable <raw_data.csv中的实际列名> --value <完整原值> --period-column <时期列> --out <过程目录/取值时期.json>`；仅在已确认ID由“时期+分隔符+身份”组成时改传ID列并加 `--id-separator <分隔符>`。这只证明实际出现范围，不能反推问卷施测范围或缺失原因。

下表右列在各自环节完成：实际人数归下载后数据核实；问卷展示标记归文案完成。不能在下载结束时提前填文案已展示。

| 字段 | 下载前 | 后续要求与完成时点 |
| --- | --- | --- |
| status / logic_review.result | READY；clear 或 reported_and_resolved，未决问题不得掩盖 | 继续保留真实结论 |
| directory_entries / discovery.value | 完整 UI 路径且 verified_in_ui=true；discovery 指向已登记条目 | 保留同一来源身份 |
| 单期 source_group | handling_decision=single_period | 与实际时期核对 |
| questionnaire_evidence | 官方完整题文、选项、路径；local_material_path 相对本数据库材料根 | 文案完成后：rendered_in_copy=true、copy_locator 指向实际文案 |
| questionnaire_path_closure | 真实进入/退出条件；未知人数和统计结论用 null | 下载后数据核实、正式 R 前：observed_count 为非负整数，unexplained_count=0，实际闭合有依据 |
| human_record / evidence_steps | 探索记录存在同号 S001 等步骤标题 | 沿用可追溯步骤，不为过检查编造观察 |

跨期复用同一 raw 列但题义变化时，按研究概念登记来源组，在各组列出准确单期与路由；组间可以共享该 raw，下载清单只保留一次。不能把不同题义合并成一个定义，也不在下载后复制列以绕过去重。

材料路径正例：`官方问卷/2011/2011 家户问卷.pdf`；反例：`references/source-materials/charls/官方问卷/...`。`locator` 是页码/题号/章节定位，不是第二个文件路径；同一个材料文件统一使用前述相对路径。校验器提示基址错误时按提示改记录，不自动改选另一份材料。
