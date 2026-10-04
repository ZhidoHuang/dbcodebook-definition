"""Exercise summary-only display, HRS identity reads and histogram defaults."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors, validate_note
q = '''## 原始问卷

### 2011

#### 问卷设计

题意概括：询问受访者日常活动是否存在困难。

未取得完整原题的原因：测试材料只提供题意说明，未包含完整题干和选项。
'''
parsed = read_questionnaire_copy(q)
assert not parsed['2011']['questions']
for marker in ['题意概括：','未取得完整原题的原因：']:
    try: read_questionnaire_copy(q.replace(marker,''))
    except ValueError: pass
    else: raise AssertionError('Unlabelled summary accepted')
# A summary does not satisfy a registered original question.
assert questionnaire_copy_errors({'questionnaire':parsed},{'schema_version':6,'questionnaire_evidence':[
    {'question_id':'Q1','periods':['2011'],'question_text':'完整原题','response_type':'open'}]})
doc='''## 摘要导读

本主题定义“**活动困难**”。

'''+q+'''
## Criteria

### result

#### 定义

是否存在活动困难。

#### 定义逻辑

根据已确定方案赋值。

#### 分类

- [0]：没有困难。
- [1]：有困难。

## 小book提示

本主题没有需要单独提示的主题级边界
'''
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    (folder/'文案.md').write_text(doc,encoding='utf-8')
    (folder/'raw_data.csv').write_text('HHID,PN,year,value\n000123,001,2011,7\n000004,020,2012,8\n',encoding='utf-8')
    (folder/'run.R').write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root,"scripts/check_public_raw_reads.R"),encoding="UTF-8")
reader <- 'dt <- read.csv("raw_data.csv", colClasses=c(HHID="character", PN="character"))'
check_public_raw_reads(c(reader,'name_z <- read.csv("raw_codebook.csv")'))
eval(parse(text=reader))
stopifnot(identical(dt$HHID,c("000123","000004")),identical(dt$PN,c("001","020")),is.integer(dt$year),is.integer(dt$value))
for (bad in c('HHID="numeric"','PN="numeric"','year="character"','value="character"')) {
  code <- paste0('dt <- read.csv("raw_data.csv", colClasses=c(',bad,'))')
  stopifnot(inherits(try(check_public_raw_reads(c(code,'name_z <- read.csv("raw_codebook.csv")')),silent=TRUE),'try-error'))
}
source(file.path(root,"scripts/summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts/render_definition_bundle.R"),encoding="UTF-8")
copy <- read_definition_copy("result")
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry,"#A33842"),
 criteria=copy$criteria, criteria_intro="", insight="",references="",
 questionnaire=render_summary_selection_paragraph(copy$summary_selection,"#A33842"))
definition_copy_check(source=actual)
row <- paste0('<tr><td>result</td><td>',copy$criteria$result,'</td><td>distribution</td></tr>')
note <- compose_definition_note_lines(c("## 摘要导读",actual$summary,actual$questionnaire),character(),
 c('<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',row,'</table>'),character(),"extract","print(1)",character())
writeLines(note,"note.md",useBytes=TRUE)
definition_copy_check(note="note.md")
suppressPackageStartupMessages(library(dbCodeBookr))
default_width <- formals(render_definition_bundle)$hist_binwidth
stopifnot(is.null(default_width))
x <- data.frame(value=seq(0,100,by=0.1))
render <- function(width) generate_var_details(x,show_hist=TRUE,hist_binwidth=width)[[1]]
count <- function(html) length(regmatches(html,gregexpr("class='hist-bar'",html,fixed=TRUE))[[1]])
auto <- count(render(default_width)); fixed <- count(render(1)); named <- count(render(c(value=1)))
stopifnot(auto > 0, fixed > 0, auto != fixed, fixed == named)
cat("HISTOGRAM_BARS",auto,fixed,named,"\\n")
''',encoding='utf-8')
    env={**os.environ,'PYTHONUTF8':'1','DBCODEBOOK_DEFINITION_PYTHON':sys.executable,'DBCODEBOOK_DEFINITION_SKILL_ROOT':str(ROOT)}
    for key in ('LC_ALL','LC_CTYPE','LANG'): env.pop(key,None)
    run=subprocess.run([os.environ['RSCRIPT'],'--vanilla','--encoding=UTF-8',str(folder/'run.R')],cwd=folder,env=env,capture_output=True,text=True,encoding='utf-8')
    assert run.returncode==0,run.stdout+run.stderr
    assert validate_note(folder/'文案.md',folder/'note.md')['ok']
    rendered=(folder/'note.md').read_text(encoding='utf-8')
    assert '题意概括' in rendered and '未取得完整原题的原因' in rendered
    assert 'data-summary-question="true"' not in rendered
    print(run.stdout)
print('GENERATION_BOUNDARIES_PASS: summary retained, real-question evidence not bypassed, leading zeros retained, auto/fixed histogram differ')
