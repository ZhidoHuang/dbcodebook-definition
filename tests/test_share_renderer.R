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
expect(call_renderer(frame,c("Wave 1","Corona Survey 3")),"Invalid SHARE declared period order")
expect(call_renderer(frame,c("Wave 2","Wave 1")),"Invalid SHARE declared period order")
expect(call_renderer(frame,c("Wave 1","Wave 1")),"Invalid SHARE declared period order")
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
definition_copy_check <- function(...) stop("SHARE_IDENTITY_CONTRACT_ACCEPTED")
expect(call_renderer(frame),"SHARE_IDENTITY_CONTRACT_ACCEPTED")
corona <- frame; corona$Wave_id[2] <- "Corona Survey 1"
expect(call_renderer(corona,c("Wave 1","Corona Survey 1","Corona Survey 2")),"SHARE_IDENTITY_CONTRACT_ACCEPTED")
reader <- 'dt <- read.csv("raw_data.csv", colClasses=c(ID="character", Wave_id="character", mergeid="character", hhid="character", country="character"))'
check_public_raw_reads(c(reader,'name_z <- read.csv("raw_codebook.csv")'),database="SHARE")
expect(check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(gender="character"))','name_z <- read.csv("raw_codebook.csv")'),database="SHARE"),"Only declared SHARE identity")
expect(check_public_raw_reads(c('dt <- read.csv("raw_data.csv", colClasses=c(mergeid="numeric"))','name_z <- read.csv("raw_codebook.csv")'),database="SHARE"),"Only declared SHARE identity")
temp <- tempfile("share_identity_read_");dir.create(temp)
writeLines(c('ID,Wave_id,mergeid,hhid,country,value','001,Wave 1,0001,0006,01,7'),file.path(temp,'raw_data.csv'))
old <- getwd();setwd(temp);eval(parse(text=reader));setwd(old)
stopifnot(identical(dt$ID,"001"),identical(dt$mergeid,"0001"),identical(dt$hhid,"0006"),identical(dt$country,"01"),is.integer(dt$value))
writeLines(c('ID,mergeid,intid (PH - Physical health),value','001,0001,0009.0,7'),file.path(temp,'raw_data.csv'))
writeLines(c('Variable,newname','ph006d1 (PH - Physical health),ph006d1'),file.path(temp,'raw_codebook.csv'))
qualified_reader <- c('dt <- read.csv("raw_data.csv", colClasses=c(ID="character",mergeid="character",intid..PH...Physical.health.="character"))', 'name_z <- read.csv("raw_codebook.csv")')
check_public_raw_reads(qualified_reader,"SHARE",temp)
old <- getwd();setwd(temp);eval(parse(text=qualified_reader[[1]]));setwd(old)
stopifnot(identical(dt$intid..PH...Physical.health.,"0009.0"),is.integer(dt$value))
expect(check_public_raw_reads(sub('intid..PH...Physical.health.=', '"intid (PH - Physical health)"=', qualified_reader,fixed=TRUE),"SHARE",temp),"Only declared SHARE identity")
cat("SHARE renderer identity/period fixtures PASS; full note generation untested\n")

# Display periods are independent of the adopted/data-validation periods.
full_cycles <- definition_display_periods("SHARE", "Wave 6")
stopifnot(identical(full_cycles, paste("Wave", c(1, 2, 4:9))))
stopifnot("2016" %in% definition_display_periods("MHAS", "2016"))
stopifnot("2003" %in% definition_display_periods("HRS", "2003"))
stopifnot(length(definition_display_periods("KNHANES", "2021")) == 21L)
grid <- dbCodeBookr::generate_var_details(
  data.frame(year=c("Wave 6","Wave 6"), value=c(1,NA_real_)),
  show_cycle_heatmap=TRUE, cycle_col="year", cycle_order=full_cycles)[[2]]
stopifnot(all(vapply(full_cycles, function(p) grepl(paste0("class='dbcb-var-cycle-label'>",p,"</span>"),grid,fixed=TRUE),logical(1))))
stopifnot(grepl("Wave 6: 1",grid,fixed=TRUE),grepl("Wave 1: 无数据",grid,fixed=TRUE))
cat("SHARE sparse/full display periods and real package cycle cells PASS\n")

# Exercise the current single-mapping API with the real HTML renderer.
# Raw Source variables are not a display role; calculated components remain distinct.
heat <- data.frame(Variable=c("A","B"), category="Defined variables", `2011`=c(2,1), check.names=FALSE)
groups <- c(A="Liver",B="Renal")
prepared <- definition_component_categories(heat,c("A","B"),groups)
meta <- data.frame(Variable=c("A","B"),original_vars=c("raw_a","raw_b"),easylabel=c("甲","乙"),detail="<p>1</p>")
markup <- definition_component_titles(dbCodeBookr::generate_html_definition_long(prepared$data,meta),prepared$groups)
stopifnot(grepl('data-component-group="Liver" data-variable-role="defined">Liver</a>',markup,fixed=TRUE))
stopifnot(grepl('<summary data-component-group="Renal" data-variable-role="defined">Renal</summary>',markup,fixed=TRUE))
stopifnot(!grepl('Source variables',markup,fixed=TRUE))
expect(definition_component_categories(heat,c("A","B"),c(A="Liver")),"every displayed component/result")
component <- rbind(data.frame(Variable="calc_a",category="Components",`2011`=2,check.names=FALSE),heat[1,,drop=FALSE])
prepared <- definition_component_categories(component,"A",c(calc_a="Liver·Components",A="Liver"))
component_meta <- data.frame(Variable=c("calc_a","A"),original_vars=c("raw_a","raw_a"),easylabel=c("成分","结果"),detail="<p>1</p>")
markup <- definition_component_titles(dbCodeBookr::generate_html_definition_long(prepared$data,component_meta),prepared$groups)
stopifnot(grepl('data-component-group="Liver·Components" data-variable-role="component"',markup,fixed=TRUE))
stopifnot(grepl('data-component-group="Liver" data-variable-role="defined"',markup,fixed=TRUE))
stopifnot(!grepl('Source variables',markup,fixed=TRUE))
expect(definition_component_categories(component,"A",c(calc_a="Liver",A="Liver")),"非最终输出的计算成分")
cat("Real category renderer: current single mapping, component/result roles and no raw Source display PASS\n")
