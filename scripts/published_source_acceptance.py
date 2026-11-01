"""Isolated, narrowly pinned published-source acceptance prototype; not deployed."""
import hashlib,json,re,html,os
from pathlib import Path
from native_user_authorization import verify_native_user_message
from published_scope_review import verify_semantic_review
STATUS='published_origin_unknown'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def nonempty_strings(value,label):
 if not isinstance(value,list) or not value or any(not isinstance(x,str) or not x.strip() for x in value) or len(value)!=len(set(value)):raise ValueError('Nonempty unique strings required: '+label)
 return value

def validate_policy(policy):
 for key in ['database','topic_id','purpose','required_disclosure']:
  if not isinstance(policy.get(key),str) or not policy[key].strip():raise ValueError('Policy requires nonempty '+key)
 if '<' in policy['required_disclosure'] or len(policy['required_disclosure'].strip())<8 or not any(c.isalnum() for c in policy['required_disclosure']):raise ValueError('Disclosure must be substantial visible plain text')
 groups=policy.get('groups')
 if not isinstance(groups,list) or not groups:raise ValueError('Policy sources cannot be empty')
 names=[];expected=set()
 for g in groups:
  if not isinstance(g,dict) or not isinstance(g.get('concept'),str) or not g['concept'].strip():raise ValueError('Policy source concept absent')
  names.append(g['concept'])
  for k in ['periods','raw_variables','source_identities']:nonempty_strings(g.get(k),'source '+k)
  expected.update((g['concept'],year) for year in g['periods'])
 if len(names)!=len(set(names)):raise ValueError('Policy source concepts repeat')
 scopes=policy.get('coverage_scopes')
 if not isinstance(scopes,list) or len(scopes)!=len(expected) or {(s.get('source_group'),s.get('period')) for s in scopes}!=expected:raise ValueError('Policy source-period coverage incomplete')
 for scope in scopes:
  group=next(g for g in groups if g['concept']==scope['source_group'])
  for k in ['raw_variables','source_identities']:
   if not set(nonempty_strings(scope.get(k),'period '+k)).issubset(group[k]):raise ValueError('Period source scope outside group')
 for group in groups:
  matching=[s for s in scopes if s['source_group']==group['concept']]
  for key in ['raw_variables','source_identities']:
   if set().union(*(set(s[key]) for s in matching))!=set(group[key]):raise ValueError('Period coverage omits declared group identities')
 results=nonempty_strings(policy.get('result_variables'),'results');projection=policy.get('projection_contract',{})
 periods=nonempty_strings(projection.get('projection_periods'),'projection periods')
 for k in ['scope','projection_rule','cross_period_input']:
  if not isinstance(projection.get(k),str) or not projection[k].strip():raise ValueError('Projection semantics absent: '+k)
 for k in ['status_value_inputs','projection_input_groups']:
  if not set(nonempty_strings(projection.get(k),k)).issubset(names):raise ValueError('Projection/value input group outside sources')
 available=set().union(*(set(g['periods']) for g in groups if g['concept'] in projection['projection_input_groups']))
 if not set(periods).issubset(available):raise ValueError('Output anchor outside its projection input periods')
 branches=policy.get('assignment_branch_ids',{})
 if set(branches)!=set(results):raise ValueError('Policy branch identities do not cover results')
 for value in branches.values():nonempty_strings(value,'branch identities')
 contracts=policy.get('assignment_branch_contracts')
 pairs={(v,y) for v in results for y in periods}
 if not isinstance(contracts,list) or len(contracts)!=len(pairs) or {(c.get('analysis_var'),c.get('period')) for c in contracts}!=pairs:raise ValueError('Policy branch semantics incomplete')
 for c in contracts:
  rows=c.get('branches',[])
  if len(rows)!=len(branches[c['analysis_var']]) or {b.get('branch_id') for b in rows}!=set(branches[c['analysis_var']]):raise ValueError('Policy semantic branches incomplete')
  for b in rows:
   for k in ['entry_condition','definition_result','evidence']:
    if not isinstance(b.get(k),str) or not b[k].strip():raise ValueError('Policy branch semantics absent: '+k)
 if type(policy.get('expected_persons')) is not int or policy['expected_persons']<=0:raise ValueError('Policy person universe must be positive')

def configured_policy(record,record_path):
 from skill_config import find_config,load_config
 config_path=find_config()
 if config_path is None:raise ValueError('No trusted execution configuration for scoped published-source policy')
 config=load_config(required=True);acceptance=record.get('published_source_acceptance')
 if not isinstance(acceptance,dict):raise ValueError('Missing explicit scoped authorization binding')
 requested=acceptance.get('policy_path')
 if not requested:raise ValueError('Policy needs a registered process path')
 requested_path=Path(requested)
 if not requested_path.is_absolute() and (requested_path.name!=requested or '..' in requested_path.parts):raise ValueError('Relative policy must be a same-directory filename')
 policy_path=(requested_path if requested_path.is_absolute() else Path(record_path).parent/requested_path).resolve();registered=[]
 entries=config.get('published_source_policies',[])
 if not isinstance(entries,list):raise ValueError('published_source_policies must be a list')
 for entry in entries:
  if not isinstance(entry,dict):raise ValueError('Registered policy must be an object')
  path=Path(os.path.expanduser(os.path.expandvars(entry.get('path',''))));path=path if path.is_absolute() else Path(config_path).parent/path
  if path.resolve()==policy_path and entry.get('sha256')==acceptance.get('policy_sha256'):registered.append(entry)
 if len(registered)!=1:raise ValueError('Policy is not uniquely registered in trusted execution configuration')
 if digest(policy_path)!=registered[0]['sha256']:raise ValueError('Registered process policy changed')
 return policy_path,load(policy_path)

def resolve_evidence_path(value,record_path,record):
 if value.startswith('formal:'):
  member=value[len('formal:'):]
  if not member or Path(member).name!=member:raise ValueError('formal: reference must be one package member')
  from skill_config import load_config,configured_path
  config=load_config(required=True);database=record['database'].lower()
  subdir=config.get('databases',{}).get(database,{}).get('formal_subdir')
  formal_root=configured_path(config,'formal_root')
  if not subdir or formal_root is None:raise ValueError('Configured formal topic root absent')
  topic_folder=Path(record_path).parent.name
  if not topic_folder.startswith(str(record['topic_id'])+'_'):raise ValueError('formal: reference needs its actual numbered topic directory')
  return formal_root/subdir/topic_folder/member
 p=Path(value);return p if p.is_absolute() else Path(record_path).parent/p
def validate(record,record_path):
 coverage=record.get('questionnaire_coverage',[])
 unknown=[x for x in coverage if x.get('status')==STATUS]
 acceptance=record.get('published_source_acceptance')
 if not unknown and acceptance is None:return None
 policy_path,policy=configured_policy(record,record_path)
 validate_policy(policy)
 if policy.get('deployment')!='ISOLATED_PROTOTYPE_ONLY':raise ValueError('Prototype is not deployable')
 if (record.get('database'),str(record.get('topic_id')))!=(policy['database'],policy['topic_id']):raise ValueError('Wrong topic/database')
 if record.get('schema_version')!=7:raise ValueError('Requires explicit v7 extension')
 if not isinstance(acceptance,dict) or acceptance.get('policy_sha256')!=digest(policy_path):raise ValueError('Missing exact authorization policy')
 auth=(policy_path.parent/policy['authorization']['path']).resolve()
 if not auth.is_relative_to(policy_path.parent):raise ValueError('Authorization must stay in scoped process policy directory')
 if digest(auth)!=policy['authorization']['sha256'] or acceptance.get('authorization_sha256')!=policy['authorization']['sha256']:raise ValueError('Authorization changed')
 native_authority=verify_native_user_message(load(auth),policy)
 if acceptance.get('purpose')!=policy['purpose']:raise ValueError('Wrong approved use')
 if record.get('source_groups') is None:raise ValueError('No sources')
 groups=[{k:g.get(k) for k in ['concept','periods','raw_variables','source_identities']} for g in record['source_groups']]
 if groups!=policy['groups']:raise ValueError('Source identity/alias/period scope changed')
 expected={(g['concept'],y) for g in policy['groups'] for y in g['periods']}
 actual=[(x.get('source_group'),x.get('period')) for x in unknown]
 if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('Unknown coverage must match all approved pairs exactly')
 scopes=[{k:x.get(k) for k in ['source_group','period','source_identities','raw_variables']} for x in unknown]
 if scopes!=policy['coverage_scopes']:raise ValueError('Per-period source/alias scope changed')
 if any(x.get('status')!=STATUS for x in coverage):raise ValueError('Cannot relabel unknown as questionnaire/not_applicable')
 for x in unknown:
  if x.get('evidence_ids') or x.get('provenance_state')!='unknown':raise ValueError('No fabricated questionnaire evidence or origin')
  if set(x.get('unknown_facts',[]))!={'field_generation','questionnaire_link','record_activity'}:raise ValueError('Missing unknown facts')
  evidence=x.get('published_field_evidence')
  if not isinstance(evidence,list) or not evidence:raise ValueError('Known published facts need referenced evidence')
  for ref in evidence:
   if not isinstance(ref,dict) or not ref.get('path') or not ref.get('sha256'):raise ValueError('Published fact reference needs path/hash')
   f=resolve_evidence_path(ref['path'],record_path,record)
   if digest(f)!=ref['sha256']:raise ValueError('Published fact evidence changed')
 for q in record.get('questionnaire_evidence',[]):
  if any((q.get('source_group'),y) in expected for y in q.get('periods',[])):raise ValueError('Unknown source cannot be a fake question')
 package=acceptance.get('package',{})
 if package!=policy['package']:raise ValueError('Package hash declaration changed')
 base=Path(record_path).parent
 for name,sha in policy['package'].items():
  member=acceptance.get('package_paths',{}).get(name)
  if not member:raise ValueError('Package file reference absent')
  p=resolve_evidence_path(member,record_path,record)
  if digest(p)!=sha:raise ValueError('Actual package/raw changed')
 if acceptance.get('disclosure_text')!=policy['required_disclosure']:raise ValueError('Required limitation must be preserved')
 operational=record.get('operational_assignment_review',{})
 ref=operational.get('data_evidence',{})
 if operational.get('status')!='exhaustive' or type(operational.get('unclassified_persons')) is not int or operational['unclassified_persons']!=0 or operational.get('origin_generation')!='unknown':raise ValueError('Separate exhaustive assignment and unknown generation states required')
 if ref.get('sha256')!=policy['operational_evidence_sha256'] or not ref.get('path'):raise ValueError('Actual exhaustive-assignment evidence not pinned')
 f=Path(ref['path']);f=f if f.is_absolute() else Path(record_path).parent/f
 if digest(f)!=ref['sha256']:raise ValueError('Operational evidence changed')
 measured=load(f)
 if measured.get('scope')!='operational_assignment_only_not_field_generation' or measured.get('raw_sha256')!=policy['package']['raw_data.csv']:raise ValueError('Wrong operational evidence scope/input')
 if measured.get('persons')!=policy['expected_persons'] or measured.get('classified_persons')!=policy['expected_persons'] or measured.get('unclassified_persons')!=0 or measured.get('duplicate_person_assignments')!=0 or measured.get('origin_generation')!='unknown':raise ValueError('Operational person partition does not close')
 if any(type(measured.get(k)) is not int for k in ['persons','classified_persons','unclassified_persons','duplicate_person_assignments']):raise ValueError('Measured person counts must be integers')
 # Unknown origins still require actual assignment closure. Never turn them into N/A.
 if record.get('approved_analysis_vars')!=policy['result_variables']:raise ValueError('Wrong result scope')
 if record.get('projection_definition')!=policy['projection_contract']:raise ValueError('Output projection changed or confused with source periods')
 periods=policy['projection_contract']['projection_periods']
 anchors=measured.get('result_anchor_period_counts',{})
 if set(anchors)!=set(periods) or sum(c.get('people',-1) for c in anchors.values())!=policy['expected_persons']:raise ValueError('Operational anchor partition does not cover the person universe')
 planned={(v,y) for v in policy['result_variables'] for y in periods}
 closures=record.get('published_assignment_closure',[])
 if {(x.get('analysis_var'),x.get('period')) for x in closures}!=planned or len(closures)!=len(planned):raise ValueError('Missing/duplicate assignment coverage')
 evidence_payload=None
 for c in closures:
  if type(c.get('unexplained_count')) is not int or c['unexplained_count']!=0 or c.get('generation_origin')!='unknown':raise ValueError('Assignment unclassified count must be 0; field generation remains independently unknown')
  ref=c.get('data_evidence',{})
  if ref.get('sha256')!=policy['assignment_data_sha256'] or not ref.get('path'):raise ValueError('Assignment evidence not pinned')
  f=Path(ref['path']);f=f if f.is_absolute() else Path(record_path).parent/f
  if digest(f)!=ref['sha256']:raise ValueError('Assignment evidence changed')
  payload=load(f);evidence_payload=payload
  if payload.get('raw_sha256')!=policy['package']['raw_data.csv']:raise ValueError('Assignment evidence uses wrong raw')
  cell=payload['result_anchor_period_counts'][c['period']]
  if measured['result_anchor_period_counts'][c['period']]!=cell:raise ValueError('Independent operational recount differs')
  if type(c.get('denominator_persons')) is not int or c['denominator_persons']!=cell['people']:raise ValueError('Wrong anchor-person denominator')
  counts=cell[c['analysis_var']]
  if set(counts)-set(policy['assignment_branch_ids'][c['analysis_var']]) or any(type(v) is not int or v<0 for v in counts.values()) or sum(counts.values())!=cell['people']:raise ValueError('Measured branch dictionary is not an exact partition')
  semantic=next(x for x in policy['assignment_branch_contracts'] if (x['analysis_var'],x['period'])==(c['analysis_var'],c['period']))
  if [{k:b.get(k) for k in ['branch_id','entry_condition','definition_result','evidence']} for b in c.get('branches',[])]!=semantic['branches']:raise ValueError('Assignment branch semantics differ from bound policy')
  branch_ids=[x.get('branch_id') for x in c.get('branches',[])]
  if len(branch_ids)!=len(set(branch_ids)) or set(branch_ids)!=set(policy['assignment_branch_ids'][c['analysis_var']]):raise ValueError('Missing/duplicate/extra branch identity')
  if sum(x.get('observed_count',-1) for x in c.get('branches',[]))!=cell['people']:raise ValueError('Branch counts do not cover anchor persons')
  for branch in c.get('branches',[]):
   if branch.get('observed_count')!=counts.get(branch['branch_id'],0):raise ValueError('Branch count differs from pinned evidence')
  if not c.get('branches') or c.get('scope')!='operational_assignment_not_generation_proof':raise ValueError('Missing bounded assignment branches')
  for branch in c['branches']:
   for k in ['entry_condition','definition_result','evidence']:
    if not branch.get(k):raise ValueError('Missing assignment evidence')
   if type(branch.get('observed_count')) is not int or branch['observed_count']<0:raise ValueError('Missing observed count')
 scope_review=verify_semantic_review(record,record_path,policy_path,auth,policy,load(auth))
 return {'pairs':expected,'disclosure':policy['required_disclosure'],'assignment_pairs':planned,'origin':'unknown','operational_assignment':'exhaustive','unclassified_persons':0,'authorization_basis':native_authority['provenance'],'authorization_scope_review':scope_review}

def normalized_text(text):return ''.join(html.unescape(re.sub(r'<[^>]+>','',str(text))).replace('`','').split())
def check_disclosure(record,record_path,visible_text):
 result=validate(record,record_path)
 if not result:return None
 wanted=normalized_text(result['disclosure']);text=str(visible_text)
 if '<table' in text.lower():
  from check_reader_copy import Document,Element
  root=Document(text).root
  rows=[[cell.text() for cell in row.children if isinstance(cell,Element) and cell.tag=='td'] for row in root.find(lambda node:node.tag=='tr')]
  for variable in configured_policy(record,record_path)[1]['result_variables']:
   matches=[row for row in rows if len(row)==3 and row[0].strip()==variable]
   if len(matches)!=1 or wanted not in normalized_text(matches[0][1]):raise ValueError('Unknown origin disclosure missing/misplaced in rendered Criteria: '+variable)
  from published_disclosure_visibility import visible_criteria_texts
  visible=visible_criteria_texts(text,configured_policy(record,record_path)[1]['result_variables'],result['disclosure'])
  for variable,value in visible.items():
   if value is None or wanted not in normalized_text(value):raise ValueError('Unknown origin disclosure is not visibly rendered in Criteria: '+variable)
 else:
  if re.search(r'<(?:span|div|style|script|link|section)\b',text,re.I):raise ValueError('Scoped disclosure copy must remain plain reader text')
  criteria=re.search(r'(?ms)^## Criteria\s*\n(.*?)(?=^## |\Z)',text)
  if not criteria:raise ValueError('No actual Criteria disclosure scope')
  for variable in configured_policy(record,record_path)[1]['result_variables']:
   blocks=re.findall(r'(?ms)^### '+re.escape(variable)+r'\s*\n(.*?)(?=^### |\Z)',criteria.group(1))
   if len(blocks)!=1:raise ValueError('Missing/duplicate result disclosure scope: '+variable)
   note=re.search(r'(?ms)^#### 注意点\s*\n(.*?)(?=^#### |\Z)',blocks[0])
   if not note or wanted not in normalized_text(note.group(1)):raise ValueError('Unknown origin disclosure missing/misplaced in result 注意点: '+variable)
 return result
