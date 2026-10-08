"""Offline synthetic evidence, long-table, dictionary and empty-result branches.

No website, production topic or real questionnaire is used.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_definition_source_record as source
import check_definition_readability as delivery
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors
from check_definition_output import check_long_table, check_workbook_contract


def rejects(fn, message=''):
    try:
        fn()
    except (ValueError, SystemExit) as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('Expected rejection: ' + message)


with tempfile.TemporaryDirectory(prefix='definition_branch_contracts_') as tmp:
    folder = Path(tmp)
    materials = folder / 'materials'; materials.mkdir()
    (materials / 'official-fixture.txt').write_text(
        'Synthetic official guide: adults; previous week; Yes=1, No=0; no skip. Full wording unavailable.',
        encoding='utf-8')
    source.LOCAL_EVIDENCE_ROOTS['CHARLS'] = materials
    item = dict(evidence_id='Q001', source_group='测试概念', periods=['2011'], question_id='',
                question_text_mode='plain_paraphrase', question_text_complete=False,
                question_text='询问成年人过去一周是否存在活动困难。',
                paraphrase_reason='测试指南说明了对象、回顾期和选项，但未刊载完整原题。',
                applicable_population='成年人', recall_period='过去一周',
                response_type='closed_options', options=[{'value':'1','label':'是'}, {'value':'0','label':'否'}],
                options_complete=True, skip_logic_status='none', skip_logic=[],
                local_material_status='verified', local_material_path='official-fixture.txt', locator='fixture section',
                missing_reason='', supplemental_official_url='', evidence_steps=[1],
                rendered_in_copy=True, copy_locator='文案.md > 测试题组 > 2011 > 问卷设计')
    record = {'schema_version':7, 'database':'CHARLS', 'questionnaire_evidence':[item],
              'questionnaire_coverage':[{'source_group':'测试概念','period':'2011','status':'questionnaire',
                                         'evidence_ids':['Q001'],'reason':'已核实定义所需事实，原题措辞不可得'}]}
    log = [{'step':1,'action':'official_material_review'}]
    periods = {'测试概念':{'2011'}}
    assert source.validate_questionnaire_evidence(record, log, periods, True)['questions'] == 1
    for field, value, error in [('question_text_complete', True, 'question_text_complete=false'),
                                ('applicable_population', '', 'applicable_population'),
                                ('recall_period', '', 'recall_period'),
                                ('options_complete', False, 'options_complete'),
                                ('options', [], 'all options'),
                                ('skip_logic_status', 'unknown', 'skip_logic_status')]:
        bad = deepcopy(record); bad['questionnaire_evidence'][0][field] = value
        rejects(lambda: source.validate_questionnaire_evidence(bad, log, periods), error)
    bad = deepcopy(record); bad['questionnaire_evidence'][0].pop('question_text_mode')
    rejects(lambda: source.validate_questionnaire_evidence(bad, log, periods), 'question_id')
    questionnaire = f'''## 原始问卷

### 测试题组

#### 2011

##### 问卷设计

题意概括：{item['question_text']}

未取得完整原题的原因：{item['paraphrase_reason']}
'''
    parsed = read_questionnaire_copy(questionnaire)
    assert questionnaire_copy_errors({'questionnaire':parsed}, record) == []
    bad = deepcopy(record); bad['questionnaire_evidence'][0]['paraphrase_reason'] = '另一种未核实原因。'
    assert questionnaire_copy_errors({'questionnaire':parsed}, bad)
    bad = deepcopy(record); bad['questionnaire_evidence'][0]['periods'] = ['2013']
    assert questionnaire_copy_errors({'questionnaire':parsed}, bad)
    extended = read_questionnaire_copy(questionnaire.replace('#### 2011', '#### 2011–2013'))
    assert questionnaire_copy_errors({'questionnaire':extended}, record)
    supported = deepcopy(record)
    supported['questionnaire_evidence'][0]['periods'] = ['2011','2012','2013']
    assert questionnaire_copy_errors({'questionnaire':extended}, supported) == []

    # All seven supported database key shapes; wide rows and duplicate person-periods fail.
    for db, keys in {'charls':['id','year'], 'elsa':['idauniq','Wave'], 'hrs':['HHID','PN','year'],
                     'share':['mergeid','Wave_id'], 'klosa':['Harmonized_id','Wave_id'],
                     'chns':['IDind','WAVE'], 'knhanes':['id','year']}.items():
        header = keys + ['result']; row = ['001'] * (len(keys)-1) + ['2011', None]
        results=[]; assert check_long_table([header,row],header,results,db)
        results=[]; assert not check_long_table([header,row,row],header,results,db)
        results=[]; assert not check_long_table([['result'],[None]],['result'],results,db)

    (folder / 'definition_search_record.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    prose = '''# CHARLS — 测试结果（Test）

## 摘要导读

本主题定义“**合计分数**”，共 **1** 个变量。

''' + questionnaire + '''
## Criteria

### defined_value

#### 定义

两个来源数值的合计分数。

#### 定义逻辑

`defined_value = source_a + source_b`；两项均有效时计算。

#### 分类

- [数值]：分。

#### 注意点

本次没有两项均有效的记录，合计分数全部缺失。

## 小book提示

本主题没有需要单独提示的主题级边界
'''
    (folder / '文案.md').write_text(prose, encoding='utf-8')
    r = r'''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
suppressPackageStartupMessages(library(dplyr))
suppressPackageStartupMessages(library(openxlsx))
source(file.path(root,"scripts/summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts/render_definition_bundle.R"),encoding="UTF-8")
source(file.path(root,"scripts/check_public_raw_reads.R"),encoding="UTF-8")
years <- c(2011L,2013L,2015L,2018L,2020L)
data <- data.frame(ID=paste0("001_",years),id="001",year=years,
                   source_a=1:5,source_b=NA_real_,defined_value=NA_real_)
name_z <- data.frame(Variable=c("source_a", "source_b"), newname=c("source_a", "source_b"),
                    Easy.label=c("来源 A", "来源 B"),Module="fixture")
template <- readLines(file.path(root,"templates/public-r-dictionary.R"), encoding="UTF-8")
template <- sub("Defined value", "合计分数", template, fixed=TRUE)
eval(parse(text=template))
stopifnot(is.data.frame(codebook), identical(codebook$Variable,names(db_data)),
          identical(analysis_codebook$Variable,analysis_vars),nrow(db_data)==nrow(analysis_data))
codebook$category <- factor(ifelse(codebook$Variable %in% analysis_vars,"结果","来源"),levels=c("来源","结果"))
facts <- build_summary_facts(analysis_data,analysis_codebook,c(defined_value="合计分数"),
  c(defined_value="测试结果"),c(defined_value=TRUE),period_col="year",expected_periods=years)
stopifnot(facts$coverage_period_count==0, facts$object=="无有效值",
          facts$min_coverage==0, facts$max_coverage==0)
copy <- read_definition_copy(analysis_vars)
render_definition_bundle(data=data,db_data=db_data,codebook=codebook,analysis_data=analysis_data,
  analysis_codebook=analysis_codebook,analysis_vars=analysis_vars,raw_vars=raw_vars,raw_codebook=name_z,
  criteria=copy$criteria,criteria_intro=copy$criteria_intro,
  summary_meanings=c(defined_value="合计分数"),summary_groups=c(defined_value="测试结果"),
  summary_entry=copy$summary_entry,summary_selection=copy$summary_selection,
  summary_insight_items=copy$summary_insight_items,reference_lines=copy$reference_lines,
  summary_source=NULL,file_stem="fixture",note_name="note.md",qa_title="Offline fixture",
  transaction_id="offline-fixture",script_file="fixture.R",database="CHARLS")
# CHNS optional main-table identity strings are preserved; business columns remain forbidden.
writeLines(c("ID,IDind,WAVE,hhid,age", "opaque,001,1989,0002,30"),"identities.csv")
reader <- c('dt <- read.csv("raw_data.csv", colClasses=c(ID="character",IDind="character",hhid="character"))',
            'name_z <- read.csv("raw_codebook.csv")')
check_public_raw_reads(reader,"CHNS")
write.csv(name_z,"raw_codebook.csv",row.names=FALSE)
file.copy("identities.csv","raw_data.csv",overwrite=TRUE)
eval(parse(text=reader[1]))
stopifnot(identical(dt$hhid,"0002"),is.integer(dt$age))
bad <- sub('hhid="character"','age="character"',reader,fixed=TRUE)
stopifnot(inherits(try(check_public_raw_reads(bad,"CHNS"),silent=TRUE),"try-error"))
cat("OFFLINE_DICTIONARY_AND_ALL_NA_NOTE_PASS\n")
'''
    (folder/'fixture.R').write_text(r,encoding='utf-8')
    env={**os.environ,'PYTHONUTF8':'1','DBCODEBOOK_DEFINITION_PYTHON':sys.executable,
         'DBCODEBOOK_DEFINITION_SKILL_ROOT':str(ROOT)}
    for key in ('LC_ALL','LC_CTYPE','LANG'): env.pop(key,None)
    executable=env.get('RSCRIPT')
    if not executable:
        raise RuntimeError('RSCRIPT must be configured for execution branch tests')
    run=subprocess.run([executable,'--vanilla','--encoding=UTF-8',str(folder/'fixture.R')],
                       cwd=folder,env=env,capture_output=True,text=True,encoding='utf-8')
    assert run.returncode==0,run.stdout+run.stderr
    assert delivery.validate_questionnaire_rendering(folder,folder,'note.md')['rendered_question_periods']==1
    contents=(folder/'note.md').read_text(encoding='utf-8')
    (folder/'note.md').write_text(contents.replace(item['paraphrase_reason'],'错误的原因。'),encoding='utf-8')
    rejects(lambda: delivery.validate_questionnaire_rendering(folder,folder,'note.md'),'verified paraphrase')
    files=['db_topic.xlsx','codebook_topic.xlsx','analysis_db_topic.xlsx','analysis_codebook_topic.xlsx']
    checks=[]
    check_workbook_contract(folder,files,files[2],files[3],['source_a','source_b'],['defined_value'],checks)
    assert checks[-1]['ok'],checks
    checks=[]
    check_workbook_contract(folder,files,files[2],files[3],['source_a'],['defined_value'],checks)
    assert not checks[-1]['ok'],checks

print('EXECUTION_BRANCH_CONTRACTS_PASS: evidence/copy/note, all-NA generation, four actual workbooks, seven key shapes, CHNS identity types')
