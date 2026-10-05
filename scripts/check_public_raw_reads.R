# Inspect expressions without executing the user's definition.
check_public_raw_reads <- function(lines, database = "CHARLS") {
  identity_names <- c("id", "householdid", "communityid", "HHID", "PN")
  if (toupper(database) == "SHARE") {
    identity_names <- c("ID", "Wave_id", "mergeid", "hhid", "country", "intid", "intidwX", "Record_id")
  }
  if (toupper(database) == "KNHANES") identity_names <- c("ID", "id", "year")
  if (toupper(database) == "KLOSA") identity_names <- c("ID", "Harmonized_id", "Wave_id")
  if (toupper(database) == "CHNS") identity_names <- c("ID", "IDind", "WAVE", "hhid", "COMMID", "Household_ID", "Community_ID")
  boundary <- grep("^# 输出\\s*$", lines)
  if (length(boundary)) lines <- head(lines, boundary[[1]] - 1L)
  expressions <- parse(text = lines, keep.source = FALSE)
  targets <- c(dt = "raw_data.csv", name_z = "raw_codebook.csv")
  if (toupper(database) == "CHNS") {
    # Static sources remain separate reads, with a literal source filename and personal key.
    for (expr in as.list(expressions)) {
      if (is.call(expr) && (identical(expr[[1]], as.name("<-")) || identical(expr[[1]], as.name("="))) &&
          is.symbol(expr[[2]]) && is.call(expr[[3]]) && identical(expr[[3]][[1]], as.name("read.csv"))) {
        args <- as.list(expr[[3]])[-1]
        if (length(args) && is.character(args[[1]]) && length(args[[1]]) == 1L &&
            grepl("^raw_data_.+\\.csv$", args[[1]])) targets[as.character(expr[[2]])] <- args[[1]]
      }
    }
  }
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
    if (length(args) == 1L) {
      if (target == "dt" && toupper(database) == "KNHANES") stop("KNHANES must preserve id as character at read time")
      if (target != "name_z" && toupper(database) == "CHNS") stop("CHNS must preserve personal identities as character at read time")
      next
    }
    if ((target != "dt" && !(toupper(database) == "CHNS" && target != "name_z")) || length(args) != 2L || labels[[2]] != "colClasses") {
      stop(target, ": only identity colClasses may be added to the raw-data read")
    }
    classes <- args[[2]]
    if (!is.call(classes) || !identical(classes[[1]], as.name("c"))) {
      stop("colClasses must be a named c(... = 'character') for identity columns")
    }
    values <- as.list(classes)[-1]
    ids <- names(values)
    if (toupper(database) == "KNHANES" && !"id" %in% ids) stop("KNHANES must preserve id as character at read time")
    if (toupper(database) == "CHNS") {
      required <- if (target == "dt") c("ID", "IDind") else "IDind"
      if (!all(required %in% ids)) stop("CHNS must preserve personal identities as character at read time")
      if (target != "dt" && any(ids != "IDind")) stop("CHNS static reads permit only IDind colClasses")
    }
    if (!length(values) || is.null(ids) || anyDuplicated(ids) ||
        any(!(ids %in% identity_names | (toupper(database) == "SHARE" & grepl("^intid \\(.+\\)$", ids)) |
          (toupper(database) == "CHNS" & grepl("^(IDind|WAVE|hhid|COMMID|Household_ID|Community_ID) \\(.+\\)$", ids)))) ||
        !all(vapply(values, identical, logical(1), "character"))) {
      stop("Only declared ", toupper(database), " identity columns may be preserved as character")
    }
  }
  invisible(TRUE)
}
