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


def check_charls_full_default_identity_fixture():
    """A validated household default may remain only in the full workbook."""
    from unittest.mock import patch
    import check_definition_output as output
    files = ['db_topic.xlsx','codebook_topic.xlsx','analysis_db_topic.xlsx','analysis_codebook_topic.xlsx']
    header = ['ID','id','year','respondent_id','source_a','source_b','defined_value']
    tables = {
        files[0]: [header, ['x','001','2011','001',1,2,3]],
        files[1]: [['Variable','Label'], *[[n,n] for n in header]],
        files[2]: [['ID','id','year','defined_value'], ['x','001','2011',3]],
        files[3]: [['Variable','Label'], ['defined_value','defined_value']],
    }
    contract = {'files': {'raw_data_household.csv': {
        'file_type':'householdID', 'header':['householdid','year','respondent_id','source_b'],
        'variables':['source_b']}}}
    with tempfile.TemporaryDirectory(prefix='charls_full_identity_') as tmp:
        folder=Path(tmp)
        for name in files: (folder/name).touch()
        def run(values, accepted_contract=None, analysis_vars=None):
            checks=[]
            with patch.object(output,'read_table_rows',side_effect=lambda p:values[p.name]):
                check_workbook_contract(folder,files,files[2],files[3],
                    ['source_a','source_b'],analysis_vars or ['defined_value'],checks,
                    charls_multifile_contract=accepted_contract)
            return checks[-1]
        assert not run(tables)['ok'], 'undeclared full-only identity was accepted'
        assert run(tables,contract)['ok'], 'validated household respondent identity rejected'
        alternate=deepcopy(contract)
        alternate['files']['raw_data_household.csv']['header'][2]='id'
        assert not run(tables,alternate)['ok'], 'respondent identity guessed from a different contract'
        extra=deepcopy(tables)
        extra[files[0]][0].append('helper')
        extra[files[0]][1].append(99)
        extra[files[1]].append(['helper','helper'])
        assert not run(extra,contract)['ok'], 'arbitrary extra full column was accepted'
        assert not run(tables,contract,['respondent_id','defined_value'])['ok'], 'default identity accepted as a definition result'
        altered=deepcopy(tables)
        altered[files[0]][1][-1]=4
        assert not run(altered,contract)['ok'], 'shared result drift was hidden'
        omitted=deepcopy(tables)
        omitted[files[0]][0].pop(3)
        omitted[files[0]][1].pop(3)
        omitted[files[1]]=[row for row in omitted[files[1]] if row[0]!='respondent_id']
        assert run(omitted,contract)['ok'], 'an unused default identity became mandatory'


def check_source_result_label_fixture(full_dictionary=None, analysis_dictionary=None, raw_rows=None, plan=None):
    """Exercise source/result Label roles with one synthetic data row, not production values."""
    import csv
    from unittest.mock import patch
    import check_definition_output as output
    if full_dictionary is None:
        header = ["Variable", "original_vars", "processed_vars", "Label", "count"]
        full_dictionary = [header, ["ID","ID","ID","Identity",1],
                           ["shared","RAW_X","shared","Official source",1],
                           ["defined","RAW_X","shared","Defined result",1]]
        analysis_dictionary = [header, ["shared","RAW_X","shared","Shared result",1],
                               ["defined","RAW_X","shared","Defined result",1]]
        raw_rows = [{"Variable":"RAW_X","newname":"shared","Label":"Official source"}]
        plan = [{"analysis_var":"shared","meaning":"Shared result"},
                {"analysis_var":"defined","meaning":"Defined result"}]
    full_dictionary, analysis_dictionary, raw_rows, plan = map(deepcopy,
        (full_dictionary, analysis_dictionary, raw_rows, plan))
    vi = full_dictionary[0].index("Variable")
    av = analysis_dictionary[0].index("Variable")
    names = [row[vi] for row in full_dictionary[1:]]
    variables = [row[av] for row in analysis_dictionary[1:]]
    identities = [name for name in names if name not in {row["newname"] for row in raw_rows} and name not in variables]
    raw_vars = [row["newname"] for row in raw_rows]
    files = ['db_topic.xlsx','codebook_topic.xlsx','analysis_db_topic.xlsx','analysis_codebook_topic.xlsx']
    values = {name:i for i,name in enumerate(names)}
    tables = {files[0]:[names,[values[name] for name in names]], files[1]:full_dictionary,
              files[2]:[identities+variables,[values[name] for name in identities+variables]],
              files[3]:analysis_dictionary}
    shared = next(name for name in variables if name in raw_vars)
    separate = next(name for name in variables if name not in raw_vars)
    fi = next(i for i,row in enumerate(full_dictionary[1:],1) if row[vi]==shared)
    ai = next(i for i,row in enumerate(analysis_dictionary[1:],1) if row[av]==shared)
    di = next(i for i,row in enumerate(full_dictionary[1:],1) if row[vi]==separate)
    cases = []
    with tempfile.TemporaryDirectory(prefix='source_result_labels_') as tmp:
        folder=Path(tmp)
        for name in files: (folder/name).touch()
        def run(label, accepted, data=None, raw=None, result_plan=None):
            raw = deepcopy(raw_rows if raw is None else raw)
            with (folder/'raw_codebook.csv').open('w',encoding='utf-8',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(raw[0]));writer.writeheader();writer.writerows(raw)
            checks=[]
            with patch.object(output,'read_table_rows',side_effect=lambda p:(data or tables)[p.name]):
                output.check_workbook_contract(folder,files,files[2],files[3],raw_vars,variables,checks,
                    result_label_plan=plan if result_plan is None else result_plan)
            assert checks[-1]['ok']==accepted,(label,checks)
            cases.append({'case':label,'expected_accept':accepted,'actual':checks[-1]})
        run('exact source/result roles',True)
        run('no approved label plan',False,result_plan=[])
        equal=deepcopy(tables)
        for row in equal[files[3]][1:]:
            name=row[av];row[analysis_dictionary[0].index('Label')]=next(x[full_dictionary[0].index('Label')] for x in full_dictionary[1:] if x[vi]==name)
        run('legacy equal Labels without plan',True,data=equal,result_plan=[])
        mutations=[('source Label',files[1],fi,'Label','Changed source'),
                   ('analysis Label',files[3],ai,'Label','Changed result'),
                   ('original identity',files[1],fi,'original_vars','WRONG'),
                   ('processed alias',files[1],fi,'processed_vars','WRONG'),
                   ('source count',files[1],fi,'count',2),
                   ('nonshared Label',files[1],di,'Label','Changed nonshared')]
        for label,filename,row,column,value in mutations:
            changed=deepcopy(tables);changed[filename][row][changed[filename][0].index(column)]=value
            run(label,False,data=changed)
        wrong_raw=deepcopy(raw_rows);next(row for row in wrong_raw if row['newname']==shared)['Variable']='WRONG'
        run('raw original identity',False,raw=wrong_raw)
        wrong_raw=deepcopy(raw_rows);next(row for row in wrong_raw if row['newname']==shared)['Label']='Changed source'
        run('raw source Label',False,raw=wrong_raw)
        wrong_raw=deepcopy(raw_rows);wrong_raw.append(deepcopy(next(row for row in raw_rows if row['newname']==shared)))
        run('duplicate raw alias',False,raw=wrong_raw)
        duplicate=deepcopy(plan);duplicate.append(deepcopy(next(row for row in plan if row['analysis_var']==shared)))
        run('duplicate result plan',False,result_plan=duplicate)
        missing=[row for row in plan if row['analysis_var']!=shared]
        run('missing result plan',False,result_plan=missing)
        empty=deepcopy(plan);next(row for row in empty if row['analysis_var']==shared)['meaning']=''
        run('blank result meaning',False,result_plan=empty)
        changed=deepcopy(tables);changed[files[2]][1][-1]+=1
        run('shared result value drift',False,data=changed)
        changed=deepcopy(tables);changed[files[2]][1][0]+=1
        run('identity drift',False,data=changed)
        changed=deepcopy(tables);changed[files[3]][1],changed[files[3]][2]=changed[files[3]][2],changed[files[3]][1]
        run('analysis dictionary order',False,data=changed)
        changed=deepcopy(tables);changed[files[0]][0].append('unknown');changed[files[0]][1].append(99)
        run('extra unknown column',False,data=changed)
        changed=deepcopy(tables);changed[files[2]].append(deepcopy(changed[files[2]][1]))
        run('row count changed',False,data=changed)
    return cases


check_charls_full_default_identity_fixture()
check_source_result_label_fixture()


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
    questionnaire = f'''## 问卷

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
  component_groups=c(defined_value="Test Module"),
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
    import csv
    from check_definition_output import read_xlsx_rows, read_table_rows
    from update_reader_copy import workbook_content, formal_table
    csv_files=list(files)
    for index in (0,2):
        csv_files[index]=files[index].replace('.xlsx','.csv')
        with (folder/csv_files[index]).open('w',encoding='utf-8-sig',newline='') as stream:
            csv.writer(stream).writerows(read_xlsx_rows(folder/files[index]))
    checks=[]
    check_workbook_contract(folder,csv_files,csv_files[2],csv_files[3],['source_a','source_b'],['defined_value'],checks)
    assert checks[-1]['ok'],checks
    assert formal_table(csv_files[0]) and formal_table(csv_files[2]) and not formal_table('raw_data.csv')
    content=workbook_content(folder/csv_files[2])
    rows=read_table_rows(folder/csv_files[2])
    with (folder/csv_files[2]).open('w',encoding='utf-8',newline='') as stream:
        csv.writer(stream,quoting=csv.QUOTE_ALL).writerows(rows)
    assert workbook_content(folder/csv_files[2])==content,'CSV quoting/BOM alone changed semantic content'
    with (folder/csv_files[2]).open('w',encoding='utf-8',newline='') as stream:
        csv.writer(stream).writerows(rows[:-1])
    checks=[]
    check_workbook_contract(folder,csv_files,csv_files[2],csv_files[3],['source_a','source_b'],['defined_value'],checks)
    assert not checks[-1]['ok'],'CSV output omitted a record without rejection'


def check_charls_psu_join_identity_fixture():
    from unittest.mock import patch
    import check_definition_output as output
    files=['db_psu.xlsx','codebook_psu.xlsx','analysis_db_psu.xlsx','analysis_codebook_psu.xlsx']
    header=['ID','id','year','a','b','x']
    tables={files[0]:[header,['2011_001','001','2011',1,2,3]],
            files[1]:[['Variable','Label'],*[[x,x] for x in header]],
            files[2]:[['ID','id','year','x'],['2011_001','001','2011',3]],
            files[3]:[['Variable','Label','processed_vars'],['x','x','a, b']]}
    contract={'files':{'raw_data_psu.csv':{'file_type':'communityID'}},'join_identity_columns':['communityid']}
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)
        for name in files:(p/name).touch()
        def run(values,con=contract):
            checks=[]
            with patch.object(output,'read_table_rows',side_effect=lambda path:values[path.name]):
                check_workbook_contract(p,files,files[2],files[3],['communityid','a','b'],['x'],checks,charls_multifile_contract=con)
            return checks[-1]['ok']
        assert run(tables)
        assert not run(tables,None),'same-name communityid was globally excluded'
        wrong=deepcopy(tables);wrong[files[3]][1][2]='a, b, communityid';assert not run(wrong),'measurement mapping accepted as join-only'
        wrong=deepcopy(tables);wrong[files[0]][0].remove('b');wrong[files[0]][1].pop(4);assert not run(wrong),'missing measurement source accepted'
        wrong=deepcopy(tables);wrong[files[2]][1][-1]=4;assert not run(wrong),'altered result accepted'
        wrong=deepcopy(tables);wrong[files[2]][1][1]='002';assert not run(wrong),'altered identity/order accepted'

check_charls_psu_join_identity_fixture()

print('EXECUTION_BRANCH_CONTRACTS_PASS: evidence/copy/note, all-NA generation, four actual workbooks, seven key shapes, CHNS identity types')
