# 可选的本地字典证据接口

普通版无需本地字典或开发者技能，可独立使用网页流程。本页只供提供本地来源证据的入口接入；不包含本机路径和查询实现。

接口版本由 `references/source-evidence-contract.json` 声明。当前 `local_dictionary_api=1`。

## 接收内容

- 来源记录使用现有格式版本7。增加 `source_access.mode="local_dictionary"`、绑定文件引用 `binding` 和查询结果引用数组 `receipts`。
- 每个文件引用含 `path` 和 `sha256`；相对路径以来源记录所在目录为基准。
- 绑定格式为 `dbcodebook.local-binding.v1`：保存数据库、KLoSA语言、网站地址、字典指纹及 `runtime_settings_same_file` 对应证据。
- 查询格式为 `dbcodebook.local-source.v1`：保存绑定哈希、字典指纹、实际动作、目录和来源结果。详情逐期保存实际来源身份，不推算变量名前缀。
- 目录标记为 `verified_in_ui=false`、`verified_in_local_dictionary=true`；只有证据中实际出现的路径才可登记。
- 来源组的 `discovery.mode` 使用 `local_dictionary`。其 `value` 指向已登记目录或查询过的关键词。
- 本地步骤使用 `local_dictionary_query`，不伪填网页步骤。没有进行网页检索时，`normal_searches` 如实填写 `performed=false` 及原因。

## 保留的要求

1. 普通网页记录没有 `source_access`，继续要求已核实的网页目录，原检查不变。
2. 本地记录检查文件哈希、绑定一致性、数据库、网站、语言、目录及所选来源和时期覆盖。失败时修复对应证据，不改成网页已核实。
3. 本地证据不是官方问卷认证；`local_dictionary_query` 不替代问卷要求的 `official_material_review`。
4. 主线程仍比较双路建议，确认定义方案后交接；附加证据不自动批准方案。
5. 网站批量选择、别名、下载包和实际 raw 的检查保持不变。本地字典不能替代正式下载。
6. 下游核对保存的证据，不要求另一台设备重新连接旧设备字典。重新查询时，由开发者入口重新核实本机对应关系。

程序验证只证明保存的记录符合接口及对应关系，不证明研究充分或字典内容正确。
