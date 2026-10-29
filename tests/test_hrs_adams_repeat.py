import csv,json,os,subprocess,sys,tempfile,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hrs_export_contract import validate_adams_repeat,ADAMS_PROVENANCE
family='ADAMS_MEDICAL_CONDITIONS_INITIAL_VISIT_CONDITION'
member=f'raw_data_repeat_{family}.csv'
identity=f'AHCODE ({family})'
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp)
 fields=['RowIndex','ID','HHID','PN','Wave_id','source_file','source_row','code']
 row=dict(zip(fields,['1','2001-2003|010059|030','010059','030','2001-2003','ADAMS1AH_C','1','053.90']))
 def write(rows):
  with (p/member).open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
 def dictionary(kind='rePersonID'):
  with (p/'raw_codebook.csv').open('w',newline='',encoding='utf-8') as h:
   w=csv.DictWriter(h,fieldnames=['Variable','Base_Variable','newname','File type']);w.writeheader();w.writerow({'Variable':identity,'Base_Variable':'HCODE','newname':'code','File type':kind})
 dictionary();write([row]);assert validate_adams_repeat(p,member,fields)==ADAMS_PROVENANCE
 second=dict(row,RowIndex='2',source_row='2');write([row,second]);assert validate_adams_repeat(p,member,fields)==ADAMS_PROVENANCE
 for key,value in [('ID','wrong'),('HHID','10059'),('PN','30'),('Wave_id','2002-2005'),('source_file','other'),('source_row','0'),('RowIndex','0')]:
  bad=dict(row);bad[key]=value;write([bad])
  try: validate_adams_repeat(p,member,fields)
  except ValueError: pass
  else: raise AssertionError(key)
 for rows in [[row,row],[row,dict(row,RowIndex='2')]]:
  write(rows)
  try: validate_adams_repeat(p,member,fields)
  except ValueError: pass
  else: raise AssertionError('duplicate provenance accepted')
 write([row]);dictionary('uniqPersonID')
 try: validate_adams_repeat(p,member,fields)
 except ValueError: pass
 else: raise AssertionError('wrong source type accepted')
 dictionary();assert validate_adams_repeat(p,'raw_data_repeat_UNKNOWN.csv',fields)==set()
 record={'database':'HRS','source_groups':[{'source_identities':[identity],'raw_variables':['code']}]}
 (p/'source.json').write_text(json.dumps(record),encoding='utf-8')
 (p/'raw_data.csv').write_text('HHID,PN\n010059,030\n',encoding='utf-8')
 def rcheck(extra,accepted,filename=member):
  lines=['dt <- read.csv("raw_data.csv", colClasses=c(HHID="character", PN="character"))','name_z <- read.csv("raw_codebook.csv")',f'repeat_dt <- read.csv("{filename}", colClasses=c({extra}))']
  code='source('+json.dumps(str(ROOT/'scripts/check_public_raw_reads.R'))+')\n'+ 'check_public_raw_reads('+ 'c('+','.join(json.dumps(x) for x in lines)+'),"HRS",'+json.dumps(str(p))+','+json.dumps(str(p/'source.json'))+')\n'
  (p/'test.R').write_text(code,encoding='utf-8')
  result=subprocess.run([os.environ['RSCRIPT'],str(p/'test.R')],capture_output=True,text=True)
  assert (result.returncode==0)==accepted,(result.stdout,result.stderr)
 rcheck('HHID="character",PN="character",code="character"',True)
 rcheck('HHID="character",PN="character"',False)
 rcheck('HHID="character",PN="character",source_row="character"',False)
 rcheck('HHID="character",PN="character",unknown="character"',False)
 rcheck('PN="character",code="character"',False)
 rcheck('HHID="character",PN="character",code="character"',False,'raw_data_repeat_UNKNOWN.csv')
 record['source_groups'][0]['source_identities']=['AHCODE (OTHER)']
 (p/'source.json').write_text(json.dumps(record),encoding='utf-8')
 rcheck('HHID="character",PN="character",code="character"',False)
 # Read-time character preservation is observable, including a leading zero and trailing zero.
 record['source_groups'][0]['source_identities']=[identity]
 (p/'source.json').write_text(json.dumps(record),encoding='utf-8')
 code='x <- read.csv('+json.dumps(str(p/member))+', colClasses=c(code="character"))\nstopifnot(identical(x$code,"053.90"))\n'
 (p/'preserve.R').write_text(code,encoding='utf-8')
 subprocess.run([os.environ['RSCRIPT'],str(p/'preserve.R')],check=True,capture_output=True)
print('ADAMS_REPEAT_METADATA_AND_CHARACTER_READ_PASS')
