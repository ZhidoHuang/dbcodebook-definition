library(jsonlite)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) == 0) stop("Run this test with Rscript.")
test_dir <- dirname(normalizePath(sub("^--file=", "", file_arg[[1]])))
repo_root <- dirname(test_dir)
eval(parse(
  file = file.path(repo_root, "scripts", "summary_fact_helpers.R"),
  encoding = "UTF-8"
))
eval(parse(
  file = file.path(repo_root, "scripts", "render_definition_bundle.R"),
  encoding = "UTF-8"
))

expect_identical <- function(name, actual, expected) {
  if (!identical(actual, expected)) {
    stop(name, " failed. expected: ", expected, "; actual: ", actual)
  }
  list(name = name, expected = expected, actual = actual, ok = TRUE)
}

stopifnot(identical(validate_hrs_period_order(c("1992", "2001-2003", "2002", "2002-2005", "2017", "2017 Spring", "2019 Spring", "2019 Fall")),
                    c("1992", "2001-2003", "2002", "2002-2005", "2017", "2017 Spring", "2019 Spring", "2019 Fall")))
for (bad_periods in list(character(), NA_character_, c("1992", "1992"), c("2004", "2002"),
                         "2003-2001", "1899", "2101", "2099-2101", "2017 Autumn", "2017 spring",
                         "2017.0", "1992-2022 extra", c("2019 Fall", "2019 Spring"))) {
  stopifnot(inherits(try(validate_hrs_period_order(bad_periods), silent = TRUE), "try-error"))
}

expect_error_contains <- function(name, expression, expected) {
  message <- tryCatch(
    {
      force(expression)
      ""
    },
    error = function(error) conditionMessage(error)
  )
  if (!grepl(expected, message, fixed = TRUE)) {
    stop(name, " failed. expected error containing: ", expected, "; actual: ", message)
  }
  list(name = name, expected = expected, actual = message, ok = TRUE)
}

expect_identical(
  "record-based topic may omit questionnaire selection",
  render_summary_selection_paragraph(NULL, "#005A9C"),
  ""
)
stopifnot(isTRUE(summary_validate_insight_inline_code("ISCED1997 与 ISCED2011 是两套教育分类标准。")))
expect_error_contains("real ISCED field still requires code span",
  summary_validate_insight_inline_code("isced2011_r 是原始变量。"), "isced2011_r")
expect_error_contains("uppercase numeric variable is not generally exempt",
  summary_validate_insight_inline_code("CF018 是原始变量。"), "CF018")

charls_periods <- c(2011L, 2013L, 2015L, 2018L, 2020L)
mixed_charls <- data.frame(
  period = charls_periods,
  nonmissing = c(90L, 80L, 90L, 80L, 80L),
  total = rep(100L, 5),
  rate = c(0.90, 0.80, 0.90, 0.80, 0.80)
)
all_high <- data.frame(
  period = c(2011L, 2013L),
  nonmissing = c(85L, 95L),
  total = c(100L, 100L),
  rate = c(0.85, 0.95)
)
multiple_low_groups <- data.frame(
  period = c(1L, 2L, 3L),
  nonmissing = c(90L, 80L, 60L),
  total = c(100L, 100L, 100L),
  rate = c(0.90, 0.80, 0.60)
)

object_override_fixture <- build_summary_facts(
  analysis_db = data.frame(
    year = c(2011L, 2013L),
    test_var = c(1, 2)
  ),
  analysis_codebook = data.frame(
    Variable = "test_var",
    original_vars = "raw_var",
    Label = "Test variable",
    stringsAsFactors = FALSE
  ),
  meanings = c(test_var = "测试变量"),
  groups = c(test_var = "Test"),
  meaning_reviewed = c(test_var = TRUE),
  period_col = "year",
  expected_periods = c(2011L, 2013L),
  object_overrides = c(test_var = "家庭指标（个人行）")
)

# SHARE uses Wave_id in the real bundle, not its local calendar-year alias.
share_summary_fixture <- function(period_col, values, expected = c("Wave 1", "Wave 2"), prefix = NULL) {
  sample <- data.frame(test_var = c(1, 2))
  sample[[period_col]] <- values
  build_summary_facts(sample,
    data.frame(Variable = "test_var", original_vars = "raw_var", Label = "Test variable"),
    meanings = c(test_var = "测试变量"), groups = c(test_var = "Test"),
    meaning_reviewed = c(test_var = TRUE), period_col = period_col,
    expected_periods = expected, period_prefix = prefix)
}
stopifnot(identical(
  share_summary_fixture("Wave_id", c("Wave 1", "Wave 2")),
  share_summary_fixture("Wave", c("Wave 1", "Wave 2"))))
expect_error_contains("SHARE Wave_id rejects calendar terminology",
  share_summary_fixture("Wave_id", c("Wave 1", "Wave 2"), prefix = ""), "周期术语")
expect_error_contains("SHARE Wave_id rejects unknown period",
  suppressWarnings(share_summary_fixture("Wave_id", c("Wave 1", "unknown"))), "无法识别")
expect_error_contains("SHARE Wave_id rejects extra wave",
  share_summary_fixture("Wave_id", c("Wave 1", "Wave 3")), "目标周期之外")

corona_summary <- share_summary_fixture("Wave_id", c("Wave 1", "Corona Survey 1"),
  expected=c("Wave 1", "Corona Survey 1", "Corona Survey 2"))
stopifnot(identical(corona_summary$period, "Wave 1、Corona Survey 1"))
expect_error_contains("SHARE rejects unknown Corona period",
  share_summary_fixture("Wave_id",c("Wave 1","Corona Survey 3")),"无法识别")
expect_error_contains("SHARE rejects undeclared Corona period",
  share_summary_fixture("Wave_id",c("Wave 1","Corona Survey 2"),expected=c("Wave 1","Corona Survey 1")),"目标周期之外")

note_order_fixture <- compose_definition_note_lines(
  summary_section = "SUMMARY",
  summary_extra_lines = character(),
  definition_html_lines = c("DEFINITION_START", "DEFINITION_END"),
  reference_lines = c("> 1、REFERENCE_ONE", "> 2、REFERENCE_TWO"),
  extract_box = "EXTRACT",
  publish_code = "CODE",
  detail_html_lines = c(
    "## 定义的组分概览",
    "OVERVIEW",
    "## 定义的组分详情",
    "DETAIL"
  )
)
empty_heading_warning <- FALSE
invisible(withCallingHandlers(
  compose_definition_note_lines("S", character(), "D", character(), "E",
                                c("x <- 1", "# ----------- 5 正式输出 -----------"), "DETAIL"),
  warning = function(w) {
    empty_heading_warning <<- grepl("空小节标题", conditionMessage(w), fixed = TRUE)
    invokeRestart("muffleWarning")
  }
))
stopifnot(empty_heading_warning)
normal_heading_warning <- FALSE
invisible(withCallingHandlers(
  compose_definition_note_lines("S", character(), "D", character(), "E",
                                c("# ----------- 5 正式输出 -----------", "write.xlsx(x, 'x.xlsx')"), "DETAIL"),
  warning = function(w) { normal_heading_warning <<- TRUE; invokeRestart("muffleWarning") }
))
stopifnot(!normal_heading_warning)
summary_section_fixture <- render_summary_note_section(
  entry = list(parts = list("目录说明。")),
  selection = list(
    raw_count = 1,
    concepts = "测试变量",
    final_count = 1
  ),
  theme_color = "#A33842"
)
summary_insight_fixture <- paste(
  render_summary_insight_card(
    c("第一段不缩进。", "第二段开始缩进。"),
    "#A33842"
  ),
  collapse = "\n"
)
summary_itemized_insight_fixture <- paste(
  render_summary_insight_card(
    c("1. 第一项。", "2. 第二项。"),
    "#A33842"
  ),
  collapse = "\n"
)
summary_multiline_selection_fixture <- render_summary_selection_paragraph(
  list(lines = list(
    list(parts = list(
      "本次从中选取 ", summary_count_part(85, " 个"), "原始变量："
    ), strong = TRUE),
    list(parts = list(
      summary_count_part(15, " 个位置"),
      " × ", summary_count_part(4, " 类记录"),
      " = ", summary_count_part(60, " 个变量"), "。"
    )),
    list(parts = list(
      "最终定义 ",
      summary_count_part(1, " 个变量", weight = 500, role = "definition"),
      "：", summary_concept_part("测试变量"), "。"
    ), strong = TRUE)
  )),
  "#A33842"
)
summary_period_tabs_fixture <- render_summary_selection_paragraph(
  list(
    display = "period-tabs",
    groups = list(
      list(
        period = "2011",
        label = "2011 年",
        lines = list(summary_period_note("①婚姻部分询问“当前婚姻状态”。"))
      ),
      list(period = "2013", label = "2013 年", lines = list("第二期。"))
    )
  ),
  "#A33842"
)
module_period <- "Wave_1_Wave_2_Wave_4_9_出生国与国籍的共同问题"
module_label <- "Wave 1、Wave 2、Wave 4–9：出生国与国籍的共同问题"
module_selection <- list(groups = list(list(period = module_period, label = module_label, lines = list("模块内容。"))))
module_html <- render_summary_selection_paragraph(module_selection, "#A33842")
stopifnot(grepl(paste0('data-raw-source-period="', module_period, '"'), module_html, fixed = TRUE),
          grepl(paste0('data-label="', module_label, '"'), module_html, fixed = TRUE),
          grepl(module_label, module_html, fixed = TRUE))
for (bad_period in c('Wave_1" onclick="bad', 'Wave_1<svg>', 'Wave 1', 'Wave_1\n模块', 'Wave_1\n', 'Wave_1=bad')) {
  bad_module <- module_selection
  bad_module$groups[[1]]$period <- bad_period
  expect_error_contains("unsafe module identifier rejected", render_summary_selection_paragraph(bad_module, "#A33842"), "安全标识")
}
escaped_module <- module_selection
escaped_module$groups[[1]]$label <- '模块 "quoted" <b> & 内容'
escaped_html <- render_summary_selection_paragraph(escaped_module, "#A33842")
stopifnot(grepl('&quot;quoted&quot; &lt;b&gt; &amp;', escaped_html, fixed = TRUE),
          !grepl('data-label="模块 "quoted"', escaped_html, fixed = TRUE))
summary_questionnaire_fixture <- render_summary_selection_paragraph(
  list(lines = list(
    summary_period_heading_line("门诊原始问卷"),
    summary_questionnaire_line(
      "ED001",
      "过去一个月是否看过门诊？",
      options = list(
        summary_questionnaire_option("1 是", "→ 跳至 `ED004`"),
        summary_questionnaire_option("2 否")
      ),
      after = "如果 ED001 = 2，跳过后续门诊题。"
    ),
    summary_definition_block("门诊定义处理", c("没有门诊时费用记为 0。"))
  )),
  "#A33842"
)
question_layout_fixture <- render_summary_selection_paragraph(
  list(groups = list(list(period = "wave1", label = "Wave 1", lines = list(
    summary_questionnaire_line(
      "Q001", "您当前是否在工作？",
      condition = "上题回答为 1 的受访者回答本题。",
      options = list(
        summary_questionnaire_option("A 是", "→ 跳至 `Q003`"),
        summary_questionnaire_option("B 否")
      ),
      after = "本题回答后，继续 Q002。"
    )
  )))),
  "#A33842"
)
mapping_note <- "各个时期的变量名：2004 年 `JD111`；2006 年 `KD111`。"
mapping_note_html <- render_summary_selection_paragraph(
  list(lines = list(summary_questionnaire_line("D111", "过去一周是否感到抑郁？", notes = mapping_note))), "#A33842")
stopifnot(grepl('<code>JD111</code>', mapping_note_html, fixed = TRUE),
          grepl('<code>KD111</code>', mapping_note_html, fixed = TRUE),
          !grepl('<code>D111</code>', mapping_note_html, fixed = TRUE),
          grepl('data-summary-question-detail-role="instruction"', mapping_note_html, fixed = TRUE),
          grepl('font-size:0.72em;', mapping_note_html, fixed = TRUE))

definition_end_position <- match("DEFINITION_END", note_order_fixture)
reference_one_position <- match("> 1、REFERENCE_ONE", note_order_fixture)
reference_two_position <- match("> 2、REFERENCE_TWO", note_order_fixture)
materials_position <- match("## 材料", note_order_fixture)
source_display_codebook <- data.frame(
  Variable = "test_var",
  original_vars = "raw1 (file), raw2 (file), raw3 (file)",
  processed_vars = "raw1, raw2, raw3",
  stringsAsFactors = FALSE
)
source_display_raw_codebook <- data.frame(
  Variable = c("raw1 (file)", "raw2 (file)", "raw3 (file)", "raw4 (file)"),
  newname = c("raw1", "raw2", "raw3", "raw4"),
  stringsAsFactors = FALSE
)

# Evaluate only the renderer's actual source-formatting call, without generation.
renderer_source_call <- Filter(function(x) is.call(x) &&
  identical(x[[1]], as.name("<-")) &&
  identical(x[[2]], as.name("formatted_card_sources")),
  as.list(body(render_definition_bundle)))[[1]]
renderer_source_fixture <- function(database, analysis_codebook, raw_codebook,
                                    codebook, db_data) {
  analysis_vars <- analysis_codebook$Variable
  eval(renderer_source_call, envir = environment())
}
charls_key_result <- data.frame(Variable="result", processed_vars="raw1, respondent_id")
charls_key_source <- data.frame(Variable="respondent_id", processed_vars="respondent_id")
charls_key_data <- data.frame(respondent_id="001")
checks <- list(
  expect_identical(
    "CHARLS renderer recognizes only its published respondent default identity",
    renderer_source_fixture("CHARLS",charls_key_result,source_display_raw_codebook,
                            charls_key_source,charls_key_data),
    c(result="raw1 (file)=raw1, respondent_id=respondent_id")
  ),
  expect_error_contains(
    "CHARLS renderer still rejects unknown self-referencing helpers",
    renderer_source_fixture("CHARLS",data.frame(Variable="result",processed_vars="helper"),
      source_display_raw_codebook,data.frame(Variable="helper",processed_vars="helper"),
      data.frame(helper="001")), "result -> helper -> helper"
  ),
  expect_error_contains(
    "CHARLS result named respondent_id is not a default identity terminal",
    renderer_source_fixture("CHARLS",data.frame(Variable="respondent_id",processed_vars="respondent_id"),
      source_display_raw_codebook,charls_key_source,charls_key_data),
      "respondent_id -> respondent_id"
  ),
  expect_error_contains(
    "CHARLS renderer still rejects genuine business dependency cycles",
    renderer_source_fixture("CHARLS",data.frame(Variable="result",processed_vars="middle"),
      source_display_raw_codebook,data.frame(Variable="middle",processed_vars="result"),
      charls_key_data), "result -> middle -> result"
  ),
  expect_error_contains(
    "CHARLS default identity exception is not granted to ELSA",
    renderer_source_fixture("ELSA",charls_key_result,source_display_raw_codebook,
      charls_key_source,charls_key_data), "result -> respondent_id -> respondent_id"
  ),
  expect_error_contains(
    "HRS requires an explicit cycle order",
    render_definition_bundle(database = "HRS"),
    "HRS requires explicit, evidence-based cycle_order."
  ),
  expect_error_contains(
    "HRS rejects invalid year order",
    render_definition_bundle(
      data = data.frame(), db_data = data.frame(), analysis_data = data.frame(),
      database = "HRS", cycle_order = c("1992", "not-a-year")
    ),
    "Invalid HRS year order."
  ),
  expect_error_contains(
    "HRS requires HHID, PN and year identities",
    render_definition_bundle(
      data = data.frame(x = 1), db_data = data.frame(x = 1),
      analysis_data = data.frame(x = 1), database = "HRS",
      cycle_order = c("1992", "1993")
    ),
    "HRS requires HHID, PN and year."
  ),
  expect_identical(
    "definition cards do not accept a separate source subset",
    "definition_card_sources" %in% names(formals(render_definition_bundle)),
    FALSE
  ),
  expect_identical(
    "definition cards format every formal source as a website mapping pair",
    format_definition_card_sources(
      source_display_codebook,
      source_display_raw_codebook
    ),
    c(test_var = "raw1 (file)=raw1, raw2 (file)=raw2, raw3 (file)=raw3")
  ),
  expect_error_contains(
    "definition cards require every formal alias in raw codebook",
    format_definition_card_sources(
      transform(source_display_codebook, processed_vars = "raw1, raw5"),
      source_display_raw_codebook
    ),
    "raw5"
  ),
  expect_identical(
    "definition cards resolve intermediate sources without changing formal mapping",
    format_definition_card_sources(
      data.frame(Variable = "result", processed_vars = "raw1, intermediate"),
      source_display_raw_codebook,
      data.frame(Variable = "intermediate", processed_vars = "raw2, raw3")
    ),
    c(result = "raw1 (file)=raw1, raw2 (file)=raw2, raw3 (file)=raw3")
  ),
  expect_identical(
    "declared default keys remain terminal formal dependencies",
    format_definition_card_sources(
      data.frame(Variable="result", processed_vars="raw1, YEAR"),
      source_display_raw_codebook,
      data.frame(Variable="YEAR", processed_vars="YEAR"),
      default_sources="YEAR"
    ),
    c(result="raw1 (file)=raw1, YEAR=YEAR")
  ),
  expect_error_contains(
    "undeclared default-looking names are not inferred",
    format_definition_card_sources(
      data.frame(Variable="result", processed_vars="raw1, YEAR"),
      source_display_raw_codebook
    ),
    "YEAR"
  ),
  expect_error_contains(
    "declaring a default does not permit unknown aliases",
    format_definition_card_sources(
      data.frame(Variable="result", processed_vars="raw1, raw5, YEAR"),
      source_display_raw_codebook, default_sources="YEAR"
    ),
    "raw5"
  ),
  expect_error_contains(
    "cyclic source relationships fail with their path",
    format_definition_card_sources(
      data.frame(Variable = c("result", "intermediate"), processed_vars = c("intermediate", "result")),
      source_display_raw_codebook
    ),
    "result -> intermediate -> result"
  ),
  expect_identical(
    "linear histogram includes its upper endpoint label",
    grepl(
      "hist-endpoint-label'[^>]*>16</div>",
      append_linear_histogram_endpoint(paste0(
        "<div data-hist-mode='linear'><div class='hist-bars-wrapper'>",
        "<div class='hist-bar' title='[15.0, 16.0): 35个'></div></div>",
        "<div class='hist-labels-wrapper'>",
        "<div class='hist-label' style='width:30px;'>15</div></div></div>"
      )),
      perl = TRUE
    ),
    TRUE
  ),
  expect_identical(
    "CHARLS five-year full coverage",
    summary_period_text(charls_periods, "", charls_periods),
    "全周期"
  ),
  expect_identical(
    "CHARLS mixed high and low coverage",
    summary_object_text(mixed_charls, prefix = ""),
    "2011、2015 全样本；<br>2013、2018、2020 约 80% 样本"
  ),
  expect_identical(
    "ELSA partial waves",
    summary_period_text(c(2L, 4L), "Wave", 1:5),
    "Wave 2、Wave 4"
  ),
  expect_identical(
    "CHARLS observed subset is not full cycle",
    summary_period_text(c(2011L, 2013L, 2015L, 2018L), "", charls_periods),
    "2011、2013、2015、2018"
  ),
  expect_identical(
    "all periods at least 85 percent",
    summary_object_text(all_high, prefix = ""),
    "全样本"
  ),
  expect_identical(
    "multiple low coverage groups",
    summary_object_text(multiple_low_groups, prefix = "Wave"),
    "Wave 1 全样本；<br>Wave 2 约 80% 样本；<br>Wave 3 约 60% 样本"
  ),
  expect_identical(
    "summary object override",
    object_override_fixture$object,
    "家庭指标（个人行）"
  ),
  expect_error_contains(
    "summary object override rejects unknown variables",
    build_summary_facts(
      analysis_db = data.frame(year = 2011L, test_var = 1),
      analysis_codebook = data.frame(
        Variable = "test_var",
        original_vars = "raw_var",
        Label = "Test variable",
        stringsAsFactors = FALSE
      ),
      meanings = c(test_var = "测试变量"),
      groups = c(test_var = "Test"),
      meaning_reviewed = c(test_var = TRUE),
      period_col = "year",
      expected_periods = 2011L,
      object_overrides = c(other_var = "家庭指标（个人行）")
    ),
    "摘要对象覆盖包含未知定义变量"
  ),
  expect_identical(
    "insight inline code rendering",
    summary_render_inline_code("变量 `da005` 进入定义。"),
    "变量 <code>da005</code> 进入定义。"
  ),
  expect_identical(
    "insight first paragraph is not indented",
    grepl('font-weight:400;">第一段不缩进。</span>', summary_insight_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "insight paragraphs do not add first-line indentation",
    grepl('text-indent:2em', summary_insight_fixture, fixed = TRUE),
    FALSE
  ),
  expect_identical(
    "insight paragraphs do not use br separators",
    grepl("<br>", summary_insight_fixture, fixed = TRUE),
    FALSE
  ),
  expect_identical(
    "insight number is separate from wrapping text",
    grepl('text-align:right;font-weight:400;">2.</span><span class="summary-insight-text"', summary_itemized_insight_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "insight body uses 14px in both variants",
    all(vapply(c("standard", "compact"), function(variant) {
      output <- paste(render_summary_insight_card(c("1. 第一项。", "2. 第二项。"), "#A33842", variant), collapse = "\n")
      grepl('data-summary-insight-body="true" style="font-size:14px;', output, fixed = TRUE) &&
        !grepl('data-summary-insight-paragraph="true" style="[^\"]*font-size', output)
    }, logical(1))),
    TRUE
  ),
  expect_identical(
    "criteria value rendering",
    criteria_value("1 Yes"),
    "<u>[1 Yes]</u>"
  ),
  expect_identical(
    "criteria item renders variable inline code",
    criteria_item("变量 `da005` 进入定义。"),
    paste0(
      "<div data-criteria-item='true' style='padding-left:1.8em;text-align:left;",
      "line-height:1.75;margin:3px 0;font-size:0.92em;'>",
      "变量 <code>da005</code> 进入定义。</div>"
    )
  ),
  expect_identical(
    "criteria context renders variable inline code",
    grepl("<code>work_status</code>", criteria_context("以 `work_status` 为基础。"), fixed = TRUE),
    TRUE
  ),
  expect_error_contains(
    "criteria inline code requires paired backticks",
    criteria_item("变量 `da005 进入定义。"),
    "反引号必须成对出现"
  ),
  expect_error_contains(
    "criteria source rejects manual code tags",
    criteria_item("变量 <code>da005</code> 进入定义。"),
    "不得手写 <code>"
  ),
  expect_identical(
    "criteria variable inline code remains valid",
    validate_criteria_markup(
      c(test_var = "回答来自 <code>da005</code>。")
    ),
    TRUE
  ),
  expect_identical(
    "official name retained rather than download alias",
    criteria_render_inline_code("题义（`OFFICIAL_A`）"),
    "题义（<code>OFFICIAL_A</code>）"
  ),
  expect_error_contains(
    "official source name with file suffix is checked as a variable",
    validate_criteria_markup(criteria_item(criteria_value("OFFICIAL_A")),
      unique(c("download_alias", "result", trimws(sub("[[:space:]]*\\(.*$", "", "OFFICIAL_A (File)"))))),
    "变量名标成了数据取值"
  ),
  expect_error_contains(
    "criteria value inline code rejected",
    validate_criteria_markup(
      c(test_var = "回答为 <code>[1 Yes]</code>。")
    ),
    "不得使用 inline code"
  ),
  expect_error_contains(
    "known source variable cannot use value markup",
    validate_criteria_markup(criteria_item(criteria_value("da023")), c("da023", "fall_status")),
    "变量名标成了数据取值"
  ),
  expect_error_contains(
    "variable in a condition cannot use value markup",
    validate_criteria_markup(criteria_item(criteria_value("fall_status = 0")), "fall_status"),
    "变量名标成了数据取值"
  ),
  expect_identical(
    "code variables and numeric or category values retain distinct markup",
    validate_criteria_markup(criteria_item(paste0(
      "`fall_status` = ", criteria_value("0"), "；`da023`回答", criteria_value("2 No")
    )), c("fall_status", "da023")),
    TRUE
  ),
  expect_identical(
    "a real category may share a source name",
    validate_criteria_markup(c(reason = criteria_item(criteria_value("hysterectomy"))),
      "hysterectomy", list(reason = c("hysterectomy", NA))),
    TRUE
  ),
  expect_error_contains(
    "a category in another result does not exempt a variable name",
    validate_criteria_markup(c(other = criteria_item(criteria_value("hysterectomy"))),
      "hysterectomy", list(reason = "hysterectomy", other = c(0, 1))),
    "变量名标成了数据取值"
  ),
  expect_error_contains(
    "a valid category does not exempt a variable expression",
    validate_criteria_markup(c(reason = criteria_item(criteria_value("hysterectomy = 1"))),
      "hysterectomy", list(reason = "hysterectomy")),
    "变量名标成了数据取值"
  ),
  expect_identical(
    "summary no longer renders the five-column table",
    any(grepl("| 定义变量 | 含义 | 组成 | 覆盖周期 | 对象 |",
              summary_section_fixture, fixed = TRUE)),
    FALSE
  ),
  expect_identical(
    "summary second information area supports semantic line breaks",
    length(gregexpr(
      'data-summary-selection-line="true"',
      summary_multiline_selection_fixture,
      fixed = TRUE
    )[[1]]),
    3L
  ),
  expect_identical(
    "period tab labels are not markdown headings",
    grepl('<h3 class="raw-source-period-label">', summary_period_tabs_fixture, fixed = TRUE),
    FALSE
  ),
  expect_identical(
    "period tab labels keep their semantic hook",
    grepl('<div class="raw-source-period-label">2011 年</div>', summary_period_tabs_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "period tab content uses the shared compact text size",
    grepl('data-raw-source-period="2011" data-label="2011 年" style="font-size:0.92em;"', summary_period_tabs_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "period note colors only the text inside Chinese quotes",
    grepl(
      paste0(
        '①婚姻部分询问“<span class="summary-period-question" ',
        'data-summary-period-question="true" style="color:#A33842;font-weight:400;">',
        '当前婚姻状态</span>”。'
      ),
      summary_period_tabs_fixture,
      fixed = TRUE
    ),
    TRUE
  ),
  expect_identical(
    "summary second information area keeps one left edge",
    grepl("margin-left", summary_multiline_selection_fixture, fixed = TRUE),
    FALSE
  ),
  expect_identical(
    "summary second information area marks two lead lines",
    length(gregexpr(
      'data-summary-selection-lead="true"',
      summary_multiline_selection_fixture,
      fixed = TRUE
    )[[1]]),
    2L
  ),
  expect_identical(
    "summary questionnaire wording uses a dedicated neutral span",
    summary_render_parts(
      list("问卷问：", summary_question_part("过去一年是否收到支持？")),
      "#A33842"
    ),
    paste0(
      "问卷问：“<span class=\"summary-question\" data-summary-question=\"true\" ",
      "style=\"font-weight:400;\">过去一年是否收到支持？</span>”"
    )
  ),
  expect_identical(
    "structured questionnaire line is compact and unquoted",
    grepl(
      paste0(
        'data-summary-questionnaire-line="true" style="display:block;line-height:1.7;',
        'text-indent:0;margin-bottom:0.75em;".*data-summary-question-id="true".*>ED001</strong> ',
        '<span class="summary-question" data-summary-question="true".*>',
        '过去一个月是否看过门诊？</span>',
        '<span class="summary-question-detail" data-summary-question-detail="true" ',
        'data-summary-question-detail-role="mixed".*',
        'data-summary-question-option="true" style="font-size:0.8em;color:#888888;">1 是</span> ',
        '<span data-summary-question-instruction="true" style="font-size:0.72em;">',
        '→ 跳至 <code>ED004</code></span></span>.*',
        'data-summary-question-detail-role="option".*color:#888888;.*>2 否</span>.*',
        'data-summary-question-detail-role="instruction" data-summary-question-position="after" style="display:block;',
        'padding-left:1.4em;text-indent:0;font-size:0.72em;">',
        '如果 ED001 = 2，跳过后续门诊题。</span>'
      ),
      summary_questionnaire_fixture,
      perl = TRUE
    ),
    TRUE
  ),
  expect_identical(
    "legacy question details remain supported with an entry condition",
    {
      legacy <- render_summary_selection_paragraph(
        list(lines = list(summary_questionnaire_line(
          "FA001", "完整原始题干",
          c("1 是 → 跳至 FB001（询问开始工作的年龄，不参与本主题定义）", "2 否"),
          before = "原问卷规定的进入条件"
        ))),
        "#A33842"
      )
      grepl('position="before" style="[^"]*font-size:0.72em;[^"]*">[^<]*进入条件.*>FA001</strong>.*完整原始题干.*font-size:0.8em;color:#888888;.*1 是</span>.*font-size:0.72em;.*跳至 FB001（询问开始工作的年龄，不参与本主题定义）.*2 否',
            legacy, perl = TRUE)
    },
    TRUE
  ),
  expect_error_contains(
    "structured options cannot be an untyped program string",
    summary_questionnaire_line("Q001", "问题", options = list("条件 → Q002")),
    "summary_questionnaire_option"
  ),
  expect_error_contains(
    "option cannot hide an unsplit jump in its label",
    summary_questionnaire_option("A Yes -> QB"),
    "跳转须单独放入 jump"
  ),
  expect_identical(
    "question condition follows the stem while options and exit follow it",
    grepl('>Q001</strong>.*您当前是否在工作？</span><span class="summary-question-condition".*font-size:0.72em;.*（上题回答为 1 的受访者回答本题。）</span>.*position="options".*font-size:0.8em;color:#888888;.*A 是.*font-size:0.72em;.*Q003.*position="after"',
          question_layout_fixture, perl = TRUE),
    TRUE
  ),
  expect_identical(
    "option and jump use independent absolute relative sizes",
    grepl(
      'data-summary-question-position="options"[^>]*font-size:.*data-summary-question-option|data-summary-question-option="true"[^>]*>.*data-summary-question-instruction="true" style="font-size:0.9em;"',
      question_layout_fixture,
      perl = TRUE
    ),
    FALSE
  ),
  expect_identical(
    "question conditions inherit the default text color",
    grepl(
      'summary-question-condition[^>]*color:|data-summary-question-position="before"[^>]*color:',
      paste(question_layout_fixture, legacy),
      perl = TRUE
    ),
    FALSE
  ),
  expect_error_contains(
    "question condition is one readable statement",
    summary_questionnaire_line("Q001", "问题", condition = c("条件一", "条件二")),
    "condition 只能包含一条"
  ),
  expect_identical(
    "question instructions after the stem inherit the default text color",
    grepl(
      'data-summary-question-detail-role="instruction" data-summary-question-position="after"[^>]*color:',
      summary_questionnaire_fixture,
      perl = TRUE
    ),
    FALSE
  ),
  expect_identical(
    "first period heading is colored and stays flush left without top spacing",
    grepl(
      'style="display:block;text-indent:0;margin:0 0 0.45em;">.*data-summary-selection-lead="true" style="font-weight:700;color:#A33842;".*门诊原始问卷',
      summary_questionnaire_fixture,
      perl = TRUE
    ),
    TRUE
  ),
  expect_identical(
    "definition handling uses the neutral background block",
    grepl(
      'data-summary-definition-block="true".*background:#F4F3F0.*门诊定义处理.*没有门诊时费用记为 0。',
      summary_questionnaire_fixture,
      perl = TRUE
    ),
    TRUE
  ),
  expect_identical(
    "criteria context uses the common neutral background",
    grepl(
      "data-criteria-context='true'.*background:#F4F3F0",
      criteria_context("背景"),
      perl = TRUE
    ),
    TRUE
  ),
  expect_error_contains(
    "insight literal code tag rejected",
    summary_validate_insight_inline_code("变量 <code>da005</code> 进入定义。"),
    "不要手写 <code> 标签"
  ),
  expect_error_contains(
    "insight unmarked variable rejected",
    summary_validate_insight_inline_code("变量 da005 进入定义。"),
    "变量名必须使用成对反引号：da005"
  ),
  expect_identical(
    "references follow the complete definition table",
    reference_one_position > definition_end_position,
    TRUE
  ),
  expect_identical(
    "references precede materials",
    reference_two_position < materials_position,
    TRUE
  ),
  expect_identical(
    "references have one blank line above",
    note_order_fixture[reference_one_position - 1L],
    ""
  ),
  expect_identical(
    "references remain contiguous",
    reference_two_position,
    reference_one_position + 1L
  ),
  expect_identical(
    "note composer does not inject an extra detail heading",
    sum(note_order_fixture == "## 定义的组分详情"),
    1L
  ),
  expect_identical(
    "note composer preserves the detail fragment overview heading",
    sum(note_order_fixture == "## 定义的组分概览"),
    1L
  )
)

for (periods in list(2011L, c(2011L, 2013L))) {
  for (variables in list("value", c("value", "other"))) {
    fixture <- data.frame(year = rep(periods, each = 3L),
                          value = rep(c(1, NA, 0), length(periods)),
                          other = NA_real_)[c("year", variables)]
    counts <- definition_period_counts(fixture)
    stopifnot(nrow(counts) == length(periods) * length(variables))
    stopifnot(identical(sort(unique(counts$year)), periods))
    stopifnot(all(counts$Count[counts$Variable == "value"] == 2L))
    stopifnot(all(counts$Count[counts$Variable == "other"] == 0L))
  }
}
cat("single/multiple period and variable count fixtures PASS\n")

# Retired navigation inputs must not affect the generated note section.
entry <- list(paragraphs = list(
  list(parts = list("本主题定义测试结果。")),
  list(type = "code_tree", text = "测试结果\n└─ 测试成分", label = "结果关系")))
questionnaire <- list(class = "raw-source-structure", lines = list("测试问卷题干。"))
legacy_sources <- list(NULL, "Core > ADL", c("Core > ADL", "Core > IADL"),
  list(path = "Core > ADL", variable_count = 88, language = "en"),
  list(lines = list("本主题在数据中对应 88 个原始变量，可从目录进入检索。")))
for (selection in list(NULL, questionnaire)) {
  expected <- render_summary_note_section(entry, selection, "#005A9C",
    insight_items = "1. 测试结果说明。", definition_basis = "测试定义依据。")
  for (source in legacy_sources) {
    actual <- render_summary_note_section(entry, selection, "#005A9C",
      insight_items = "1. 测试结果说明。", definition_basis = "测试定义依据。",
      summary_source = source)
    stopifnot(identical(actual, expected),
      !any(grepl("raw-source-link|source-directory-tree|进入检索|88 个原始变量", actual)),
      any(grepl('data-summary-tree="true"', actual, fixed = TRUE)),
      any(grepl("测试成分", actual, fixed = TRUE)),
      "## 定义依据" %in% actual,
      any(grepl('data-summary-insight-card="true"', actual, fixed = TRUE)),
      identical("## 问卷" %in% actual, !is.null(selection)))
  }
}
# Older summary entry APIs also keep content without injecting navigation.
for (type in c("directory", "search")) {
  actual <- render_summary_entry_paragraph(list(type = type, paths = "Core > ADL",
    keyword = "ADL", count = 88, description = "测试定义内容。"), "#005A9C")
  stopifnot(identical(actual, "测试定义内容。"))
}
cat("retired source navigation omitted; questionnaire, relationship tree and notes retained PASS\n")

for (variant in c("standard", "compact")) {
  expected_items <- c("1. 第一项。\n这是同一条的续行。", "2. 第二项。", "3. 第三项。")
  expected_html <- render_summary_insight_card(expected_items, "#A33842", variant)
  for (separator in c("\n", "\r\n", "\n\n")) {
    compact_items <- paste(expected_items, collapse = separator)
    actual_html <- render_summary_insight_card(compact_items, "#A33842", variant)
    stopifnot(identical(actual_html, expected_html))
  }
}

report <- list(ok = TRUE, checks = checks, questionnaire_html = question_layout_fixture)
nhis <- data.frame(ID=c("1968FY:adult:1","1968CY:adult:1"),Wave_id=c("1968FY","1968CY"),Survey_year="1968",value=c(10,NA_real_))
validate_nhis_render_inputs(list(nhis),c("1968FY","1968CY"),"nhis_pre1997")
expect_error_contains("NHIS wrong data set",validate_nhis_render_inputs(list(nhis),c("1968FY","1968CY"),"nhis_2019_plus"),"Invalid NHIS")
expect_error_contains("NHIS default year mismatch",validate_nhis_render_inputs(list(transform(nhis,Survey_year="1969")),c("1968FY","1968CY"),"nhis_pre1997"),"Invalid NHIS")
nhis$Survey_period <- nhis$Wave_id
nhis_facts <- build_summary_facts(nhis,data.frame(Variable="value",original_vars="source",Label="Value"),
  c(value="值"),c(value="人口学"),c(value=TRUE),period_col="Survey_period",expected_periods=c("1968FY","1968CY"))
stopifnot(identical(nhis_facts$period,"1968FY"),identical(nhis_facts$coverage_period_count,1L))
check_public_reads <- file.path(repo_root,"scripts","check_public_raw_reads.R")
eval(parse(file=check_public_reads,encoding="UTF-8"))
check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(ID="character",Wave_id="character",Survey_year="character"))',
  'name_z <- read.csv("raw_codebook.csv")'),"NHIS")
expect_error_contains("NHIS raw keys must be character",check_public_raw_reads(c('dt <- read.csv("raw_data.csv")','name_z <- read.csv("raw_codebook.csv")'),"NHIS"),"NHIS must preserve")
# HRS Tracker default identity reader: package and record must agree.
local({
  hrs_reader_fixture <- tempfile("hrs_reader_")
  dir.create(hrs_reader_fixture)
  on.exit(unlink(hrs_reader_fixture, recursive = TRUE))
  tracker <- "TRACKER_FILE_HRS_2022_EARLY_RELEASE_TRACKER_FILE_VERSION_2_RESPONDENT"
  defaults <- c("OVHHID", "OVPN", "OVRESULT", "OVYEAR")
  source_identity <- paste0("APROXY (", tracker, ")")
  record_path <- file.path(hrs_reader_fixture, "record.json")
  write_fixture <- function(file = tracker, header = c("HHID", "PN", defaults, "proxy92"),
                            record_db = "HRS", record_file = tracker,
                            record_defaults = defaults, business = TRUE, record_business = TRUE) {
    dictionary <- data.frame(Variable = if (business) paste0("APROXY (", file, ")") else paste0("OVHHID (", file, ")"))
    write.csv(dictionary, file.path(hrs_reader_fixture, "raw_codebook.csv"), row.names = FALSE)
    raw <- as.data.frame(setNames(rep(list("001"), length(header)), header), check.names = FALSE)
    write.csv(raw, file.path(hrs_reader_fixture, "raw_data.csv"), row.names = FALSE)
    groups <- list(list(source_identities = as.list(paste0(record_defaults, " (", record_file, ")")),
                        raw_variables = as.list(record_defaults)))
    if (record_business) groups <- c(groups, list(list(source_identities = list(source_identity), raw_variables = list("proxy92"))))
    write_json(list(database = record_db, source_groups = groups), record_path, auto_unbox = TRUE)
  }
  reader <- function(extra = c(OVHHID = "character", OVPN = "character"), database = "HRS", record = record_path) {
    classes <- c(HHID = "character", PN = "character", extra)
    code <- paste0('dt <- read.csv("raw_data.csv", colClasses=c(',
      paste(sprintf('%s="%s"', names(classes), classes), collapse = ","), '))')
    check_public_raw_reads(c(code, 'name_z <- read.csv("raw_codebook.csv")'), database,
      source_dir = hrs_reader_fixture, source_record_path = record)
  }
  reject <- function(label, expression) expect_error_contains(label, expression, "identity columns")
  write_fixture()
  reader(); reader(c(OVHHID = "character")); reader(c(OVPN = "character"))
  reader(character(), record = "") # HRS without OV keys keeps its existing optional contract.
  raw <- read.csv(file.path(hrs_reader_fixture, "raw_data.csv"),
    colClasses = c(HHID = "character", PN = "character", OVHHID = "character", OVPN = "character"))
  stopifnot(identical(raw$OVHHID, "001"), identical(raw$OVPN, "001"))
  reject("HRS no source record", reader(record = ""))
  for (field in c("OVRESULT", "OVYEAR", "proxy92"))
    reject(paste("HRS nonidentity", field), reader(setNames("character", field)))
  reject("HRS wrong character type", reader(c(OVHHID = "numeric")))
  reject("other database OV keys", reader(database = "CHARLS"))
  write_fixture(file = "OTHER_FILE"); reject("non Tracker file", reader())
  write_fixture(business = FALSE); reject("defaults only dictionary", reader())
  write_fixture(record_business = FALSE); reject("record missing selected business source", reader())
  write_fixture(record_db = "ELSA"); reject("wrong record database", reader())
  write_fixture(record_file = "OTHER_FILE"); reject("fake default identity", reader())
  write_fixture(record_defaults = defaults[-4]); reject("incomplete declared defaults", reader())
  for (field in defaults) {
    write_fixture(header = c("HHID", "PN", setdiff(defaults, field), "proxy92"))
    reject(paste("missing actual default", field), reader())
  }
  write_fixture()
  unlink(file.path(hrs_reader_fixture, "raw_data.csv")); reject("no raw header evidence", reader())
  write_fixture()
  unlink(file.path(hrs_reader_fixture, "raw_codebook.csv")); reject("no dictionary evidence", reader())
  cat("HRS Tracker default identity reader fixtures PASS\n")
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 1 && nzchar(args[1])) {
  write_json(report, args[1], pretty = TRUE, auto_unbox = TRUE)
}
cat("summary helper fixtures PASS\n")

local({
p <- c("2001-2003", "2002-2005", "2006-2008", "2008-2009", "2019", "2022")
book <- data.frame(Variable="x", original_vars="raw_x", Label="结果")
db <- data.frame(year=p, x=c(1,NA,1,NA,0,1))
make_facts <- function(periods=p, mode="hrs_original", frame=db) build_summary_facts(
  frame, book, c(x="结果"), c(x="定义"), c(x=TRUE), period_col="year",
  expected_periods=periods, period_mode=mode)
original <- db
facts <- make_facts()
stopifnot(identical(db,original), !grepl("NA", facts$period, fixed=TRUE),
  grepl("2001-2003",facts$period,fixed=TRUE), grepl("2006-2008",facts$period,fixed=TRUE))
seasons <- c("2017 Spring", "2017 Fall", "2019", "2019 Winter")
season_db <- data.frame(year=seasons, x=c(1,0,1,NA))
season_facts <- make_facts(seasons,frame=season_db)
stopifnot(grepl("2017 Spring",season_facts$period,fixed=TRUE), identical(season_db$year,seasons))
stopifnot(identical(summary_period_text("2019","",p),"2019"))
stopifnot(identical(summary_period_text(p,"",p),"全周期"))
reject <- function(expr) stopifnot(inherits(tryCatch({force(expr);NULL},error=identity),"error"))
for (bad in c("2003-2001","2019 Autumn","1899","2101","2099-2101","2019.0"))
  reject(make_facts(c(p,bad)))
reject(make_facts(c(p,p[1])))
reject(make_facts(p[-1]))
reject(make_facts(mode="anything"))
reject(make_facts(mode=NULL))
cat("HRS_ORIGINAL_PERIOD_SUMMARY_TARGETS_PASS\n")
})

local({
original <- c('<style>.var-name{flex-shrink:0}</style>', '<table class="hm-table"><tr><td class="card-cell"><div class="var-name-line"><span class="var-name">Very_long_defined_variable</span><span class="varlink-block"><span class="varlink-info">FULL_ORIGINAL (FULL_FILE)=alias</span></span></div></td></tr></table>')
wrapped <- definition_wrap_source_cards(original)
stopifnot(identical(head(wrapped,length(original)),original), length(wrapped)>length(original),
  identical(definition_wrap_source_cards(wrapped),wrapped),
  identical(definition_wrap_source_cards('plain unchanged HTML'),'plain unchanged HTML'))
cat("SOURCE_CARD_LAYOUT_WRAP_FIXTURE_PASS\n")
})
