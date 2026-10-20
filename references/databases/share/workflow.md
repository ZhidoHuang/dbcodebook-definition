# SHARE 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 下方只列普通个人唯一来源的接口差异及验证范围，身份和文件结构见 [profile](profile.md)。

- 当前选择、下载及生成接口仅覆盖普通 Wave 1–9 的个人唯一来源。
- 本文件不授权付费下载或网站发布。

1. 复用已绑定的原始SHARE标签，先确认本轮来源、身份、时期、别名及研究方法已确定，再使用公共选择入口。
   - 目录、搜索和详情使用[固定来源读取入口](../../rules/stages/01-source-plan.md#网页取证固定入口)，传 `--database share`。
   - 保持原有READY来源门禁及双路合并要求，不因程序已接受share参数而绕过来源问题。
2. 页面正常预览响应必须包含一个uniqID数据文件和完整Dictionary。新版还包含连接说明标签；按 profile 核对其中的时期、来源与个人连接关系。
   - 核对完整来源身份及别名、文件类型、match_key、header及样本行维度。
   - 超过50个来源的截断预览不能证明完整字典。
   - `share_export_contract.validate_unique_preview`只检查已取得的正常UI响应，不调用网站接口，不把样本键检查当全文件验收。
3. 在用户已授权的下载范围内，按公共固定入口发起一次下载；通过 `--database share` 校验本次新包，再落盘。
   - 当前接入遇到其他层级文件、特殊时期、重复ID或个人—时期键、未知自动标识列及漏选/多选业务列须停止，不能自动拼接或选错文件。
4. R保留字符型ID、Wave_id、mergeid及实际身份列。
   - 明示普通Wave顺序。
   - 公共生成器只在本地展示副本提供year兼容列，不改原raw或解析ID；未知Wave、空/重复键先失败，再生成输出。
5. `check_definition_output.py --db share`检验完整个人键组合来自raw，以及原数据header/字典契约；分析样本可经已定义的本人访谈筛选，但不能换Wave、改变mergeid或多次重复同一记录。

- Corona、SHARELIFE 独立记录层级及重复明细不在当前接入范围。
- 不得拿网站存量parquet生成正式raw。
