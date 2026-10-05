import csv,hashlib,importlib,json,os,py_compile,sys,tempfile,unittest,zipfile
from unittest.mock import patch,MagicMock
from pathlib import Path
HERE=Path(__file__).resolve().parent
SCRIPTS=Path(os.environ.get('DBCODEBOOK_TEST_SCRIPTS', HERE/'staged/scripts' if (HERE/'staged/scripts').exists() else HERE.parent/'scripts'))
sys.path.insert(0,str(SCRIPTS))
import klosa_adapter_contract as k
import skill_config,prepare_source_selection as selection,recover_dbcodebook_export as recovery,source_read
import playwright_session_action as browser
import check_definition_output as output_check

class ContractTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.expected=['sex10','mi_sex1']
  self.dictrows=[['sex','gender1','Wave 10','w10gender1 (KLoSA_str)','uniqID','sex10'],['sex','gender1','Wave 1','w01gender1 (KLoSA_Imputation)','reID','mi_sex1']]
  self.reg=[['00001_10','00001','10','1']]
  self.mi=[['1','00001_1','00001','1','1','1'],['2','00001_1','00001','1','2','1']]
  self.write()
 def tearDown(self):self.temp.cleanup()
 def csv(self,name,header,rows):
  with (self.root/name).open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows([header,*rows])
 def write(self):
  self.csv('raw_codebook.csv',k.DICT_HEADER,self.dictrows);self.csv('raw_data.csv',k.IDENTIFIERS+['sex10'],self.reg);self.csv(k.REPEAT_MEMBER,k.REPEAT_IDENTIFIERS+['mi_sex1'],self.mi)
 def runvalid(self,lang='ko'):return k.validate_package(self.root,['raw_data.csv',k.REPEAT_MEMBER],self.expected,lang)
 def test_language_routes(self):
  config={'website':{'base_url':'http://localhost:8000'}}
  for lang in ['en','ko']:
   target=f'http://localhost:8000/home/klosa/{lang}/'
   self.assertEqual(skill_config.database_url(config,'klosa',lang),target)
   self.assertEqual(recovery.database_page_url('http://localhost:8000','klosa',lang),target)
  for lang in [None,'kr','KO','']:
   with self.assertRaises(ValueError):skill_config.database_url(config,'klosa',lang)
 def test_other_database_route_retained(self):
  self.assertEqual(skill_config.database_url({'website':{'base_url':'http://localhost:8000','database_paths':{'hrs':'/home/hrs/'}}},'hrs'),'http://localhost:8000/home/hrs/')
 def test_context_mismatch(self):
  for document in [{},{'database':'klosa','language':'en'},{'database':'hrs','language':'ko'}]:
   with self.assertRaises(ValueError):k.require_context(document,'ko')
  with self.assertRaises(ValueError):k.require_context({'database':'klosa','language':'ko','url':'http://localhost:8000/home/klosa/'},'ko',k.page_url('http://localhost:8000','ko'))
 def test_exact_selection(self):
  action=selection.build_action('w10gender1 (KLoSA_str)=sex10',k.page_url('http://localhost:8000','ko'));action.update(database='klosa',language='ko')
  k.require_wave_source_identities(action,'ko');self.assertIn('language',selection.browser_code(action,'select'))
  action['input_text']='gender1 (KLoSA_str)=sex10'
  with self.assertRaises(ValueError):k.require_wave_source_identities(action,'ko')
 def test_selection_rejects_draft(self):
  with self.assertRaises(ValueError):selection.build_record_action({'status':'DRAFT'},k.page_url('http://localhost:8000','ko'))
 def test_package_regular_and_imputation(self):
  result=self.runvalid();self.assertEqual(result['language'],'ko');self.assertEqual(result['data'][k.REPEAT_MEMBER]['rows'],2)
  self.assertEqual((self.root/'raw_data.csv').read_text(encoding='utf-8-sig').splitlines()[1],'00001_10,00001,10,1')
 def test_ordinary_duplicate(self):
  self.reg.append(self.reg[0]);self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_person_wave_duplicate(self):
  self.reg.append(['different_id','00001','10','5']);self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_imputation_duplicate_draw(self):
  self.mi[1][4]='1';self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_rowindex_duplicate(self):
  self.mi[1][0]='1';self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_cross_member_metadata_conflict(self):
  self.mi[0][1]='00001_10';self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_wrong_dictionary_type(self):
  self.dictrows[1][4]='uniqID';self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_dictionary_missing_alias(self):
  self.dictrows.pop();self.write()
  with self.assertRaises(ValueError):self.runvalid()
 def test_wrong_member_owner(self):
  self.csv('raw_data.csv',k.IDENTIFIERS+['mi_sex1'],self.reg)
  with self.assertRaises(ValueError):self.runvalid()
 def test_unknown_member(self):
  with self.assertRaises(ValueError):k.validate_package(self.root,['raw_data_unknown.csv'],self.expected,'ko')
 def test_no_global_identity_whitelist_expansion(self):
  self.assertNotIn('Harmonized_id',recovery.identity_columns_for_member('raw_data.csv'))
 def test_en_rejects_wave10(self):
  with self.assertRaises(ValueError):self.runvalid('en')
 def test_archive_dispatch(self):
  archive=self.root/'fixture.zip'
  with zipfile.ZipFile(archive,'w') as z:
   for name in ['raw_data.csv',k.REPEAT_MEMBER,'raw_codebook.csv']:z.write(self.root/name,name)
  result=recovery.inspect_archive(archive,self.expected,'klosa','ko');self.assertEqual(result['language'],'ko')
  with self.assertRaises(ValueError):recovery.inspect_archive(archive,self.expected,'klosa','en')
 def test_watch_changed_language(self):
  snapshot=recovery.download_snapshot(self.root);snapshot.update(database='klosa',language='ko',expected_vars=self.expected)
  with self.assertRaises(ValueError):recovery.wait_for_download(self.root,snapshot,self.expected,0,database='klosa',language='en')
 def test_download_action_has_language(self):
  action=recovery.build_download_browser_action('http://localhost:8000','klosa','fake-attempt',2,self.root/'attempt.json','ko')
  k.require_context(action,'ko','http://localhost:8000/home/klosa/ko/');self.assertIn('/home/klosa/ko/',action['run_script'])
 @unittest.skipUnless((SCRIPTS/'klosa_source_read.js').exists(),'experimental source-read excluded from core integration')
 def test_source_read_bounded(self):
  a={'database':'klosa','language':'ko','kind':'detail','variable':'gender1','file':'KLoSA_str','periods':['Wave 9','Wave 10']}
  code=source_read.browser_code(a,k.page_url('http://localhost:8000','ko'),'klosa');self.assertIn('hover',code)
  a['periods']=['Wave 1','Wave 2','Wave 3']
  with self.assertRaises(ValueError):source_read.browser_code(a,k.page_url('http://localhost:8000','ko'),'klosa')
 def test_all_staged_python_compile(self):
  for name in ['skill_config.py','prepare_source_selection.py','playwright_session_action.py','recover_dbcodebook_export.py','check_definition_output.py','klosa_adapter_contract.py']:py_compile.compile(str(SCRIPTS/name),doraise=True)
 def main_mock(self,mode,lang='ko'):
  config={'website':{'base_url':'http://localhost:8000'}}
  action=selection.build_action('w10gender1 (KLoSA_str)=sex10',k.page_url('http://localhost:8000','ko'));action.update(database='klosa',language='ko')
  path=self.root/'selection.json';path.write_text(json.dumps(action),encoding='utf8')
  argv=['candidate','--mode',mode,'--database','klosa','--language',lang,'--tab-id','fake-id','--session','fake-session','--session-workdir',str(self.root),'--out',str(self.root/'receipt.json')]
  if mode=='select':argv+=['--action',str(path)]
  with patch.object(sys,'argv',argv),patch.object(browser,'load_config',return_value=config),patch.object(browser,'playwright_command',return_value=['never-executed']),patch.object(browser,'Session') as session:
   session.return_value.code.return_value={'ok':True,'status':'MOCK_UI_NOT_EXECUTED'}
   try: browser.main()
   except SystemExit as exc:self.assertEqual(exc.code,0)
   session.return_value.code.assert_called_once()
 def test_actual_main_login_offline(self):self.main_mock('login-status')
 def test_actual_main_selection_offline(self):self.main_mock('select')
 def test_actual_main_language_change_rejected(self):
  with self.assertRaises(ValueError):self.main_mock('select','en')
 def test_actual_main_download_language_change_rejected(self):
  action=recovery.build_download_browser_action('http://localhost:8000','klosa','mock-attempt',2,self.root/'attempt.json','ko')
  action_path=self.root/'action.json';action_path.write_text(json.dumps({'browser_action':action}),encoding='utf8')
  argv=['candidate','--mode','download','--database','klosa','--language','en','--action',str(action_path),'--tab-id','fake','--session','fake','--session-workdir',str(self.root),'--out',str(self.root/'receipt.json')]
  with patch.object(sys,'argv',argv),patch.object(browser,'load_config',return_value={'website':{'base_url':'http://localhost:8000'}}),patch.object(browser,'playwright_command',return_value=['never-executed']),patch.object(browser.subprocess,'run') as dispatched:
   with self.assertRaises(ValueError):browser.main()
   dispatched.assert_not_called();self.assertFalse((self.root/'attempt.json').exists())
 def test_output_identity_preservation(self):
  self.assertEqual(output_check.expected_raw_header('klosa',['sex10']),k.IDENTIFIERS+['sex10'])
  results=[]
  output_check.check_identity_values(self.root/'raw_data.csv',k.IDENTIFIERS+['sex10'],[k.IDENTIFIERS+['sex10'],['00001_10','00001','10',1]],k.IDENTIFIERS+['sex10'],results,'klosa')
  self.assertFalse(any(r.get('ok') is False for r in results))
  results=[]
  output_check.check_identity_values(self.root/'raw_data.csv',k.IDENTIFIERS+['sex10'],[k.IDENTIFIERS+['sex10'],['00001_10','changed','10',1]],k.IDENTIFIERS+['sex10'],results,'klosa')
  self.assertTrue(any(r.get('ok') is False for r in results))

if __name__=='__main__':unittest.main(verbosity=2)
