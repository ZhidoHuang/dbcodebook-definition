# SHARE 个人唯一记录接入契约

本接入仅针对普通 Wave 1–9 的 personal `uniqID` 文件。隔离fixture通过不等于真实下载或完整成品验收。Corona、SHARELIFE独立记录层级、重复明细、国家及访员文件须另核契约，当前不支持这些文件进入此接入。

- 网站原始入口 `/home/share/` 与 Harmonized SHARE 为不同产品。
- 使用网站完整 `Variable (File)` 身份和下载前别名；同名来源不合并猜测。
- `ID` 是平台原样字符串。个人跨期身份为 `mergeid`，当期唯一键为 `Wave_id + mergeid`；不解析或重建ID，也不把问卷版本 `waveid` 当调查Wave。
- 同一mergeid可跨期出现，ID及当期个人键都须非空且唯一。国家、家庭和访员标识按实际包保留字符身份。
- 所选个人文件合并为 `raw_data.csv`。字典列为 `Variable,Label,Period,File type,Match key,newname`；此次契约要求类型为 `uniqID`、连接说明为 `Wave_id + mergeid（ID）`。
- 自动标识列可包含ID、Wave_id、Record_id、mergeid、hhid、country、intid、intidwX。多个来源同时有intid时保留 `intid (实际来源文件名)`；不将它误判为漏选业务变量，也不重命名原CSV表头。
- 来源值可能已经是发布标签字符串。按本次实际字典和官方材料解释，不能只调用数值转换而静默丢失标签。

这些接口事实已由2026-10-05人口学正式包核实：26个来源、731726条原始记录，完整header、唯一键和本主题实际取值已检查。网站导出包没有明确的release标识，不能把所用官方文档版本当作包版本；其他来源仍须按实际下载包核实。
