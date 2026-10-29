from pathlib import Path
import sys,tempfile,csv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hrs_export_contract import (TRACKER_FILE,TRACKER_DEFAULTS,record_defaults,validate_defaults,
                                 documented_lowercase_periods,person_identity)
from prepare_source_selection import build_record_action
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'raw_codebook.csv'
 with p.open('w',newline='',encoding='utf-8') as h:
  w=csv.DictWriter(h,fieldnames=['Variable','newname']);w.writeheader();w.writerow({'Variable':f'APROXY ({TRACKER_FILE})','newname':'proxy92'})
 assert validate_defaults(p,['ID','HHID','PN','Wave_id',*TRACKER_DEFAULTS,'proxy92'])==TRACKER_DEFAULTS
 try:validate_defaults(p,['ID','proxy92'])
 except ValueError:pass
 else:raise AssertionError('missing defaults accepted')
 record={'database':'HRS','status':'READY','source_groups':[{'source_identities':[f'{v} ({TRACKER_FILE})'],'raw_variables':[v]} for v in sorted(TRACKER_DEFAULTS)] + [{'source_identities':[f'APROXY ({TRACKER_FILE})'],'raw_variables':['proxy92']}]}
 assert len(record_defaults(record))==4
 assert build_record_action(record,'http://localhost:8000/home/hrs/')['aliases']==['proxy92']
 record['database']='ELSA';assert not record_defaults(record)
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 assert documented_lowercase_periods(p)==set()
 (p/'连接说明.html').write_text('<div>ID = Wave_id | hhid | pn [2003]</div>',encoding='utf-8')
 periods=documented_lowercase_periods(p)
 assert periods=={'2003'}
 assert person_identity({'ID':'2003|010075|020','Wave_id':'2003','HHID':'','PN':''},periods)==('010075','020')
 assert person_identity({'HHID':'001234','PN':'010'})==('001234','010')
 for row,allowed in [
  ({'ID':'2003|010075|020','Wave_id':'2003'},set()),
  ({'ID':'2001|010075|020','Wave_id':'2003'},periods),
  ({'ID':'2003|10075|20','Wave_id':'2003'},periods),
  ({'ID':'2003|010075|020','Wave_id':'2003','HHID':'010075'},periods)]:
  try:person_identity(row,allowed)
  except ValueError:pass
  else:raise AssertionError('undocumented or malformed identity accepted')
 # Verify the output checker uses the declared source identity, including people
 # who have no other period with populated uppercase default columns.
 from check_definition_output import check_identity_values
 raw=p/'raw_data.csv'
 raw.write_text('ID,HHID,PN,Wave_id\n2003|010075|020,,,2003\n',encoding='utf-8')
 checks=[]
 check_identity_values(raw,['ID','HHID','PN','Wave_id'],
                       [['HHID','PN','year'],['010075','020',2003]],['HHID','PN','year'],checks,'hrs')
 assert all(c['ok'] for c in checks),checks
 checks=[]
 check_identity_values(raw,['ID','HHID','PN','Wave_id'],
                       [['HHID','PN','year'],['999999','020',2003]],['HHID','PN','year'],checks,'hrs')
 assert any(not c['ok'] for c in checks)
with tempfile.TemporaryDirectory() as d:
 from check_definition_output import check_public_code_outline
 p=Path(d); script=p/'define_hrs.R'
 for classes,accepted in [
  ('HHID="character", PN="character"',True),
  ('ID="character", HHID="character",\n PN="character", Wave_id="character"',True),
  ('PN="character", HHID="character"',True),
  ('HHID="character", PN="numeric"',False),
  ('ID="character", HHID="character"',False)]:
  code='dt <- read.csv("raw_data.csv", colClasses=c('+classes+'))\nname_z <- read.csv("raw_codebook.csv")\n'
  script.write_text(code+'# 输出\n',encoding='utf-8')
  checks=[]
  check_public_code_outline(p,'### 2-代码材料\n```r\n'+code+'```',checks,'hrs',script)
  details=[x.get('detail',[]) for x in checks if x['check']=='public R structural contract']
  rejected=any('HRS public R must preserve HHID and PN as character when reading raw_data.csv' in x for x in details)
  assert rejected != accepted,(classes,checks)
print('HRS_DEFAULT_COLUMNS_AND_DOCUMENTED_IDENTITY_PASS')
