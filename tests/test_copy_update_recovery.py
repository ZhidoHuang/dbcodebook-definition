"""Exercise real report transitions with explicitly simulated generation/checks.

R computation and rendering are tested separately by execution_branch_contracts.
All reports and artifacts here are temporary synthetic fixtures.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_report as er
import update_reader_copy as update
from source_record_binding import SOURCE_SCOPE


def rejects(fn, expected=''):
    try:
        fn()
    except (ValueError, SystemExit) as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError('Expected rejection: '+expected)


@contextmanager
def fixture(failure=None, reader=False, change=True):
    with tempfile.TemporaryDirectory(prefix='copy_retry_synthetic_') as tmp:
        root=Path(tmp); formal=root/'formal'; process=root/'process'; backup=process/'copy_updates'/'baseline'
        formal.mkdir(); backup.mkdir(parents=True)
        for name,text in {'文案.md':'original copy', 'note.md':'rendered original copy',
                          'define_fixture.R':'# synthetic R fixture', 'raw_data.csv':'id,year,x\n001,2011,1',
                          'raw_codebook.csv':'Variable,newname\nx,x', 'fixture_detail.html':'old detail',
                          'fixture_run_ok.log':'old log'}.items():
            (formal/name).write_text(text,encoding='utf-8')
        for name in ('db_fixture.xlsx','codebook_fixture.xlsx','analysis_db_fixture.xlsx','analysis_codebook_fixture.xlsx'):
            with zipfile.ZipFile(formal/name,'w') as z:
                z.writestr('xl/worksheets/sheet1.xml','<synthetic>unchanged cells</synthetic>')
        source=process/'definition_search_record.json'
        record={'schema_version':7,'database':'CHARLS','source_groups':[{'raw_variables':['x']}],
                'questionnaire_evidence':[], 'definition_plan':{'formula':'x'}}
        update.write(source,record); update.write(backup/source.name,record)
        update.write(backup/'definition_change_impact.json',{'schema_version':3,'changed_dimensions':['copy']})
        for f in formal.iterdir():
            if f.suffix=='.xlsx' or f.name=='文案.md':
                (backup/f.name).write_bytes(f.read_bytes())
        update.call('execution_report.py','init','--process-dir',process,'--database','CHARLS',
                    '--topic-id','999','--topic-name','Synthetic retry fixture',
                    '--task','Synthetic lifecycle test only; no production execution','--workflow','general')
        update.call('execution_report.py','stage-start','--process-dir',process,'--stage-id','copy',
                    '--name','Synthetic copy','--role','Fixture','--model','synthetic')
        art={key:{'path':name,'sha256':update.digest(formal/name)} for key,name in
             {'note':'note.md','analysis_db':'analysis_db_fixture.xlsx','analysis_codebook':'analysis_codebook_fixture.xlsx'}.items()}
        result={'artifacts':{f.name:update.digest(f) for f in formal.iterdir()},
                'analysis_vars':['result'], 'checks':[{'check':'analysis_db columns','detail':['id','year','result']}]}
        binding={'formal_dir':str(formal.resolve()),'folder':str(backup),'reason':'仅修正文案表达，保留已确定的研究方案、来源与计算。',
                 'source_hash':update.digest(backup/source.name),'result':result,'r_script':'define_fixture.R',
                 'audit_artifacts':art,'review':{'inputs':er.input_hashes([source,formal/'define_fixture.R'],source_scope=SOURCE_SCOPE)},
                 'status':'prepared','issue_numbers':[],'attempts':[]}
        report=update.read(process/er.REPORT_NAME); report['copy_update']=binding
        er.save(*er.paths(process),report)
        update.write(process/'readability_audit.json',{'schema_version':7,'status':'ARTIFACTS_BOUND',
                      'reader_review_required':reader,'artifacts':art})
        if reader: update.write(process/'reader_comprehension_review.json',{'synthetic':True,'pass':True})
        if change: (formal/'文案.md').write_text('revised copy',encoding='utf-8')
        args=SimpleNamespace(formal_dir=formal,process_dir=process,config=None,pwsh='synthetic-pwsh',
                             omit_questionnaire=None,reason='已修正文案或测试注入的失败，研究事实、原始数据及计算脚本未改变。')
        original_call=update.call; original_run=subprocess.run
        state={'failed':False,'renders':0}

        def fail_once(stage):
            if failure==stage and not state['failed']:
                state['failed']=True
                raise ValueError('injected '+stage+' failure')

        def simulated_runner(cmd,*a,**kw):
            if cmd[0]!='synthetic-pwsh': return original_run(cmd,*a,**kw)
            state['renders']+=1
            (formal/'note.md').write_text('rendered '+(formal/'文案.md').read_text(encoding='utf-8'),encoding='utf-8')
            (formal/'fixture_detail.html').write_text('new detail',encoding='utf-8')
            try: fail_once('generate')
            except ValueError: return SimpleNamespace(returncode=1)
            return SimpleNamespace(returncode=0)

        def simulated_check(script,*params,log=None):
            if script=='execution_report.py': return original_call(script,*params,log=log)
            if log: Path(log).write_text('SYNTHETIC '+script,encoding='utf-8')
            if script=='check_reader_copy.py': fail_once('copy')
            elif script=='check_definition_output.py': fail_once('results')
            elif script=='check_definition_readability.py':
                review=process/'reader_comprehension_review.json'
                audit=update.read(process/'readability_audit.json')
                if params[0]=='init':
                    audit['reader_review_required']=audit.get('reader_review_required',False) or review.exists()
                    audit['artifacts']['note']['sha256']=update.digest(formal/'note.md')
                    if review.exists() and '--preserve-reader' not in params: review.unlink()
                    update.write(process/'readability_audit.json',audit)
                else:
                    fail_once('delivery')
                    if audit.get('reader_review_required'):
                        if not review.exists() or not update.read(review).get('pass'):
                            raise ValueError('reader review still required')
            else: raise AssertionError(script)
            return SimpleNamespace(returncode=0,stdout='{}',stderr='')

        with patch.object(update,'call',side_effect=simulated_check), \
             patch.object(update.subprocess,'run',side_effect=simulated_runner):
            yield args,formal,process,backup,state


for stage in ('copy','generate','results','delivery'):
    with fixture(failure=stage) as (args,formal,process,backup,state):
        original_baseline={f.name:update.digest(f) for f in backup.iterdir()}
        rejects(lambda:update.run(args))
        failed=update.read(process/er.REPORT_NAME)
        assert failed['copy_update']['status']=='failed' and failed['issues'][0]['status']=='open'
        for name in ('define_fixture.R','raw_data.csv','raw_codebook.csv'):
            p=formal/name; original=p.read_bytes();p.write_bytes(original+b'\nchanged')
            rejects(lambda:update.retry(args),'变化');p.write_bytes(original)
        source=process/'definition_search_record.json'; original=source.read_bytes()
        changed=update.read(source); changed['definition_plan']['formula']='x + 1';update.write(source,changed)
        rejects(lambda:update.retry(args),'研究内容');source.write_bytes(original)
        result=update.retry(args)
        current=update.read(process/er.REPORT_NAME)
        assert result['status']=='LOCAL_UPDATE_COMPLETE'
        assert current['status']=='completed_with_issues'
        assert len(current['issues'])==1 and current['issues'][0]['status']=='resolved'
        assert current['issues'][0]['amendments']
        assert [a['status'] for a in current['copy_update']['attempts']]==['failed','completed']
        assert {f.name:update.digest(f) for f in backup.iterdir() if f.is_file()}==original_baseline
        assert len(list(backup.glob('attempts/*/copy-check.log')))==2

with fixture(reader=True) as (args,formal,process,backup,state):
    assert update.run(args)['status']=='READER_REVIEW_REQUIRED'
    assert update.read(process/'readability_audit.json')['reader_review_required']
    assert (backup/'attempts/1/reader_comprehension_review.json').exists()
    rejects(lambda:update.finish(args),'reader review')
    update.write(process/'reader_comprehension_review.json',{'synthetic':True,'pass':True})
    runs=state['renders']
    assert update.finish(args)['status']=='LOCAL_UPDATE_COMPLETE' and state['renders']==runs

with fixture(reader=True) as (args,formal,process,backup,state):
    assert update.run(args)['status']=='READER_REVIEW_REQUIRED'
    (formal/'文案.md').write_text('reader requested correction',encoding='utf-8')
    rejects(lambda:update.finish(args),'成果已变化')
    assert update.retry(args)['status']=='READER_REVIEW_REQUIRED'
    update.write(process/'reader_comprehension_review.json',{'synthetic':True,'pass':True})
    assert update.finish(args)['status']=='LOCAL_UPDATE_COMPLETE'

with fixture(reader=True,change=False) as (args,formal,process,backup,state):
    assert update.run(args)['status']=='LOCAL_UPDATE_COMPLETE'
    assert (process/'reader_comprehension_review.json').exists()

print('COPY_UPDATE_RECOVERY_PASS: four failure points, immutable inputs, retained history, required-reader return and retry, valid review reuse')
