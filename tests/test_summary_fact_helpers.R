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

checks <- list(
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
    grepl('text-indent:0;">第一段不缩进。', summary_insight_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "insight later paragraphs are indented",
    grepl('text-indent:2em;">第二段开始缩进。', summary_insight_fixture, fixed = TRUE),
    TRUE
  ),
  expect_identical(
    "insight paragraphs do not use br separators",
    grepl("<br>", summary_insight_fixture, fixed = TRUE),
    FALSE
  ),
  expect_identical(
    "insight numbered items are not indented",
    grepl('text-indent:0;">2. 第二项。', summary_itemized_insight_fixture, fixed = TRUE),
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

report <- list(ok = TRUE, checks = checks, questionnaire_html = question_layout_fixture)
args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 1 && nzchar(args[1])) {
  write_json(report, args[1], pretty = TRUE, auto_unbox = TRUE)
}
cat("summary helper fixtures PASS\n")
