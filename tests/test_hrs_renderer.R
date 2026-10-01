args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) == 0) stop("Run this test with Rscript.")
test_dir <- dirname(normalizePath(sub("^--file=", "", file_arg[[1]])))
repo_root <- dirname(test_dir)

eval(parse(file = file.path(repo_root, "scripts", "summary_fact_helpers.R"), encoding = "UTF-8"))
eval(parse(file = file.path(repo_root, "scripts", "render_definition_bundle.R"), encoding = "UTF-8"))

expect_error_contains <- function(name, expression, expected) {
  message <- tryCatch({ force(expression); "" }, error = function(error) conditionMessage(error))
  if (!grepl(expected, message, fixed = TRUE)) {
    stop(name, " failed. expected error containing: ", expected, "; actual: ", message)
  }
}

expect_error_contains(
  "explicit cycle order",
  render_definition_bundle(database = "HRS"),
  "HRS requires explicit, evidence-based cycle_order."
)
expect_error_contains(
  "valid year order",
  render_definition_bundle(
    data = data.frame(), db_data = data.frame(), analysis_data = data.frame(),
    database = "HRS", cycle_order = c("1992", "not-a-year")
  ),
  "Invalid HRS year order."
)
expect_error_contains(
  "HRS identity",
  render_definition_bundle(
    data = data.frame(x = 1), db_data = data.frame(x = 1),
    analysis_data = data.frame(x = 1), database = "HRS",
    cycle_order = c("1992", "1993")
  ),
  "HRS requires HHID, PN and year."
)

cat("HRS renderer fixtures PASS\n")
