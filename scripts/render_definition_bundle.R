criteria_value <- function(x) {
  value <- as.character(x)
  if (anyNA(value) || any(!nzchar(value))) {
    stop("Criteria 取值不能为空。")
  }
  if (any(grepl("[<>]", value))) {
    stop("Criteria 取值不得包含 HTML 标签。")
  }
  paste0("<u>[", value, "]</u>")
}

criteria_escape_code <- function(x) {
  x <- gsub("&", "&amp;", x, fixed = TRUE)
  x <- gsub("<", "&lt;", x, fixed = TRUE)
  x <- gsub(">", "&gt;", x, fixed = TRUE)
  x <- gsub('"', "&quot;", x, fixed = TRUE)
  x
}

criteria_render_inline_code <- function(x) {
  value <- as.character(x)
  if (anyNA(value)) {
    stop("Criteria 文案不能为空。")
  }
  if (any(grepl("<code\\b", value, ignore.case = TRUE, perl = TRUE))) {
    stop("Criteria 生成源不得手写 <code>；请使用成对反引号标记变量名和代码对象。")
  }

  vapply(value, function(item) {
    ticks <- gregexpr("`", item, fixed = TRUE)[[1]]
    tick_count <- if (length(ticks) == 1L && ticks[[1]] == -1L) {
      0L
    } else {
      length(ticks)
    }
    if (tick_count %% 2L != 0L) {
      stop("Criteria 文案中的反引号必须成对出现。")
    }
    if (tick_count == 0L) {
      return(item)
    }

    rendered <- ""
    cursor <- 1L
    for (i in seq.int(1L, tick_count, by = 2L)) {
      open_tick <- ticks[[i]]
      close_tick <- ticks[[i + 1L]]
      code_value <- substr(item, open_tick + 1L, close_tick - 1L)
      if (!nzchar(code_value)) {
        stop("Criteria 的 inline code 内容不能为空。")
      }
      rendered <- paste0(
        rendered,
        substr(item, cursor, open_tick - 1L),
        "<code>", criteria_escape_code(code_value), "</code>"
      )
      cursor <- close_tick + 1L
    }
    paste0(rendered, substr(item, cursor, nchar(item)))
  }, character(1), USE.NAMES = FALSE)
}

criteria_context <- function(x) paste0(
  "<div data-criteria-context='true' style='background:#F4F3F0;",
  "border-radius:6px;padding:8px 10px;margin:4px 0 8px 1.8em;",
  "text-align:left;line-height:1.75;font-size:0.92em;'>",
  criteria_render_inline_code(x), "</div>"
)

criteria_heading <- function(x) paste0(
  "<div data-criteria-heading='true' style='text-align:left;line-height:1.6;",
  "margin:4px 0 1px 0;'><strong>", x, "</strong></div>"
)

criteria_item <- function(x) paste0(
  "<div data-criteria-item='true' style='padding-left:1.8em;text-align:left;",
  "line-height:1.75;margin:3px 0;font-size:0.92em;'>",
  criteria_render_inline_code(x), "</div>"
)

criteria_block <- function(...) paste(..., sep = "")

definition_copy_check <- function(copy_path = "文案.md", source = NULL,
                                  note = NULL, export = NULL) {
  root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
  if (!nzchar(root)) {
    home <- Sys.getenv("CODEX_HOME")
    if (!nzchar(home)) {
      user_home <- Sys.getenv("USERPROFILE")
      if (!nzchar(user_home)) user_home <- path.expand("~")
      home <- file.path(user_home, ".codex")
    }
    root <- file.path(home, "skills", "dbcodebook-definition")
  }
  config <- Sys.getenv("DBCODEBOOK_DEFINITION_CONFIG")
  if (!nzchar(config)) config <- file.path(root, "config.local.json")
  python <- Sys.getenv("DBCODEBOOK_DEFINITION_PYTHON")
  if (!nzchar(python) && file.exists(config)) {
    settings <- jsonlite::read_json(config)
    python <- settings$executables$python
    if (is.null(python)) python <- ""
    if (nzchar(python) && !grepl("^([A-Za-z]:|/|\\\\)", python)) {
      python <- file.path(dirname(config), python)
    }
  }
  if (!nzchar(python)) python <- Sys.which("python3")
  if (!nzchar(python)) python <- Sys.which("python")
  if (!nzchar(python)) stop("请在 Skill 配置中设置 Python 路径。")
  args <- c("-X", "utf8", shQuote(file.path(root, "scripts", "check_reader_copy.py")),
            "--copy", shQuote(copy_path))
  temporary <- character()
  on.exit(unlink(temporary), add = TRUE)
  if (!is.null(source)) {
    temporary <- tempfile(fileext = ".json")
    jsonlite::write_json(source, temporary, auto_unbox = TRUE)
    args <- c(args, "--source-json", shQuote(temporary))
  }
  if (!is.null(note)) args <- c(args, "--note", shQuote(note))
  if (!is.null(export)) args <- c(args, "--export", shQuote(export))
  output <- suppressWarnings(system2(python, args, stdout = TRUE, stderr = TRUE))
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"))
  invisible(output)
}

read_definition_copy <- function(analysis_vars, path = "文案.md") {
  exported <- tempfile(fileext = ".json")
  on.exit(unlink(exported), add = TRUE)
  definition_copy_check(path, export = exported)
  copy <- jsonlite::read_json(exported)
  if (!identical(names(copy$criteria), analysis_vars)) {
    stop("文案 Criteria 的变量或顺序与 analysis_vars 不一致。")
  }
  paragraphs <- function(text) strsplit(text, "\n[[:blank:]]*\n", perl = TRUE)[[1]]
  inline_parts <- function(text) {
    pieces <- strsplit(text, "**", fixed = TRUE)[[1]]
    lapply(seq_along(pieces), function(i) {
      if (i %% 2L == 0L) {
        if (grepl("^[0-9]+$", pieces[i])) summary_count_part(as.integer(pieces[i]), "") else summary_concept_part(pieces[i], quote = FALSE)
      } else pieces[i]
    })
  }
  render_values <- function(text) {
    # Append one ordinary character so strsplit() cannot discard a trailing
    # empty field when a valid inline-code span ends the line.
    padded <- paste0(text, " ")
    pieces <- strsplit(padded, "`", fixed = TRUE)[[1]]
    for (i in seq.int(1L, length(pieces), by = 2L)) {
      pieces[i] <- gsub("\\[([^][]+)\\]", "<u>[\\1]</u>", pieces[i], perl = TRUE)
    }
    rendered <- paste(pieces, collapse = "`")
    substr(rendered, 1L, nchar(rendered) - 1L)
  }
  criteria <- lapply(copy$criteria, function(fields) {
    paste0(vapply(names(fields), function(field) {
      lines <- strsplit(fields[[field]], "\n", fixed = TRUE)[[1]]
      lines <- lines[nzchar(trimws(lines))]
      paste0(criteria_heading(field), paste0(vapply(lines, function(line) {
        criteria_item(render_values(line))
      }, character(1)), collapse = ""))
    }, character(1)), collapse = "")
  })
  result <- list(
    criteria = criteria,
    summary_entry = list(paragraphs = lapply(copy$summary_blocks, function(block) {
      if (identical(block$type, "code_tree")) return(block)
      list(parts = inline_parts(block$text))
    })),
    summary_insight_items = if (nzchar(copy$insight)) paragraphs(copy$insight) else NULL,
    reference_lines = c("## 参考资料说明", "", copy$references)
  )
  if (!is.null(copy$questionnaire)) {
    result$summary_selection <- list(class = "raw-source-structure", display = "period-tabs",
      groups = lapply(names(copy$questionnaire), function(period) {
        block <- copy$questionnaire[[period]]
        lines <- c(list(summary_period_note(paragraphs(block$design))),
          lapply(block$questions, function(question) {
            summary_questionnaire_line(question$id, question$text,
              condition = if (nzchar(question$condition)) question$condition else character(),
              options = lapply(question$options, function(option) {
                summary_questionnaire_option(option$text, option$jump)
              }), after = unlist(question$instructions, use.names = FALSE))
          }))
        list(period = period, label = block$label, lines = lines)
      }))
  }
  result
}

validate_criteria_markup <- function(criteria, variable_names = character()) {
  criteria <- as.character(criteria)
  invalid_value_code <- grepl(
    "<code\\b[^>]*>[[:space:]]*\\[[^<]*\\][[:space:]]*</code>",
    criteria,
    ignore.case = TRUE,
    perl = TRUE
  )
  if (any(invalid_value_code)) {
    invalid_names <- names(criteria)[invalid_value_code]
    if (is.null(invalid_names) || any(!nzchar(invalid_names))) {
      invalid_names <- as.character(which(invalid_value_code))
    }
    stop(
      "Criteria 中的数据取值、编码值、分类值和问卷选项不得使用 inline code；",
      "请改用 criteria_value()：",
      paste(invalid_names, collapse = "、")
    )
  }
  value_markup <- unlist(regmatches(criteria, gregexpr("<u>\\[[^<>]*\\]</u>", criteria)))
  value_text <- gsub("^<u>\\[|\\]</u>$", "", value_markup)
  identifiers <- unlist(regmatches(value_text, gregexpr("[[:alpha:]_.][[:alnum:]_.]*", value_text)))
  misplaced <- intersect(identifiers, variable_names)
  if (length(misplaced)) {
    stop("Criteria 将本主题变量名标成了数据取值；变量名请用成对反引号：",
         paste(misplaced, collapse = "、"))
  }
  invisible(TRUE)
}

definition_source_members <- function(value) {
  trimws(strsplit(as.character(value), ",", fixed = TRUE)[[1]])
}

definition_card_default_sources <- function(analysis_codebook) {
  if (!"processed_vars" %in% names(analysis_codebook)) {
    stop("analysis_codebook 缺少 processed_vars，无法生成定义卡来源。")
  }
  setNames(
    lapply(analysis_codebook$processed_vars, definition_source_members),
    analysis_codebook$Variable
  )
}

format_definition_card_sources <- function(analysis_codebook, raw_codebook,
                                           source_codebook = analysis_codebook) {
  if (!all(c("Variable", "newname") %in% names(raw_codebook))) {
    stop("raw_codebook 必须包含 Variable 和 newname。")
  }
  sources <- definition_card_default_sources(source_codebook)
  sources[names(definition_card_default_sources(analysis_codebook))] <-
    definition_card_default_sources(analysis_codebook)
  resolve_sources <- function(aliases, visiting = character()) {
    resolved <- lapply(aliases, function(alias) {
      if (alias %in% raw_codebook$newname) return(alias)
      if (alias %in% visiting) stop("正式来源关系存在循环：", paste(c(visiting, alias), collapse = " -> "))
      if (!alias %in% names(sources)) {
        stop("raw_codebook 或正式来源关系中找不到变量：", alias)
      }
      resolve_sources(sources[[alias]], c(visiting, alias))
    })
    unique(unlist(resolved, use.names = FALSE))
  }
  vapply(analysis_codebook$Variable, function(variable) {
    rows <- match(resolve_sources(sources[[variable]], variable), raw_codebook$newname)
    paste0(raw_codebook$Variable[rows], "=", raw_codebook$newname[rows], collapse = ", ")
  }, character(1))
}

append_linear_histogram_endpoint <- function(detail_html) {
  if (!grepl("data-hist-mode='linear'", detail_html, fixed = TRUE)) {
    return(detail_html)
  }
  interval_pattern <- "title='\\[[^,]+, ([^)]+)\\):"
  intervals <- regmatches(
    detail_html,
    gregexpr(interval_pattern, detail_html, perl = TRUE)
  )[[1]]
  if (!length(intervals) || identical(intervals, character())) return(detail_html)
  endpoint <- sub("^.*,[[:space:]]*([^)]+)\\):$", "\\1", tail(intervals, 1L))
  endpoint_number <- suppressWarnings(as.numeric(endpoint))
  if (!is.na(endpoint_number)) {
    endpoint <- format(endpoint_number, trim = TRUE, scientific = FALSE)
  }
  labels_pattern <- paste0(
    "(<div class='hist-labels-wrapper'>)",
    "((?:<div class='hist-label'[^>]*>[^<]*</div>)+)",
    "(</div>)"
  )
  endpoint_html <- paste0(
    "<div class='hist-label hist-endpoint-label' ",
    "style='width:0;margin-left:-3px;margin-right:0;overflow:visible;'>",
    endpoint,
    "</div>"
  )
  sub(
    labels_pattern,
    paste0("\\1\\2", endpoint_html, "\\3"),
    detail_html,
    perl = TRUE
  )
}

compose_definition_note_lines <- function(
    summary_section,
    summary_extra_lines,
    definition_html_lines,
    reference_lines,
    extract_box,
    publish_code,
    detail_html_lines) {
  visible_code <- trimws(publish_code[nzchar(trimws(publish_code))])
  if (length(visible_code) && grepl("^#[- #]*[0-9]+[ .、_-]", tail(visible_code, 1))) {
    warning("公开代码以空小节标题结束；请把正式工作簿写出放在 # 输出 之前。", call. = FALSE)
  }
  c(
    summary_section,
    if (length(summary_extra_lines) > 0) c(summary_extra_lines, "") else character(),
    "## 定义", "", definition_html_lines, "",
    if (length(reference_lines) > 0) c(reference_lines, "") else character(),
    detail_html_lines, "",
    "## 材料", "", "### 1-提取变量", "", extract_box, "",
    "### 2-代码材料", "", paste0(strrep(intToUtf8(96), 3), "r"),
    publish_code, paste0(strrep(intToUtf8(96), 3)), ""
  )
}

definition_period_counts <- function(data) {
  counts <- data |>
    dplyr::filter(!is.na(year)) |>
    dplyr::group_by(year) |>
    dplyr::summarise(
      dplyr::across(dplyr::everything(), ~ sum(!is.na(.x))),
      .groups = "drop"
    )
  tidyr::pivot_longer(
    counts, cols = -year, names_to = "Variable", values_to = "Count"
  )
}

definition_source_entry <- function(value, database = "CHARLS") {
  if (is.null(value)) return(NULL)
  if (is.list(value) && !is.null(value$path)) {
    note <- if (is.null(value$note)) "" else value$note
    if (!is.character(note) || length(note) != 1L || is.na(note)) stop("summary_source note must be one string.")
    return(list(class = "raw-source-link", lines = list(list(parts = list(
      list(type = "source_link", value = value$path, database = database), note
    )))))
  }
  if (is.character(value) && length(value) && all(!is.na(value)) && all(nzchar(value))) {
    return(list(class = "raw-source-link", lines = lapply(value, function(path) {
      list(parts = list(list(type = "source_link", value = path, database = database)))
    })))
  }
  if (!is.list(value) || is.null(value$lines)) stop("summary_source requires nonempty text or a source entry with lines.")
  value$class <- "raw-source-link"
  value
}

render_definition_bundle <- function(
    data,
    db_data,
    codebook,
    analysis_data,
    analysis_codebook,
    analysis_vars,
    raw_vars,
    raw_codebook,
    criteria,
    summary_meanings,
    summary_groups,
    summary_object_overrides = NULL,
    summary_entry,
    summary_selection,
    summary_insight_items,
    summary_source = NULL,
    file_stem,
    note_name,
    qa_title,
    transaction_id,
    script_file,
    theme_color = "#A33842",
    cycle_order = c("2011", "2013", "2015", "2018", "2020"),
    raw_source_years = NULL,
    raw_row_count = nrow(data),
    hist_binwidth = 1,
    hist_mode = "linear",
    evidence_lines = character(),
    reference_lines = character(),
    summary_extra_lines = character(),
    database = "CHARLS") {
  database <- toupper(database)
  if (!database %in% c("CHARLS", "ELSA", "HRS")) stop("Unsupported definition database: ", database)
  period_col <- if (database == "ELSA") "Wave" else "year"
  if (database == "ELSA" && missing(cycle_order)) stop("ELSA requires explicit, evidence-based cycle_order.")
  if (database == "ELSA") {
    wave_numbers <- suppressWarnings(as.integer(sub("^Wave ", "", cycle_order)))
    if (anyNA(wave_numbers) || any(wave_numbers < 1L) ||
        !identical(as.character(cycle_order), paste("Wave", wave_numbers)) ||
        anyDuplicated(wave_numbers) || is.unsorted(wave_numbers)) stop("Invalid ELSA Wave order.")
    for (frame in list(data, db_data, analysis_data)) {
      if (!all(c("ID", "idauniq", "Wave") %in% names(frame))) stop("ELSA requires ID, idauniq and Wave.")
      if (any(!is.na(frame$Wave) & !frame$Wave %in% cycle_order)) stop("Observed Wave outside declared cycle_order.")
    }
    # Local rendering copies only; formal input and exported identities remain unchanged.
    db_data$year <- db_data$Wave
    analysis_data$year <- analysis_data$Wave
  }
  if (database == "HRS") {
    if (missing(cycle_order)) stop("HRS requires explicit, evidence-based cycle_order.")
    hrs_years <- suppressWarnings(as.integer(cycle_order))
    if (anyNA(hrs_years) || any(hrs_years < 1900L) || any(hrs_years > 2100L) ||
        !identical(as.character(cycle_order), as.character(hrs_years)) ||
        anyDuplicated(hrs_years) || is.unsorted(hrs_years)) stop("Invalid HRS year order.")
    for (frame in list(data, db_data, analysis_data)) {
      if (!all(c("HHID", "PN", "year") %in% names(frame))) stop("HRS requires HHID, PN and year.")
      if (any(!is.na(frame$year) & !as.character(frame$year) %in% cycle_order)) stop("Observed year outside declared cycle_order.")
    }
  }
  summary_source <- definition_source_entry(summary_source, database)
  # Validate source structure before any output files are written.
  if (!is.null(summary_source)) render_summary_selection_paragraph(summary_source, theme_color)
  definition_copy_check(source = list(
    summary = render_summary_entry_paragraph(summary_entry, theme_color),
    criteria = as.list(criteria[analysis_vars]),
    insight = paste(summary_insight_items, collapse = "\n\n"),
    references = paste(reference_lines[!grepl("^## 参考资料说明$", reference_lines)], collapse = "\n"),
    questionnaire = if (missing(summary_selection)) "" else render_summary_selection_paragraph(summary_selection, theme_color)
  ))
  for (pkg in c("dplyr", "tidyr", "dbCodeBookr")) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      stop("Required package is not installed: ", pkg)
    }
  }
  library("dplyr")
  library("tidyr")
  library("dbCodeBookr")
  expected_charls_cycles <- c("2011", "2013", "2015", "2018", "2020")
  if (database == "CHARLS" && !identical(as.character(cycle_order), expected_charls_cycles)) {
    stop(
      "CHARLS target cycles must be 2011, 2013, 2015, 2018, and 2020; ",
      "a topic cannot redefine full-cycle coverage from its observed rows."
    )
  }
  stopifnot(identical(analysis_vars, analysis_codebook$Variable))
  stopifnot(all(analysis_vars %in% names(criteria)))
  stopifnot(all(nzchar(criteria[analysis_vars])))
  validate_criteria_markup(criteria[analysis_vars], unique(c(raw_vars, analysis_vars)))
  formatted_card_sources <- format_definition_card_sources(analysis_codebook, raw_codebook, codebook)

  format_n <- function(x) {
    format(x, big.mark = ",", scientific = FALSE)
  }

  summary_reviewed <- setNames(rep(TRUE, length(analysis_vars)), analysis_vars)
  summary_facts <- build_summary_facts(
    analysis_data,
    analysis_codebook,
    summary_meanings,
    summary_groups,
    summary_reviewed,
    period_col = period_col,
    expected_periods = cycle_order,
    object_overrides = summary_object_overrides
  )
  coverage <- analysis_data %>%
    select(year, all_of(analysis_vars)) %>%
    pivot_longer(
      cols = all_of(analysis_vars),
      names_to = "Variable",
      values_to = "Value",
      values_transform = list(Value = as.character)
    ) %>%
    group_by(year, Variable) %>%
    summarise(
      nonmissing = sum(!is.na(Value)),
      missing = sum(is.na(Value)),
      .groups = "drop"
    ) %>%
    arrange(year, match(Variable, analysis_vars))

  qa_lines <- c(
    qa_title,
    "",
    "1. raw / recover",
    paste0("- recover transaction: ", transaction_id),
    paste0("- raw rows: ", format_n(raw_row_count)),
    paste0("- analysis rows: ", format_n(nrow(analysis_data))),
    paste0("- raw variables: ", format_n(length(raw_vars))),
    "",
    "2. final variables",
    paste0("- ", paste(analysis_vars, collapse = ", ")),
    "",
    "3. yearly coverage",
    capture.output(print(coverage)),
    "",
    "4. summary facts",
    capture.output(print(summary_facts)),
    "",
    "5. evidence boundary",
    paste0("- ", evidence_lines)
  )
  writeLines(
    qa_lines,
    paste0(database, "_", file_stem, "_QA.txt"),
    useBytes = TRUE
  )

  detail_data <- db_data
  if (!is.null(raw_source_years)) {
    for (var_name in intersect(names(raw_source_years), names(detail_data))) {
      active <- as.character(detail_data$year) %in%
        as.character(raw_source_years[[var_name]])
      detail_data[[var_name]][!active] <- NA
    }
  }

  details <- generate_var_details(
    detail_data,
    bar_color = paste0(theme_color, "90"),
    show_hist = TRUE,
    hist_binwidth = hist_binwidth,
    hist_mode = hist_mode,
    show_distribution_nav = FALSE,
    show_cycle_heatmap = FALSE
  )
  details <- vapply(details, append_linear_histogram_endpoint, character(1))
  date_detail_vars <- names(detail_data)[vapply(detail_data, inherits, logical(1), "Date")]
  date_detail_positions <- match(date_detail_vars, names(db_data))
  date_detail_positions <- date_detail_positions[!is.na(date_detail_positions)]
  if (length(date_detail_vars) > 0L) {
    details[date_detail_positions] <- gsub(
      "Unsupported type",
      "日期变量（近似构造）",
      details[date_detail_positions],
      fixed = TRUE
    )
  }
  names(details) <- names(db_data)
  analysis_source_rows <- match(codebook$Variable, names(formatted_card_sources))
  has_analysis_source <- !is.na(analysis_source_rows)
  codebook$original_vars[has_analysis_source] <- unname(
    formatted_card_sources[analysis_source_rows[has_analysis_source]]
  )
  codebook$detail <- unname(details[codebook$Variable])
  codebook$easylabel <- codebook$Label

  identity_columns <- intersect(
    c("ID", "id", "idauniq", "HHID", "PN", "HHIDPN", "RAHHIDPN", "Wave", "householdid", "communityid"),
    names(detail_data)
  )
  z <- detail_data[, setdiff(names(detail_data), identity_columns), drop = FALSE]
  count_data <- definition_period_counts(z)
  wide_data <- pivot_wider(
    count_data,
    names_from = year,
    values_from = Count,
    values_fill = NA,
    names_sort = FALSE
  )
  period_columns <- intersect(as.character(cycle_order), names(wide_data))
  wide_data <- wide_data[c(setdiff(names(wide_data), period_columns), period_columns)]
  wide_data <- wide_data[
    order(factor(wide_data$Variable, levels = names(db_data))),
  ]
  wide_data$category <- ifelse(
    wide_data$Variable %in% analysis_vars,
    "Defined variables",
    "Source variables"
  )
  wide_data$category <- factor(
    wide_data$category,
    levels = c("Source variables", "Defined variables")
  )
  wide_data$category <- droplevels(wide_data$category)
  wide_data <- wide_data[
    order(wide_data$category, match(wide_data$Variable, names(db_data))),
  ]

  heat_df <- left_join(
    wide_data,
    codebook[, c("Variable", "original_vars", "easylabel")],
    by = "Variable"
  )
  meta_df <- left_join(wide_data, codebook, by = "Variable")
  generate_html_definition_long(
    heat_df,
    meta_df,
    paste0(database, "_", file_stem, "_detail.html"),
    "#2c3e50",
    theme_color
  )

  definition_data <- meta_df[
    meta_df$Variable %in% analysis_vars,
    c("Variable", "original_vars", "detail")
  ]
  definition_data <- definition_data[
    match(analysis_vars, definition_data$Variable),
  ]
  definition_details <- generate_var_details(
    detail_data,
    bar_color = paste0(theme_color, "90"),
    show_hist = TRUE,
    hist_binwidth = hist_binwidth,
    hist_mode = hist_mode,
    show_distribution_nav = TRUE,
    show_cycle_heatmap = TRUE,
    cycle_col = "year",
    cycle_order = cycle_order,
    heatmap_color = theme_color
  )
  definition_details <- vapply(
    definition_details,
    append_linear_histogram_endpoint,
    character(1)
  )
  if (length(date_detail_positions) > 0L) {
    definition_details[date_detail_positions] <- gsub(
      "Unsupported type",
      "日期变量（近似构造）",
      definition_details[date_detail_positions],
      fixed = TRUE
    )
  }
  names(definition_details) <- names(db_data)
  definition_data$detail <- unname(
    definition_details[definition_data$Variable]
  )
  definition_data$Definition <- definition_data$Variable
  definition_data$Criteria <- unname(criteria[definition_data$Variable])
  definition_data <- definition_data[
    c("Variable", "original_vars", "Definition", "Criteria", "detail")
  ]
  generate_html_definition(
    definition_data,
    paste0(database, "_", file_stem, "_definition.html"),
    theme_color
  )

  clean_html <- function(path) {
    text <- readLines(path, encoding = "UTF-8", warn = FALSE)
    text <- gsub("mapping", "varlink", text, fixed = TRUE)
    text <- gsub("&emsp;&emsp;", "", text, fixed = TRUE)
    writeLines(text, path, useBytes = TRUE)
  }
  clean_html(paste0(database, "_", file_stem, "_detail.html"))
  clean_html(paste0(database, "_", file_stem, "_definition.html"))

  extract_vars <- paste0(raw_codebook$Variable, "=", raw_codebook$newname)
  extract_box <- c(
    '<div class="custom-textbox">',
    '<div class="textbox-content">',
    paste0(extract_vars, collapse = ",\n"),
    "</div>",
    paste0(
      '<button class="textbox-button" ',
      'onclick="goToExtractVariables(this)">Go to 提取变量</button>'
    ),
    "</div>"
  )

  script_lines <- readLines(
    script_file,
    encoding = "UTF-8",
    warn = FALSE
  )
  output_idx <- grep("^# 输出$", script_lines)
  publish_code <- if (length(output_idx) == 0) {
    script_lines
  } else {
    script_lines[seq_len(output_idx[1] - 1)]
  }
  definition_html_lines <- readLines(
    paste0(database, "_", file_stem, "_definition.html"),
    encoding = "UTF-8",
    warn = FALSE
  )
  detail_html_lines <- readLines(
    paste0(database, "_", file_stem, "_detail.html"),
    encoding = "UTF-8",
    warn = FALSE
  )

  summary_section <- render_summary_note_section(
    entry = summary_entry,
    selection = summary_selection,
    theme_color = theme_color,
    insight_items = summary_insight_items,
    insight_variant = "compact",
    summary_source = summary_source
  )
  note_lines <- compose_definition_note_lines(
    summary_section,
    summary_extra_lines,
    definition_html_lines,
    reference_lines,
    extract_box,
    publish_code,
    detail_html_lines
  )
  writeLines(note_lines, note_name, useBytes = TRUE)
  definition_copy_check(note = note_name)
}
