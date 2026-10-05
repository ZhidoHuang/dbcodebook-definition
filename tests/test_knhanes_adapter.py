import pathlib,sys,csv,json,zipfile,tempfile,importlib.util,unittest,copy,subprocess,hashlib
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import knhanes_export as k
import recover_dbcodebook_export as recover
import prepare_source_selection as select
import check_definition_output as output
from unittest.mock import patch

class Contract(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.r=pathlib.Path(self.temp.name)
  self.cb=[['sex (Core data)','성별','性别','uniqID','s'],['n_amt (Dietary recall detail)','量','量','reID','n']]
  self.reg=[['2007_001','001','2007','1'],['2008_001','001','2008','2']]
  self.rep=[['1','2007_001','001','2007','4'],['2','2007_001','001','2007','5']]
  self.members=['raw_data.csv','raw_data_Dietary_recall_detail.csv']
  self.write()
 def tearDown(self):self.temp.cleanup()
 def csv(self,name,header,rows):
  with (self.r/name).open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows([header,*rows])
 def write(self):
  self.csv('raw_codebook.csv',k.CODEBOOK_COLUMNS,self.cb)
  self.csv('raw_data.csv',k.IDENTIFIERS+('s',),self.reg)
  self.csv(self.members[1],('RowIndex',*k.IDENTIFIERS,'n'),self.rep)
 def check(self):return k.validate_bundle(self.r,self.members,['s','n'],{'s':'sex (Core data)','n':'n_amt (Dietary recall detail)'})
 def test_preserve_leading_zero_cross_year_and_repeat(self):
  report=self.check();self.assertEqual(report['data']['raw_data.csv']['unique_respondent_years'],2);self.assertEqual(report['data'][self.members[1]]['unique_respondent_years'],1)
 def test_letter_id(self):
  self.reg[0][:2]=['2007_A001','A001'];self.write();self.check()
 def test_duplicate_person_year_rejected(self):
  self.reg.append(self.reg[0]);self.write()
  with self.assertRaisesRegex(ValueError,'duplicate id-year'):self.check()
 def test_numeric_coercion_loss_rejected(self):
  self.reg[0][1]='1';self.write()
  with self.assertRaisesRegex(ValueError,'ID is not'):self.check()
 def test_unsupported_gap_year_rejected(self):
  self.reg[0][:3]=['2006_001','001','2006'];self.write()
  with self.assertRaisesRegex(ValueError,'unsupported year'):self.check()
 def test_unknown_file_not_assumed_unique(self):
  self.cb[0][0]='sex (Unverified future file)';self.write()
  with self.assertRaisesRegex(ValueError,'unknown source file'):k.validate_bundle(self.r,self.members,['s','n'])
 def test_wrong_file_type_rejected(self):
  self.cb[1][3]='uniqID';self.write()
  with self.assertRaisesRegex(ValueError,'File type'):self.check()
 def test_alias_in_wrong_member_rejected(self):
  self.csv('raw_data.csv',k.IDENTIFIERS+('n',),self.reg)
  with self.assertRaisesRegex(ValueError,'coverage'):self.check()
 def test_extra_file_rejected(self):
  with self.assertRaisesRegex(ValueError,'file set'):k.validate_bundle(self.r,self.members+['raw_data_other.csv'],['s','n'])
 def test_repeat_rowindex_rejected(self):
  self.rep[1][0]='1';self.write()
  with self.assertRaisesRegex(ValueError,'RowIndex'):self.check()
 def test_person_renderer_no_repeat_collapse(self):
  with self.assertRaisesRegex(ValueError,'prefix'):k.validate_person_frame(self.r/self.members[1])
 def test_full_source_identity_comparison(self):
  with self.assertRaisesRegex(ValueError,'settled selection'):k.validate_bundle(self.r,self.members,['s','n'],{'s':'sex (Other data)','n':'n_amt (Dietary recall detail)'})
 def test_alias_reserved_empty(self):
  for aliases in [['s',''],['s','ID']]:
   with self.assertRaises(ValueError):k.validate_bundle(self.r,self.members,aliases)
 def test_dict_scope_duplicate_and_missing_column(self):
  self.cb[1][0]=self.cb[0][0];self.cb[1][3]='uniqID';self.write()
  with self.assertRaisesRegex(ValueError,'duplicate source'):self.check()
 def test_recovery_explicit_dispatch_synthetic_zip(self):
  z=self.r/'synthetic_KNHANES.zip'
  with zipfile.ZipFile(z,'w') as f:
   for n in ['raw_codebook.csv',*self.members]:f.write(self.r/n,n)
  original=tempfile.TemporaryDirectory
  with patch.object(recover.tempfile,'TemporaryDirectory',side_effect=lambda **kw:original(dir=ROOT,prefix=kw.get('prefix',''))):report=recover.inspect_archive(z,['s','n'],'knhanes')
  self.assertEqual(report['data'][self.members[1]]['rows'],2)
 def test_output_identity_requires_all_columns(self):
  results=[];output.check_identity_values(self.r/'raw_data.csv',['ID','id','year','s'],[['year','s'],['2007','1']],['year','s'],results,'knhanes')
  self.assertTrue(any(x.get('ok') is False for x in results))
 def test_output_identity_rejects_numeric_string_key(self):
  results=[];header=['ID','id','year','s'];output.check_identity_values(self.r/'raw_data.csv',header,[header,['2007_001',1,2007,1]],header,results,'knhanes')
  self.assertTrue(any(x.get('ok') is False for x in results))
 def test_output_identity_valid_subset(self):
  results=[];header=['ID','id','year','s'];output.check_identity_values(self.r/'raw_data.csv',header,[header,['2007_001','001',2007,1]],header,results,'knhanes')
  self.assertFalse(any(x.get('ok') is False for x in results))
 def test_selection_ready_required_and_full_identity(self):
  action=select.build_record_action({'status':'READY','source_groups':[{'source_identities':['sex (Core data)'],'raw_variables':['s']}]},'http://test/home/knhanes/')
  self.assertEqual(action['input_text'],'sex (Core data)=s')
  with self.assertRaises(ValueError):select.build_record_action({'status':'DRAFT'},'http://test/home/knhanes/')

if __name__=='__main__':
 unittest.main()
