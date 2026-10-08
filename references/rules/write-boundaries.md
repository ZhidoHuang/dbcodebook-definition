# 定义任务角色与写入边界规则

## 适用范围

本规则适用于所有数据库变量定义、返修和正式重生任务。

## 允许写入

定义任务只允许写入：

1. 当前主题正式目录；
2. 当前主题执行目录；
3. 主题完成后需要原位更新的主题索引和定义验收台账。

除此之外的写入，必须拆成独立任务，并由用户明确批准。

## 定义角色

定义任务负责从现有来源中检索、选择、解释和定义变量，并生成当前主题的正式成果。它不是网站维护、数据库维护或上游数据加工任务。

定义任务可以：

1. 使用 dbCodeBook 已有页面和既有接口进行目录浏览、普通检索、变量选择和数据下载；
2. 只读查看网站源码、生产数据、官方材料、Harmonized 材料和既有定义，用于理解来源与核对事实。

通过网站正常浏览、检索、选择和下载时，由网站自行产生的会话、下载、积分或审计记录属于网站正常运行，不属于定义任务篡改数据。

## 禁止越界

定义任务不得：

1. 修改网站源码、网页逻辑、数据库脚本、生产数据库、生产数据或旧数据库副本；
2. 直接执行 SQL、ORM 写操作、迁移、导入、同步、修库脚本或文件级编辑，改变网站或数据库内容；
3. 因网站缺少变量而修改上游数据、网页、目录、下载逻辑或数据库生成逻辑；
4. 从本地 DTA、Parquet、旧下载包、既有主题数据、Harmonized 数据或其它数据库文件补列、拼接、替换或重建正式 raw；
5. 为绕过路径或写入限制创建、修改或删除 `SUBST` 盘符映射；
6. 修改其它主题，或把网站维护、数据修复和定义工作混在同一个任务中。

正式 raw 只能来自 dbCodeBook 网站本次实际下载的数据包。官方材料、Harmonized 数据和其它本地资料只能用于理解与核对，不能替代网站下载数据。

- 是否需要重新下载，只看最终来源清单有没有变化，不看主题是新建、拆分还是改名。
- 来源清单中的变量、周期、文件、来源身份或最终别名只要有一项变化，就按改变后的完整清单从网站一次重新下载；不得筛选旧包或拼接补充下载。
- 来源清单没有变化时，不因文案、展示、注释、主题编号或同一批 raw 上的实现调整重复下载。

## 浏览器会话

- 新设备或 Node/CLI 更新后，先运行 `scripts/check_definition_environment.py --config $Config --mode browser --browser msedge`（按实际选择改为 chrome）。
- 它离线检查 Python、Node、已缓存 CLI 和所选浏览器程序，不安装软件或打开网页；通过不表示已控制浏览器或登录成功。
- 仅同步网站无需检查 R。
- 已验证且未变化的环境不重复检查。

- dbCodeBook 的网页探索、变量选择、下载和网站同步只使用 Chrome 或 Edge，不再使用 Codex 内置浏览器，即使内置浏览器已经打开相关页面也不复用。
- 用户指定哪一个就使用哪一个；未指定时，在 Chrome 和 Edge 中优先复用已连接且已登录 dbCodeBook 的会话，尚无可复用会话时默认 Chrome。
- 选定后，本任务始终沿用该浏览器，不因失败自动切换到另一个浏览器、内置浏览器或临时访客配置。

- 使用本地 Playwright CLI 直接控制已安装的 Chrome 或 Edge，不需要、不安装 ChatGPT 扩展，不走 Browser/Chrome 插件连接。
- 先读取可用的 Playwright 技能。
- 首次启动明确指定 `--browser msedge` 或 `--browser chrome`，不使用默认 Chromium；使用独立的持久配置目录，不能复制普通浏览器的配置或 Cookie。
- 首次会话可能需要登录；验证码由用户在页面输入。
- 浏览器窗口打开不等于控制成功，须实际读取页面、确认登录并完成一次无写入副作用的目录操作。

- 在现有执行报告中记录浏览器、CLI 会话名、启动工作目录、持久配置目录及本任务标签页绑定。
- 同一主题续办复用这些值，不重复 `open`、清空会话或另建配置。
- 会话确已关闭才用原配置重新打开。
- 共享会话并发必须使用下方标签页绑定入口，不能使用依赖当前页的CLI命令。
- 其中 `dbCodeBookBrowser` 是执行入口内部提供的兼容对象，不需要模型配置扩展。

- 网站单登录时，多个定义共用一个已登录浏览器、各占一个标签页。
- 不要运行topic_browser.py为每个主题新建登录配置。
- 首次用tab-list观察页号和URL，绑定为稳定target ID；后续即使页号变化也不能改用当前页。
- 每个任务只操作自己的标签，不关闭或重启整个浏览器，不修改另一任务的标签或同一篇文章。
- 正文、动作文件和下载结果仍使用各自主题目录。

```powershell
$Binding = & $Python -X utf8 "$Skill/scripts/playwright_session_action.py" --config $Config --mode bind --tab-index $ObservedTabIndex --session $Session --session-workdir $SessionWorkdir --out "$Process/browser-binding.json" | ConvertFrom-Json
$TabId = $Binding.tab_id
```

- 绑定结果的url必须是本任务刚观察到的页面。
- 绑定只读取浏览器target ID，不写网站属性、Cookie或会话。
- 标签关闭后明确停止，不悄悄替换成另一页。
- 探索时用同一入口的 `--mode tab-code --tab-id $TabId --script <本地JS文件>`；脚本为 `async page => {...}`，page即绑定页，只对它执行导航、读取DOM、点击和填写，返回JSON。
- 用 `page.locator('body').ariaSnapshot()` 读取本页可见结构；不得在脚本内另选context.pages()、切换当前页或关闭context。
- 并发中禁止裸用CLI的click、fill、upload、goto、tab-select、open及close等共享当前页命令。

- 网站同步直接使用[第8步的网站准备入口](stages/08-website.md#1-准备与预检)检查登录及编辑页，不另做目录操作。
- 以下 login-status/login-open 仅用于本数据库选择页；它只读取页面公开的登录布尔状态，不读取密码、验证码或 Cookie：

```powershell
& $Python -X utf8 "$Skill/scripts/playwright_session_action.py" --config $Config --mode login-status --database $Database --session $Session --session-workdir $SessionWorkdir --tab-id $TabId --out "$Process/login_result.json"
```

- `LOGGED_IN` 才继续。
- `LOGIN_REQUIRED` 时将同一命令的 mode 改为 `login-open`，在原标签打开网站登录面板，请用户完成登录；用户告知完成后重跑 `login-status`。
- 登录等待单独计时，不反复轮询，不代填验证码。
- `LOGIN_STATE_UNKNOWN` 或 `WRONG_PAGE` 先核实页面；连接失败保留原会话，不能据此断言会话关闭。
- 只有确证已关闭才按下方原配置 open、重新观察并绑定标签。
- 随后按[固定选择入口](stages/02-download.md#固定选择与别名输入)输入已定来源和别名。

- 绑定入口在操作前监听本标签的原生弹窗：仅对消息含“清空…标签”的 confirm 自动取消，并返回 `native_dialogs` 记录。
- 这表示清空没有执行；后续按固定选择入口替换标签，不反复点击清空。
- 其它弹窗不自动确认。
- 若 CLI 因弹窗提前返回空结果，入口只取回同次操作结果，不重放点击、下载或提交。
- 操作开始前已存在的原生弹窗仍可能阻塞 CLI，此时明确请用户取消，不切换共享当前页或重载绕过。

- 这不是沙箱：绑定解决固定动作误选页，不阻止任意脚本故意操作其他页。
- 多任务分配不同标签是执行前提；同一主题不能由两个主执行者并发续办。
- 已验证本地双进程的填写、直接文件输入和下载互不串页；真实网站并发下载及发布尚待实测，不能据此宣称端到端已验收。

- 预检与正式动作共用同一个 CLI 解析入口。
- 优先使用配置 executables.playwright_cli；填写 JS 入口时同时配置 executables.node，无需 npm/npx。
- 没有显式配置时使用 PATH 中的 playwright-cli，再退到 npx 离线缓存；运行中不联网装包或生成伪造的 npx 包装器。
- 缓存缺失只在环境准备时安装一次。
- 配置指向的文件不存在时明确失败，不偷偷换入口。

```powershell
# $SessionWorkdir / $Profile 来自本次记录，不把机器路径写入公共规则。
Set-Location $SessionWorkdir
$Cli = @((& $Python -X utf8 "$Skill/scripts/skill_config.py" --config $Config --browser-cli | ConvertFrom-Json).browser_cli)
$CliArgs = @($Cli | Select-Object -Skip 1)
& $Cli[0] @CliArgs "-s=$Session" snapshot --filename "$Process/browser-state.md"
# 仅首次建立或确认会话已关闭时执行 open：
& $Cli[0] @CliArgs "-s=$Session" open $PageUrl --browser msedge --headed --profile $Profile
```

- 全页快照保存到上述文件后，只读取当前操作需要的目录、搜索结果或对话框段落，不把整页表格输出到模型上下文。
- 当前CLI支持 `find <text>` 搜索可见快照及 `snapshot <已观察到的ref或唯一选择器>` 获取局部；先通过 `--help` 核实本机版本支持。
- 操作已返回快照文件时直接按需读取，不紧接着再输出一次全页 snapshot。
- 元素变化后重新获取相关范围，不复用旧引用。

- 下载与网站操作分别按[下载步骤](stages/02-download.md#download-commands)和[网站步骤](stages/08-website.md#website-only-commands)执行，完整动作JSON保存在本任务目录，不改写载荷或直接运行旧run_script。
- 绑定只解决操作页的选择，不代替身份和内容检查。
- CLI生成的快照不得将密码、验证码或Cookie带入报告、Git或交接。

## 来源缺口

正常目录浏览、检索和下载无法提供必要来源时，停止受影响的定义工作并报告缺口，不改造网站或从本地资料补列。网站或上游数据维护属于另一项明确授权的工作；完成后再从网站取得所需来源。

## 网站发布权限

派发任务时，从用户已授权范围明确写出“本地完成”或“包含网站同步”，同步还要明确新建还是更新哪篇文章；不只写“完整定义”。这是整理已有授权，不要求重复向用户确认，也不扩大发布权限。

- 定义与生成阶段不提前写网站。
- 用户已确认：修改或更新定义主题内容，包含更新对应网站文章；完成生成、检查和成品交接后连续同步，由用户在网站检查，不重复询问同步授权。
- 只读审核或只修改 Skill 不产生主题发布任务。用户明确限定“只改本地”或“不生成、不同步”时，按该限定执行。新建文章仍须有新建主题或发布任务的授权，不将更新现有文章擅自改成另建文章。
- 只同步已验收成果时不重跑探索、问卷或定义流程。

- 发布使用网站正常页面和固定入口，不直接写SQL、ORM、数据库文件或临时同步脚本。
- 超时、附件较大或普通发布失败不构成绕过理由。
- 具体对象、附件、提交和失败处理只按[第8步](stages/08-website.md)，本文件不另列一套操作。

## 执行方式

按实际行为判断是否越界，不为网站、数据库或源目录新建哈希基线，也不每次运行R前后扫描它们。正式runner检查定义脚本、来源记录及成果，不能用机器未发现变化代替权限判断。
