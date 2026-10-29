from pathlib import Path
import csv,json,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
checker=ROOT/'scripts/check_definition_output.py'
family='ADAMS_MEDICAL_CONDITIONS_INITIAL_VISIT_CONDITION'
member=f'raw_data_repeat_{family}.csv'
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder)
 def write(name,fields,rows):
  with (p/name).open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
 def fixture():
  write('raw_data.csv',['ID','HHID','PN','Wave_id','direct'],[{'ID':'2001-2003|010059|030','HHID':'010059','PN':'030','Wave_id':'2001-2003','direct':'YES'}])
  write('raw_codebook.csv',['Variable','newname','Base_Variable','File type'],[
   {'Variable':'SC317 (HRS_CORE_INTERVIEW_PHYSICAL_HEALTH_RESPONDENT)','newname':'direct','Base_Variable':'C317','File type':'uniqPersonID'},
   {'Variable':f'AHCODE ({family})','newname':'code','Base_Variable':'HCODE','File type':'rePersonID'}])
  write(member,['RowIndex','ID','HHID','PN','Wave_id','source_file','source_row','code'],[
   {'RowIndex':'1','ID':'2001-2003|010059|030','HHID':'010059','PN':'030','Wave_id':'2001-2003','source_file':'ADAMS1AH_C','source_row':'1','code':'362.5'}])
 def check(accepted):
  report=p/'check.json'
  subprocess.run([sys.executable,str(checker),'--formal-dir',str(p),'--db','hrs','--raw-vars','direct,code','--report',str(report)],capture_output=True,text=True)
  data=json.loads(report.read_text(encoding='utf-8'))
  contracts=[x for x in data['checks'] if x['check']=='HRS repeated person-source file contracts']
  headers=[x for x in data['checks'] if x['check']=='raw_data header']
  assert contracts and contracts[0]['ok']==accepted,(accepted,data)
  assert headers and headers[0]['ok']==accepted,(accepted,data)
 fixture();check(True)
 (p/member).rename(p/'raw_data_repeat_UNKNOWN.csv');check(False)
 (p/'raw_data_repeat_UNKNOWN.csv').rename(p/member)
 content=(p/member).read_text(encoding='utf-8')
 (p/member).write_text(content.replace('ADAMS1AH_C','ADAMS1BH_C'),encoding='utf-8');check(False)
 fixture();content=(p/member).read_text(encoding='utf-8')
 (p/member).write_text(content.replace(',code',',unexpected'),encoding='utf-8');check(False)
 fixture();content=(p/'raw_data.csv').read_text(encoding='utf-8')
 (p/'raw_data.csv').write_text(content.replace('direct','missing_selected'),encoding='utf-8');check(False)
print('HRS_REPEAT_OUTPUT_HEADER_PASS: same scoped repeat validation, unknown file/provenance/extra/missing sources rejected')
