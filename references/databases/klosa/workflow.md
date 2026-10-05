# KLoSA 候选流程

先按通用来源流程完成双路探索及主线程合并，正式来源记录带`database=KLoSA`、`language=en`或`ko`。已确定的语言在本任务中不自动切换。材料、身份和文件区别见[profile](profile.md)。

1. 固定选择准备使用`prepare_source_selection.py --database klosa --language <已定语言>`；来源记录必须READY，来源为已确认的实际波次字段。选择及登录使用公共浏览器入口、同一语言和原绑定标签，不依赖当前页。
2. 下载准备和恢复显式传`--database klosa --language <已定语言>`。固定快照与动作保留语言，变更语言或数据库时拒绝续用旧尝试。一次提交、新鲜文件和失败处理遵循第2步，不新增审批点。
3. `klosa_adapter_contract.py`按普通/插补文件分别检查字典、别名、身份和记录键。包没有语言标记，离线校验不能单凭ZIP证明来源语言；真实网页动作与下载回执须一同保留。
4. 公开R在读取时保留字符型`ID`、`Harmonized_id`、`Wave_id`。普通个人结果用`render_definition_bundle(database="KLOSA", language=chosen_language, cycle_order=verified_waves, ...)`，目录输入同样带`summary_source=list(path=verified_paths, language=chosen_language)`。时期为有证据的有序子集，不从非缺失行反推。生成器只在工作副本投影时期，不改raw。
5. 结果检查使用`check_definition_output.py --db klosa --language <已定语言>`。当前完整生成仅接普通个人表；插补包结构可校验，不代表插补分析或多文件主题已验证。

首次真实任务仍需证明实际选择/下载、身份与字段格式、计算实现、完整生成及结果验证。合成测试与网页取证不能代替完整主题验收。
