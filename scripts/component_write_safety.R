args<-commandArgs(TRUE)
expr<-parse(args[[1]],encoding='UTF-8')
allowed<-c('-', '!', '!=', '$', '%>%', '%in%', '&', '[', '[[', '{', '|', '~', '+', '*', ':', '<-', '==', '>', '>=', 'add_mapping', 'all', 'anyDuplicated', 'anyNA', 'as.character', 'as.integer', 'as.numeric', 'bind_rows', 'c', 'case_when', 'character', 'data.frame', 'factor', 'file.exists', 'file.path', 'floor', 'for', 'function', 'get', 'if', 'ifelse', 'install.packages', 'install_github', 'is.na', 'lapply', 'length', 'library', 'list', 'logical', 'ls', 'match', 'names', 'nrow', 'nzchar', 'paste', 'path.expand', 'print', 'rbind', 'read.csv', 'read_definition_copy', 'render_definition_bundle', 'rep', 'requireNamespace', 'rm', 'sapply', 'select', 'seq_len', 'setdiff', 'setequal', 'setNames', 'stop', 'stopifnot', 'str', 'strsplit', 'sum', 'summary', 'Sys.getenv', 'table', 'trimws', 'unique', 'unlist', 'unname', 'vapply', 'write.xlsx', 'do.call', 'duplicated', 'identical')
allowed<-unique(c(allowed,'(',')','<','<=','/','%%','%/%','&&','||','any','is.character','suppressWarnings','if_else','sprintf','paste0','arrange','group_by','mutate','ungroup','coalesce','cumall','cumany','first','yyds_coalesce','all_of','class','isTRUE','left_join','next','order','subset','new.env','emptyenv','exists','assign','writeLines'))
allowed<-unique(c(allowed,'rowSums','is.numeric','cbind','is.nan','is.infinite','sub','grepl','^','return','ncol','log','filter','na.omit','summarise','sort','apply','tapply','mapply'))
allowed<-unique(c(allowed,'mean','integer','sqrt','max','min','matrix','which','seq_along','log10','n','as.matrix','substr','rowMeans','pmin','pmax','replace','as.data.frame','gsub','head','tail','complete.cases','startsWith','endsWith','abs','bind_cols','lag','lead','all.equal','cummax','cummin','median','sd','var','round','ceiling','is.finite','nchar','tolower','toupper','unique','is.null','is.integer','as.logical','anyDuplicated','str_detect','str_replace','str_extract','between','dense_rank'))
allowed<-unique(c(allowed,'split','quantile','break','exp','plogis','switch','summary_count_part','summary_search_part','summary_path_part','summary_concept_part','summary_question_part','summary_strong_part','criteria_block','criteria_item','criteria_heading','criteria_context','cat','capture.output'))
allowed<-unique(c(allowed,'vector','aggregate','ave','lengths','rename','dirname'))
expected_writes<-strsplit(args[[2]],'|',fixed=TRUE)[[1]]
valid_file<-function(x) is.character(x)&&length(x)==1&&!grepl('[/\\\\]',x)&&!grepl('(^|[.])[.][.]',x)&&!grepl('^[A-Za-z]:',x)&&nzchar(x)
helper_expected<-quote(file.path(skill_root,"scripts",c("summary_fact_helpers.R","render_definition_bundle.R")))
helper_seen<-0L;writes<-character();libraries<-character();local_functions<-character()
collect<-function(e){
 if(is.expression(e)){for(v in e)collect(v);return()}
 if(is.pairlist(e)){z<-as.list(e);for(i in seq_along(z))if(!identical(z[[i]],quote(expr=)))collect(z[[i]]);return()}
 if(!is.call(e))return()
 if(identical(e[[1]],as.name('<-'))&&length(e)==3&&is.symbol(e[[2]])&&is.call(e[[3]])&&identical(e[[3]][[1]],as.name('function')))local_functions<<-c(local_functions,as.character(e[[2]]))
 z<-as.list(e);for(i in seq_along(z)[-1])if(!identical(z[[i]],quote(expr=)))collect(z[[i]])
}
collect(expr)
if(anyDuplicated(local_functions)||any(local_functions%in%setdiff(allowed,'add_mapping')))stop('duplicate or shadowing function declaration')
walk<-function(e,in_function=FALSE){
 if(is.character(e)) {if(any(grepl('(^|[/\\\\])[.][.]($|[/\\\\])|^[A-Za-z]:|^[/\\\\]|^~[/\\\\]',e)))stop('unsafe path literal');return()}
 if(is.expression(e)) {for(i in seq_along(e))walk(e[[i]],in_function);return()}
 if(is.pairlist(e)) {z<-as.list(e);for(i in seq_along(z))if(!identical(z[[i]],quote(expr=)))walk(z[[i]],in_function);return()}
 if(!is.call(e))return()
 head<-e[[1]]
 if(is.call(head)&&identical(head,quote(openxlsx::write.xlsx)))name<-'write.xlsx'
 else if(is.symbol(head))name<-as.character(head)
 else stop('indirect or namespaced call not supported')
 if(name=='%>%') {
  right<-e[[3]]
  safe_pipe<-c('select','left_join','bind_rows','arrange','group_by','mutate','ungroup','as.numeric','as.character','filter','summarise','as.data.frame','na.omit','rename',local_functions)
  direct_call<-is.call(right)&&is.symbol(right[[1]])&&as.character(right[[1]])%in%safe_pipe
  direct_symbol<-is.symbol(right)&&as.character(right)%in%c('as.numeric','as.character')
  if(!direct_call&&!direct_symbol)stop(paste('unsupported pipe target',paste(deparse(right),collapse=' ')))
 }
 if(name=='for'&&is.symbol(e[[2]])&&as.character(e[[2]])%in%c('helper_files','skill_root','last_hukou_by_id',allowed,local_functions))stop('protected loop binding')
 if(name=='function'&&any(names(as.list(e[[2]]))%in%c('helper_files','skill_root','last_hukou_by_id',allowed,local_functions)))stop('protected function parameter')
 if(in_function && name%in%c('eval','get','assign','exists','new.env','emptyenv','file.exists','file.path','path.expand','Sys.getenv','read.csv','write.xlsx','writeLines','render_definition_bundle','read_definition_copy','library','install.packages','install_github','requireNamespace','rm','yyds_coalesce'))stop('side effect or dynamic operation in function body')
 # 仅允许既有、由 runner 预检所有对应 library 的包准备模式。
 # 不允许脚本中其他安装路径，即使安装代码处于条件分支。
 if(name=='for' && identical(e,quote(for (pkg in c("devtools", "openxlsx", "dplyr")) { if (!requireNamespace(pkg, quietly = TRUE)) install.packages(pkg) }))) return()
 if(name=='for' && identical(e,quote(for (pkg in c("devtools", "openxlsx", "dplyr")) { if (!requireNamespace(pkg, quietly = TRUE)) { install.packages(pkg) } }))) return()
 if(name=='install_github' && identical(e,quote(install_github("ZhidoHuang/dbCodeBookr")))) return()
 if(name%in%c('install.packages','install_github'))stop('unsupported installation call')
 if(name=='eval') {
  x<-e[[2]]
  if(length(e)!=2||!is.call(x)||!identical(x[[1]],as.name('parse')))stop('unsupported eval')
  y<-as.list(x);f<-y[['file']];enc<-y[['encoding']]
  if(is.null(f)||!is.call(f)||!identical(f[[1]],as.name('['))||length(f)!=3||!identical(f[[2]],as.name('helper_files'))||!(identical(f[[3]],1)||identical(f[[3]],2))||!identical(enc,'UTF-8')||length(y)!=3)stop('unverified helper source')
  return()
 }
 if(!(name%in%c(allowed,local_functions)))stop(paste('unsupported call',name))
 if(name%in%c('get','assign','exists')) {
  z<-as.list(e);env<-z[['envir']]
  answer<-name=='get'&&length(e)==2&&identical(e[[2]],as.name('answer'))
  local<-identical(env,as.name('last_hukou_by_id'))&&!(name%in%c('get','exists')&&!identical(z[['inherits']],FALSE))
  if(!answer&&!local)stop('unsupported dynamic environment access')
 }
 if(name=='new.env'&&!identical(e,quote(new.env(parent=emptyenv(),hash=TRUE))))stop('unsupported environment')
 if(name=='emptyenv'&&length(e)!=1)stop('unsupported environment')
 if(name%in%c('lapply','sapply','vapply','apply','tapply','mapply','aggregate','ave')) {
  z<-as.list(e);fun<-z[['FUN']];pos<-if(name=='mapply')2 else if(name%in%c('apply','tapply','aggregate'))4 else if(name=='ave')Inf else 3
  if(is.null(fun)&&length(z)>=pos)fun<-z[[pos]]
  if(name=='ave'&&is.null(fun))fun<-as.name('mean')
  pure_callback<-c('as.character','as.numeric','is.na','is.character','is.numeric','identity','sum','table','summary','nrow','ncol','rowSums','rowMeans','sort','na.omit','mean','min','max','sd','median','length','any','all','unique','str')
  if(!(is.call(fun)&&identical(fun[[1]],as.name('function')))&&!(is.symbol(fun)&&as.character(fun)%in%c(local_functions,pure_callback)))stop(paste('unsupported callback',paste(deparse(fun),collapse=' ')))
 }
 if(name=='do.call' && !(length(e)==3&&identical(e[[2]],as.name('rbind'))))stop('unsupported indirect call')
 if(name=='cat') {z<-as.list(e);file<-z[['file']];if(!is.null(file)&&!identical(file,''))stop('cat file output not supported')}
 if(name=='capture.output') {z<-as.list(e);file<-z[['file']];if(!is.null(file)&&!identical(file,quote(NULL)))stop('capture file output not supported')}
 if(name=='library') {
  if(length(e)!=2||!is.character(e[[2]])||length(e[[2]])!=1L||!(e[[2]]%in%c('devtools','openxlsx','dplyr','dbCodeBookr')))stop('unsupported library')
  libraries<<-c(libraries,e[[2]])
 }
 if(name=='<-') {
  lhs<-e[[2]]
  root_symbol<-function(x){if(is.symbol(x))return(as.character(x));if(is.call(x)&&length(x)>1)return(root_symbol(x[[2]]));''}
  if(!is.symbol(lhs)&&root_symbol(lhs)%in%c('helper_files','skill_root','last_hukou_by_id'))stop('protected binding mutation')
  if(is.symbol(lhs)&&as.character(lhs)%in%setdiff(allowed,'add_mapping'))stop('overriding callable not supported')
  if(is.symbol(lhs)&&as.character(lhs)%in%local_functions&&!(is.call(e[[3]])&&identical(e[[3]][[1]],as.name('function'))))stop('function reassignment not supported')
  if(is.symbol(lhs)&&identical(lhs,as.name('last_hukou_by_id'))&&!identical(e[[3]],quote(new.env(parent=emptyenv(),hash=TRUE))))stop('unverified local environment')
  if(is.symbol(lhs)&&identical(lhs,as.name('helper_files'))) {if(!identical(e[[3]],helper_expected))stop('helper loader differs');helper_seen<<-helper_seen+1L}
  if(is.symbol(lhs)&&identical(lhs,as.name('skill_root'))) {
   v<-e[[3]];safe<-identical(v,quote(Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")))||identical(v,quote(file.path(codex_home,"skills","dbcodebook-definition")))
   if(!safe)stop('unverified skill root')
  }
 }
 if(name=='write.xlsx') {
  z<-as.list(e);file<-z[['file']];if(is.null(file)&&length(z)>=3)file<-z[[3]]
  if(!valid_file(file)||!(file%in%expected_writes))stop('write target not an approved local file')
  writes<<-c(writes,file)
 }
 if(name=='read.csv') {
  z<-as.list(e);file<-z[['file']];if(is.null(file)&&length(z)>=2)file<-z[[2]]
  if(!valid_file(file)||!grepl('^raw.*[.]csv$',file))stop('unsupported read target')
 }
 if(name=='read_definition_copy' && !(length(e)==2&&identical(e[[2]],as.name('analysis_vars'))))stop('unsupported copy input')
 if(name=='file.exists' && !(length(e)==2&&identical(e[[2]],as.name('helper_files'))))stop('unsupported file existence check')
 if(name=='writeLines') {
  z<-as.list(e);file<-z[['con']];if(is.null(file)&&length(z)>=3)file<-z[[3]]
  if(!valid_file(file)||!grepl('_QA[.]txt$',file)||!file.exists(file.path(dirname(args[[1]]),file)))stop('unsupported QA output')
 }
 if(name=='render_definition_bundle') {
  z<-as.list(e)
  for(k in c('file_stem','note_name','script_file'))if(!valid_file(z[[k]]))stop(paste('unsupported renderer path',k))
 }
 z<-as.list(e);for(i in seq_along(z)[-1])if(!identical(z[[i]],quote(expr=)))walk(z[[i]],in_function||name=='function')
}
walk(expr)
if(helper_seen!=1L || !setequal(writes,expected_writes) || length(writes)!=length(expected_writes))stop('incomplete helper or writes')
if(!setequal(libraries,c('devtools','openxlsx','dplyr','dbCodeBookr')))stop('incomplete preflight package list')
cat('COMPONENT_WRITE_SAFETY_PASS\n')
