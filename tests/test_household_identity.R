if (!exists("args")) args <- commandArgs(trailingOnly = TRUE)
source(file.path(args[[1]], "scripts", "render_definition_bundle.R"), encoding="UTF-8")
source(file.path(args[[1]], "scripts", "check_public_raw_reads.R"), encoding="UTF-8")
contract <- definition_analysis_identity_contract("CHARLS", "household_period", c("householdid", "year"), record_path=args[[2]])
standalone <- definition_analysis_identity_contract("CHARLS", "household_period", c("householdid", "year"), record_path="")
stopifnot(identical(contract, standalone))
stopifnot(identical(contract$identity_keys, c("householdid", "year")))
x <- data.frame(householdid=c("001", "002"), year=c("2011", "2011"))
validate_person_period_outputs(list(x,x,x), "CHARLS", contract)
fails <- function(expr) stopifnot(inherits(tryCatch({force(expr); NULL}, error=function(e)e), "error"))
fails(definition_analysis_identity_contract("CHARLS", record_path=args[[2]]))
fails(definition_analysis_identity_contract("CHARLS", "household_period", c("id", "year"), record_path=""))
fails(validate_person_period_outputs(list(x), "CHARLS"))
y <- x; y$year <- as.integer(y$year)
fails(validate_person_period_outputs(list(y), "CHARLS", contract))
fails(validate_person_period_outputs(list(x,x[2:1,]), "CHARLS", contract))
fails(validate_person_period_outputs(list(rbind(x,x[1,])), "CHARLS", contract))
fails(validate_person_period_outputs(list(x,x[1,,drop=FALSE]), "CHARLS", contract))
y <- x; y$householdid[1] <- " "
fails(validate_person_period_outputs(list(y), "CHARLS", contract))
lines <- c('dt <- read.csv("raw_data_household.csv", colClasses=c(householdid="character", year="character"))', 'name_z <- read.csv("raw_codebook.csv")')
check_public_raw_reads(lines, "CHARLS", source_record_path=args[[2]])
fails(check_public_raw_reads(lines, "CHARLS"))
fails(check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(householdid="character", year="character"))',lines[2]), "CHARLS", source_record_path=args[[2]]))
fails(check_public_raw_reads(c('dt <- read.csv("raw_data_household.csv")',lines[2]), "CHARLS", source_record_path=args[[2]]))
check_public_raw_reads(c('dt <- read.csv("raw_data.csv")', lines[2]), "CHARLS")

# A default household respondent identifier may be preserved only when the
# actual household file contains it; other columns and contracts stay guarded.
raw_dir <- tempfile("charls_household_identity_")
dir.create(raw_dir)
writeLines("householdid,year,respondent_id,ha007", file.path(raw_dir, "raw_data_household.csv"))
respondent_lines <- c(
  'dt <- read.csv("raw_data_household.csv", colClasses=c(householdid="character", year="character", respondent_id="character"))',
  lines[2]
)
check_public_raw_reads(respondent_lines, "CHARLS", source_dir=raw_dir, source_record_path=args[[2]])
fails(check_public_raw_reads(
  c('dt <- read.csv("raw_data_household.csv", colClasses=c(householdid="character", year="character", ha007="character"))', lines[2]),
  "CHARLS", source_dir=raw_dir, source_record_path=args[[2]]
))
fails(check_public_raw_reads(
  c('dt <- read.csv("raw_data.csv", colClasses=c(id="character", respondent_id="character"))', lines[2]),
  "CHARLS", source_dir=raw_dir
))
writeLines("householdid,year,ha007", file.path(raw_dir, "raw_data_household.csv"))
fails(check_public_raw_reads(respondent_lines, "CHARLS", source_dir=raw_dir, source_record_path=args[[2]]))
cat("HOUSEHOLD_R_IDENTITY_PASS\n")
