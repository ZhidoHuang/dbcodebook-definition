# Inspect expressions without executing the user's definition.
check_public_raw_reads <- function(lines, database = "CHARLS", source_dir = ".", source_record_path = "") {
  household <- FALSE
  record <- NULL
  if (nzchar(source_record_path)) {
    record <- jsonlite::fromJSON(source_record_path, simplifyVector = FALSE)
    household <- identical(record$analysis_unit, "household_period")
    if (household && (toupper(database) != "CHARLS" || !identical(toupper(record$database), "CHARLS") ||
        !identical(record$identity_keys, list("householdid", "year")))) stop("Invalid household identity contract.")
  }
  identity_names <- c("id", "householdid", "communityid", "HHID", "PN")
  if (toupper(database) == "SHARE") {
    identity_names <- c("ID", "Wave_id", "mergeid", "hhid", "country", "intid", "intidwX", "Record_id")
  }
  if (toupper(database) == "KNHANES") identity_names <- c("ID", "id", "year")
  if (toupper(database) == "KLOSA") identity_names <- c("ID", "Harmonized_id", "Wave_id", "pid")
  if (toupper(database) == "CHNS") identity_names <- c("ID", "IDind", "WAVE", "hhid", "COMMID", "Household_ID", "Community_ID")
  if (toupper(database) == "MHAS") identity_names <- c("ID", "Wave_id", "UNHHIDNP", "CUNICAH", "NP",
    "cunicah", "np", "unhhid", "ps3", "acthog", "ent2", "codent01", "codent03", "source_file", "source_row")
  if (toupper(database) == "NHANES") identity_names <- c("SEQN", "YEAR", "RowIndex", "DOC_FILE")
  if (toupper(database) == "NHANESIII") identity_names <- c("SEQN", "_survey_period", "_period")
  if (toupper(database) == "NHIS") identity_names <- c("ID","Wave_id","Survey_year","Record_id","Baseline_year","Imputation_number")
  if (household) identity_names <- c(identity_names, "year")
  boundary <- grep("^# 输出\\s*$", lines)
  if (length(boundary)) lines <- head(lines, boundary[[1]] - 1L)
  expressions <- parse(text = lines, keep.source = FALSE)
  targets <- c(dt = if (household) "raw_data_household.csv" else "raw_data.csv", name_z = "raw_codebook.csv")
  if (toupper(database) == "NHANESIII") targets[["dt"]] <- "raw_data_NHANES_III.csv"
  if (toupper(database) == "KNHANES") {
    dictionary_path <- file.path(source_dir, "raw_codebook.csv")
    if (file.exists(dictionary_path)) {
      dictionary <- read.csv(dictionary_path)
      if (!all(c("Variable", "File.type") %in% names(dictionary)) || !nrow(dictionary)) {
        stop("KNHANES requires the source dictionary to resolve its personal file")
      }
      if (any(dictionary$File.type != "uniqID")) {
        plan <- record$knhanes_person_aggregation
        fixed <- list(schema_version=1L, primary_file="raw_data.csv",
          repeat_file="raw_data_Dietary_recall_second_day.csv", source_file="Dietary recall second day",
          group_keys=list("ID","id","year"), visit_periods=list("2009","2019"),
          method="constant_within_person_visit", missing_rule="single_known_or_all_missing",
          conflict_rule="group_na_and_report", join="left_to_primary", orphan_rule="stop")
        if (is.null(plan) || any(!vapply(names(fixed), function(k) identical(plan[[k]],fixed[[k]]), logical(1))))
          stop("KNHANES reID sources require a supported source-bound aggregation plan")
        repeat_dict <- dictionary[dictionary$File.type != "uniqID", , drop=FALSE]
        originals <- c("n_diet", "n_diet_why", "n_dt_ds", "n_dt_etc")
        expected <- paste0(originals, " (Dietary recall second day)")
        if (nrow(repeat_dict)!=4L || !all(repeat_dict$File.type=="reID") ||
            !setequal(repeat_dict$Variable,expected) || anyDuplicated(repeat_dict$Variable))
          stop("Unsupported KNHANES repeat question family")
        summaries <- plan$source_summaries
        if (length(summaries)!=4L) stop("Four explicit repeated question summaries required")
        summary_names <- vapply(summaries, function(x) x$variable, character(1))
        source_names <- vapply(summaries, function(x) {
          index <- match(paste0(x$original_variable," (Dietary recall second day)"),repeat_dict$Variable)
          expected_type <- if (x$original_variable %in% originals[1:2]) "numeric_code" else "text"
          if (is.na(index) || !identical(x$source_variables,list(repeat_dict$newname[[index]])) ||
              !identical(x$value_type,expected_type)) stop("Repeated source summary lineage differs")
          x$source_variables[[1]]
        },character(1))
        if (anyDuplicated(summary_names) || anyDuplicated(source_names) ||
            any(!grepl("^[A-Za-z][A-Za-z0-9_]*$",summary_names)) ||
            any(summary_names %in% c(dictionary$newname,unlist(record$approved_analysis_vars),"ID","id","year")))
          stop("Invalid summary names or source identities")
        targets <- c(dt="raw_data.csv",dt_day2=plan$repeat_file,name_z="raw_codebook.csv")
      }
      files <- sub("^.* \\(([^()]*)\\)$", "\\1", dictionary$Variable)
      special <- c("Indoor air quality special release", "Cycle 7 oral special release")
      if (any(files %in% special)) {
        if (setequal(unique(files), c("Core data", "Indoor air quality special release"))) {
          targets <- c(dt_core="raw_data.csv",
            dt_special="raw_data_Indoor_air_quality_special_release.csv", name_z="raw_codebook.csv")
        } else {
          if (length(unique(files)) != 1L) stop("KNHANES standalone uniqID release requires one source family")
          targets[["dt"]] <- paste0("raw_data_", gsub(" ", "_", files[[1]], fixed = TRUE), ".csv")
        }
      }
    }
    for (expr in as.list(expressions)) {
      if (is.call(expr) && (identical(expr[[1]], as.name("<-")) || identical(expr[[1]], as.name("="))) &&
          is.symbol(expr[[2]]) && is.call(expr[[3]]) && identical(expr[[3]][[1]], as.name("read.csv"))) {
        args <- as.list(expr[[3]])[-1]
        if (length(args) && is.character(args[[1]]) && length(args[[1]]) == 1L &&
            grepl("^raw_data.*\\.csv$", args[[1]]) &&
            (!as.character(expr[[2]]) %in% names(targets) ||
             !identical(args[[1]], unname(targets[[as.character(expr[[2]])]])))) {
          stop("KNHANES personal definition must read only its dictionary-bound data file into dt")
        }
      }
    }
  }
  if (toupper(database) == "MHAS") {
    questionnaire_files <- paste0("raw_data_", c("MHAS_SURVEY_CORE_RESPONDENT", "MHAS_SURVEY_NEXT_OF_KIN",
      "MHAS_MEXCOG_COGNITIVE_ASSESSMENT", "MHAS_MEXCOG_INFORMANT_INTERVIEW"), ".csv")
    biomarker_files <- paste0("raw_data_", c("MHAS_ANCILLARY_ANTHROPOMETRICS_BIOMARKERS", "MHAS_ANCILLARY_HEAVY_METALS"), ".csv")
    allowed <- c(questionnaire_files, biomarker_files)
    targets <- c(name_z = "raw_codebook.csv")
    for (expr in as.list(expressions)) {
      if (is.call(expr) && (identical(expr[[1]], as.name("<-")) || identical(expr[[1]], as.name("="))) &&
          is.symbol(expr[[2]]) && is.call(expr[[3]]) && identical(expr[[3]][[1]], as.name("read.csv"))) {
        args <- as.list(expr[[3]])[-1]
        if (length(args) && is.character(args[[1]]) && length(args[[1]]) == 1L &&
            grepl("^raw_data.*\\.csv$", args[[1]])) {
          if (!args[[1]] %in% allowed) stop("Unsupported MHAS source file: ", args[[1]])
          targets[as.character(expr[[2]])] <- args[[1]]
        }
      }
    }
    sources <- unname(targets[names(targets) != "name_z"])
    if (!length(sources) || anyDuplicated(sources) ||
        !(all(sources %in% questionnaire_files) || all(sources %in% biomarker_files))) stop("Invalid MHAS source-file combination.")
  }
  if (toupper(database) %in% c("CHNS", "NHANES")) {
    # Static sources remain separate reads, with a literal source filename and personal key.
    for (expr in as.list(expressions)) {
      if (is.call(expr) && (identical(expr[[1]], as.name("<-")) || identical(expr[[1]], as.name("="))) &&
          is.symbol(expr[[2]]) && is.call(expr[[3]]) && identical(expr[[3]][[1]], as.name("read.csv"))) {
        args <- as.list(expr[[3]])[-1]
        if (length(args) && is.character(args[[1]]) && length(args[[1]]) == 1L &&
            (grepl("^raw_data_.+\\.csv$", args[[1]]) ||
             (toupper(database) == "NHANES" && args[[1]] == "raw_drug.csv"))) {
          if (toupper(database) == "NHANES" &&
              !args[[1]] %in% c("raw_data_PAQIAF.csv", "raw_data_RXQ_RX.csv", "raw_drug.csv")) {
            stop("Unsupported NHANES repeated source file: ", args[[1]])
          }
          targets[as.character(expr[[2]])] <- args[[1]]
        }
      }
    }
  }
  if (toupper(database) == "HRS") {
    allowed <- paste0("raw_data_repeat_ADAMS_MEDICAL_CONDITIONS_",
      c("INITIAL_VISIT_CONDITION", "FOLLOW_UP_VISIT_CONDITION"), ".csv")
    internet_member <- "raw_data_repeat_INTERNET_SURVEY_INTERNET_QUESTIONNAIRE_RESPONDENT.csv"
    allowed <- c(allowed, internet_member)
    for (expr in as.list(expressions)) {
      if (is.call(expr) && (identical(expr[[1]], as.name("<-")) || identical(expr[[1]], as.name("="))) &&
          is.symbol(expr[[2]]) && is.call(expr[[3]]) && identical(expr[[3]][[1]], as.name("read.csv"))) {
        args <- as.list(expr[[3]])[-1]
        if (length(args) && is.character(args[[1]]) && length(args[[1]]) == 1L &&
            grepl("^raw_data_.+\\.csv$", args[[1]])) {
          if (!args[[1]] %in% allowed) stop("Unsupported HRS repeated source file")
          if (identical(args[[1]], internet_member)) {
            if (!nzchar(source_record_path) || !identical(toupper(record$database), "HRS"))
              stop("Internet repeat requires its current HRS source record")
            dictionary <- read.csv(file.path(source_dir, "raw_codebook.csv"), check.names = FALSE)
            if (!all(c("Variable", "newname", "File type") %in% names(dictionary)))
              stop("Internet repeat requires its source dictionary")
            selected <- dictionary[endsWith(dictionary$Variable,
              " (INTERNET_SURVEY_INTERNET_QUESTIONNAIRE_RESPONDENT)"), , drop = FALSE]
            declared <- unique(unlist(lapply(record$source_groups, function(group) {
              if (length(group$source_identities) != length(group$raw_variables)) return(character())
              paste(unlist(group$source_identities), unlist(group$raw_variables), sep = "|alias|")
            }), use.names = FALSE))
            if (!nrow(selected) || any(selected[["File type"]] != "rePersonID") ||
                !all(paste(selected$Variable, selected$newname, sep = "|alias|") %in% declared))
              stop("Internet repeat dictionary and current source record disagree")
          }
          targets[as.character(expr[[2]])] <- args[[1]]
        }
      }
    }
    if (anyDuplicated(unname(targets))) stop("Duplicated HRS source-file read")
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
      if (household && target != "name_z") stop("Household raw read must preserve householdid and year as character")
      if (target != "name_z" && toupper(database) == "NHANES") stop("NHANES must preserve SEQN and YEAR as character")
      if (target != "name_z" && toupper(database) == "NHANESIII") stop("NHANES III must preserve SEQN as character")
      if (target != "name_z" && toupper(database) == "NHIS") stop("NHIS must preserve ID, Wave_id and Survey_year as character")
      if (target != "name_z" && toupper(database) == "MHAS") stop("MHAS must preserve ID and Wave_id as character")
      if (target != "name_z" && toupper(database) == "KNHANES") stop("KNHANES must preserve id as character at read time")
      if (target != "name_z" && toupper(database) == "CHNS") stop("CHNS must preserve personal identities as character at read time")
      if (target != "name_z" && toupper(database) == "HRS") stop("HRS must preserve both person keys as character")
      next
    }
    if ((target != "dt" && !(toupper(database) %in% c("CHNS", "NHANES", "MHAS", "KNHANES", "HRS") && target != "name_z")) || length(args) != 2L || labels[[2]] != "colClasses") {
      stop(target, ": only identity colClasses may be added to the raw-data read")
    }
    classes <- args[[2]]
    if (!is.call(classes) || !identical(classes[[1]], as.name("c"))) {
      stop("colClasses must be a named c(... = 'character') for identity columns")
    }
    values <- as.list(classes)[-1]
    ids <- names(values)
    if (household && target != "name_z" && !all(c("householdid", "year") %in% ids)) stop("Household raw read must preserve both keys as character")
    if (toupper(database) == "NHANESIII" && !"SEQN" %in% ids) stop("NHANES III must preserve SEQN as character at read time")
    if (toupper(database) == "NHIS" && !all(c("ID","Wave_id","Survey_year") %in% ids)) stop("NHIS must preserve all three default keys as character at read time")
    if (toupper(database) == "NHANES") {
      required <- if (target == "dt") c("SEQN", "YEAR") else "SEQN"
      if (!all(required %in% ids)) stop("NHANES must preserve source identity columns as character")
    }
    if (toupper(database) == "MHAS" && !all(c("ID", "Wave_id") %in% ids)) stop("MHAS must preserve ID and Wave_id as character")
    if (toupper(database) == "KNHANES" && !"id" %in% ids) stop("KNHANES must preserve id as character at read time")
    if (toupper(database) == "CHNS") {
      required <- if (target == "dt") c("ID", "IDind") else "IDind"
      if (!all(required %in% ids)) stop("CHNS must preserve personal identities as character at read time")
      if (target != "dt" && any(ids != "IDind")) stop("CHNS static reads permit only IDind colClasses")
    }
    allowed_ids <- identity_names
    if (toupper(database) == "HRS" && target != "name_z") {
      if (!all(c("HHID", "PN") %in% ids)) stop("HRS must preserve both person keys as character")
      # These official ADAMS ICD fields are Character; numeric inference loses code text.
      dictionary_path <- file.path(source_dir, "raw_codebook.csv")
      raw_path <- file.path(source_dir, targets[[target]])
      if (nzchar(source_record_path) && identical(toupper(record$database), "HRS") &&
          file.exists(dictionary_path) && file.exists(raw_path)) {
        dictionary <- read.csv(dictionary_path, check.names = FALSE)
        header <- names(read.csv(raw_path, nrows = 0L, check.names = FALSE))
        if (all(c("Variable", "Base_Variable", "newname", "File type") %in% names(dictionary))) {
          family <- sub("^.* \\(([^()]*)\\)$", "\\1", dictionary$Variable)
          condition <- family %in% paste0("ADAMS_MEDICAL_CONDITIONS_",
            c("INITIAL_VISIT_CONDITION", "FOLLOW_UP_VISIT_CONDITION")) &
            dictionary$Base_Variable == "HCODE" & dictionary[["File type"]] == "rePersonID"
          history <- family %in% paste0("ADAMS_MEDICAL_HISTORY_",
            c("INITIAL_VISIT_RESPONDENT", "FOLLOW_UP_VISIT_RESPONDENT")) &
            grepl("^M251[A-HJK]$", dictionary$Base_Variable) & dictionary[["File type"]] == "uniqPersonID"
          expected_file <- ifelse(condition, paste0("raw_data_repeat_", family, ".csv"), "raw_data.csv")
          declared <- unique(unlist(lapply(record$source_groups, function(group) {
            if (length(group$source_identities) != length(group$raw_variables)) return(character())
            paste(unlist(group$source_identities), unlist(group$raw_variables), sep = "|alias|")
          }), use.names = FALSE))
          eligible <- (condition | history) & expected_file == targets[[target]] &
            dictionary$newname %in% header &
            paste(dictionary$Variable, dictionary$newname, sep = "|alias|") %in% declared
          allowed_ids <- c(allowed_ids, make.names(dictionary$newname[eligible], unique = TRUE))
          if (!all(make.names(dictionary$newname[eligible], unique = TRUE) %in% ids))
            stop("Official ADAMS Character ICD fields must be preserved at read time")
        }
      }
    }
    # Tracker export defaults are metadata identities, not arbitrary OV business columns.
    if (toupper(database) == "HRS" && target == "dt" && nzchar(source_record_path)) {
      tracker_file <- "TRACKER_FILE_HRS_2022_EARLY_RELEASE_TRACKER_FILE_VERSION_2_RESPONDENT"
      defaults <- c("OVHHID", "OVPN", "OVRESULT", "OVYEAR")
      raw_path <- file.path(source_dir, targets[[target]])
      dictionary_path <- file.path(source_dir, "raw_codebook.csv")
      if (identical(toupper(record$database), "HRS") &&
          file.exists(raw_path) && file.exists(dictionary_path)) {
        header <- names(read.csv(raw_path, nrows = 0L, check.names = FALSE))
        dictionary <- read.csv(dictionary_path, check.names = FALSE)
        tracker_sources <- if ("Variable" %in% names(dictionary))
          dictionary$Variable[endsWith(dictionary$Variable, paste0(" (", tracker_file, ")"))] else character()
        business_sources <- setdiff(tracker_sources, paste0(defaults, " (", tracker_file, ")"))
        declared_defaults <- unique(unlist(lapply(record$source_groups, function(group) {
          identities <- group$source_identities
          aliases <- group$raw_variables
          if (length(identities) != length(aliases)) return(character())
          aliases[vapply(seq_along(aliases), function(i)
            aliases[[i]] %in% defaults &&
              identical(identities[[i]], paste0(aliases[[i]], " (", tracker_file, ")")), logical(1))]
        }), use.names = FALSE))
        if (any(business_sources %in% unlist(lapply(record$source_groups, `[[`, "source_identities"), use.names = FALSE)) &&
            all(defaults %in% header) &&
            all(defaults %in% declared_defaults)) allowed_ids <- c(allowed_ids, "OVHHID", "OVPN")
      }
    }
    qualified_pattern <- switch(toupper(database),
      SHARE = "^intid \\(.+\\)$",
      CHNS = "^(IDind|WAVE|hhid|COMMID|Household_ID|Community_ID) \\(.+\\)$", NULL)
    if (!is.null(qualified_pattern)) {
      raw_path <- file.path(source_dir, targets[[target]])
      dictionary_path <- file.path(source_dir, "raw_codebook.csv")
      if (file.exists(raw_path) && file.exists(dictionary_path)) {
        header <- names(read.csv(raw_path, nrows = 0L, check.names = FALSE))
        dictionary <- read.csv(dictionary_path)
        files <- if ("Variable" %in% names(dictionary))
          unique(sub("^.* \\(([^()]*)\\)$", "\\1", dictionary$Variable)) else character()
        qualified <- grepl(qualified_pattern, header) & vapply(header, function(name)
          any(endsWith(name, paste0(" (", files, ")"))), logical(1))
        # colClasses matches the default read.csv names, not the printed CSV header.
        allowed_ids <- c(allowed_ids, make.names(header, unique = TRUE)[qualified])
      } else {
        # Static inspection without source files retains its prior, limited scope.
        allowed_ids <- c(allowed_ids, ids[grepl(qualified_pattern, ids)])
      }
    }
    if (!length(values) || is.null(ids) || anyDuplicated(ids) ||
        any(!ids %in% allowed_ids) ||
        !all(vapply(values, identical, logical(1), "character"))) {
      stop("Only declared ", toupper(database), " identity columns may be preserved as character")
    }
  }
  invisible(TRUE)
}
