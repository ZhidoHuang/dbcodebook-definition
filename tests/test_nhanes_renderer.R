source("scripts/render_definition_bundle.R")
source("scripts/check_public_raw_reads.R")
source("scripts/summary_fact_helpers.R")
historical <- data.frame(SEQN=c("1", "2"), YEAR="1988-1994")
validate_nhanesiii_render_inputs(list(historical), "1988-1994")
validate_nhanesiii_render_inputs(list(data.frame(SEQN=c("1","2"),YEAR=c("1988-1991","1991-1994"))), c("1988-1991","1991-1994"))
stopifnot(inherits(tryCatch(validate_nhanesiii_render_inputs(list(historical), "1988-1991"),error=identity), "error"))
stopifnot(inherits(tryCatch(validate_nhanesiii_render_inputs(list(transform(historical,SEQN=c("1","01.0"))), "1988-1994"),error=identity), "error"))
check_public_raw_reads(c('dt <- read.csv("raw_data_NHANES_III.csv", colClasses=c(SEQN="character"))',
                        'name_z <- read.csv("raw_codebook.csv")'), "NHANESIII")
stopifnot(inherits(tryCatch(check_public_raw_reads(c('dt <- read.csv("raw_data_NHANES_III.csv")',
                    'name_z <- read.csv("raw_codebook.csv")'), "NHANESIII"),error=identity), "error"))
periods <- c("2017-2018", "2017-2020")
frame <- data.frame(SEQN=c("1.0", "1.0"), YEAR=periods)
validate_nhanes_render_inputs(list(frame), periods)
reject <- function(expr) stopifnot(inherits(tryCatch({force(expr); NULL}, error=identity), "error"))
reject(validate_nhanes_render_inputs(list(transform(frame, SEQN=c("1", "1.0"), YEAR="2017-2018")), periods))
reject(validate_nhanes_render_inputs(list(transform(frame, SEQN=c(1, 2))), periods))
reject(validate_nhanes_render_inputs(list(frame), "2017-2018"))
frame$value <- c(1,NA)
facts <- build_summary_facts(frame,data.frame(Variable="value",original_vars="source",Label="value"),
  c(value="value"),c(value="demo"),c(value=TRUE),period_col="YEAR",expected_periods=periods)
stopifnot(facts$period=="2017-2018",facts$coverage_period_count==1)
stopifnot(summary_period_text(periods,"",periods)=="全周期")
stopifnot(summary_period_text(periods,"")=="2017-2018、2017-2020")
check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(SEQN="character", YEAR="character"))',
                        'name_z <- read.csv("raw_codebook.csv")'), "NHANES")
reject(check_public_raw_reads(c('dt <- read.csv("raw_data.csv")',
                               'name_z <- read.csv("raw_codebook.csv")'), "NHANES"))
repeated_reads <- c('dt <- read.csv("raw_data.csv", colClasses=c(SEQN="character", YEAR="character"))',
 'name_z <- read.csv("raw_codebook.csv")',
 'activities <- read.csv("raw_data_PAQIAF.csv", colClasses=c(SEQN="character", YEAR="character", DOC_FILE="character"))',
 'prescriptions <- read.csv("raw_data_RXQ_RX.csv", colClasses=c(SEQN="character", YEAR="character"))')
check_public_raw_reads(repeated_reads, "NHANES")
check_public_raw_reads(sub(', YEAR="character", DOC_FILE=', ', DOC_FILE=', repeated_reads, fixed=TRUE), "NHANES")
reject(check_public_raw_reads(sub('YEAR="character"', 'YEAR="numeric"', repeated_reads, fixed=TRUE), "NHANES"))
reject(check_public_raw_reads(sub('raw_data_PAQIAF.csv', 'raw_data_RXQ_DRUG.csv', repeated_reads, fixed=TRUE), "NHANES"))
medicine_reads <- c(repeated_reads[1:2], 'drug <- read.csv("raw_drug.csv", colClasses=c(SEQN="character"))')
check_public_raw_reads(medicine_reads,"NHANES")
reject(check_public_raw_reads(sub(', colClasses=c(SEQN="character")', '', medicine_reads, fixed=TRUE),"NHANES"))
cat("NHANES render identities and read contract PASS; full bundle not tested by this fixture\n")
