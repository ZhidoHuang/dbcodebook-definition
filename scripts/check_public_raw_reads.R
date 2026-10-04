# Inspect expressions without executing the user's definition.
check_public_raw_reads <- function(lines) {
  boundary <- grep("^# 输出\\s*$", lines)
  if (length(boundary)) lines <- head(lines, boundary[[1]] - 1L)
  expressions <- parse(text = lines, keep.source = FALSE)
  targets <- c(dt = "raw_data.csv", name_z = "raw_codebook.csv")
  for (target in names(targets)) {
    assignments <- Filter(function(x) {
      is.call(x) && (identical(x[[1]], as.name("<-")) || identical(x[[1]], as.name("="))) &&
        identical(x[[2]], as.name(target)) && is.call(x[[3]]) &&
        identical(x[[3]][[1]], as.name("read.csv"))
    }, as.list(expressions))
    if (length(assignments) != 1L) {
      stop("Expected one direct read.csv assignment to ", target)
    }
    args <- as.list(assignments[[1]][[3]])[-1]
    labels <- names(args)
    if (is.null(labels)) labels <- rep("", length(args))
    if (!length(args) || !identical(args[[1]], unname(targets[[target]])) ||
        !labels[[1]] %in% c("", "file")) {
      stop(target, " must read ", targets[[target]])
    }
    if (length(args) == 1L) next
    if (target != "dt" || length(args) != 2L || labels[[2]] != "colClasses") {
      stop(target, ": only identity colClasses may be added to the raw-data read")
    }
    classes <- args[[2]]
    if (!is.call(classes) || !identical(classes[[1]], as.name("c"))) {
      stop("colClasses must be a named c(... = 'character') for identity columns")
    }
    values <- as.list(classes)[-1]
    ids <- names(values)
    if (!length(values) || is.null(ids) || anyDuplicated(ids) ||
        any(!ids %in% c("id", "householdid", "communityid", "HHID", "PN")) ||
        !all(vapply(values, identical, logical(1), "character"))) {
      stop("Only id, householdid, communityid, HHID and PN may be preserved as character")
    }
  }
  invisible(TRUE)
}
