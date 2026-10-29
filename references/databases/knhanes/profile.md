# KNHANES profile

正式入口 `/home/knhanes/`。网站时期1998、2001、2005、2007–2024；未来时期须重新核实契约。普通核心资料为重复横断面，记录单位为受访者×调查年，不能解释为纵向随访。

- 原身份为字符串id与时期标记year（普通核心资料为调查年，独立专项见下文），派生ID为trim(year)+下划线+trim(id)。
- 保留前导零和字母，不数值化个人号。
- 普通文件必须id-year唯一；网站按ID外合并，身份冲突报错。
- `Indoor air quality special release` 与 `Cycle 7 oral special release` 虽为uniqID，仍以 `raw_data_<英文文件名空格改下划线>.csv` 独立输出，保留ID/id/year，不带RowIndex。专项使用独立编号；没有经核实的Core桥接，不能因同名身份列连接记录。Core 与室内空气专项在同一主题按行交付时，按[差异流程](workflow.md#公开r与生成)保留样本身份。
- 空气质量专项实际调查为2020年7月至2021年8月，year=2021是网站栏目时期标记，不是逐行调查年。唯一性检查不证明它是2021年核心样本。
- 完整来源身份使用Variable (File)中的原英文文件名，不能仅Variable选择同名来源。
- id/year自动随包附带，不加入选择别名。

- 重复文件：Dietary recall detail、Dietary recall second day、Dietary supplement detail、Physical activity monitor。
- 包内独立CSV，身份前缀RowIndex,ID,id,year；RowIndex是该文件1..n行序号，不是跨版本稳定记录ID。
- 允许重复个人年，不允许直接与个人年表一对多连接后当作唯一受访者。

本profile是网站观察/源码契约，具体题义、缺失与时期变更由主题研究和真实字典决定。合成测试不能证明真实导出或生产验收。
