# ELSA 数据库差异说明

- 通用流程按[公共规则](../../rules/validation.md)执行。
- 本页只补充当前环节涉及的 ELSA 差异；稳定身份、文件族、对象和编码见 [profile](profile.md)，材料从[统一材料索引](../../source-materials/材料索引.md)进入。

## 来源探索

- 页面由配置中的 `website.database_paths.elsa` 确定。读取页面 Label，记录完整 `Variable (File)`、Wave、文件族及对象。
- 同名来源跨 File 分开识别，例如 `palevel (Core data)` 与 `palevel (Derived Variables)`。
- Core、COVID、Wave 0、Nurse、Life History、End of Life、HCAP、Nutrition、Pension Grid 和 Harmonised ELSA 的边界见 profile。
- 核实 core member、partner、proxy、copied value、refreshment sample 及访谈 outcome 的含义；是否纳入由本次方案决定。
- 权重核实其对象、Wave及横断面或纵向用途。
- Harmonised ELSA 和官方派生说明可用于理解方法。
- 来源取舍、文献探索和未决问题处理按[第1步](../../rules/stages/01-source-plan.md)，不因出现多个候选就固定停下来等待用户。

## 选择与下载

使用[第2步固定入口](../../rules/stages/02-download.md)，数据库参数为 `elsa`。

- 预览核对 File/Wave 覆盖、记录数和文件分组。
- 普通个人来源 raw header 按 `ID, idauniq, <selected variables...>` 核实，不套用 CHARLS 的 `id/year`。
- codebook 同时保留 `Variable (File)` 与 `newname`；恢复结果保留 variable、file、transaction 和文件列表，不去掉 File 后用裸变量对账。
- Nutrition detail、Pension Grid 等重复明细不能套用普通个人表的 header 或唯一键，先按实际文件结构及支持范围确认。

## R 与生成

- 正式个人—Wave对象保留 `ID, idauniq, Wave`；`Wave` 从平台 `ID` 提取，使用 `Wave 1`、`Wave 2` 等文本，raw 不变。
- 无法解析的 ID 不猜写时期。
- `idauniq` 跨 Wave 重复属于纵向记录；同一时期多行时核实附加键和每行对象。household id 可能随 Wave 变化，不能当稳定家庭键。
- 每个来源的负值按 File、Wave 和官方材料解释，不套用全库统一负值字典。
- mapping 保留完整 `Variable (File)`。
- 公共生成器使用 `database="ELSA"` 和已核实的 `cycle_order`，detail 周期列使用 `Wave 1`、`Wave 2` 等名称。

## 结果验证与支持范围

- 在[第6步](../../rules/stages/06-results.md)中核对完整 File 身份、个人—Wave键、特殊文件族、负值解释及覆盖范围。
- 部分 Wave 来源重叠时，按[公共来源重叠核对](../../rules/stages/06-results.md#来源重叠核对)处理，不另设一套暂停条件。

生成接口和边界见[第5步](../../rules/stages/05-generate.md#数据库适配边界)，既有验证证据见[验收矩阵](../../../tests/acceptance-matrix.md)。
