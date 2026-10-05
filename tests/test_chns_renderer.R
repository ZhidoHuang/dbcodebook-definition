root <- normalizePath(".")
source(file.path(root, "scripts/check_public_raw_reads.R"), encoding="UTF-8")
source(file.path(root, "scripts/render_definition_bundle.R"), encoding="UTF-8")
reject <- function(expr, message) {
  error <- tryCatch({force(expr); ""}, error=function(e) conditionMessage(e))
  stopifnot(grepl(message, error, fixed=TRUE))
}
years <- c("1989", "1991", "1993", "1997", "2000", "2004", "2006", "2009", "2011", "2015")
frame <- data.frame(ID=paste0("opaque-", seq_along(years)), IDind="001", WAVE=years, age=30L+seq_along(years))
validate_chns_render_inputs(list(frame,frame,frame), years)
decimal_frame <- frame; decimal_frame$WAVE <- paste0(years,".0")
validate_chns_render_inputs(list(decimal_frame), years)
stopifnot(identical(chns_year_values(decimal_frame$WAVE), years),
  identical(decimal_frame$WAVE,paste0(years,".0")))
wrong <- decimal_frame; wrong$WAVE[1] <- "1989.5"
reject(validate_chns_render_inputs(list(wrong), years), "integer survey year")
wrong <- decimal_frame; wrong$WAVE[2] <- "1989"
reject(validate_chns_render_inputs(list(wrong), years), "Duplicate CHNS")
reject(validate_chns_render_inputs(list(frame), rev(years)), "Invalid CHNS year order")
reject(validate_chns_render_inputs(list(frame), c(years,"2020")), "Invalid CHNS year order")
wrong <- frame; wrong$IDind <- as.integer(wrong$IDind)
reject(validate_chns_render_inputs(list(wrong), years), "must remain character")
wrong <- frame; wrong$ID[2] <- wrong$ID[1]
reject(validate_chns_render_inputs(list(wrong), years), "Duplicate CHNS")
wrong <- frame; wrong$WAVE[2] <- wrong$WAVE[1]
reject(validate_chns_render_inputs(list(wrong), years), "Duplicate CHNS")
reject(render_definition_bundle(database="CHNS"), "CHNS requires explicit")
definition_source_entry <- function(...) stop("CHNS_IDENTITY_CONTRACT_ACCEPTED")
reject(render_definition_bundle(data=frame, db_data=frame, analysis_data=frame,
  database="CHNS", cycle_order=years), "CHNS_IDENTITY_CONTRACT_ACCEPTED")
reader <- c('dt <- read.csv("raw_data.csv", colClasses=c(ID="character",IDind="character"))',
  'name_z <- read.csv("raw_codebook.csv")',
  'static_person <- read.csv("raw_data_mast_pub_12.csv", colClasses=c(IDind="character"))')
check_public_raw_reads(reader, "CHNS")
reject(check_public_raw_reads(sub('ID="character",','',reader,fixed=TRUE),"CHNS"), "preserve personal identities")
reject(check_public_raw_reads(sub(', colClasses=c(IDind="character")','',reader,fixed=TRUE),"CHNS"), "preserve personal identities")
reject(check_public_raw_reads(sub('IDind="character")','IDind="character",sex="character")',reader,fixed=TRUE),"CHNS"), "Only declared CHNS")
temp <- tempfile("chns_person_read_"); dir.create(temp)
writeLines(c("ID,IDind,WAVE,age", "opaque-a,001,1989,30", "opaque-b,001,1991,32", "opaque-c,002,1991,28"), file.path(temp,"raw_data.csv"))
writeLines(c("IDind,sex", "001,Female"),file.path(temp,"raw_data_mast_pub_12.csv"))
old <- getwd(); setwd(temp); eval(parse(text=reader[c(1,3)])); setwd(old)
original <- dt
stopifnot(!anyDuplicated(static_person$IDind))
data <- dplyr::left_join(dt,static_person,by="IDind",relationship="many-to-one")
stopifnot(identical(dt,original), identical(dt$IDind,c("001","001","002")),
  identical(data$sex,c("Female","Female",NA_character_)), is.integer(data$age))
raw_codebook <- data.frame(Variable=c("age (rst_12)","sex (mast_pub_12)"),
  newname=c("age","sex"), check.names=FALSE)
analysis_codebook <- data.frame(Variable="defined_sex", original_vars="sex (mast_pub_12)",
  processed_vars="sex", count=1L)
stopifnot(identical(unname(format_definition_card_sources(analysis_codebook,raw_codebook)),
  "sex (mast_pub_12)=sex"), definition_source_count(c("age","sex"),raw_codebook,"CHNS") == 2L,
  !"sex" %in% names(dt))
static_person <- rbind(static_person, static_person)
reject(dplyr::left_join(dt,static_person,by="IDind",relationship="many-to-one"), "at most 1 row")
unlink(temp, recursive=TRUE)
cat("CHNS ten-period identity, static read and many-to-one fixtures PASS; full note generation untested\n")
