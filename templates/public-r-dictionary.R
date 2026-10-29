# ----------- 4 变量字典 -----------
# defined_value 是格式占位；实际名称按第1步命名规范填写。
# 按已定方案填写：analysis_vars 沿用 approved_analysis_vars 的展示顺序；
# result_labels 使用各结果的 display_name。计算语句的先后不改变此顺序。
analysis_vars <- c("defined_value")
result_labels <- c(defined_value = "定义结果")

# 统一最终文字分类的书写形式；不处理来源列、数值结果或是/否的 0/1。
format_category_values <- function(values) {
  labels <- if (is.factor(values)) levels(values) else unique(values[!is.na(values)])
  formatted <- trimws(gsub("[[:space:]_]+", " ", labels))
  substr(formatted, 1L, 1L) <- toupper(substr(formatted, 1L, 1L))
  if (any(!nzchar(formatted)) || anyDuplicated(formatted)) {
    stop("分类标签为空或格式统一后重名，请核对已确认的分类。")
  }
  if (is.factor(values)) {
    levels(values) <- formatted
    return(values)
  }
  formatted[match(values, labels)]
}
for (variable in analysis_vars) {
  if (is.character(data[[variable]]) || is.factor(data[[variable]])) {
    data[[variable]] <- format_category_values(data[[variable]])
  }
}

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
analysis_codebook <- analysis_codebook[match(analysis_vars, analysis_codebook$Variable), ]

# 以下为默认 CHARLS 个人期身份列示例；按实际数据库替换身份、来源及其标签。
# 仅真实来源记录显式声明 household_period 且用户已确认家庭年度单位时，改为
# identity_vars <- c("householdid", "year")；若来源有答卷人 id，可追加但不作为键。
# 相应 identity_labels 使用家庭标识/调查年/答卷人标识，并在 raw read 的 colClasses
# 中保留 householdid、year 及存在的 id 为 character；原始家庭年度行不展开、不去重。
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
# 经确认使用CSV时，仅将两份数据表的写入替换为：
# write.csv(db_data, "db_topic.csv", row.names = FALSE, na = "", fileEncoding = "UTF-8")
# write.csv(analysis_data, "analysis_db_topic.csv", row.names = FALSE, na = "", fileEncoding = "UTF-8")

# 输出
# 后台 QA、HTML 与笔记生成放在此处；上面的四份正式表格属于公开代码。
# 按第5步加载公共helper后读取文案，完整生成调用须包含以下展示参数：
# copy <- read_definition_copy(analysis_vars)
# render_definition_bundle(..., display_policy = copy$display_policy)

# 已确认并在来源记录声明的 CHARLS 家庭年度主题，后台须显式传：
# render_definition_bundle(..., analysis_unit = "household_period",
#   identity_keys = c("householdid", "year"), display_policy = copy$display_policy)
# 这两个字面参数与来源记录一致，RStudio独立执行也不依赖runner或过程目录。
