"""Explicit historical evidence must not silently weaken current copy-update guards."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from copy import deepcopy
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import update_reader_copy as u
import execution_report as er
from source_record_binding import SOURCE_SCOPE

def reject(fn,fragment):
 try:fn()
 except ValueError as e:assert fragment in str(e),str(e)
 else:raise AssertionError('Expected rejection: '+fragment)

def fixture(root):
 f=root/'formal';p=root/'process';f.mkdir();p.mkdir();legacy=p/'archived_runs'/'legacy'/'execution_report.json';legacy.parent.mkdir(parents=True)
 for n in ['define_test.R','raw_codebook.csv','raw_data.csv','文案.md','note.md']:(f/n).write_text('Synthetic fixture '+n,encoding='utf8')
 source=p/'definition_search_record.json';u.write(source,dict(database='elsa',topic_id='999',definition_plan={'formula':'x'},source_groups=[]))
 inp=er.input_hashes([f/'define_test.R',source,f/'raw_codebook.csv'],source_scope=SOURCE_SCOPE)
 review=dict(status='pass',mode='independent',agent_id='fixture-r',started_at='2026-01-01T00:00:00Z',finished_at='2026-01-01T00:02:00Z',inputs=inp,source_scope=SOURCE_SCOPE,evidence='SYNTHETIC test fixture, not an actual review')
 old=dict(schema_version=1,run_id='legacy',database='ELSA',topic_id='999',topic_name='Fixture',status='completed',workflow='general',stage_reviews={er.COMBINED_REVIEW_ROLE:review},reviews=[dict(agent_id='fixture-r',role=er.COMBINED_REVIEW_ROLE,unfinished_turns=0,closed=True,rounds=[dict(started_at='2026-01-01T00:00:00Z',outcome='completed')])],stages=[],issues=[])
 u.write(legacy,old);current=dict(old,run_id='current',database='elsa',stage_reviews={},reviews=[]);u.write(p/er.REPORT_NAME,current)
 u.write(p/'result_check.json',dict(ok=True,scope='complete',artifacts={n.name:u.digest(n) for n in f.iterdir()},source_sha256=u.digest(source)))
 u.write(p/'readability_audit.json',dict(unresolved_issues=[],artifacts={}))
 u.write(p/'definition_change_impact.json',dict(schema_version=3,changed_dimensions=['copy']))
 return f,p,legacy,old,current

for case in ['explicit_pass','current_report_pass','default_reject','wrong_topic','missing_review','invalid_r','existing_dual_invalid']:
 with TemporaryDirectory(prefix='legacy_copy_fixture_') as tmp:
  f,p,legacy,old,current=fixture(Path(tmp));args=SimpleNamespace(formal_dir=f,process_dir=p,legacy_report=legacy,reason='Synthetic explicit historical evidence test; original requirements remain unchanged.')
  if case=='current_report_pass':
   current.update(stage_reviews=old['stage_reviews'],reviews=old['reviews']);u.write(p/er.REPORT_NAME,current);args.legacy_report=p/er.REPORT_NAME
   result=u.prepare(args);assert result['status']=='PREPARED';saved=u.read(p/er.REPORT_NAME);bound=saved['copy_update']['legacy_evidence'];assert Path(bound['path']).parent.name=='current' and bound['sha256']==u.digest(bound['path'])
  elif case=='default_reject':args.legacy_report=None;reject(lambda:u.prepare(args),'--legacy-report')
  elif case=='wrong_topic':old['topic_id']='998';u.write(legacy,old);reject(lambda:u.prepare(args),'历史报告')
  elif case=='missing_review':old['stage_reviews']={};u.write(legacy,old);reject(lambda:u.prepare(args),'历史报告')
  elif case=='invalid_r':
   old['stage_reviews'][er.COMBINED_REVIEW_ROLE]['inputs'][str((f/'define_test.R').resolve())]='invalid';u.write(legacy,old);reject(lambda:u.prepare(args),'变化')
  elif case=='existing_dual_invalid':
   current['exploration_policy']='dual_exploration_v1';u.write(p/er.REPORT_NAME,current);reject(lambda:u.prepare(args),'双路探索')
  else:
   result=u.prepare(args);assert result['status']=='PREPARED';saved=u.read(p/er.REPORT_NAME);assert saved['copy_update']['legacy_evidence']['sha256']==u.digest(legacy)
print('COPY_UPDATE_LEGACY_PASS: explicit evidence, default rejection, scope, current R, and existing dual guards')

assert u.previous_raw_order({'checks':[{'check':'raw_codebook vars','ok':True,'detail':['y','x']}]}, ['x','y']) == ['y','x']
reject(lambda:u.previous_raw_order({'checks':[{'check':'raw_codebook vars','ok':True,'detail':['x','z']}]}, ['x','y']), '清单')
reject(lambda:u.previous_raw_order({'checks':[{'check':'raw_codebook vars','ok':True,'detail':['x','x']}]}, ['x','y']), '清单')
print('COPY_UPDATE_ORDER_PASS: accepted order preserved; missing, extra and duplicate sources rejected')

from hrs_export_contract import accepts_legacy_package, validate_defaults, TRACKER_FILE
with TemporaryDirectory(prefix='legacy_tracker_fixture_') as tmp:
    root=Path(tmp);formal=root/'formal';process=root/'process';formal.mkdir();process.mkdir()
    (formal/'raw_data.csv').write_text('ID,HHID,PN,Wave_id,BIRTHYR\na,001,01,1992-2022,1940\n',encoding='utf8')
    (formal/'raw_codebook.csv').write_text('Variable,newname\nBIRTHYR ('+TRACKER_FILE+'),BIRTHYR\n',encoding='utf8')
    legacy=process/'legacy.json';u.write(legacy,{'status':'completed'})
    reject(lambda:validate_defaults(formal/'raw_codebook.csv',['BIRTHYR']), 'Missing automatic')
    assert not accepts_legacy_package(process,formal)
    u.write(process/'execution_report.json',{'copy_update':{'formal_dir':str(formal),'legacy_evidence':{'path':str(legacy),'sha256':u.digest(legacy)},'result':{'artifacts':{p.name:u.digest(p) for p in formal.iterdir()}}}})
    assert accepts_legacy_package(process,formal)
    assert validate_defaults(formal/'raw_codebook.csv',['BIRTHYR'],legacy_package=True)==set()
    (formal/'raw_data.csv').write_text('changed',encoding='utf8')
    reject(lambda:accepts_legacy_package(process,formal),'baseline')
print('COPY_UPDATE_OLD_TRACKER_PASS: only explicit unchanged historical packages; current exports retain default-column checks')
