definition_wrap_source_cards <- function(text) {
  if (!any(grepl("hm-table", text, fixed=TRUE)) ||
      !any(grepl("var-name-line", text, fixed=TRUE)) ||
      any(grepl('data-definition-source-card-layout="wrap-v1"', text, fixed=TRUE))) return(text)
  c(text,
    '<style data-definition-source-card-layout="wrap-v1">',
    '.hm-table .var-name-line{flex-wrap:wrap;align-items:flex-start;}',
    '.hm-table .var-name{flex:0 1 auto;min-width:0;max-width:100%;overflow-wrap:anywhere;white-space:normal;}',
    '.hm-table .varlink-block{flex:1 0 100%;width:100%;min-width:0;max-width:100%;align-items:flex-start;}',
    '.hm-table .varlink-info{flex:1 1 auto;min-width:0;max-width:100%;overflow-wrap:anywhere;white-space:normal;}',
    '</style>')
}

validate_hrs_period_order <- function(cycle_order) {
  periods <- as.character(cycle_order)
  fail <- function() stop("Invalid HRS year order.")
  if (!length(periods) || anyNA(periods) || anyDuplicated(periods) ||
      any(!grepl("^[0-9]{4}(-[0-9]{4}| (Spring|Summer|Fall|Winter))?$", periods))) fail()
  start <- as.integer(substr(periods, 1L, 4L))
  end <- start
  interval <- grepl("^[0-9]{4}-[0-9]{4}$", periods)
  end[interval] <- as.integer(substr(periods[interval], 6L, 9L))
  season <- match(sub("^[0-9]{4} ", "", periods), c("Spring", "Summer", "Fall", "Winter"))
  season[is.na(season)] <- 0L
  if (any(start < 1900L | end > 2100L | end < start) ||
      is.unsorted(start * 10L + season)) fail()
  invisible(periods)
}

mhas_questionnaire_periods <- function() list(
  MHAS_SURVEY_CORE_RESPONDENT=c("2001","2003","2012","2015","2018","2021","2024"),
  MHAS_SURVEY_NEXT_OF_KIN=c("2003","2012","2015","2018","2021","2024"),
  MHAS_MEXCOG_COGNITIVE_ASSESSMENT=c("2016","2021"),
  MHAS_MEXCOG_INFORMANT_INTERVIEW=c("2016","2021"))

validate_mhas_analysis_scope <- function(frames, mhas_analysis_scope = NULL, analysis_vars = NULL) {
    if (!is.null(mhas_analysis_scope) || any(vapply(frames, function(frame) "source_module" %in% names(frame), logical(1)))) {
      if (is.null(mhas_analysis_scope) || is.null(names(mhas_analysis_scope))) stop("MHAS scoped analysis requires mhas_analysis_scope.")
      supported_modules <- mhas_questionnaire_periods()
      if (any(!names(mhas_analysis_scope) %in% names(supported_modules))) stop("Unknown MHAS analysis module.")
      for (module in names(mhas_analysis_scope)) {
        periods <- mhas_analysis_scope[[module]]$analysis_periods
        if (!is.character(periods) || !length(periods) || anyNA(periods) || anyDuplicated(periods) ||
            any(!periods %in% supported_modules[[module]])) stop("Invalid MHAS module analysis periods.")
      }
      source_record_path <- Sys.getenv("DBCODEBOOK_DEFINITION_SOURCE_RECORD")
      if (nzchar(source_record_path)) {
        declared <- jsonlite::fromJSON(source_record_path, simplifyVector=FALSE)$mhas_analysis_scope
        if (!setequal(names(declared), names(mhas_analysis_scope))) stop("MHAS renderer scope differs from source record.")
        for (module in names(mhas_analysis_scope)) for (field in c("analysis_periods", "result_variables")) {
          if (!identical(as.character(unlist(declared[[module]][[field]])), as.character(unlist(mhas_analysis_scope[[module]][[field]])))) stop("MHAS renderer scope differs from source record.")
        }
      }
      owned <- unlist(lapply(mhas_analysis_scope, function(scope) scope$result_variables), use.names=FALSE)
      if (anyDuplicated(owned) || (!is.null(analysis_vars) && !setequal(owned, analysis_vars))) stop("MHAS scope must own every result exactly once.")
      for (frame in frames) {
        if (!"source_module" %in% names(frame) || any(!frame$source_module %in% names(mhas_analysis_scope))) stop("Missing or unknown MHAS source module.")
        for (module in names(mhas_analysis_scope)) {
          scope <- mhas_analysis_scope[[module]]
          if (!length(scope$analysis_periods) || !length(scope$result_variables) || !all(scope$result_variables %in% names(frame))) stop("Incomplete MHAS module scope.")
          own <- frame$source_module == module
          if (any(!frame$Wave_id[own] %in% scope$analysis_periods)) stop("MHAS analysis outside module applicability.")
          for (variable in scope$result_variables) {
            other <- frame[[variable]][!own]
            if (any(!is.na(other) & as.character(other) != "")) stop("MHAS result populated in another source module.")
          }
        }
      }
    }

}

validate_nhis_render_inputs <- function(frames, cycle_order, dataset_id) {
  supported <- switch(dataset_id,
    nhis_pre1997=c(paste0(1963:1967,"FY"),"1968FY","1968CY",as.character(1969:1996)),
    nhis_1997_2018=as.character(1997:2018), nhis_2019_plus=as.character(2019:2025),
    stop("NHIS requires an explicit supported dataset_id."))
  if (!is.character(cycle_order) || !length(cycle_order) || anyNA(cycle_order) ||
      any(!cycle_order %in% supported) || anyDuplicated(cycle_order) ||
      is.unsorted(match(cycle_order,supported))) stop("Invalid NHIS declared period order.")
  for (frame in frames) {
    keys <- c("ID","Wave_id","Survey_year")
    if (!all(keys %in% names(frame)) || !all(vapply(frame[keys],is.character,logical(1)))) stop("NHIS requires original character identity columns.")
    if (anyNA(frame[keys]) || any(vapply(frame[keys],function(x) any(!nzchar(trimws(x))),logical(1))) ||
        anyDuplicated(frame$ID) || any(!frame$Wave_id %in% cycle_order) ||
        any(frame$Survey_year != substr(frame$Wave_id,1,4))) stop("Invalid NHIS unique-person export identity.")
  }
}

validate_nhanes_render_inputs <- function(frames, cycle_order) {
  if (!is.character(cycle_order) || !length(cycle_order) || anyNA(cycle_order) ||
      any(!grepl("^[0-9]{4}-[0-9]{4}$", cycle_order)) || anyDuplicated(cycle_order) ||
      is.unsorted(cycle_order)) stop("Invalid NHANES declared periods.")
  if (any(substr(cycle_order, 1, 4) >= substr(cycle_order, 6, 9))) stop("Invalid NHANES period bounds.")
  for (frame in frames) {
    keys <- c("SEQN", "YEAR")
    if (!all(keys %in% names(frame)) || !all(vapply(frame[keys], is.character, logical(1)))) stop("NHANES requires character SEQN and YEAR.")
    if (anyNA(frame[keys]) || any(!grepl("^[0-9]+(\\.0+)?$", frame$SEQN)) ||
        any(!frame$YEAR %in% cycle_order)) stop("Invalid NHANES person-period identity.")
    normalized <- sub("\\.0+$", "", frame$SEQN)
    normalized <- sub("^0+", "", normalized)
    if (anyDuplicated(data.frame(SEQN=normalized, YEAR=frame$YEAR))) stop("Duplicate NHANES person-period.")
  }
}

validate_nhanesiii_render_inputs <- function(frames, cycle_order) {
  if (!(identical(cycle_order, "1988-1994") ||
        identical(cycle_order, c("1988-1991", "1991-1994")))) stop("NHANES III requires the confirmed whole-survey or two-phase period order.")
  validate_nhanes_render_inputs(frames, cycle_order)
  for (frame in frames) {
    key <- sub("^0+", "", sub("\\.0+$", "", frame$SEQN))
    if (any(!nzchar(key)) || anyDuplicated(key)) stop("NHANES III requires unique positive personal identifiers.")
  }
}

validate_mhas_render_inputs <- function(frames, cycle_order) {
  periods <- c("2001", "2003", "2012", "2015", "2016", "2018", "2021", "2024")
  if (!is.character(cycle_order) || !length(cycle_order) || anyNA(cycle_order) ||
      any(!cycle_order %in% periods) || anyDuplicated(cycle_order) ||
      is.unsorted(match(cycle_order, periods))) stop("Invalid MHAS period order.")
  for (frame in frames) {
    keys <- if ("source_module" %in% names(frame)) c("source_module", "ID", "Wave_id") else c("ID", "Wave_id")
    if ("source_module" %in% names(frame)) {
      supported_modules <- mhas_questionnaire_periods()
      if (any(!frame$source_module %in% names(supported_modules))) stop("Unknown MHAS source_module.")
      for (module in unique(frame$source_module)) {
        if (any(!frame$Wave_id[frame$source_module == module] %in% supported_modules[[module]])) stop("Invalid MHAS source module period.")
      }
    }
    if (!all(keys %in% names(frame)) || !all(vapply(frame[keys], is.character, logical(1)))) {
      stop("MHAS requires character ID and Wave_id.")
    }
    if (anyNA(frame[keys]) || any(vapply(frame[keys], function(x) any(!nzchar(trimws(x))), logical(1))) ||
        anyDuplicated(frame[keys])) stop("Invalid MHAS person-period identity.")
    if (any(!startsWith(frame$ID, paste0(frame$Wave_id, "|")))) stop("MHAS ID period prefix differs from Wave_id.")
    if (any(!frame$Wave_id %in% cycle_order)) stop("MHAS observed period outside declared cycle_order.")
  }
}

chns_year_values <- function(values) {
  text <- as.character(values)
  if (anyNA(text) || any(!grepl("^[0-9]{4}(\\.0+)?$", text))) stop("Invalid CHNS integer survey year.")
  sub("\\.0+$", "", text)
}

validate_chns_render_inputs <- function(frames, cycle_order) {
  supported <- c("1989", "1991", "1993", "1997", "2000", "2004", "2006", "2009", "2011", "2015")
  if (!length(cycle_order) || anyNA(cycle_order) || any(!cycle_order %in% supported) ||
      anyDuplicated(cycle_order) || is.unsorted(match(cycle_order, supported))) stop("Invalid CHNS year order.")
  for (frame in frames) {
    keys <- c("ID", "IDind", "WAVE")
    if (!all(keys %in% names(frame))) stop("CHNS requires ID, IDind and WAVE.")
    if (!all(vapply(frame[c("ID", "IDind")], is.character, logical(1)))) stop("CHNS ID and IDind must remain character.")
    if (anyNA(frame[keys]) || any(vapply(frame[keys], function(x) any(!nzchar(trimws(as.character(x)))), logical(1)))) stop("CHNS identities must be nonempty.")
    years <- chns_year_values(frame$WAVE)
    if (anyDuplicated(frame$ID) || anyDuplicated(data.frame(IDind=frame$IDind, WAVE=years))) stop("Duplicate CHNS person-period identity.")
    if (any(!years %in% cycle_order)) stop("Observed CHNS WAVE outside declared cycle_order.")
  }
  invisible(TRUE)
}

validate_knhanes_render_inputs <- function(frames, cycle_order) {
  supported <- c("1998", "2001", "2005", as.character(2007:2024))
  if (!is.character(cycle_order) || !length(cycle_order) || anyNA(cycle_order) ||
      anyDuplicated(cycle_order) || any(!cycle_order %in% supported) ||
      is.unsorted(match(cycle_order, supported))) stop("Invalid KNHANES year order.")
  for (frame in frames) {
    if (!all(c("ID", "id", "year") %in% names(frame))) stop("KNHANES requires ID, id and year.")
    if (!is.character(frame$id) || !is.character(frame$ID)) stop("KNHANES ID and id must remain character.")
    respondent <- trimws(frame$id)
    year <- trimws(as.character(frame$year))
    if (anyNA(respondent) || any(!nzchar(respondent)) || anyNA(year) ||
        any(!year %in% cycle_order) || anyNA(frame$ID) ||
        any(frame$ID != paste(year, respondent, sep="_"))) stop("Invalid KNHANES respondent-year identity.")
    keys <- frame[c("ID", "id", "year")]
    if ("sample_source" %in% names(frame)) {
      if (!is.character(frame$sample_source) || anyNA(frame$sample_source) ||
          any(!frame$sample_source %in% c("Core data", "Indoor air quality special release"))) stop("Invalid KNHANES sample_source.")
      keys$sample_source <- frame$sample_source
    }
    if (anyDuplicated(keys)) stop("KNHANES renderer needs unique respondent-year rows within each sample.")
  }
  invisible(TRUE)
}

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
    stop("Criteria 生成源不得手写 <code>；请使用成对反引号标记变量名和程序代码。")
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

criteria_table <- function(block, render_values) {
  render_row <- function(cells, tag) {
    paste0("<tr>", paste0(vapply(seq_along(cells), function(i) {
      paste0("<", tag, ' style="padding:4px 8px;border:1px solid #ddd;text-align:',
             block$align[[i]], ';">',
             criteria_render_inline_code(render_values(cells[[i]])), "</", tag, ">")
    }, character(1)), collapse = ""), "</tr>")
  }
  paste0('<div data-criteria-item="true" style="margin:6px 0 6px 1.8em;overflow-x:auto;">',
         '<table data-criteria-table="true" style="border-collapse:collapse;font-size:0.92em;">',
         "<thead>", render_row(block$header, "th"), "</thead><tbody>",
         paste0(vapply(block$rows, render_row, character(1), tag = "td"), collapse = ""),
         "</tbody></table></div>")
}

definition_copy_check <- function(copy_path = "文案.md", source = NULL,
                                  note = NULL, export = NULL, analysis_vars = NULL) {
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
  if (!is.null(analysis_vars)) {
    args <- c(args, "--analysis-vars", shQuote(paste(analysis_vars, collapse = ",")))
  }
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

validate_definition_display_policy <- function(display_policy, analysis_vars) {
  # Python resolves the topic policy. R only checks that it belongs to this output.
  if (is.null(display_policy)) return(NULL)
  policy_vars <- as.character(unlist(display_policy$analysis_vars, use.names = FALSE))
  if (!identical(policy_vars, analysis_vars)) {
    stop("display_policy analysis_vars differs from the actual analysis_vars or order.")
  }
  if (!is.character(display_policy$topic_kind) || length(display_policy$topic_kind) != 1L ||
      !display_policy$topic_kind %in% c("module", "standard", "questionnaire_module") ||
      !is.logical(display_policy$compact_module) || length(display_policy$compact_module) != 1L ||
      is.na(display_policy$compact_module)) stop("Invalid definition display_policy.")
  expected_compact <- identical(display_policy$topic_kind, "module") && length(analysis_vars) > 10L
  if (!identical(display_policy$compact_module, expected_compact)) stop("display_policy compact flag differs from topic kind and result count.")
  display_policy
}

read_definition_copy <- function(analysis_vars, path = "文案.md") {
  exported <- tempfile(fileext = ".json")
  on.exit(unlink(exported), add = TRUE)
  definition_copy_check(path, export = exported, analysis_vars = analysis_vars)
  copy <- jsonlite::read_json(exported)
  display_policy <- validate_definition_display_policy(copy$display_policy, analysis_vars)
  compact_module <- !is.null(display_policy) && isTRUE(display_policy$compact_module)
  if (!compact_module && !identical(names(copy$criteria), analysis_vars)) {
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
  criteria <- lapply(names(copy$criteria), function(variable) {
    fields <- copy$criteria[[variable]]
    paste0(vapply(names(fields), function(field) {
      blocks <- copy$criteria_blocks[[variable]][[field]]
      paste0(criteria_heading(field), paste0(vapply(blocks, function(block) {
        if (identical(block$type, "table")) criteria_table(block, render_values)
        else criteria_item(render_values(block$text))
      }, character(1)), collapse = ""))
    }, character(1)), collapse = "")
  })
  names(criteria) <- names(copy$criteria)
  result <- list(
    display_policy = display_policy,
    criteria = criteria,
    criteria_intro = copy$criteria_intro,
    definition_basis = if (is.null(copy$definition_basis)) "" else copy$definition_basis,
    summary_entry = list(paragraphs = lapply(copy$summary_blocks, function(block) {
      if (identical(block$type, "code_tree")) return(block)
      list(parts = inline_parts(block$text))
    })),
    summary_insight_items = if (nzchar(copy$insight)) paragraphs(copy$insight) else NULL,
    reference_lines = if (nzchar(copy$references)) c("## 参考资料说明", "", copy$references) else character()
  )
  if (!is.null(copy$questionnaire)) {
    result$summary_selection <- list(class = "raw-source-structure", display = "period-tabs",
      groups = lapply(names(copy$questionnaire), function(period) {
        block <- copy$questionnaire[[period]]
        lines <- list(summary_period_note(paragraphs(block$design), title = block$design_title))
        previous_group <- ""
        for (question in block$questions) {
            group <- if (is.null(question$group)) "" else question$group
            if (nzchar(group) && !identical(group, previous_group)) {
              lines <- c(lines, list(summary_period_heading_line(group)))
            }
            previous_group <- group
            lines <- c(lines, list(summary_questionnaire_line(question$id, question$text,
              notes = unlist(question$notes, use.names = FALSE),
              condition = if (nzchar(question$condition)) question$condition else character(),
              options = lapply(question$options, function(option) {
                summary_questionnaire_option(option$text, option$jump)
              }), after = unlist(question$instructions, use.names = FALSE))))
            for (flow in question$flows) lines <- c(lines, list(list(type = "questionnaire_flow", text = flow)))
        }
        list(period = period, label = block$label, module = block$module, lines = lines)
      }))
    modules <- vapply(copy$questionnaire, function(block) if (is.null(block$module)) "" else block$module, character(1))
    if (all(nzchar(modules))) {
      groups <- result$summary_selection$groups
      result$summary_selection <- list(modules = lapply(unique(modules), function(name) {
        list(label = name, class = "raw-source-structure", display = "period-tabs",
             groups = unname(groups[modules == name]))
      }))
    }
  }
  result
}

render_copy_fragments <- function(copy_path, analysis_vars, theme_color) {
  copy <- read_definition_copy(analysis_vars, path = copy_path)
  list(
    summary = render_summary_entry_paragraph(copy$summary_entry, theme_color),
    insight = if (is.null(copy$summary_insight_items)) "" else paste(
      render_summary_insight_card(copy$summary_insight_items, theme_color, variant = "compact"),
      collapse = "\n"
    ),
    references = paste(copy$reference_lines, collapse = "\n")
  )
}

render_criteria_intro <- function(text) {
  if (is.null(text) || !nzchar(trimws(text))) return(character())
  lines <- strsplit(text, "\n", fixed = TRUE)[[1]]
  lines <- lines[nzchar(trimws(lines))]
  paste0('<div data-criteria-intro="true">',
         paste0(vapply(lines, criteria_item, character(1)), collapse = ''), '</div>')
}

definition_html_with_intro <- function(lines, intro) {
  if (is.null(intro) || !nzchar(trimws(intro))) return(lines)
  text <- paste(lines, collapse = "\n")
  table_start <- regexpr("<table\\b", text, perl = TRUE)
  if (table_start[[1]] < 0L) stop("定义HTML缺少表格，不能放入共同说明。")
  paste0(substr(text, 1L, table_start[[1]] - 1L), render_criteria_intro(intro),
         "\n", substring(text, table_start[[1]]))
}

validate_criteria_markup <- function(criteria, variable_names = character(), result_values = list()) {
  criterion_names <- names(criteria)
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
      "请在文案中使用普通方括号，如 [0]、[No_difficulty]，去掉外层反引号：",
      paste(invalid_names, collapse = "、")
    )
  }
  value_text <- unlist(lapply(seq_along(criteria), function(i) {
    markup <- regmatches(criteria[i], gregexpr("<u>\\[[^<>]*\\]</u>", criteria[i]))[[1]]
    values <- gsub("^<u>\\[|\\]</u>$", "", markup)
    # Only an exact value observed in this result is exempt from the name check.
    allowed <- if (is.null(criterion_names)) character() else result_values[[criterion_names[i]]]
    values[!values %in% as.character(allowed[!is.na(allowed)])]
  }))
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
                                           source_codebook = analysis_codebook,
                                           default_sources = character()) {
  if (!all(c("Variable", "newname") %in% names(raw_codebook))) {
    stop("raw_codebook 必须包含 Variable 和 newname。")
  }
  sources <- definition_card_default_sources(source_codebook)
  sources[names(definition_card_default_sources(analysis_codebook))] <-
    definition_card_default_sources(analysis_codebook)
  resolve_sources <- function(aliases, visiting = character()) {
    resolved <- lapply(aliases, function(alias) {
      if (alias %in% raw_codebook$newname || alias %in% default_sources) return(alias)
      if (alias %in% visiting) stop("正式来源关系存在循环：", paste(c(visiting, alias), collapse = " -> "))
      if (!alias %in% names(sources)) {
        stop("raw_codebook 或正式来源关系中找不到变量：", alias)
      }
      resolve_sources(sources[[alias]], c(visiting, alias))
    })
    unique(unlist(resolved, use.names = FALSE))
  }
  vapply(analysis_codebook$Variable, function(variable) {
    aliases <- resolve_sources(sources[[variable]], variable)
    rows <- match(aliases, raw_codebook$newname)
    original_names <- as.character(raw_codebook$Variable[rows])
    original_names[is.na(rows)] <- aliases[is.na(rows)]
    paste0(original_names, "=", aliases, collapse = ", ")
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
    detail_html_lines,
    include_definition = TRUE) {
  visible_code <- trimws(publish_code[nzchar(trimws(publish_code))])
  if (length(visible_code) && grepl("^#[- #]*[0-9]+[ .、_-]", tail(visible_code, 1))) {
    warning("公开代码以空小节标题结束；请把正式工作簿写出放在 # 输出 之前。", call. = FALSE)
  }
  c(
    summary_section,
    if (length(summary_extra_lines) > 0) c(summary_extra_lines, "") else character(),
    if (include_definition) c("## 定义", "", definition_html_lines, "") else character(),
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

definition_analysis_identity_contract <- function(database, analysis_unit = "person_period", identity_keys = NULL,
    record_path = Sys.getenv("DBCODEBOOK_DEFINITION_SOURCE_RECORD")) {
  if (identical(analysis_unit, "person_period") && is.null(identity_keys)) {
    contract <- list(analysis_unit = analysis_unit)
  } else if (identical(analysis_unit, "person_period") && toupper(database) == "MHAS" &&
      identical(identity_keys, c("source_module", "ID", "Wave_id"))) {
    contract <- list(analysis_unit = analysis_unit, identity_keys = identity_keys)
  } else if (identical(analysis_unit, "household_period") && toupper(database) == "CHARLS" &&
      identical(identity_keys, c("householdid", "year"))) {
    contract <- list(analysis_unit = analysis_unit, identity_keys = identity_keys)
  } else stop("Invalid explicit renderer analysis_unit/identity_keys contract.")
  if (!nzchar(record_path)) return(contract)
  if (!file.exists(record_path)) stop("Definition source record does not exist: ", record_path)
  record <- jsonlite::fromJSON(record_path, simplifyVector = FALSE)
  unit <- record$analysis_unit
  if (is.null(unit)) unit <- "person_period"
  keys <- if (is.null(record$identity_keys)) NULL else unlist(record$identity_keys, use.names = FALSE)
  if (!identical(unit, analysis_unit) || !identical(keys, identity_keys) ||
      (identical(unit, "household_period") && !identical(toupper(record$database), "CHARLS"))) {
    stop("Renderer identity declaration differs from the bound source record.")
  }
  contract
}

validate_person_period_outputs <- function(frames, database, contract = list(analysis_unit = "person_period")) {
  household <- identical(contract$analysis_unit, "household_period")
  keys <- switch(toupper(database), CHARLS=c("id", "year"), ELSA=c("idauniq", "Wave"),
    HRS=c("HHID", "PN", "year"), SHARE=c("mergeid", "Wave_id"),
    KLOSA=c("Harmonized_id", "Wave_id"), CHNS=c("IDind", "WAVE"), KNHANES=c("id", "year"), MHAS=c("ID", "Wave_id"), NHANES=c("SEQN", "YEAR"), NHANESIII=c("SEQN", "YEAR"), NHIS=c("ID","Wave_id"))
  if (!is.null(contract$identity_keys)) keys <- contract$identity_keys
  original_keys <- NULL
  for (frame in frames) {
    key_names <- if (toupper(database) == "KNHANES" && "sample_source" %in% names(frame)) c("sample_source", keys) else keys
    if (!all(key_names %in% names(frame))) stop(if (household) "Final data requires household-year rows: " else "Final data requires person-period long rows: ", paste(key_names, collapse=", "))
    if (toupper(database) == "MHAS" && "source_module" %in% names(frame) && !"source_module" %in% keys) key_names <- c("source_module", keys)
    identity <- frame[key_names]
    if (anyNA(identity) || any(vapply(identity, function(x) any(!nzchar(trimws(as.character(x)))), logical(1)))) {
      stop(if (household) "Final household-year keys must not be missing." else "Final person-period keys must not be missing.")
    }
    if (household) {
      if (!all(vapply(identity, is.character, logical(1)))) stop("Household keys must remain character strings.")
      if (anyDuplicated(identity)) stop("Final data must contain one row per household per year.")
      if (is.null(original_keys)) original_keys <- identity
      else if (!identical(lapply(identity, unname), lapply(original_keys, unname))) stop("Household outputs must preserve all source keys and row order.")
      next
    }
    period <- sub("^Wave +", "", as.character(identity[[length(key_names)]]))
    identity[[length(key_names)]] <- sub("\\.0+$", "", period)
    if (anyDuplicated(identity)) stop("Final data must contain one row per person per period.")
  }
}


definition_display_periods <- function(database, adopted_periods, language = NULL, dataset_id = NULL) {
  root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
  if (!nzchar(root)) {
    home <- Sys.getenv("CODEX_HOME")
    if (!nzchar(home)) home <- file.path(Sys.getenv("USERPROFILE", path.expand("~")), ".codex")
    root <- file.path(home, "skills", "dbcodebook-definition")
  }
  catalog <- jsonlite::fromJSON(file.path(root, "references", "display-periods.json"))
  periods <- catalog[[toupper(database)]]
  if (toupper(database) == "NHIS") {
    periods <- periods[[dataset_id]]
    if (is.null(periods)) stop("NHIS display requires dataset_id.")
    return(unique(c(periods,as.character(adopted_periods))))
  }
  if (toupper(database) == "KLOSA" && identical(language, "en")) periods <- periods[seq_len(9L)]
  periods <- unique(c(periods, as.character(adopted_periods)))
  if (all(grepl("^Wave ", periods))) periods[order(as.integer(sub("^Wave ", "", periods)))] else periods[order(periods)]
}

# One display mapping: names are calculated components/results; values are final group labels.
definition_component_categories <- function(wide_data, analysis_vars, component_groups) {
  variables <- as.character(wide_data$Variable)
  if (is.null(names(component_groups)) || anyDuplicated(names(component_groups)) ||
      !setequal(variables, names(component_groups))) {
    stop("component_groups must name every displayed component/result exactly once")
  }
  assigned <- as.character(component_groups[variables])
  if (anyNA(assigned) || any(!nzchar(trimws(assigned))) || any(grepl("(^|·)(组分|定义)$", assigned))) {
    stop("Use an English module/category name for results and append ·Components for calculated components")
  }
  if (any(!variables %in% analysis_vars & !grepl(".+·Components$", assigned))) {
    stop("非最终输出的计算成分须归入组分，不能标成定义")
  }
  groups <- if (is.factor(component_groups)) levels(component_groups) else unique(assigned)
  groups <- groups[groups %in% assigned]
  wide_data$category <- factor(assigned, levels = groups)
  wide_data <- wide_data[order(wide_data$category, seq_along(variables)), , drop = FALSE]
  if (!identical(as.character(wide_data$Variable[wide_data$Variable %in% analysis_vars]), analysis_vars)) {
    stop("分组顺序与 analysis_vars 不一致；按已确认顺序组织分组映射。")
  }
  list(data = wide_data, groups = groups)
}

definition_component_titles <- function(text, groups) {
  esc <- function(x) as.character(htmltools::htmlEscape(x, attribute = TRUE))
  for (group in groups) {
    role <- if (grepl(".+·Components$", group)) "component" else "defined"
    attributes <- paste0(' data-component-group="', esc(group),
      '" data-variable-role="', role, '"')
    text <- gsub(paste0('>', esc(group), '</a>'),
      paste0(attributes, '>', esc(group), '</a>'), text, fixed = TRUE)
    text <- gsub(paste0('<summary>', esc(group), '</summary>'),
      paste0('<summary', attributes, '>', esc(group), '</summary>'), text, fixed = TRUE)
  }
  text
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
    summary_source = NULL, # Retired: accepted for existing scripts, never rendered.
    file_stem,
    note_name,
    qa_title,
    transaction_id,
    script_file,
    theme_color = "#A33842",
    cycle_order = c("2011", "2013", "2015", "2018", "2020"),
    raw_source_years = NULL,
    raw_row_count = nrow(data),
    hist_binwidth = NULL,
    hist_mode = "linear",
    evidence_lines = character(),
    reference_lines = character(),
    summary_extra_lines = character(),
    database = "CHARLS",
    criteria_intro = "",
    language = NULL,
    definition_basis = "",
    display_policy = NULL,
    medicine_codebook = NULL,
    component_groups = NULL,
    dataset_id = NULL,
    nhis_source_ids = NULL,
    analysis_unit = "person_period",
    identity_keys = NULL,
    mhas_analysis_scope = NULL,
    component_card_labels = NULL) {
  display_policy <- validate_definition_display_policy(display_policy, analysis_vars)
  compact_module <- !is.null(display_policy) && isTRUE(display_policy$compact_module)
  database <- toupper(database)
  if (!is.null(medicine_codebook)) {
    extract_codebook <- raw_codebook
    required <- c("Variable", "newname", "Label", "input_name", "definition_path", "selected_values")
    if (database != "NHANES" || !all(required %in% names(medicine_codebook)) ||
        !nrow(medicine_codebook) || anyNA(medicine_codebook[required]) ||
        anyDuplicated(medicine_codebook$newname) ||
        any(medicine_codebook$newname %in% c(raw_vars, analysis_vars)) ||
        !all(medicine_codebook$newname %in% names(db_data)) ||
        !all(medicine_codebook$definition_path %in% c("multum", "icd", "drugnames"))) {
      stop("Invalid separate NHANES medicine source dictionary.")
    }
    raw_codebook <- dplyr::bind_rows(raw_codebook, medicine_codebook)
    raw_vars <- c(raw_vars, medicine_codebook$newname)
  }
  if (!is.character(theme_color) || length(theme_color) != 1L ||
      is.na(theme_color) || !nzchar(trimws(theme_color))) {
    theme_color <- "#A33842"
  }
  theme_color <- tryCatch({
    grDevices::col2rgb(theme_color)
    theme_color
  }, error = function(e) "#A33842")
  if (!database %in% c("CHARLS", "ELSA", "HRS", "SHARE", "KNHANES", "KLOSA", "CHNS", "MHAS", "NHANES", "NHANESIII", "NHIS")) stop("Unsupported definition database: ", database)
  if (database == "NHIS") {
    if (missing(cycle_order)) stop("NHIS requires explicit cycle_order.")
    validate_nhis_render_inputs(list(data,db_data,analysis_data),cycle_order,dataset_id)
    data$year <- data$Wave_id; db_data$year <- db_data$Wave_id; analysis_data$year <- analysis_data$Wave_id
    analysis_data$Survey_period <- analysis_data$Wave_id
    if (!is.character(nhis_source_ids) || is.null(names(nhis_source_ids)) ||
        anyDuplicated(names(nhis_source_ids)) || anyDuplicated(nhis_source_ids) ||
        !setequal(names(nhis_source_ids),as.character(raw_codebook$newname)) ||
        anyNA(nhis_source_ids) || any(!grepl("^NHIS_[A-Za-z0-9_]+$",nhis_source_ids))) {
      stop("NHIS requires exact source IDs named by each downloaded alias.")
    }
  }
  if (database %in% c("NHANES", "NHANESIII")) {
    if (missing(cycle_order)) stop("NHANES requires explicit cycle_order.")
    if (database == "NHANESIII") validate_nhanesiii_render_inputs(list(data, db_data, analysis_data), cycle_order)
    else validate_nhanes_render_inputs(list(data, db_data, analysis_data), cycle_order)
    data$year <- data$YEAR
    db_data$year <- db_data$YEAR
    analysis_data$year <- analysis_data$YEAR
  }
  if (database == "MHAS") {
    if (missing(cycle_order)) stop("MHAS requires explicit evidence-based cycle_order.")
    validate_mhas_render_inputs(list(data, db_data, analysis_data), cycle_order)
    validate_mhas_analysis_scope(list(db_data, analysis_data), mhas_analysis_scope, analysis_vars)
    # Project periods only in rendering copies. Retain all original identifiers.
    data$year <- data$Wave_id
    db_data$year <- db_data$Wave_id
    analysis_data$year <- analysis_data$Wave_id
  }
  if (database == "CHNS") {
    if (missing(cycle_order)) stop("CHNS requires explicit, evidence-based cycle_order.")
    validate_chns_render_inputs(list(data, db_data, analysis_data), cycle_order)
    # Local rendering copies only; retain exported WAVE and opaque personal identities.
    data$year <- chns_year_values(data$WAVE)
    db_data$year <- chns_year_values(db_data$WAVE)
    analysis_data$year <- chns_year_values(analysis_data$WAVE)
  }
  if (database == "KNHANES") {
    if (missing(cycle_order)) stop("KNHANES requires explicit, evidence-based cycle_order.")
    validate_knhanes_render_inputs(list(data, db_data, analysis_data), cycle_order)
  }
  period_col <- if (database %in% c("NHANES", "NHANESIII")) "YEAR" else if (database %in% c("ELSA", "KLOSA")) "Wave" else if (database %in% c("SHARE", "MHAS")) "Wave_id" else "year"
  if (database == "NHIS") period_col <- "Survey_period"
  if (database == "KLOSA") {
    if (is.null(language) || length(language) != 1L || !language %in% c("en", "ko")) stop("KLoSA requires language=en or ko.")
    if (missing(cycle_order) || !length(cycle_order) || anyNA(cycle_order)) stop("KLoSA requires explicit nonempty cycle_order.")
    wave_numbers <- suppressWarnings(as.integer(sub("^Wave ", "", cycle_order)))
    if (anyNA(wave_numbers) || !identical(as.character(cycle_order), paste("Wave", wave_numbers)) ||
        any(wave_numbers < 1L | wave_numbers > if (language == "ko") 10L else 9L) ||
        anyDuplicated(wave_numbers) || is.unsorted(wave_numbers)) stop("Invalid KLoSA declared Wave order.")
    expected <- as.character(cycle_order)
    project <- function(frame) {
      if (!all(c("ID", "Harmonized_id", "Wave_id") %in% names(frame))) stop("KLoSA export identities missing.")
      for (key in c("ID", "Harmonized_id")) {
        if (!is.character(frame[[key]]) || anyNA(frame[[key]]) || any(!nzchar(trimws(frame[[key]])))) stop("KLoSA personal identifiers must remain nonempty character values.")
      }
      if (anyNA(frame$ID) || anyDuplicated(frame$ID)) stop("KLoSA renderer supports ordinary unique-ID data only.")
      wave <- as.character(frame$Wave_id)
      if (anyNA(wave) || any(!grepl("^(Wave )?([1-9]|10)$", wave))) stop("Invalid KLoSA Wave_id.")
      wave <- paste("Wave", as.integer(sub("^Wave ", "", wave)))
      if (any(!wave %in% expected)) stop("KLoSA Wave_id outside language coverage.")
      if (anyDuplicated(data.frame(person=frame$Harmonized_id, wave=wave))) stop("Duplicate KLoSA person-wave identity.")
      frame$Wave <- wave; frame$year <- wave
      frame
    }
    data <- project(data); db_data <- project(db_data); analysis_data <- project(analysis_data)
  }
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
  if (database == "SHARE") {
    if (missing(cycle_order)) stop("SHARE requires explicit, evidence-based cycle_order.")
    supported_periods <- c(paste("Wave", 1:9), "Corona Survey 1", "Corona Survey 2")
    period_indexes <- match(as.character(cycle_order), supported_periods)
    if (!length(period_indexes) || anyNA(period_indexes) ||
        anyDuplicated(period_indexes) || is.unsorted(period_indexes)) stop("Invalid SHARE declared period order.")
    for (frame in list(data, db_data, analysis_data)) {
      keys <- c("ID", "Wave_id", "mergeid")
      if (!all(keys %in% names(frame))) stop("SHARE requires ID, Wave_id and mergeid.")
      if (!all(vapply(frame[keys], is.character, logical(1)))) stop("SHARE identities must remain character.")
      if (anyNA(frame[keys]) || any(vapply(frame[keys], function(x) any(!nzchar(x)), logical(1)))) stop("SHARE identities must be nonempty.")
      if (anyDuplicated(frame$ID) || anyDuplicated(frame[c("Wave_id", "mergeid")])) stop("Duplicate SHARE personal identity.")
      if (any(!frame$Wave_id %in% cycle_order)) stop("Observed SHARE Wave outside declared cycle_order.")
    }
    # Rendering copies only. Never rewrite raw, infer Wave from ID, or alter mergeid.
    db_data$year <- db_data$Wave_id
    analysis_data$year <- analysis_data$Wave_id
  }
  if (database == "HRS") {
    if (missing(cycle_order)) stop("HRS requires explicit, evidence-based cycle_order.")
    validate_hrs_period_order(cycle_order)
    for (frame in list(data, db_data, analysis_data)) {
      if (!all(c("HHID", "PN", "year") %in% names(frame))) stop("HRS requires HHID, PN and year.")
      if (any(!is.na(frame$year) & !as.character(frame$year) %in% cycle_order)) stop("Observed year outside declared cycle_order.")
    }
  }
  definition_copy_check(source = list(
    result_display_names = if (missing(analysis_codebook)) NULL else
      as.list(setNames(as.character(analysis_codebook$Label), analysis_codebook$Variable)),
    summary = render_summary_entry_paragraph(summary_entry, theme_color),
    criteria = if (compact_module) structure(list(), names = character()) else as.list(criteria[analysis_vars]),
    criteria_intro = paste(render_criteria_intro(criteria_intro), collapse = ""),
    definition_basis = definition_basis,
    insight = paste(summary_insight_items, collapse = "\n\n"),
    references = paste(reference_lines[!grepl("^## 参考资料说明$", reference_lines)], collapse = "\n"),
    questionnaire = if (missing(summary_selection)) "" else render_summary_selection_paragraph(summary_selection, theme_color)
  ), analysis_vars = analysis_vars)
  if (is.null(medicine_codebook)) extract_codebook <- raw_codebook
  identity_contract <- definition_analysis_identity_contract(database, analysis_unit, identity_keys)
  identity_frames <- if (identical(identity_contract$analysis_unit, "household_period")) list(data, db_data, analysis_data) else list(db_data, analysis_data)
  validate_person_period_outputs(identity_frames, database, identity_contract)
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
  if (!compact_module) {
    stopifnot(all(analysis_vars %in% names(criteria)))
    stopifnot(all(nzchar(criteria[analysis_vars])))
    validate_criteria_markup(criteria[analysis_vars], unique(c(raw_vars, analysis_vars,
      trimws(sub("[[:space:]]*\\(.*$", "", as.character(raw_codebook$Variable))))),
                             lapply(analysis_data[analysis_vars], unique))
  }
  formatted_card_sources <- format_definition_card_sources(
    analysis_codebook, raw_codebook, codebook,
    default_sources = if (database == "CHARLS") {
      intersect("respondent_id", setdiff(names(db_data), analysis_vars))
    } else if (database %in% c("NHANES", "NHANESIII")) {
      intersect(c("SEQN", "YEAR", "_survey_period", "_period"), names(db_data))
    } else character())

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
    object_overrides = summary_object_overrides,
    period_mode = if (identical(database, "HRS")) "hrs_original" else NULL
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

  # Source columns remain in downloads/workbooks, never in overview/detail charts.
  # summary_groups belongs to summary facts; it is not a second display-group input.
  if (is.null(component_groups)) stop("Provide component_groups with explicit module/category names")
  display_vars <- names(component_groups)
  if (is.null(display_vars) || anyDuplicated(display_vars) || !all(analysis_vars %in% display_vars)) {
    stop("component_groups must include every final result exactly once")
  }
  if (length(intersect(setdiff(raw_vars, analysis_vars), display_vars))) {
    stop("原始变量不得进入组分概览或详情；component_groups 只列计算成分和最终定义变量")
  }
  if (!all(display_vars %in% names(db_data)) || !all(display_vars %in% codebook$Variable)) {
    stop("展示成分必须在计算数据和字典中存在，不能按来源名称推测")
  }
  detail_data <- db_data[unique(c("year", display_vars))]
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
  date_detail_positions <- match(date_detail_vars, names(detail_data))
  date_detail_positions <- date_detail_positions[!is.na(date_detail_positions)]
  if (length(date_detail_vars) > 0L) {
    details[date_detail_positions] <- gsub(
      "Unsupported type",
      "日期变量（近似构造）",
      details[date_detail_positions],
      fixed = TRUE
    )
  }
  names(details) <- names(detail_data)
  analysis_source_rows <- match(codebook$Variable, names(formatted_card_sources))
  has_analysis_source <- !is.na(analysis_source_rows)
  codebook$original_vars[has_analysis_source] <- unname(
    formatted_card_sources[analysis_source_rows[has_analysis_source]]
  )
  codebook$detail <- unname(details[codebook$Variable])
  codebook$easylabel <- codebook$Label
  if (!is.null(component_card_labels)) {
    if (is.null(names(component_card_labels)) || anyDuplicated(names(component_card_labels)) ||
        !setequal(names(component_card_labels), analysis_vars) ||
        anyNA(component_card_labels) || any(!nzchar(trimws(component_card_labels)))) stop("invalid component card labels")
    codebook$easylabel[match(analysis_vars, codebook$Variable)] <- unname(component_card_labels[analysis_vars])
  }

  identity_columns <- intersect(
    c("ID", "id", "idauniq", "HHID", "PN", "HHIDPN", "RAHHIDPN", "Wave", "householdid", "communityid"),
    names(detail_data)
  )
  if (database == "SHARE") {
    identity_columns <- union(identity_columns, intersect(
      c("Wave_id", "mergeid", "hhid", "country", "intid", "intidwX", "Record_id",
        grep("^intid[ .(]", names(detail_data), value = TRUE)), names(detail_data)))
  }
  if (database %in% c("NHANES", "NHANESIII")) identity_columns <- union(identity_columns, intersect(c("SEQN", "YEAR", "_survey_period", "_period"), names(detail_data)))
  if (database == "KNHANES") identity_columns <- union(identity_columns, intersect("sample_source", names(detail_data)))
  if (database == "MHAS") identity_columns <- union(identity_columns, intersect(
    c("source_module", "Wave_id", "UNHHIDNP", "CUNICAH", "NP", "cunicah", "np", "unhhid", "ps3", "acthog",
      "ent2", "codent01", "codent03", "source_file", "source_row"), names(detail_data)))
  if (database == "KLOSA") identity_columns <- union(identity_columns, intersect(c("Harmonized_id", "Wave_id", "pid"), names(detail_data)))
  if (database == "CHNS") identity_columns <- union(identity_columns, intersect(
    c("IDind", "WAVE", "hhid", "COMMID", "Household_ID", "Community_ID",
      grep("^(IDind|WAVE|hhid|COMMID|Household_ID|Community_ID)[ .(]", names(detail_data), value = TRUE)), names(detail_data)))
  if (database == "NHIS") identity_columns <- union(identity_columns, intersect(c("Wave_id","Survey_year","Survey_period","Record_id","Baseline_year","Imputation_number"),names(detail_data)))
  z <- detail_data[, setdiff(names(detail_data), identity_columns), drop = FALSE]
  count_data <- definition_period_counts(z)
  wide_data <- pivot_wider(
    count_data,
    names_from = year,
    values_from = Count,
    values_fill = NA,
    names_sort = FALSE
  )
  display_cycles <- definition_display_periods(database, cycle_order, language, dataset_id)
  for (period in setdiff(display_cycles, names(wide_data))) wide_data[[period]] <- NA_integer_
  period_columns <- display_cycles
  wide_data <- wide_data[c(setdiff(names(wide_data), period_columns), period_columns)]
  wide_data <- wide_data[
    order(factor(wide_data$Variable, levels = names(db_data))),
  ]
  wide_data <- wide_data[match(display_vars, wide_data$Variable), , drop = FALSE]
  component_categories <- definition_component_categories(wide_data, analysis_vars, component_groups)
  wide_data <- component_categories$data

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

  definition_path <- paste0(database, "_", file_stem, "_definition.html")
  if (compact_module) {
    # Remove only this generated artifact if a previous full render left it behind.
    if (file.exists(definition_path)) unlink(definition_path)
  } else {
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
      cycle_order = display_cycles,
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
    names(definition_details) <- names(detail_data)
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
  }

  clean_html <- function(path) {
    text <- readLines(path, encoding = "UTF-8", warn = FALSE)
    text <- gsub("mapping", "varlink", text, fixed = TRUE)
    text <- gsub("&emsp;&emsp;", "", text, fixed = TRUE)
    text <- definition_wrap_source_cards(text)
    writeLines(text, path, useBytes = TRUE)
  }
  clean_html(paste0(database, "_", file_stem, "_detail.html"))
  detail_path <- paste0(database, "_", file_stem, "_detail.html")
  detail_text <- paste(readLines(detail_path, encoding = "UTF-8", warn = FALSE), collapse = "\n")
  detail_text <- definition_component_titles(detail_text, component_categories$groups)
  writeLines(detail_text, detail_path, useBytes = TRUE)
  if (compact_module) {
    detail_path <- paste0(database, "_", file_stem, "_detail.html")
    detail_text <- readLines(detail_path, encoding = "UTF-8", warn = FALSE)
    detail_text <- sub('<table class="heatmap-table">',
      '<table class="heatmap-table" data-defined-overview="true">', detail_text, fixed = TRUE)
    for (variable in analysis_vars) {
      escaped <- criteria_escape_code(variable)
      target <- paste0('<span class="var-name" id="var-', escaped, '">')
      detail_text <- sub(target, paste0('<span class="var-name" id="var-', escaped,
        '" data-defined-variable="', escaped, '">'), detail_text, fixed = TRUE)
    }
    writeLines(detail_text, detail_path, useBytes = TRUE)
  }
  if (!compact_module) clean_html(definition_path)
  if (!compact_module && nzchar(trimws(criteria_intro))) {
    definition_path <- paste0(database, "_", file_stem, "_definition.html")
    definition_text <- definition_html_with_intro(
      readLines(definition_path, encoding = "UTF-8", warn = FALSE), criteria_intro)
    writeLines(definition_text, definition_path, useBytes = TRUE)
  }

  extract_vars <- paste0(extract_codebook$Variable, "=", extract_codebook$newname)
  if (database == "NHIS") extract_vars <- paste0(extract_codebook$Variable," [",nhis_source_ids[extract_codebook$newname],"]=",extract_codebook$newname)
  extract_box <- c(
    '<div class="custom-textbox">',
    '<div class="textbox-content">',
    paste0(extract_vars, collapse = ",\n"),
    "</div>",
    paste0(
      '<button class="textbox-button" ',
      if (database == "NHIS") paste0('data-dataset-id="',dataset_id,'" ') else '',
      'onclick="goToExtractVariables(this)">Go to 提取变量</button>'
    ),
    "</div>"
  )
  if (!is.null(medicine_codebook)) {
    requests <- unique(medicine_codebook[c("input_name", "definition_path", "selected_values")])
    rows <- vapply(seq_len(nrow(requests)), function(i) {
      item <- requests[i, ]
      paste0('<tr data-drug-content="', criteria_escape_code(item$selected_values),
        '" data-drug-table-type="', item$definition_path, '"><td>药物分类</td><td>',
        criteria_escape_code(item$input_name), '</td><td>', criteria_escape_code(item$selected_values),
        '</td><td>', criteria_escape_code(item$definition_path),
        '</td><td><button class="drug-extract-btn" onclick="goToExtractMedicine(this)">Go to 提取药物</button></td></tr>')
    }, character(1))
    extract_box <- c(extract_box, '<table class="drug-extract-table"><thead><tr><th>说明</th><th>命名</th><th>输入内容</th><th>定义方式</th><th>提取</th></tr></thead><tbody>', rows, '</tbody></table>')
  }

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
  definition_html_lines <- if (compact_module) character() else readLines(
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
    definition_basis = definition_basis
  )
  note_lines <- compose_definition_note_lines(
    summary_section,
    summary_extra_lines,
    definition_html_lines,
    reference_lines,
    extract_box,
    publish_code,
    detail_html_lines,
    include_definition = !compact_module
  )
  writeLines(note_lines, note_name, useBytes = TRUE)
  definition_copy_check(note = note_name, analysis_vars = analysis_vars)
}

