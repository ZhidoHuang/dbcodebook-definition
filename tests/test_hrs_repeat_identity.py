import csv,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_definition_output import check_identity_values
from hrs_export_contract import INTERNET_RESPONDENT_FILE
family=INTERNET_RESPONDENT_FILE
member=f'raw_data_repeat_{family}.csv'
fields=['RowIndex','ID','HHID','PN','Wave_id','source_file','source_row','med']
note='合并文件（官方）：net03_r.da、net06_r.da、NET07_R.da、NET09_R.da、NET11_R.da、NET13I_R.da\n连接键：ID = Wave_id | hhid | PN [2011]'
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp);raw=p/'raw_data.csv'
 raw.write_text('ID,HHID,PN,Wave_id\n2011|000001|010,000001,010,2011\n',encoding='utf-8')
 with (p/'raw_codebook.csv').open('w',encoding='utf-8',newline='') as h:
  w=csv.DictWriter(h,fieldnames=['Variable','Base_Variable','newname','File type']);w.writeheader();w.writerow({'Variable':f'B021_11 ({family})','Base_Variable':'B021_11','newname':'med','File type':'rePersonID'})
 (p/'连接说明.html').write_text(note,encoding='utf-8')
 row=dict(zip(fields,['1','2011|010004|040','','040','2011','NET11_R','1','Yes']))
 def write(value):
  with (p/member).open('w',encoding='utf-8',newline='') as h:
   w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerow(value)
 def check(accepted,hhid='010004',pn='040'):
  results=[];header=['ID','HHID','PN','year']
  check_identity_values(raw,['ID','HHID','PN','Wave_id'],[header,[f'2011|{hhid}|{pn}',hhid,pn,'2011']],header,results,'hrs')
  identities=[x for x in results if x['check']=='analysis identity values']
  assert identities and identities[-1]['ok']==accepted,results
 write(row);check(True);check(False,pn='041');check(False,hhid='10004')
 (p/member).rename(p/'raw_data_repeat_UNKNOWN.csv');check(False)
 (p/'raw_data_repeat_UNKNOWN.csv').rename(p/member)
 for field,value in [('ID','2011|010005|041'),('PN','40'),('HHID','999999'),('source_file','NET13I_R'),('source_row','0')]:
  write(dict(row,**{field:value}));check(False)
 write(row);(p/'连接说明.html').unlink();check(False)
 (p/'连接说明.html').write_text(note,encoding='utf-8');check(True)
print('HRS_REPEAT_ONLY_PERSON_IDENTITY_PASS')
