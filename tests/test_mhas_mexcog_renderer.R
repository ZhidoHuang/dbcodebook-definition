args <- commandArgs(trailingOnly=FALSE)
root <- dirname(dirname(normalizePath(sub("^--file=", "", grep("^--file=", args, value=TRUE)[[1]]))))
eval(parse(file=file.path(root,"scripts/render_definition_bundle.R"),encoding="UTF-8"))
eval(parse(file=file.path(root,"scripts/check_public_raw_reads.R"),encoding="UTF-8"))
bad <- function(expr) stopifnot(inherits(tryCatch({force(expr);NULL},error=function(e)e),"error"))
readers <- c(
 'mc <- read.csv("raw_data_MHAS_MEXCOG_COGNITIVE_ASSESSMENT.csv", colClasses=c(ID="character",Wave_id="character",cunicah="character",np="character",CUNICAH="character",NP="character"))',
 'mi <- read.csv("raw_data_MHAS_MEXCOG_INFORMANT_INTERVIEW.csv", colClasses=c(ID="character",Wave_id="character",CUNICAH="character",NP="character"))',
 'core <- read.csv("raw_data_MHAS_SURVEY_CORE_RESPONDENT.csv", colClasses=c(ID="character",Wave_id="character"))',
 'nok <- read.csv("raw_data_MHAS_SURVEY_NEXT_OF_KIN.csv", colClasses=c(ID="character",Wave_id="character"))',
 'name_z <- read.csv("raw_codebook.csv")')
check_public_raw_reads(readers,"MHAS")
check_public_raw_reads(readers[c(2,5)],"MHAS")
bad(check_public_raw_reads(c(readers,'hair <- read.csv("raw_data_MHAS_ANCILLARY_HEAVY_METALS.csv", colClasses=c(ID="character",Wave_id="character"))'),"MHAS"))
bad(check_public_raw_reads(sub('ID="character",','',readers,fixed=TRUE),"MHAS"))
modules <- c("MHAS_SURVEY_CORE_RESPONDENT","MHAS_SURVEY_NEXT_OF_KIN","MHAS_MEXCOG_COGNITIVE_ASSESSMENT","MHAS_MEXCOG_INFORMANT_INTERVIEW")
x <- data.frame(source_module=modules,ID=rep("2021|001|02",4),Wave_id=rep("2021",4))
vars <- c("core_result","nok_result","mc_result","mi_result")
for (i in seq_along(vars)) x[[vars[i]]] <- ifelse(seq_len(4)==i,1,NA)
scopes <- setNames(lapply(vars,function(v) list(analysis_periods="2021",result_variables=v)),modules)
validate_mhas_render_inputs(list(x),"2021")
validate_mhas_analysis_scope(list(x),scopes,vars)
validate_person_period_outputs(list(x),"MHAS")
y<-x;y$mi_result[1]<-1;bad(validate_mhas_analysis_scope(list(y),scopes,vars))
y<-x;y$Wave_id[3]<-"2024";y$ID[3]<-"2024|001|02";bad(validate_mhas_render_inputs(list(y),c("2021","2024")))
wrong<-scopes;wrong[[3]]$analysis_periods<-"2024";bad(validate_mhas_analysis_scope(list(x),wrong,vars))
bad(validate_mhas_render_inputs(list(rbind(x,x[4,])),"2021"))
cat("MHAS Mex-Cog direct reads, source partitions and supported periods PASS\n")
