# KNHANES profile（Core data 人口学已完成真实流程）

正式入口 `/home/knhanes/`。网站时期1998、2001、2005、2007–2024；未来时期须重新核实契约。重复横断面，记录单位为受访者×调查年，不能解释为纵向随访。

原身份为字符串id与调查年year，派生ID为trim(year)+下划线+trim(id)。保留前导零和字母，不数值化个人号。普通文件必须id-year唯一；网站按ID外合并，身份冲突报错。完整来源身份使用Variable (File)中的原英文文件名，不能仅Variable选择同名来源。id/year自动随包附带，不加入选择别名。

重复文件：Dietary recall detail、Dietary recall second day、Dietary supplement detail、Physical activity monitor。包内独立CSV，身份前缀RowIndex,ID,id,year；RowIndex是该文件1..n行序号，不是跨版本稳定记录ID。允许重复个人年，不允许直接与个人年表一对多连接后当作唯一受访者。

本profile是网站观察/源码契约，具体题义、缺失与时期变更由主题研究和真实字典决定。合成测试不能证明真实导出或生产验收。
