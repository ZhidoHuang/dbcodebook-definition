# Run from the Skill root. This creates only a temporary synthetic topic.
local({
  root <- normalizePath(".", winslash="/")
  source(file.path(root, "scripts/summary_fact_helpers.R"), encoding="UTF-8")
  source(file.path(root, "scripts/render_definition_bundle.R"), encoding="UTF-8")
  library(dbCodeBookr)
  library(openxlsx)
  Sys.setenv(DBCODEBOOK_DEFINITION_SKILL_ROOT=root)
  before_dir <- getwd()
  folder <- tempfile("compact_module_31_")
  dir.create(folder)
  on.exit(setwd(before_dir), add=TRUE)
  setwd(folder)

  vars <- sprintf("defined_%02d", 1:31)
  vars[1] <- "defined_01_ng.ml"
  raw <- "raw_source_only"
  periods <- c("2017-2018", "2017-2020")
  db <- data.frame(SEQN=as.character(1:4), YEAR=rep(periods, each=2), raw_source_only=101:104)
  for (v in vars) db[[v]] <- c(1, 2, NA_real_, 3)
  analysis <- db[c("SEQN", "YEAR", vars)]
  raw_book <- data.frame(Variable="ORIGINAL_SOURCE", newname=raw, Label="SOURCE_ONLY_MARKER")
  analysis_book <- data.frame(Variable=vars, original_vars="ORIGINAL_SOURCE",
    processed_vars=raw, Label=paste0("检测", seq_along(vars)), count=1L)
  book <- dplyr::bind_rows(
    data.frame(Variable=c("SEQN", "YEAR", raw), original_vars=c("SEQN", "YEAR", "ORIGINAL_SOURCE"),
      processed_vars=c("SEQN", "YEAR", raw), Label=c("编号", "周期", "SOURCE_ONLY_MARKER"), count=1L),
    analysis_book)
  # Default cycle participates in the first definition; it is not a manually selected source.
  analysis_book$original_vars[1] <- "ORIGINAL_SOURCE, YEAR"
  analysis_book$processed_vars[1] <- paste(raw, "YEAR", sep=", ")
  analysis_book$count[1] <- 2L
  book$original_vars[book$Variable==vars[1]] <- analysis_book$original_vars[1]
  book$processed_vars[book$Variable==vars[1]] <- analysis_book$processed_vars[1]
  book$count[book$Variable==vars[1]] <- 2L
  before_objects <- list(db=db, book=book, analysis=analysis, analysis_book=analysis_book)
  files <- c("db.xlsx", "codebook.xlsx", "analysis_db.xlsx", "analysis_codebook.xlsx")
  objects <- list(db, book, analysis, analysis_book)
  for (i in seq_along(files)) write.xlsx(objects[[i]], files[i])
  before_hashes <- tools::md5sum(files)
  writeLines(c("---", "topic_kind: module", "---", "",
    "# NHANES — 检测模块（Test Module）", "", "## 摘要导读", "",
    "本主题定义 **31** 个变量：**检测数值**。", "", "## 小book提示", "",
    "保留每日发布的检测数值。"), "文案.md", useBytes=TRUE)
  writeLines(c("# synthetic public code", "print('fixture')", "# 输出"), "define_fixture.R")
  copy <- read_definition_copy(vars)
  stopifnot(isTRUE(copy$display_policy$compact_module), length(copy$criteria)==0L)
  reject <- function(expr) stopifnot(inherits(tryCatch({force(expr); NULL}, error=identity), "error"))
  reject(validate_definition_display_policy(copy$display_policy, rev(vars)))
  stopifnot(is.null(validate_definition_display_policy(NULL, vars)))

  # Observe the real renderer inputs without replacing chart or HTML generation.
  detail_calls <- list(); long_inputs <- NULL; compact_test <- TRUE
  real_details <- dbCodeBookr::generate_var_details
  real_long <- dbCodeBookr::generate_html_definition_long
  generate_var_details <- function(data, ...) {
    detail_calls[[length(detail_calls)+1L]] <<- names(data)
    if (compact_test) stopifnot(identical(setdiff(names(data), "year"), vars))
    real_details(data, ...)
  }
  generate_html_definition_long <- function(heat_df, meta_df, ...) {
    long_inputs <<- list(heat=heat_df, meta=meta_df)
    if (compact_test) stopifnot(identical(as.character(heat_df$Variable), vars),
      all(as.character(heat_df$category)=="Defined variables"),
      !any(c("Definition", "Criteria") %in% names(meta_df)))
    real_long(heat_df, meta_df, ...)
  }
  generate_html_definition <- function(...) {
    if (compact_test) stop("Compact module attempted a definition table")
    dbCodeBookr::generate_html_definition(...)
  }
  # Source the function into this scope so its calls resolve the observing wrappers.
  environment(render_definition_bundle) <- environment()
  writeLines("STALE_DEFINITION", "NHANES_compact_definition.html")
  render_definition_bundle(data=db, db_data=db, codebook=book, analysis_data=analysis,
    analysis_codebook=analysis_book, analysis_vars=vars, raw_vars=raw, raw_codebook=raw_book,
    criteria=copy$criteria, summary_meanings=setNames(analysis_book$Label, vars),
    summary_groups=setNames(rep("检测", 31), vars), summary_entry=copy$summary_entry,
    summary_selection=NULL, summary_insight_items=copy$summary_insight_items,
    file_stem="compact", note_name="note.md", qa_title="fixture QA", transaction_id="fixture",
    script_file="define_fixture.R", database="NHANES", cycle_order=periods,
    reference_lines=copy$reference_lines, display_policy=copy$display_policy)
  stopifnot(length(detail_calls)==1L, !is.null(long_inputs),
    !file.exists("NHANES_compact_definition.html"), file.exists("NHANES_compact_detail.html"))
  note <- readLines("note.md", encoding="UTF-8")
  html <- paste(readLines("NHANES_compact_detail.html", encoding="UTF-8"), collapse="\n")
  stopifnot(!any(note %in% c("## 定义", "## Criteria")),
    !grepl("Source variables", html, fixed=TRUE), grepl("Defined variables", html, fixed=TRUE),
    grepl('data-defined-overview="true"', html, fixed=TRUE),
    all(vapply(paste0('data-defined-variable="', vars, '"'), grepl, logical(1), x=html, fixed=TRUE)),
    !grepl("SOURCE_ONLY_MARKER", html, fixed=TRUE),
    all(vapply(vars, grepl, logical(1), x=html, fixed=TRUE)),
    identical(before_hashes, tools::md5sum(files)),
    identical(before_objects, list(db=db, book=book, analysis=analysis, analysis_book=analysis_book)))
  for (i in seq_along(files)) {
    actual <- read.xlsx(files[i])
    stopifnot(identical(names(actual), names(objects[[i]])),
      isTRUE(all.equal(actual, objects[[i]], check.attributes=FALSE)))
  }
  # A legacy topic without metadata, and without a policy argument, keeps the
  # complete definition output. Reuse the dotted result name in this path too.
  compact_test <- FALSE
  single <- vars[1]
  writeLines(c("# NHANES — 检测（Test）", "", "## 摘要导读", "",
    "本主题定义 **1** 个变量：**检测数值**。", "", "## Criteria", "",
    paste0("### ", single), "", "#### 定义", "", "检测的发布数值。", "",
    "#### 定义逻辑", "", "保留来源发布的检测数值。", "", "#### 分类", "",
    "- [数值] 检测单位。", "", "## 小book提示", "", "保留每日发布的检测数值。"),
    "文案.md", useBytes=TRUE)
  legacy_copy <- read_definition_copy(single)
  stopifnot(!legacy_copy$display_policy$compact_module,
    identical(legacy_copy$display_policy$topic_kind, "standard"))
  render_definition_bundle(data=db, db_data=db, codebook=book,
    analysis_data=analysis[c("SEQN", "YEAR", single)], analysis_codebook=analysis_book[1,,drop=FALSE],
    analysis_vars=single, raw_vars=raw, raw_codebook=raw_book, criteria=legacy_copy$criteria,
    summary_meanings=setNames(analysis_book$Label[1], single),
    summary_groups=setNames("检测", single), summary_entry=legacy_copy$summary_entry,
    summary_selection=NULL, summary_insight_items=legacy_copy$summary_insight_items,
    file_stem="legacy", note_name="legacy-note.md", qa_title="legacy QA", transaction_id="fixture",
    script_file="define_fixture.R", database="NHANES", cycle_order=periods)
  stopifnot(file.exists("NHANES_legacy_definition.html"),
    "## 定义" %in% readLines("legacy-note.md", encoding="UTF-8"),
    length(detail_calls)==3L, identical(before_hashes, tools::md5sum(files)))
  setwd(before_dir)
  unlink(folder, recursive=TRUE)
  cat("COMPACT_MODULE_RENDER_PASS: 31 variables; real detail HTML and one chart pass; no source charts or definition output; four xlsx and original objects unchanged; dotted names and legacy NULL-policy full render pass\n")
})
