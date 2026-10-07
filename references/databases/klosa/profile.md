# KLoSA 接口与版本

网站有英文 `/home/klosa/en/` 与韩文 `/home/klosa/ko/` 两个产品入口，当前分别覆盖普通 Wave 1–9 与 Wave 1–10。来源计划、选择动作、下载快照、恢复记录和目录链接必须使用同一显式语言，不能将两版当成只换显示文字。

普通导出身份为 `ID`、`Harmonized_id`、`Wave_id`。ID保持原样，不能推断其内部编码或把Harmonized_id直接等同官方pid。普通表按ID连接，同时检查个人—时期唯一；插补表另带`RowIndex`、`v_imputation_`，不得当普通个人表去重。

普通CSV为`raw_data.csv`，插补为`raw_data_KLoSA_Imputation.csv`。字典六列为`Easy label`、`Base_Variable`、`Wave`、`Variable`、`File type`、`newname`。`Base_Variable`批量选择会展开并改变别名，因此当前固定选择须采用网页已经确认的具体`wXX`字段身份，不能凭变量命名自行猜出各期来源。

Core、str、Light、Exit及Imputation的对象与覆盖分别核实；同名字段不证明同一版本或同一对象。具体教育、年龄、婚姻等含义由当期材料与主题方案确定，不由本接口代定。

普通个人表韩文人口学已有完整成果检查通过及发布回执，范围见[数据库差异说明](workflow.md)。英文入口、插补分析和多文件主题不能据此视为通过。实验性固定source-read未纳入当前支持范围。
