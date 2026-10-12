from pathlib import Path
import sys,tempfile,csv
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hrs_export_contract import TRACKER_FILE,TRACKER_DEFAULTS,record_defaults,validate_defaults
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
print('HRS_DEFAULT_COLUMNS_PASS')
