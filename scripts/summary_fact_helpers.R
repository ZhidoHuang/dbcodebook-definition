# 摘要导读和定义成果核对使用的公共事实函数。
# “含义”和概念分组由主题人工提供；变量集合、顺序、来源数、覆盖周期和对象均从正式产物推导。

summary_split_sources <- function(x) {
  values <- trimws(unlist(strsplit(ifelse(is.na(x), "", x), ",\\s*")))
  unique(values[nzchar(values)])
}

summary_period_ranges <- function(periods, prefix = "Wave") {
  periods <- sort(unique(as.integer(periods)))
  if (length(periods) == 0) return(character())
  breaks <- c(1, which(diff(periods) != 1) + 1, length(periods) + 1)
  vapply(seq_len(length(breaks) - 1), function(i) {
    values <- periods[breaks[i]:(breaks[i + 1] - 1)]
    if (length(values) == 1) {
      if (nzchar(prefix)) paste(prefix, values) else as.character(values)
    } else {
      if (nzchar(prefix)) {
        paste0(prefix, " ", values[1], "-", values[length(values)])
      } else {
        paste0(values[1], "-", values[length(values)])
      }
    }
  }, character(1))
}

summary_period_text <- function(periods, prefix = "Wave", all_periods = NULL) {
  periods <- sort(unique(as.integer(periods)))
  if (!is.null(all_periods) && identical(periods, sort(unique(as.integer(all_periods))))) {
    return("全周期")
  }
  paste(summary_period_ranges(periods, prefix), collapse = "、")
}

summary_object_text <- function(period_stats,
                                threshold = 0.85,
                                split_gap = 0.20,
                                prefix = "Wave") {
  if (nrow(period_stats) == 0) stop("摘要变量没有任何非缺失覆盖周期。")
  rates <- period_stats$rate
  if (all(rates >= threshold)) return("全样本")

  low <- period_stats[rates < threshold, , drop = FALSE]
  high <- period_stats[rates >= threshold, , drop = FALSE]
  parts <- character()
  if (nrow(high) > 0) {
    parts <- c(parts, paste0(summary_period_text(high$period, prefix), " 全样本"))
  }
  if (nrow(low) > 0) {
    rounded <- round(low$rate * 10) * 10
    percentages <- sort(unique(rounded), decreasing = TRUE)
    low_parts <- vapply(percentages, function(percent) {
      periods <- low$period[rounded == percent]
      paste0(summary_period_text(periods, prefix), " 约 ", percent, "% 样本")
    }, character(1))
    parts <- c(parts, low_parts)
  }
  paste(parts, collapse = "；<br>")
}

build_summary_facts <- function(analysis_db,
                                analysis_codebook,
                                meanings,
                                groups,
                                meaning_reviewed,
                                source_identity = NULL,
                                period_col = "wave",
                                expected_periods = NULL,
                                threshold = 0.85,
                                split_gap = 0.20,
                                period_prefix = NULL,
                                object_overrides = NULL) {
  required_codebook <- c("Variable", "original_vars", "Label")
  missing_codebook <- setdiff(required_codebook, names(analysis_codebook))
  if (length(missing_codebook) > 0) {
    stop("analysis_codebook 缺少摘要事实列：", paste(missing_codebook, collapse = ", "))
  }
  if (!period_col %in% names(analysis_db)) stop("analysis_db 缺少周期列。")
  expected_prefix <- if (identical(period_col, "year")) {
    ""
  } else if (period_col %in% c("wave", "Wave")) {
    "Wave"
  } else {
    NULL
  }
  if (is.null(expected_prefix)) stop("摘要周期列必须是 year、wave 或 Wave。")
  if (is.null(period_prefix)) period_prefix <- expected_prefix
  if (!identical(period_prefix, expected_prefix)) {
    expected_display <- if (nzchar(expected_prefix)) expected_prefix else "直接年份"
    stop("摘要周期术语与周期列不一致：", period_col, " 必须使用 ", expected_display, "。")
  }
  period_values <- if (identical(period_col, "Wave")) {
    as.integer(sub("^Wave[[:space:]]+", "", as.character(analysis_db[[period_col]])))
  } else {
    as.integer(analysis_db[[period_col]])
  }
  if (anyNA(period_values)) stop("analysis_db 的周期列包含无法识别的值。")
  observed_periods <- sort(unique(period_values))
  if (is.null(expected_periods)) {
    expected_periods <- observed_periods
  } else {
    expected_periods <- if (identical(period_col, "Wave")) {
      as.integer(sub("^Wave[[:space:]]+", "", as.character(expected_periods)))
    } else {
      as.integer(expected_periods)
    }
    if (anyNA(expected_periods)) stop("expected_periods 包含无法识别的周期。")
    expected_periods <- sort(unique(expected_periods))
    unexpected_periods <- setdiff(observed_periods, expected_periods)
    if (length(unexpected_periods) > 0) {
      stop(
        "analysis_db 出现目标周期之外的记录：",
        paste(unexpected_periods, collapse = ", ")
      )
    }
  }

  variables <- as.character(analysis_codebook$Variable)
  if (anyNA(variables) || any(!nzchar(variables)) || anyDuplicated(variables)) {
    stop("analysis_codebook 的定义变量集合必须非空且不重复。")
  }
  if (!is.null(object_overrides)) {
    if (!is.character(object_overrides) || is.null(names(object_overrides)) ||
        anyNA(object_overrides) || any(!nzchar(trimws(object_overrides))) ||
        anyNA(names(object_overrides)) || any(!nzchar(names(object_overrides))) ||
        anyDuplicated(names(object_overrides))) {
      stop("摘要对象覆盖必须是 names 为定义变量的非空字符向量。")
    }
    unknown_overrides <- setdiff(names(object_overrides), variables)
    if (length(unknown_overrides) > 0) {
      stop("摘要对象覆盖包含未知定义变量：", paste(unknown_overrides, collapse = ", "))
    }
  }
  if (!identical(names(meanings), variables) || any(!nzchar(meanings))) {
    stop("摘要含义必须按 analysis_codebook 的变量集合与顺序逐项人工填写。")
  }
  if (!identical(names(groups), variables) || any(!nzchar(groups))) {
    stop("摘要分组必须按 analysis_codebook 的变量集合与顺序逐项填写。")
  }
  if (!identical(names(meaning_reviewed), variables) ||
      anyNA(meaning_reviewed) || any(!meaning_reviewed)) {
    stop("摘要含义必须逐项完成人工核对：Criteria 定义与 codebook Label。")
  }
  if (any(!variables %in% names(analysis_db))) {
    stop("analysis_db 缺少 analysis_codebook 中的定义变量。")
  }
  if (any(is.na(analysis_codebook$Label) | !nzchar(trimws(analysis_codebook$Label)))) {
    stop("analysis_codebook Label 不能为空，摘要含义需与其核对。")
  }

  facts <- lapply(seq_along(variables), function(i) {
    variable <- variables[i]
    stats <- do.call(rbind, lapply(observed_periods, function(period) {
      idx <- period_values == period
      total <- sum(idx, na.rm = TRUE)
      nonmissing <- sum(!is.na(analysis_db[[variable]][idx]))
      data.frame(period = period,
                 nonmissing = nonmissing,
                 total = total,
                 rate = if (total == 0) NA_real_ else nonmissing / total)
    }))
    covered <- stats[stats$nonmissing > 0 & !is.na(stats$rate), , drop = FALSE]
    object <- summary_object_text(covered, threshold, split_gap, period_prefix)

    if (all(covered$rate >= threshold) && !identical(object, "全样本")) {
      stop(variable, "：所有覆盖周期均达到阈值，但对象不是全样本。")
    }
    if (any(covered$rate < threshold) && identical(object, "全样本")) {
      stop(variable, "：存在低覆盖周期，但对象被写成全样本。")
    }
    if (grepl("有.*(题目信息|变量信息)|非缺失者", object)) {
      stop(variable, "：对象字段出现由结果反推对象的循环表达。")
    }
    if (!is.null(object_overrides) && variable %in% names(object_overrides)) {
      object <- unname(object_overrides[variable])
    }

    raw_sources <- summary_split_sources(analysis_codebook$original_vars[i])
    if (!is.null(source_identity)) {
      if (is.null(names(source_identity))) stop("来源身份映射必须使用导出列名作为 names。")
      resolved_sources <- vapply(raw_sources, function(source) {
        if (source %in% names(source_identity)) return(unname(source_identity[source]))
        if (source %in% unname(source_identity)) return(source)
        NA_character_
      }, character(1))
      raw_sources <- unique(resolved_sources)
      if (anyNA(raw_sources) || any(!nzchar(raw_sources))) {
        stop(variable, "：mapping/original_vars 无法完整追溯到非空来源身份。")
      }
    }

    data.frame(
      group = unname(groups[i]),
      Variable = variable,
      meaning = unname(meanings[i]),
      raw_count = length(unique(raw_sources)),
      period = summary_period_text(
        covered$period,
        period_prefix,
        expected_periods
      ),
      object = object,
      coverage_period_count = nrow(covered),
      min_coverage = min(covered$rate),
      max_coverage = max(covered$rate),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, facts)
}

summary_escape_html <- function(x) {
  x <- as.character(x)
  x <- gsub("&", "&amp;", x, fixed = TRUE)
  x <- gsub("<", "&lt;", x, fixed = TRUE)
  x <- gsub(">", "&gt;", x, fixed = TRUE)
  x <- gsub('"', "&quot;", x, fixed = TRUE)
  x
}

summary_render_inline_code <- function(x) {
  vapply(as.character(x), function(value) {
    positions <- gregexpr("`", value, fixed = TRUE)[[1]]
    if (length(positions) == 1L && positions[1] == -1L) {
      return(summary_escape_html(value))
    }
    if (length(positions) %% 2 != 0) stop("摘要文案中的反引号必须成对出现。")

    parts <- character()
    cursor <- 1L
    for (i in seq(1L, length(positions), by = 2L)) {
      open <- positions[i]
      close <- positions[i + 1L]
      if (open > cursor) {
        parts <- c(parts, summary_escape_html(substr(value, cursor, open - 1L)))
      }
      code_value <- substr(value, open + 1L, close - 1L)
      if (!nzchar(code_value)) stop("摘要文案中的 inline code 不能为空。")
      parts <- c(parts, paste0("<code>", summary_escape_html(code_value), "</code>"))
      cursor <- close + 1L
    }
    if (cursor <= nchar(value)) {
      parts <- c(parts, summary_escape_html(substr(value, cursor, nchar(value))))
    }
    paste0(parts, collapse = "")
  }, character(1), USE.NAMES = FALSE)
}

summary_validate_insight_inline_code <- function(items) {
  items <- as.character(items)
  if (any(grepl("</?code\\b|&lt;/?code\\b", items, ignore.case = TRUE, perl = TRUE))) {
    stop("小book提示中的变量名请使用成对反引号，不要手写 <code> 标签。")
  }

  unmarked <- unique(unlist(lapply(items, function(value) {
    plain <- gsub("`[^`]*`", "", value, perl = TRUE)
    hits <- regmatches(
      plain,
      gregexpr(
        "(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*[0-9][A-Za-z0-9_]*)(?![A-Za-z0-9_])",
        plain,
        perl = TRUE
      )
    )[[1]]
    hits[nzchar(hits)]
  }), use.names = FALSE))

  if (length(unmarked) > 0) {
    stop(
      "小book提示中的变量名必须使用成对反引号：",
      paste(unmarked, collapse = "、")
    )
  }
  invisible(TRUE)
}

summary_count_span <- function(value,
                               suffix,
                               theme_color,
                               weight = 400,
                               role = NULL) {
  role_attr <- if (is.null(role)) "" else paste0(' data-summary-count-role="', role, '"')
  paste0(
    '<span data-summary-measure="true" style="white-space:nowrap;">',
    '<span data-summary-count="true"', role_attr,
    ' style="color:', theme_color, ';font-weight:', weight, ';">',
    summary_escape_html(value), '</span>', summary_escape_html(suffix), '</span>'
  )
}

summary_path_span <- function(path, theme_color) {
  paste0(
    '<span data-summary-path="true" style="color:', theme_color,
    ';font-style:italic;">', summary_escape_html(path), '</span>'
  )
}

summary_search_span <- function(keyword, theme_color) {
  paste0(
    '<span data-summary-search="true" style="color:', theme_color,
    ';font-style:normal;">', summary_escape_html(keyword), '</span>'
  )
}

summary_concept_span <- function(concept, theme_color, quote = TRUE) {
  opening <- if (isTRUE(quote)) "“" else ""
  closing <- if (isTRUE(quote)) "”" else ""
  paste0(
    opening, '<span data-summary-concept="true" style="color:', theme_color,
    ';font-weight:400;">', summary_escape_html(concept), '</span>', closing
  )
}

summary_question_span <- function(question, theme_color, quote = TRUE) {
  opening <- if (isTRUE(quote)) "“" else ""
  closing <- if (isTRUE(quote)) "”" else ""
  paste0(
    opening, '<span class="summary-question" data-summary-question="true" ',
    'style="font-weight:400;">', summary_escape_html(question),
    '</span>', closing
  )
}

summary_path_part <- function(path) {
  list(type = "path", value = as.character(path))
}

summary_search_part <- function(keyword) {
  list(type = "search", value = as.character(keyword))
}

summary_count_part <- function(value,
                               suffix,
                               weight = 400,
                               role = NULL) {
  list(
    type = "count",
    value = value,
    suffix = as.character(suffix),
    weight = weight,
    role = role
  )
}

summary_concept_part <- function(concept, quote = TRUE) {
  list(
    type = "concept",
    value = as.character(concept),
    quote = isTRUE(quote)
  )
}

summary_question_part <- function(question, quote = TRUE) {
  list(
    type = "question",
    value = as.character(question),
    quote = isTRUE(quote)
  )
}

summary_strong_part <- function(text) {
  list(type = "strong", value = as.character(text))
}

summary_question_detail_part <- function(text) {
  list(type = "question_detail", value = as.character(text))
}

summary_questionnaire_option <- function(text, jump = "") {
  if (length(text) != 1 || is.na(text) || !nzchar(trimws(text)) ||
      length(jump) != 1 || is.na(jump)) {
    stop("每个选项必须包含一条完整选项文本和可选的原始跳转说明。")
  }
  if (grepl("→|->|=>", text, perl = TRUE)) {
    stop("选项中的跳转须单独放入 jump，避免跳题说明被着色为选项。")
  }
  list(type = "question_detail", value = text, role = "option",
       position = "options", jump = jump)
}

summary_questionnaire_line <- function(question_id, question, details = character(),
                                       before = character(), condition = character(),
                                       options = list(),
                                       after = character()) {
  if (!is.list(options) || any(!vapply(options, function(option) {
    is.list(option) && identical(option$role, "option") &&
      identical(option$position, "options") && identical(option$type, "question_detail")
  }, logical(1)))) {
    stop("options 中每个选项须使用 summary_questionnaire_option()。")
  }
  programs <- function(values, position) {
    lapply(as.character(values), function(value) {
      list(type = "question_detail", value = value, role = "instruction",
           position = position)
    })
  }
  if (length(condition) > 1 || anyNA(condition) ||
      (length(condition) == 1 && !nzchar(trimws(condition)))) {
    stop("condition 只能包含一条非空的题目进入条件。")
  }
  condition_part <- if (length(condition) == 1) {
    list(list(type = "question_condition", value = as.character(condition)))
  } else {
    list()
  }
  parts <- c(programs(before, "before"), list(
    summary_strong_part(question_id),
    " ",
    summary_question_part(question, quote = FALSE)
  ), condition_part, lapply(as.character(details), summary_question_detail_part),
  options, programs(after, "after"))
  list(parts = parts, questionnaire = TRUE)
}

summary_period_heading_line <- function(text) {
  list(parts = list(as.character(text)), strong = TRUE, period_heading = TRUE)
}

summary_period_note_parts <- function(line) {
  line <- as.character(line)
  matches <- gregexpr("“[^”]+”", line, perl = TRUE)[[1]]
  if (length(matches) == 1 && matches[[1]] == -1) return(list(line))

  lengths <- attr(matches, "match.length")
  parts <- list()
  cursor <- 1L
  for (index in seq_along(matches)) {
    start <- matches[[index]]
    match_length <- lengths[[index]]
    if (start > cursor) {
      parts <- c(parts, list(substr(line, cursor, start - 1L)))
    }
    value <- substr(line, start + 1L, start + match_length - 2L)
    parts <- c(parts, list(list(type = "period_question", value = value)))
    cursor <- start + match_length
  }
  if (cursor <= nchar(line)) {
    parts <- c(parts, list(substr(line, cursor, nchar(line))))
  }
  parts
}

summary_period_note <- function(lines, title = "问卷设计") {
  lines <- as.character(lines)
  list(
    type = "period_note",
    title = as.character(title),
    lines = lapply(seq_along(lines), function(index) {
      list(
        parts = summary_period_note_parts(lines[[index]]),
        period_note_item = TRUE,
        period_note_first = index == 1
      )
    })
  )
}

summary_definition_block <- function(title, lines) {
  lines <- as.character(lines)
  list(
    type = "definition_block",
    title = as.character(title),
    lines = lapply(lines, function(line) {
      list(parts = list(line), definition_item = TRUE)
    })
  )
}

summary_render_question_detail <- function(value, role = NULL, position = NULL, jump = "") {
  value <- as.character(value)
  line_style <- "display:block;padding-left:1.4em;text-indent:0;"
  option_style <- "font-size:0.8em;color:#888888;"
  instruction_style <- "font-size:0.72em;"
  if (!is.null(role)) {
    if (role == "instruction" && position %in% c("before", "after")) {
      style <- if (position == "before") {
        "display:block;text-indent:0;font-size:0.72em;margin:0 0 0.35em;"
      } else paste0(line_style, instruction_style)
      return(paste0(
        '<span class="summary-question-detail" data-summary-question-detail="true" ',
        'data-summary-question-detail-role="instruction" data-summary-question-position="',
        position, '" style="', style, '">',
        summary_render_inline_code(value), '</span>'
      ))
    }
    if (role != "option" || !identical(position, "options")) {
      stop("问卷说明的角色与位置不匹配。")
    }
    mixed <- nzchar(jump)
    return(paste0(
      '<span class="summary-question-detail" data-summary-question-detail="true" ',
      'data-summary-question-detail-role="', if (mixed) 'mixed' else 'option',
      '" data-summary-question-position="options" style="', line_style, '">',
      '<span data-summary-question-option="true" style="', option_style, '">',
      summary_render_inline_code(value), '</span>',
      if (mixed) paste0(' <span data-summary-question-instruction="true" ',
                        'style="', instruction_style, '">',
                        summary_render_inline_code(jump), '</span>') else '',
      '</span>'
    ))
  }
  is_option <- grepl(
    "^\\s*(?:\\[[^]]+\\]|-?[0-9]+(?:\\.[0-9]+)?)(?:\\s|$)",
    value,
    perl = TRUE
  )
  if (!is_option) {
    return(paste0(
      '<span class="summary-question-detail" data-summary-question-detail="true" ',
      'data-summary-question-detail-role="instruction" style="', line_style,
      instruction_style,
      '">', summary_render_inline_code(value), '</span>'
    ))
  }

  arrow <- regexpr("\\s*(?:→|->|=>)\\s*", value, perl = TRUE)
  if (arrow[[1]] > 0) {
    option_text <- trimws(substr(value, 1, arrow[[1]] - 1))
    instruction_text <- trimws(substr(value, arrow[[1]], nchar(value)))
    return(paste0(
      '<span class="summary-question-detail" data-summary-question-detail="true" ',
      'data-summary-question-detail-role="mixed" style="', line_style, '">',
      '<span data-summary-question-option="true" style="', option_style, '">',
      summary_render_inline_code(option_text), '</span> ',
      '<span data-summary-question-instruction="true" style="', instruction_style, '">',
      summary_render_inline_code(instruction_text), '</span></span>'
    ))
  }

  paste0(
    '<span class="summary-question-detail" data-summary-question-detail="true" ',
    'data-summary-question-detail-role="option" style="', line_style,
    option_style, '">', summary_render_inline_code(value), '</span>'
  )
}

summary_render_parts <- function(parts, theme_color) {
  if (!is.list(parts) || length(parts) == 0) stop("摘要语义片段不能为空。")
  rendered <- vapply(parts, function(part) {
    if (is.character(part) && length(part) == 1) {
      return(summary_render_inline_code(part))
    }
    if (!is.list(part) || is.null(part$type) || is.null(part$value)) {
      stop("摘要语义片段必须是文本或带 type/value 的结构。")
    }
    if (identical(part$type, "path")) {
      return(summary_path_span(part$value, theme_color))
    }
    if (identical(part$type, "search")) {
      return(summary_search_span(part$value, theme_color))
    }
    if (identical(part$type, "count")) {
      suffix <- if (is.null(part$suffix)) "" else part$suffix
      weight <- if (is.null(part$weight)) 400 else part$weight
      role <- if (is.null(part$role)) NULL else part$role
      return(summary_count_span(part$value, suffix, theme_color, weight, role))
    }
    if (identical(part$type, "concept")) {
      quote <- if (is.null(part$quote)) TRUE else isTRUE(part$quote)
      return(summary_concept_span(part$value, theme_color, quote = quote))
    }
    if (identical(part$type, "question")) {
      quote <- if (is.null(part$quote)) TRUE else isTRUE(part$quote)
      return(summary_question_span(part$value, theme_color, quote = quote))
    }
    if (identical(part$type, "question_condition")) {
      return(paste0(
        '<span class="summary-question-condition" ',
        'data-summary-question-condition="true" ',
        'style="font-size:0.72em;">（',
        summary_render_inline_code(part$value), '）</span>'
      ))
    }
    if (identical(part$type, "period_question")) {
      return(paste0(
        '“<span class="summary-period-question" ',
        'data-summary-period-question="true" style="color:', theme_color,
        ';font-weight:400;">', summary_escape_html(part$value), '</span>”'
      ))
    }
    if (identical(part$type, "strong")) {
      return(paste0(
        '<strong data-summary-question-id="true" style="font-weight:700;">',
        summary_escape_html(part$value), '</strong>'
      ))
    }
    if (identical(part$type, "question_detail")) {
      return(summary_render_question_detail(
        part$value, part$role, part$position,
        if (is.null(part$jump)) "" else part$jump
      ))
    }
    stop("未知的摘要语义片段类型：", part$type)
  }, character(1))
  paste0(rendered, collapse = "")
}

summary_join_concepts <- function(concepts, final_count, theme_color) {
  concepts <- as.character(concepts)
  if (length(concepts) == 0 || any(!nzchar(concepts))) stop("摘要定义概念不能为空。")
  if (final_count < length(concepts)) stop("展示的定义概念数不能超过最终变量数。")
  rendered <- vapply(concepts, summary_concept_span, character(1), theme_color = theme_color)
  if (final_count > length(rendered)) return(paste0(paste0(rendered, collapse = ""), "等 "))
  if (length(rendered) == 1) return(rendered)
  paste0(paste0(rendered[-length(rendered)], collapse = ""), "和", rendered[length(rendered)])
}

render_summary_entry_paragraph <- function(entry, theme_color) {
  if (!is.null(entry$paragraphs)) {
    if (!is.list(entry$paragraphs) || length(entry$paragraphs) == 0) {
      stop("摘要导读的 paragraphs 必须是非空列表。")
    }
    rendered <- vapply(seq_along(entry$paragraphs), function(i) {
      paragraph <- entry$paragraphs[[i]]
      parts <- if (is.list(paragraph) && !is.null(paragraph$parts)) {
        paragraph$parts
      } else {
        paragraph
      }
      paste0(
        '<div class="summary-entry-paragraph" data-summary-entry-paragraph="true" ',
        'style="margin:0 0 0.75em;text-indent:', if (i == 1) '0' else '2em', ';">',
        summary_render_parts(parts, theme_color),
        '</div>'
      )
    }, character(1))
    return(paste0(rendered, collapse = ""))
  }
  if (!is.null(entry$parts)) {
    return(summary_render_parts(entry$parts, theme_color))
  }
  entry_type <- if (is.null(entry$type)) "directory" else entry$type
  description <- if (is.null(entry$description)) "" else entry$description
  if (!nzchar(description)) stop("摘要第一段的主题内容说明不能为空。")

  if (identical(entry_type, "directory")) {
    paths <- as.character(entry$paths)
    if (length(paths) == 0 || any(!nzchar(paths))) stop("目录入口不能为空。")
    path_text <- paste(
      vapply(paths, summary_path_span, character(1), theme_color = theme_color),
      collapse = "、"
    )
    prefix <- paste0("从 dbCodeBook 的目录 ", path_text, " 进入，可以看到 ")
  } else if (identical(entry_type, "search")) {
    keyword <- as.character(entry$keyword)
    if (length(keyword) != 1 || !nzchar(keyword)) stop("普通检索关键词不能为空。")
    prefix <- paste0(
      "在 dbCodeBook 中，通过 ",
      summary_search_span(keyword, theme_color),
      " 检索，可以看到 "
    )
  } else {
    stop("摘要入口类型只能是 directory 或 search。")
  }

  count_text <- ""
  if (!is.null(entry$count)) {
    count_text <- summary_count_span(entry$count, " 条", theme_color, weight = 400)
  }
  paste0(prefix, count_text, summary_render_inline_code(description))
}

render_summary_selection_paragraph <- function(selection, theme_color) {
  wrap_source_structure <- function(content) {
    class_name <- selection$class
    if (is.null(class_name) || !nzchar(class_name)) {
      return(content)
    }
    if (length(class_name) != 1 || !grepl("^[A-Za-z][A-Za-z0-9_-]*$", class_name)) {
      stop("摘要第二信息区的 class 必须是单个合法 CSS class 名称。")
    }
    display_attr <- ""
    if (!is.null(selection$display)) {
      if (!identical(selection$display, "period-tabs")) {
        stop("摘要第二信息区目前只支持 display = period-tabs。")
      }
      display_attr <- ' data-display="period-tabs"'
    }
    paste0(
      '<div class="', class_name,
      '" data-raw-source-structure="true"', display_attr, '>',
      content, '</div>'
    )
  }

  render_selection_lines <- function(lines) {
    if (!is.list(lines) || length(lines) == 0) {
      stop("摘要第二信息区的 lines 必须是非空列表。")
    }
    rendered <- vapply(seq_along(lines), function(line_index) {
      line <- lines[[line_index]]
      if (is.list(line) && identical(line$type, "period_note")) {
        if (length(line$title) != 1 || !nzchar(line$title) ||
            !is.list(line$lines) || length(line$lines) == 0) {
          stop("时期说明块必须包含一个标题和至少一行内容。")
        }
        return(paste0(
          '<div class="summary-period-note" data-summary-period-note="true" ',
          'style="background:#F4F3F0;border:1px solid #F4F3F0;border-radius:8px;',
          'padding:10px 12px;margin:0 0 0.9em;text-indent:0;">',
          '<div class="summary-period-note-title" ',
          'data-summary-period-note-title="true" ',
          'style="font-weight:700;margin-bottom:0.45em;text-indent:0;">',
          summary_escape_html(line$title), '</div>',
          render_selection_lines(line$lines),
          '</div>'
        ))
      }
      if (is.list(line) && identical(line$type, "definition_block")) {
        if (length(line$title) != 1 || !nzchar(line$title) ||
            !is.list(line$lines) || length(line$lines) == 0) {
          stop("定义处理块必须包含一个标题和至少一行内容。")
        }
        return(paste0(
          '<div class="summary-definition-block" data-summary-definition-block="true" ',
          'style="background:#F4F3F0;border:1px solid #F4F3F0;border-radius:8px;',
          'padding:10px 12px;margin:0.9em 0;text-indent:0;">',
          '<div class="summary-definition-block-title" ',
          'data-summary-definition-block-title="true" ',
          'style="font-weight:700;margin-bottom:0.45em;text-indent:0;">',
          summary_escape_html(line$title), '</div>',
          render_selection_lines(line$lines),
          '</div>'
        ))
      }
      if (is.character(line) && length(line) == 1) {
        content <- summary_render_inline_code(line)
        strong <- FALSE
        questionnaire <- FALSE
        period_heading <- FALSE
        definition_item <- FALSE
        period_note_item <- FALSE
        period_note_first <- FALSE
      } else {
        if (!is.list(line) || is.null(line$parts)) {
          stop("摘要第二信息区的每一行必须是文本或带 parts 的结构。")
        }
        if (!is.null(line$indent)) {
          stop("摘要第二信息区不使用分项缩进；需要突出层级时请使用 strong = TRUE 标记总领句。")
        }
        content <- summary_render_parts(line$parts, theme_color)
        strong <- isTRUE(line$strong)
        questionnaire <- isTRUE(line$questionnaire)
        period_heading <- isTRUE(line$period_heading)
        definition_item <- isTRUE(line$definition_item)
        period_note_item <- isTRUE(line$period_note_item)
        period_note_first <- isTRUE(line$period_note_first)
      }
      if (strong) {
        strong_style <- if (period_heading) {
          paste0('font-weight:700;color:', theme_color, ';')
        } else {
          'font-weight:700;'
        }
        content <- paste0(
          '<strong data-summary-selection-lead="true" style="', strong_style, '">',
          content, '</strong>'
        )
      }
      line_style <- if (period_heading && line_index == 1) {
        'display:block;text-indent:0;margin:0 0 0.45em;'
      } else if (period_heading) {
        'display:block;text-indent:0;margin:0.9em 0 0.45em;'
      } else if (questionnaire) {
        'display:block;line-height:1.7;text-indent:0;margin-bottom:0.75em;'
      } else if (period_note_item && period_note_first) {
        'display:block;line-height:1.7;text-indent:0;margin-top:0.35em;'
      } else if (period_note_item) {
        'display:block;line-height:1.7;text-indent:2em;margin-top:0.35em;'
      } else if (definition_item) {
        'display:block;line-height:1.7;text-indent:0;margin-top:0.35em;'
      } else {
        'display:block;'
      }
      questionnaire_attr <- if (questionnaire) {
        ' class="summary-questionnaire-line" data-summary-questionnaire-line="true"'
      } else {
        ''
      }
      paste0(
        '<span data-summary-selection-line="true"', questionnaire_attr,
        ' style="', line_style, '">', content, '</span>'
      )
    }, character(1))
    paste0(rendered, collapse = "")
  }

  if (!is.null(selection$groups)) {
    groups <- selection$groups
    if (!is.list(groups) || length(groups) == 0) {
      stop("摘要第二信息区的 groups 必须是非空列表。")
    }
    intro <- if (is.null(selection$intro)) "" else {
      render_selection_lines(selection$intro)
    }
    rendered_groups <- vapply(groups, function(group) {
      if (!is.list(group) || is.null(group$period) || is.null(group$label) ||
          is.null(group$lines)) {
        stop("每个来源分组必须包含 period、label 和 lines。")
      }
      period <- as.character(group$period)
      label <- as.character(group$label)
      if (length(period) != 1 || !grepl("^[A-Za-z0-9_-]+$", period)) {
        stop("来源分组的 period 必须是单个安全标识。")
      }
      if (length(label) != 1 || !nzchar(label)) {
        stop("来源分组的 label 必须是非空文本。")
      }
      paste0(
        '<section class="raw-source-period" data-raw-source-period="', period,
        '" data-label="', summary_escape_html(label), '" style="font-size:0.92em;">',
        '<div class="raw-source-period-label">', summary_escape_html(label), '</div>',
        render_selection_lines(group$lines),
        '</section>'
      )
    }, character(1))
    if (anyDuplicated(vapply(groups, function(group) as.character(group$period), character(1))) ||
        anyDuplicated(vapply(groups, function(group) as.character(group$label), character(1)))) {
      stop("时期标识和标签须各自唯一，不能让不同问卷时期共用同一标识。")
    }
    footer <- if (is.null(selection$footer)) "" else {
      render_selection_lines(selection$footer)
    }
    return(wrap_source_structure(paste0(
      intro, paste0(rendered_groups, collapse = ""), footer
    )))
  }

  if (!is.null(selection$lines)) {
    return(wrap_source_structure(render_selection_lines(selection$lines)))
  }
  if (!is.null(selection$parts)) {
    return(wrap_source_structure(summary_render_parts(selection$parts, theme_color)))
  }
  required <- c("raw_count", "concepts", "final_count")
  missing <- required[!vapply(required, function(name) !is.null(selection[[name]]), logical(1))]
  if (length(missing) > 0) stop("摘要第二段缺少字段：", paste(missing, collapse = ", "))
  relation <- if (is.null(selection$relation)) "" else selection$relation
  relation_prefix <- if (is.null(selection$relation_prefix)) "，" else selection$relation_prefix
  relation_text <- if (nzchar(relation)) {
    paste0(relation_prefix, summary_render_inline_code(relation))
  } else {
    ""
  }
  before_count <- if (is.null(selection$before_count)) "" else selection$before_count
  wrap_source_structure(paste0(
    "从中选取 ",
    summary_count_span(selection$raw_count, " 个", theme_color, weight = 400),
    "原始变量，定义",
    summary_join_concepts(selection$concepts, selection$final_count, theme_color),
    before_count,
    summary_count_span(
      selection$final_count,
      " 个变量",
      theme_color,
      weight = 500,
      role = "definition"
    ),
    relation_text
  ))
}

render_summary_insight_card <- function(items,
                                        theme_color,
                                        variant = c("standard", "compact")) {
  variant <- match.arg(variant)
  items <- as.character(items)
  if (length(items) == 0 || any(!nzchar(items))) stop("小book提示文案不能为空。")
  summary_validate_insight_inline_code(items)
  rendered_items <- summary_render_inline_code(items)
  itemized <- grepl(
    "^\\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]|[0-9]+[、.)．])",
    items,
    perl = TRUE
  )
  body <- paste0(
    vapply(seq_along(rendered_items), function(index) {
      text_indent <- if (index == 1L || itemized[[index]]) "0" else "2em"
      paste0(
        '<div class="summary-insight-paragraph" data-summary-insight-paragraph="true" ',
        'style="margin:0;text-indent:', text_indent, ';">',
        rendered_items[[index]],
        '</div>'
      )
    }, character(1)),
    collapse = ""
  )
  if (identical(variant, "compact")) {
    return(c(
      "<!-- summary-insight-card:start -->",
      '<div class="summary-insight-card" data-summary-insight-card="true" style="background:#F4F3F0;border:1px solid #F4F3F0;border-radius:10px;padding:14px 16px;">',
      paste0(
        '<div class="summary-insight-title" data-summary-insight-title="true" ',
        'style="color:', theme_color,
        ';font-weight:700;margin-bottom:6px;">小book提示</div>'
      ),
      paste0(
        '<div class="summary-insight-body" data-summary-insight-body="true" style="font-size:14px;">',
        body, '</div>'
      ),
      "</div>",
      "<!-- summary-insight-card:end -->"
    ))
  }
  c(
    "<!-- summary-insight-card:start -->",
    '<div class="summary-insight-card" data-summary-insight-card="true" style="box-sizing:border-box;margin:18px 0;padding:20px 24px 22px;background:#F4F3F0;border:1px solid #F4F3F0;border-radius:10px;box-shadow:none;">',
    paste0(
      '<div class="summary-insight-title" data-summary-insight-title="true" ',
      'style="margin:0 0 12px;font-size:18px;line-height:1.5;font-weight:700;color:',
      theme_color, ';">小book提示</div>'
    ),
    paste0(
      '<div class="summary-insight-body" data-summary-insight-body="true" ',
      'style="font-size:14px;line-height:1.85;font-style:normal;font-weight:400;',
      'color:#344054;letter-spacing:0;">', body, '</div>'
    ),
    "</div>",
    "<!-- summary-insight-card:end -->"
  )
}

render_summary_note_section <- function(entry,
                                        selection,
                                        theme_color,
                                        insight_items = NULL,
                                        insight_variant = c("standard", "compact"),
                                        summary_source = NULL) {
  insight_variant <- match.arg(insight_variant)
  lines <- c(
    "## 摘要导读",
    "",
    render_summary_entry_paragraph(entry, theme_color),
    "",
    render_summary_selection_paragraph(selection, theme_color)
  )
  if (!is.null(insight_items)) {
    lines <- c(lines, "", render_summary_insight_card(
      insight_items,
      theme_color,
      variant = insight_variant
    ))
  }
  if (!is.null(summary_source)) {
    lines <- c(
      lines,
      "",
      render_summary_selection_paragraph(summary_source, theme_color)
    )
  }
  c(lines, "")
}
