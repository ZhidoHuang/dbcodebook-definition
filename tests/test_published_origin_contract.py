"""Synthetic contract fixtures only; none is authorization for a real topic."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import published_source_acceptance as api

class ScopedPublishedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.path=self.base/'record.json'
  def put(name,payload):
   p=self.base/name;p.write_text(json.dumps(payload),encoding='utf-8');return p
  raw=put('raw_data.csv',{'fixture':'SYNTHETIC_ONLY'});facts=put('facts.json',{'fixture':'published identity only'})
  self.auth=put('authority.json',{'authority_kind':'native_user_message','native_user_message':{'fixture':'SYNTHETIC_ONLY_NOT_REAL_AUTHORIZATION'}})
  counts={'2000':{'people':2,'synthetic_result':{'observed':2}}}
  measured=put('partition.json',{'scope':'operational_assignment_only_not_field_generation','origin_generation':'unknown','raw_sha256':api.digest(raw),'persons':2,'classified_persons':2,'unclassified_persons':0,'duplicate_person_assignments':0,'result_anchor_period_counts':counts})
  assignment=put('counts.json',{'raw_sha256':api.digest(raw),'result_anchor_period_counts':counts})
  group={'concept':'synthetic source','periods':['2000'],'raw_variables':['source_alias'],'source_identities':['source (module)']}
  scope={'source_group':group['concept'],'period':'2000','raw_variables':group['raw_variables'],'source_identities':group['source_identities']}
  projection={'scope':'individual output anchor distinct from source periods','projection_periods':['2000'],'status_value_inputs':['synthetic source'],'projection_input_groups':['synthetic source'],'projection_rule':'synthetic anchor','cross_period_input':'synthetic fixture'}
  policy={'database':'TEST_DATABASE','topic_id':'999','purpose':'synthetic_bounded_use','deployment':'ISOLATED_PROTOTYPE_ONLY','authorization':{'path':self.auth.name,'sha256':api.digest(self.auth)},'groups':[group],'coverage_scopes':[scope],'package':{'raw_data.csv':api.digest(raw)},'required_disclosure':'Published generation remains unknown.','result_variables':['synthetic_result'],'projection_contract':projection,'expected_persons':2,'operational_evidence_sha256':api.digest(measured),'assignment_data_sha256':api.digest(assignment),'assignment_branch_ids':{'synthetic_result':['observed']}}
  policy['assignment_branch_contracts']=[{'analysis_var':'synthetic_result','period':'2000','branches':[{'branch_id':'observed','entry_condition':'SYNTHETIC','definition_result':'1','evidence':'synthetic counts'}]}]
  self.policy=put('policy.json',policy);self.config=put('config.json',{'schema_version':1,'published_source_policies':[{'path':str(self.policy),'sha256':api.digest(self.policy)}]})
  self.r={'database':policy['database'],'topic_id':policy['topic_id'],'schema_version':7,'source_groups':[group],'approved_analysis_vars':['synthetic_result'],'projection_definition':projection,'questionnaire_evidence':[],'questionnaire_coverage':[{**scope,'status':'published_origin_unknown','provenance_state':'unknown','unknown_facts':['field_generation','questionnaire_link','record_activity'],'evidence_ids':[],'published_field_evidence':[{'path':str(facts),'sha256':api.digest(facts)}]}],'published_source_acceptance':{'policy_path':str(self.policy),'policy_sha256':api.digest(self.policy),'authorization_sha256':api.digest(self.auth),'purpose':policy['purpose'],'package':policy['package'],'package_paths':{'raw_data.csv':str(raw)},'disclosure_text':policy['required_disclosure']},'operational_assignment_review':{'status':'exhaustive','unclassified_persons':0,'origin_generation':'unknown','data_evidence':{'path':str(measured),'sha256':api.digest(measured)}},'published_assignment_closure':[{'analysis_var':'synthetic_result','period':'2000','scope':'operational_assignment_not_generation_proof','denominator_persons':2,'unexplained_count':None,'data_evidence':{'path':str(assignment),'sha256':api.digest(assignment)},'branches':[{'branch_id':'observed','observed_count':2,'entry_condition':'SYNTHETIC','definition_result':'1','evidence':'synthetic counts'}]}]}
  self.r['published_assignment_closure'][0].update(unexplained_count=0,generation_origin='unknown')
  self.env=patch.dict(os.environ,{'DBCODEBOOK_DEFINITION_CONFIG':str(self.config)});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def invoke(self,record=None):
  # Explicit provider mock for contract units, never an actual authority receipt.
  with patch.object(api,'verify_native_user_message',return_value={'provenance':'MOCK_UNIT_ONLY'}),patch.object(api,'verify_semantic_review',return_value={'status':'MOCK_UNIT_ONLY_NOT_REAL_REVIEW'}):
   return api.validate(self.r if record is None else record,self.path)
 def disclose(self,text):
  with patch.object(api,'verify_native_user_message',return_value={'provenance':'MOCK_UNIT_ONLY'}),patch.object(api,'verify_semantic_review',return_value={'status':'MOCK_UNIT_ONLY_NOT_REAL_REVIEW'}):
   return api.check_disclosure(self.r,self.path,text)
 def change_policy(self,mutate):
  policy=json.loads(self.policy.read_text());mutate(policy);self.policy.write_text(json.dumps(policy));self.r['published_source_acceptance']['policy_sha256']=api.digest(self.policy);self.config.write_text(json.dumps({'schema_version':1,'published_source_policies':[{'path':str(self.policy),'sha256':api.digest(self.policy)}]}))
 def reject(self,mutate):
  r=copy.deepcopy(self.r);mutate(r)
  with self.assertRaises((ValueError,OSError)):self.invoke(r)
 def test_distinct_states(self):
  result=self.invoke();self.assertEqual(('unknown','exhaustive',0),(result['origin'],result['operational_assignment'],result['unclassified_persons']))
 def test_no_activation_by_record_alone(self):
  self.config.write_text('{"schema_version":1}')
  with self.assertRaises(ValueError):self.invoke()
 def test_policy_content_tamper(self):
  self.policy.write_text('{}')
  with self.assertRaises(ValueError):self.invoke()
 def test_authority_tamper(self):
  self.auth.write_text('{}')
  with self.assertRaises(ValueError):self.invoke()
 def test_other_topic(self):self.reject(lambda r:r.update(topic_id='998'))
 def test_other_database(self):self.reject(lambda r:r.update(database='OTHER'))
 def test_other_source(self):self.reject(lambda r:r['source_groups'][0].update(raw_variables=['other']))
 def test_other_period(self):self.reject(lambda r:r['questionnaire_coverage'][0].update(period='2001'))
 def test_other_package(self):self.reject(lambda r:r['published_source_acceptance']['package'].update({'raw_data.csv':'0'*64}))
 def test_not_applicable_laundering(self):self.reject(lambda r:r['questionnaire_coverage'][0].update(status='not_applicable'))
 def test_questionnaire_laundering(self):self.reject(lambda r:r['questionnaire_coverage'][0].update(status='questionnaire'))
 def test_missing_field_fact_hash(self):self.reject(lambda r:r['questionnaire_coverage'][0]['published_field_evidence'][0].pop('sha256'))
 def test_wrong_person_count(self):self.reject(lambda r:r['published_assignment_closure'][0].update(denominator_persons=1))
 def test_nonzero_unclassified(self):self.reject(lambda r:r['operational_assignment_review'].update(unclassified_persons=1))
 def test_boolean_count_rejected(self):self.reject(lambda r:r['operational_assignment_review'].update(unclassified_persons=False))
 def test_missing_assignment(self):self.reject(lambda r:r.update(published_assignment_closure=[]))
 def test_duplicate_branch(self):self.reject(lambda r:r['published_assignment_closure'][0]['branches'].append(copy.deepcopy(r['published_assignment_closure'][0]['branches'][0])))
 def test_assignment_unclassified_cannot_hide_as_unknown(self):self.reject(lambda r:r['published_assignment_closure'][0].update(unexplained_count=None))
 def test_legacy_no_registration_required(self):self.assertIsNone(api.validate({'schema_version':7,'questionnaire_coverage':[]},self.path))
 def test_disclosure_copy(self):self.assertIsNotNone(self.disclose('## Criteria\n### synthetic_result\n#### 注意点\nPublished generation remains unknown.'))
 def test_disclosure_actual_cell_with_nested_detail(self):self.assertIsNotNone(self.disclose('<table><tr><td>synthetic_result</td><td>Published generation remains unknown.</td><td><table><tr><td>nested</td></tr></table></td></tr></table>'))
 def test_disclosure_wrong_cell(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td>missing</td><td>Published generation remains unknown.</td></tr></table>')
 def test_disclosure_summary_only(self):
  with self.assertRaises(ValueError):self.disclose('Published generation remains unknown.\n## Criteria\n### synthetic_result\n#### 注意点\nmissing')
 def test_production_rejects_self_authored_authority(self):
  # No mock: a synthetic process receipt must never establish native user evidence.
  with self.assertRaises(ValueError):api.validate(self.r,self.path)
 def test_empty_disclosure_policy_rejected(self):
  self.change_policy(lambda p:p.update(required_disclosure=''));self.r['published_source_acceptance']['disclosure_text']=''
  with self.assertRaises(ValueError):self.invoke()
 def test_empty_sources_policy_rejected(self):
  self.change_policy(lambda p:p.update(groups=[],coverage_scopes=[]));self.r.update(source_groups=[],questionnaire_coverage=[])
  with self.assertRaises(ValueError):self.invoke()
 def test_empty_results_policy_rejected(self):
  self.change_policy(lambda p:p.update(result_variables=[],assignment_branch_ids={},assignment_branch_contracts=[]));self.r.update(approved_analysis_vars=[],published_assignment_closure=[])
  with self.assertRaises(ValueError):self.invoke()
 def test_empty_projection_periods_rejected(self):
  self.change_policy(lambda p:p['projection_contract'].update(projection_periods=[]));self.r['projection_definition']['projection_periods']=[]
  with self.assertRaises(ValueError):self.invoke()
 def test_unrelated_branch_condition_rejected(self):self.reject(lambda r:r['published_assignment_closure'][0]['branches'][0].update(entry_condition='unrelated'))
 def test_wrong_branch_result_rejected(self):self.reject(lambda r:r['published_assignment_closure'][0]['branches'][0].update(definition_result='0'))
 def test_display_none_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td><span style="display:none">Published generation remains unknown.</span>Visible</td><td>detail</td></tr></table>')
 def test_stylesheet_hidden_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<style>.concealed {display:none}</style><table><tr><td>synthetic_result</td><td><span class="concealed">Published generation remains unknown.</span>Visible</td><td>detail</td></tr></table>')
 def test_opacity_zero_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td><span style="opacity:0">Published generation remains unknown.</span>Visible</td><td>detail</td></tr></table>')
 def test_negative_page_coordinates_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td><span style="position:absolute;left:-10000px;top:-10000px">Published generation remains unknown.</span>Visible</td><td>detail</td></tr></table>')
 def test_extreme_transparency_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td><span style="opacity:0.001">Published generation remains unknown.</span>Visible</td><td>detail</td></tr></table>')
 def test_white_on_white_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td style="color:white;background:white">Published generation remains unknown.</td><td>detail</td></tr></table>')
 def test_covering_overlay_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<div style="position:fixed;inset:0;background:black;z-index:9999">Cover</div><table><tr><td>synthetic_result</td><td>Published generation remains unknown.</td><td>detail</td></tr></table>')
 def test_native_words_without_semantic_review_still_block(self):
  self.path.write_text(json.dumps(self.r),encoding='utf-8')
  with patch.object(api,'verify_native_user_message',return_value={'provenance':'MOCK_NATIVE_ONLY'}):
   with self.assertRaisesRegex(ValueError,'semantic-scope review'):api.validate(self.r,self.path)
 def test_pointer_events_none_overlay_rejected(self):
  with self.assertRaises(ValueError):self.disclose('<table><tr><td>synthetic_result</td><td style="position:relative"><span>Published generation remains unknown.</span><div style="position:absolute;inset:0;background:black;z-index:999;pointer-events:none"></div></td><td>detail</td></tr></table>')
 def test_formal_reference_config_relative_and_environment(self):
  cfg=json.loads(self.config.read_text());cfg.update(paths={'formal_root':'$PUBLISHED_FIXTURE_FORMAL_ROOT'},databases={'test_database':{'formal_subdir':'TestDB'}});self.config.write_text(json.dumps(cfg))
  path=self.base/'records/999_fixture/record.json';path.parent.mkdir(parents=True)
  before=Path.cwd();other=self.base/'different-working-directory';other.mkdir()
  try:
   os.chdir(other)
   with patch.dict(os.environ,{'PUBLISHED_FIXTURE_FORMAL_ROOT':'relative-formal'}):
    self.assertEqual(self.base/'relative-formal/TestDB/999_fixture/raw_data.csv',api.resolve_evidence_path('formal:raw_data.csv',path,self.r))
  finally:os.chdir(before)
 def test_formal_reference_absolute_config_preserved(self):
  cfg=json.loads(self.config.read_text());cfg.update(paths={'formal_root':str(self.base/'absolute-formal')},databases={'test_database':{'formal_subdir':'TestDB'}});self.config.write_text(json.dumps(cfg));path=self.base/'records/999_fixture/record.json'
  self.assertEqual(self.base/'absolute-formal/TestDB/999_fixture/raw_data.csv',api.resolve_evidence_path('formal:raw_data.csv',path,self.r))
if __name__=='__main__':unittest.main(verbosity=2)
