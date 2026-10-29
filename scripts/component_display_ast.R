args<-commandArgs(TRUE)
if(identical(readBin(args[[1]],'raw',n=file.info(args[[1]])$size),readBin(args[[2]],'raw',n=file.info(args[[2]])$size))) {cat('AST_UNCHANGED_PASS\n');quit(status=0)}
a<-parse(args[[1]],encoding='UTF-8');b<-parse(args[[2]],encoding='UTF-8')
if(length(a)!=length(b)) stop('expression count changed')
changed<-0L
unparen<-function(x) if(is.call(x)&&identical(x[[1]],as.name('('))) unparen(x[[2]]) else x
literal_vec<-function(x){
 x<-unparen(x)
 if(!is.call(x)||!identical(x[[1]],as.name('c'))) stop('labels must use literal c()')
 parts<-as.list(x)[-1]; if(!length(parts)||any(!vapply(parts,function(z)is.character(z)&&length(z)==1L&&!is.na(z)&&nzchar(trimws(z)),logical(1))))stop('nonliteral or empty label')
 unlist(parts,use.names=FALSE)
}
for(i in seq_along(a)) {
 u<-a[[i]];v<-b[[i]];if(identical(u,v)) next
 if(!is.call(u)||!is.call(v)||!identical(u[[1]],as.name('render_definition_bundle'))||!identical(v[[1]],u[[1]]))stop('change outside renderer')
 ul<-as.list(u);vl<-as.list(v); uc<-ul[['component_groups']];vc<-vl[['component_groups']]
 old_labels<-ul[['component_card_labels']];new_labels<-vl[['component_card_labels']]
 ul[['component_groups']]<-NULL;vl[['component_groups']]<-NULL
 ul[['component_card_labels']]<-NULL;vl[['component_card_labels']]<-NULL
 if(!identical(as.call(ul),as.call(vl)))stop('renderer argument other than grouping or card labels changed')
 if(!identical(uc,vc)) {
  if(is.null(vc))stop('component group missing')
  vc<-unparen(vc)
  if(!is.call(vc)||!identical(vc[[1]],as.name('['))||length(vc)!=3||!identical(vc[[3]],as.name('analysis_vars')))stop('new group is not filtered by analysis_vars')
  base<-unparen(vc[[2]])
  if(is.null(uc)) {if(is.null(ul[['summary_groups']])||!identical(base,unparen(ul[['summary_groups']])))stop('new group does not derive from existing summary groups')}
  else if(!identical(base,unparen(uc)))stop('changed existing groups instead of filtering')
 }
 if(!identical(old_labels,new_labels)) {
  if(!is.null(old_labels)||is.null(new_labels)||length(args)<3)stop('unsupported label change')
  x<-unparen(new_labels)
  if(!is.call(x)||!identical(x[[1]],as.name('setNames'))||length(x)!=3||!is.null(names(as.list(x))))stop('labels must be setNames of two literal vectors')
  values<-literal_vec(x[[2]]);keys<-literal_vec(x[[3]])
  if(length(values)!=length(keys)||anyDuplicated(keys))stop('invalid card label keys')
  jsonlite::write_json(as.list(setNames(values,keys)),args[[3]],auto_unbox=TRUE,pretty=TRUE)
 }
 changed<-changed+1L
}
if(changed!=1L)stop('expected exactly one renderer change')
cat('AST_GROUP_CHANGE_PASS\n')
