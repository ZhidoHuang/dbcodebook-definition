# NHANES 数据库差异

- 网站入口为 `/home/`，不与 NHANES III、Harmonized 或 KNHANES 混用。
- 来源身份为 `Variable` 与 `数据源类型`。当前只接入“常规(唯一SEQN)”。同名变量不能跨数据源类型替换。
- 普通来源导出 `raw_data.csv` 和 `raw_codebook.csv`。默认列 `SEQN`、`YEAR` 不作为业务变量重复选择。
- 在公开 R 中按字符读取并保留 `SEQN`、`YEAR`。最终长表按这两列检查唯一性；同一 SEQN 在不同周期不自动合并。
- `YEAR` 保留原周期字符串，例如 `2017-2018`。重叠周期仍分别保留；是否选用或排除某个周期由已确定的主题方案决定。
- 字典用 `Variable`、`File type`、`newname` 对应原变量、文件层级及下载别名。普通来源的 `File type` 为 `uniqID`。
- 重复明细、受限数据及其他数据源类型不在本次接入范围。
