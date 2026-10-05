args <- commandArgs(trailingOnly = FALSE)
test_dir <- dirname(normalizePath(sub("^--file=", "", grep("^--file=", args, value = TRUE)[[1]])))
root <- dirname(test_dir)
eval(parse(file=file.path(root,"scripts","summary_fact_helpers.R"),encoding="UTF-8"))
eval(parse(file=file.path(root,"scripts","render_definition_bundle.R"),encoding="UTF-8"))
eval(parse(file=file.path(root,"scripts","check_public_raw_reads.R"),encoding="UTF-8"))
expect <- function(expr, message) {
  actual <- tryCatch({force(expr); ""}, error=function(e) conditionMessage(e))
  if (!grepl(message,actual,fixed=TRUE)) stop("Expected: ",message,"; actual: ",actual)
}
call_renderer <- function(frame, order=c("Wave 1","Wave 2")) {
  render_definition_bundle(data=frame,db_data=frame,analysis_data=frame,database="SHARE",cycle_order=order)
}
expect(render_definition_bundle(database="SHARE"),"SHARE requires explicit")
frame <- data.frame(ID=c("opaque-a","opaque-b"),Wave_id=c("Wave 1","Wave 2"),mergeid=c("0001","0001"))
expect(call_renderer(frame,c("Wave 1","Corona Survey 1")),"Invalid SHARE ordinary Wave order")
wrong <- frame;wrong$mergeid <- c(1,1)
expect(call_renderer(wrong),"identities must remain character")
wrong <- frame;wrong$ID[2] <- wrong$ID[1]
expect(call_renderer(wrong),"Duplicate SHARE personal identity")
wrong <- frame;wrong$Wave_id[2] <- "Wave 1"
expect(call_renderer(wrong),"Duplicate SHARE personal identity")
wrong <- frame;wrong$Wave_id[2] <- "Wave 3"
expect(call_renderer(wrong),"outside declared cycle_order")
wrong <- frame;wrong$mergeid[2] <- ""
expect(call_renderer(wrong),"identities must be nonempty")
# A valid same-person cross-wave frame must reach the downstream rendering stage.
# Deliberately stop there: this fixture does not claim complete note generation.
definition_source_entry <- function(...) stop("SHARE_IDENTITY_CONTRACT_ACCEPTED")
expect(call_renderer(frame),"SHARE_IDENTITY_CONTRACT_ACCEPTED")
reader <- 'dt <- read.csv("raw_data.csv", colClasses=c(ID="character", Wave_id="character", mergeid="character", hhid="character", country="character"))'
check_public_raw_reads(c(reader,'name_z <- read.csv("raw_codebook.csv")'),database="SHARE")
expect(check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(gender="character"))','name_z <- read.csv("raw_codebook.csv")'),database="SHARE"),"Only declared SHARE identity")
expect(check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(mergeid="numeric"))','name_z <- read.csv("raw_codebook.csv")'),database="SHARE"),"Only declared SHARE identity")
temp <- tempfile("share_identity_read_");dir.create(temp)
writeLines(c('ID,Wave_id,mergeid,hhid,country,value','001,Wave 1,0001,0006,01,7'),file.path(temp,'raw_data.csv'))
old <- getwd();setwd(temp);eval(parse(text=reader));setwd(old)
stopifnot(identical(dt$ID,"001"),identical(dt$mergeid,"0001"),identical(dt$hhid,"0006"),identical(dt$country,"01"),is.integer(dt$value))
cat("SHARE renderer identity/period fixtures PASS; full note generation untested\n")
