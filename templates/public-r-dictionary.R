# ----------- 4 变量字典 -----------
# Example: replace the result, source aliases and label with the settled definition.
analysis_vars <- c("defined_value")
result_labels <- c(defined_value = "Defined value")

map <- data.frame(Variable = character(), original_vars = character())
add_mapping <- function(map, variable, source_vars) {
  rbind(map, data.frame(
    Variable = variable,
    original_vars = paste(unique(source_vars), collapse = ", ")
  ))
}
map <- add_mapping(map, "defined_value", c("source_a", "source_b"))

codebook <- lapply(seq_len(nrow(map)), function(i) {
  variable <- map$Variable[i]
  source_vars <- strsplit(map$original_vars[i], ", ", fixed = TRUE)[[1]]
  source_names <- name_z$Variable[match(source_vars, name_z$newname)]
  source_names[is.na(source_names)] <- source_vars[is.na(source_names)]
  data.frame(
    Variable = variable,
    original_vars = paste(source_names, collapse = ", "),
    processed_vars = paste(source_vars, collapse = ", "),
    Label = result_labels[[variable]],
    count = length(source_vars)
  )
})
analysis_codebook <- bind_rows(codebook)

# 以下为 CHARLS 身份列示例；按实际数据库替换身份、来源及其标签。
identity_vars <- c("ID", "id", "year")
identity_labels <- c(ID = "个人时期记录标识", id = "个人标识", year = "调查年")
raw_vars <- c("source_a", "source_b")
source_labels <- c(source_a = "来源 A", source_b = "来源 B")
db_data <- data[c(identity_vars, raw_vars, analysis_vars)]
analysis_data <- data[c(identity_vars, analysis_vars)]

identity_codebook <- data.frame(
  Variable = identity_vars, original_vars = identity_vars, processed_vars = identity_vars,
  Label = unname(identity_labels[identity_vars]), count = 1L
)
source_codebook <- data.frame(
  Variable = raw_vars, original_vars = name_z$Variable[match(raw_vars, name_z$newname)],
  processed_vars = raw_vars, Label = unname(source_labels[raw_vars]), count = 1L
)
codebook <- bind_rows(identity_codebook, source_codebook, analysis_codebook)
codebook <- codebook[match(names(db_data), codebook$Variable), ]
# 完整字典是表格；各列对应 db_data。分析字典仅含最终结果。
# 按本主题替换文件名，并按第5步设置实际业务分组。
# ----------- 5 正式输出 -----------
openxlsx::write.xlsx(db_data, "db_topic.xlsx", overwrite = TRUE)
openxlsx::write.xlsx(codebook, "codebook_topic.xlsx", overwrite = TRUE)
openxlsx::write.xlsx(analysis_data, "analysis_db_topic.xlsx", overwrite = TRUE)
openxlsx::write.xlsx(analysis_codebook, "analysis_codebook_topic.xlsx", overwrite = TRUE)

# 输出
# 后台 QA、HTML 与笔记生成放在此处；上面的四份正式工作簿属于公开代码。
