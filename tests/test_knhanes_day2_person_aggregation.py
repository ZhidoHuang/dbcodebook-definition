import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

from knhanes_person_aggregation import (
    expected_person_summaries, validate_summary_cells, MEMBER, KEYS)

_temporary=tempfile.TemporaryDirectory()
P=Path(_temporary.name)
spec=importlib.util.spec_from_file_location("installed_knhanes_export",Path(__file__).resolve().parents[1]/"scripts/knhanes_export.py")
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
aliases=['diet2','why2','disease2','other2']
originals=['n_diet','n_diet_why','n_dt_ds','n_dt_etc']
summaries=['diet2_person','why2_person','disease2_person','other2_person']
plan={'knhanes_person_aggregation':{'schema_version':1,'primary_file':'raw_data.csv','repeat_file':MEMBER,
 'source_file':'Dietary recall second day','group_keys':list(KEYS),'visit_periods':['2009','2019'],
 'method':'constant_within_person_visit','missing_rule':'single_known_or_all_missing',
 'conflict_rule':'group_na_and_report','join':'left_to_primary','orphan_rule':'stop',
 'source_summaries':[{'variable':name,'source_variables':[alias],'original_variable':original,
 'value_type':'numeric_code' if original in originals[:2] else 'text'} for name,alias,original in zip(summaries,aliases,originals)]},'approved_analysis_vars':['JB_FIXTURE']}

def write_csv(path,header,rows):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(header);writer.writerows(rows)

def fixture(name,variant=None):
    directory=P/'synthetic_only'/('v2_'+name);directory.mkdir(parents=True,exist_ok=False)
    primary=[['2019_A','A','2019',40],['2019_B','B','2019',50],['2019_C','C','2019',60],['2020_D','D','2020',70]]
    repeat=[['1','2019_A','A','2019','1','1','당뇨병',''],
            ['2','2019_A','A','2019','1','1','당뇨병',''],
            ['3','2019_B','B','2019','1','1','고혈압',''],
            ['4','2019_B','B','2019','1','1','당뇨병',''],
            ['5','2019_C','C','2019','1','3','','체중조절'],
            ['6','2019_C','C','2019','','','','체중조절']]
    if variant=='orphan':repeat[0][1:3]=['2019_Z','Z']
    if variant=='period':repeat[0][1:4]=['2020_A','A','2020']
    if variant=='rowindex':repeat[1][0]='1'
    if variant=='source_id':repeat[0][1]='2018_A'
    cb=[['age (Core data)','만나이','年龄','uniqID','age']]+[[f'{o} (Dietary recall second day)',o,o,'reID',a] for o,a in zip(originals,aliases)]
    write_csv(directory/'raw_data.csv',[*KEYS,'age'],primary)
    write_csv(directory/MEMBER,['RowIndex',*KEYS,*aliases],repeat)
    write_csv(directory/'raw_codebook.csv',['Variable','Label原文','Label中文','File type','newname'],cb)
    return directory

def contract(directory):
    return transport.validate_bundle(directory,['raw_data.csv',MEMBER],['age',*aliases])

results=[]
def rejects(name,call):
    try:call()
    except ValueError as error:results.append({'case':name,'status':'PASS','expected_rejection':str(error)});return
    raise AssertionError(name+' unexpectedly accepted')

d=fixture('01_valid');before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in d.iterdir()}
expected,specs,stats=expected_person_summaries(d,plan,contract(d))
manual={('2019_A','A','2019'):dict(zip(summaries,['1','1','당뇨병',None])),
 ('2019_B','B','2019'):dict.fromkeys(summaries),
 ('2019_C','C','2019'):dict(zip(summaries,['1','3',None,'체중조절'])),
 ('2020_D','D','2020'):dict.fromkeys(summaries)}
assert expected==manual
assert stats['conflict_person_visits']==1 and stats['repeat_person_visits']==3 and stats['mixed_missing_fields']==2
assert stats['conflicts'][0]['source_rows']==['3','4']
header=[*KEYS,*summaries]
rows=[[ *key,*values.values()] for key,values in manual.items()]
assert validate_summary_cells(header,rows,expected,specs)=={'rows':4,'source_summary_cells':16,'differences':0}
assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in d.iterdir()}
results.append({'case':'constant values, mixed missing, isolated conflict, nonparticipant and untouched raw','status':'PASS','independent_expected_cells':16})

bad=copy.deepcopy(rows);bad[0][3]='2'
rejects('tampered numeric summary cell',lambda:validate_summary_cells(header,bad,expected,specs))
bad_text=copy.deepcopy(rows);bad_text[0][5]='다른 병'
rejects('tampered original text summary',lambda:validate_summary_cells(header,bad_text,expected,specs))
rejects('person dropped',lambda:validate_summary_cells(header,rows[:-1],expected,specs))
rejects('food rows leaked to final personal table',lambda:validate_summary_cells(header,rows+[rows[0]],expected,specs))
rejects('arbitrary take-first policy',lambda:expected_person_summaries(d,{'knhanes_person_aggregation':dict(plan['knhanes_person_aggregation'],conflict_rule='first')},contract(d)))
rejects('missing explicit plan',lambda:expected_person_summaries(d,{},contract(d)))
collision=copy.deepcopy(plan);collision['knhanes_person_aggregation']['source_summaries'][0]['variable']='JB_FIXTURE'
rejects('summary name collides with final result',lambda:expected_person_summaries(d,collision,contract(d)))
orphan=fixture('02_orphan','orphan');rejects('repeat respondent absent from primary',lambda:expected_person_summaries(orphan,plan,contract(orphan)))
period=fixture('03_wrong_visit','period');rejects('unexpected visit period',lambda:expected_person_summaries(period,plan,contract(period)))
index=fixture('04_rowindex','rowindex');rejects('original RowIndex sequence invalid',lambda:contract(index))
identity=fixture('05_wrong_id','source_id');rejects('source ID differs from year_id',lambda:contract(identity))
unsupported=copy.deepcopy(plan);unsupported['knhanes_person_aggregation']['source_file']='Physical activity monitor'
rejects('unresearched repeat family',lambda:expected_person_summaries(d,unsupported,contract(d)))
report={'status':'CANDIDATE_UNIT_TESTS_PASS','cases':results,'case_count':len(results),
 'scope':'Only synthetic fixtures and the bounded Python aggregation/check proposal; no real export, public-R integration, shared install or full production acceptance.',
 'shared_files_modified':False,'real_data_used':False}
out=P/'候选聚合契约测试结果_v2.json';assert not out.exists();out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'cases':len(results),'independent_expected_summary_cells':16,'shared_files_modified':False},ensure_ascii=False))
