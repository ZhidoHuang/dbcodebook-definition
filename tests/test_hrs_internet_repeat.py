import csv,json,os,subprocess,sys,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hrs_export_contract import validate_internet_repeat,ADAMS_PROVENANCE,INTERNET_RESPONDENT_FILE
from recover_dbcodebook_export import validate_data_members
family=INTERNET_RESPONDENT_FILE;member=f'raw_data_repeat_{family}.csv'
fields=['RowIndex','ID','HHID','PN','Wave_id','source_file','source_row','med']
note='合并文件（官方）：net03_r.da、net06_r.da、NET07_R.da、NET09_R.da、NET11_R.da、NET13I_R.da\n连接键：ID = Wave_id | hhid | PN [2011]'
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp);row=dict(zip(fields,['1','2011|010004|040','','040','2011','NET11_R','1','Yes']))
 def write(rows):
  with (p/member).open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
 def dictionary(kind='rePersonID'):
  with (p/'raw_codebook.csv').open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=['Variable','Base_Variable','newname','File type']);w.writeheader();w.writerow({'Variable':f'B021_11 ({family})','Base_Variable':'B021_11','newname':'med','File type':kind})
 def accepted():return validate_internet_repeat(p,member,fields)==ADAMS_PROVENANCE
 def rejected():
  try:accepted()
  except ValueError:return
  raise AssertionError('bad package accepted')
 dictionary();write([row]);(p/'连接说明.html').write_text(note,encoding='utf-8');assert accepted()
 assert validate_data_members(p,[member],['med'])[member]['rows']==1
 # A duplicate parent ID is allowed as raw evidence, while provenance stays unique.
 write([row,dict(row,RowIndex='2',source_row='2',med='No')]);assert accepted()
 for key,value in [('ID','2011|010005|041'),('HHID','999999'),('PN','40'),('Wave_id','2013'),('source_file','NET13I_R'),('source_row','0'),('RowIndex','-1')]:
  write([dict(row,**{key:value})]);rejected()
 write([row]);(p/'连接说明.html').unlink();rejected()
 (p/'连接说明.html').write_text(note.replace('[2011]','[2013]'),encoding='utf-8');rejected()
 (p/'连接说明.html').write_text(note,encoding='utf-8')
 for rows in [[row,row],[row,dict(row,RowIndex='2')]]:write(rows);rejected()
 write([row]);dictionary('uniqPersonID');rejected();dictionary()
 try:validate_internet_repeat(p,member,fields+['unexpected'])
 except ValueError:pass
 else:raise AssertionError('extra business column accepted')
 assert validate_internet_repeat(p,'raw_data_repeat_UNKNOWN.csv',fields)==set()
 write([row]);record={'database':'HRS','source_groups':[{'source_identities':[f'B021_11 ({family})'],'raw_variables':['med']}]}
 (p/'record.json').write_text(json.dumps(record),encoding='utf-8');(p/'raw_data.csv').write_text('HHID,PN\n010004,040\n',encoding='utf-8')
 rscript=os.environ.get('RSCRIPT') or shutil.which('Rscript')
 if not rscript:raise RuntimeError('Rscript is required for public raw-read validation')
 def rcheck(accepted,classes='HHID="character",PN="character"'):
  lines=['dt <- read.csv("raw_data.csv", colClasses=c(HHID="character",PN="character"))','name_z <- read.csv("raw_codebook.csv")',f'internet <- read.csv("{member}", colClasses=c({classes}))']
  code='source('+json.dumps(str(ROOT/'scripts/check_public_raw_reads.R'))+')\ncheck_public_raw_reads(c('+','.join(json.dumps(x) for x in lines)+'),"HRS",'+json.dumps(str(p))+','+json.dumps(str(p/'record.json'))+')\n'
  (p/'test.R').write_text(code,encoding='utf-8');result=subprocess.run([rscript,str(p/'test.R')],capture_output=True,text=True)
  assert (result.returncode==0)==accepted,(result.stdout,result.stderr)
 rcheck(True);rcheck(False,'PN="character"');rcheck(False,'HHID="character",PN="character",med="character"')
 dictionary('uniqPersonID');rcheck(False);dictionary()
 record['source_groups'][0]['source_identities']=['B021_11 (OTHER)'];(p/'record.json').write_text(json.dumps(record),encoding='utf-8');rcheck(False)
 # The complete-output entry must use the same validated transport contract.
 with (p/'raw_codebook.csv').open('a',encoding='utf-8',newline='') as h:
  csv.writer(h).writerow(['SC283 (HRS_CORE_INTERVIEW_PHYSICAL_HEALTH_RESPONDENT)','C283','direct','uniqPersonID'])
 (p/'raw_data.csv').write_text('ID,HHID,PN,Wave_id,direct\n2011|010004|040,010004,040,2011,YES\n',encoding='utf-8')
 def output_check(accepted):
  report=p/'output_check.json'
  subprocess.run([sys.executable,str(ROOT/'scripts/check_definition_output.py'),'--formal-dir',str(p),'--db','hrs','--raw-vars','direct,med','--report',str(report)],capture_output=True,text=True)
  checks=json.loads(report.read_text(encoding='utf-8'))['checks']
  for name in ('HRS repeated person-source file contracts','raw_data header'):
   matches=[c for c in checks if c['check']==name];assert matches and matches[0]['ok']==accepted,(name,matches)
 output_check(True)
 (p/member).rename(p/'raw_data_repeat_UNKNOWN.csv');output_check(False)
print('HRS_INTERNET_REPEAT_TRANSPORT_AND_RAW_READ_PASS')
