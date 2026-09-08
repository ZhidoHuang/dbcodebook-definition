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

definition_source_range_members <- function(value) {
  match <- regexec("^(.*?)([0-9]+)~(.*?)([0-9]+)$", value, perl = TRUE)
  pieces <- regmatches(value, match)[[1]]
  if (length(pieces) != 5L || pieces[2] != pieces[4]) return(character())
  first <- as.integer(pieces[3])
  last <- as.integer(pieces[5])
  if (is.na(first) || is.na(last) || first > last) return(character())
  paste0(pieces[2], seq.int(first, last))
}

validate_definition_source_display <- function(display, analysis_codebook) {
  if (is.null(display)) return(invisible(TRUE))
  if (!is.character(display) || is.null(names(display)) ||
      anyNA(display) || any(!nzchar(trimws(display)))) {
    stop("定义卡来源展示必须是带变量名且内容非空的字符向量。")
  }
  unknown <- setdiff(names(display), analysis_codebook$Variable)
  if (length(unknown)) {
    stop("定义卡来源展示包含未知变量：", paste(unknown, collapse = ", "))
  }
  for (variable in names(display)) {
    row <- match(variable, analysis_codebook$Variable)
    original_allowed <- definition_source_members(
      analysis_codebook$original_vars[row]
    )
    processed_allowed <- if ("processed_vars" %in% names(analysis_codebook)) {
      definition_source_members(analysis_codebook$processed_vars[row])
    } else {
      character()
    }
    allowed <- unique(c(original_allowed, processed_allowed))
    shown <- definition_source_members(display[[variable]])
    invalid <- vapply(shown, function(item) {
      if (grepl("=", item, fixed = TRUE)) {
        pair <- trimws(strsplit(item, "=", fixed = TRUE)[[1]])
        if (length(pair) != 2L || any(!nzchar(pair))) return(TRUE)
        pair_positions <- which(original_allowed == pair[1])
        return(
          !length(pair_positions) ||
            !length(processed_allowed) ||
            !any(processed_allowed[pair_positions] == pair[2])
        )
      }
      if (item %in% allowed) return(FALSE)
      expanded <- definition_source_range_members(item)
      !length(expanded) || !all(expanded %in% allowed)
    }, logical(1))
    if (any(invalid)) {
      stop(
        variable, "：定义卡来源展示只能使用正确配对的完整映射、完整来源名或已核实的连续范围：",
        paste(shown[invalid], collapse = ", ")
      )
    }
  }
  invisible(TRUE)
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
    definition_source_display = NULL,
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
    summary_extra_lines = character()) {
  for (pkg in c("dplyr", "tidyr", "dbCodeBookr")) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      stop("Required package is not installed: ", pkg)
    }
  }
  library("dplyr")
  library("tidyr")
  library("dbCodeBookr")
  expected_charls_cycles <- c("2011", "2013", "2015", "2018", "2020")
  if (!identical(as.character(cycle_order), expected_charls_cycles)) {
    stop(
      "CHARLS target cycles must be 2011, 2013, 2015, 2018, and 2020; ",
      "a topic cannot redefine full-cycle coverage from its observed rows."
    )
  }
  stopifnot(identical(analysis_vars, analysis_codebook$Variable))
  stopifnot(all(analysis_vars %in% names(criteria)))
  stopifnot(all(nzchar(criteria[analysis_vars])))
  validate_criteria_markup(criteria[analysis_vars], unique(c(raw_vars, analysis_vars)))
  validate_definition_source_display(definition_source_display, analysis_codebook)

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
    period_col = "year",
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
    paste0("CHARLS_", file_stem, "_QA.txt"),
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
  names(details) <- names(db_data)
  codebook$detail <- unname(details[codebook$Variable])
  codebook$easylabel <- codebook$Label

  identity_columns <- intersect(
    c("ID", "id", "householdid", "communityid"),
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
    paste0("CHARLS_", file_stem, "_detail.html"),
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
  if (!is.null(definition_source_display)) {
    display_rows <- match(
      definition_data$Variable,
      names(definition_source_display)
    )
    has_display <- !is.na(display_rows)
    definition_data$original_vars[has_display] <- unname(
      definition_source_display[display_rows[has_display]]
    )
  }
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
    paste0("CHARLS_", file_stem, "_definition.html"),
    theme_color
  )

  clean_html <- function(path) {
    text <- readLines(path, encoding = "UTF-8", warn = FALSE)
    text <- gsub("mapping", "varlink", text, fixed = TRUE)
    text <- gsub("&emsp;&emsp;", "", text, fixed = TRUE)
    writeLines(text, path, useBytes = TRUE)
  }
  clean_html(paste0("CHARLS_", file_stem, "_detail.html"))
  clean_html(paste0("CHARLS_", file_stem, "_definition.html"))

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
    paste0("CHARLS_", file_stem, "_definition.html"),
    encoding = "UTF-8",
    warn = FALSE
  )
  detail_html_lines <- readLines(
    paste0("CHARLS_", file_stem, "_detail.html"),
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
}
