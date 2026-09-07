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

# ----------- 5 正式输出 -----------
