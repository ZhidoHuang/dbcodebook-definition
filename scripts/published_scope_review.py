"""Require a real independent semantic-scope verdict, not policy/config approval."""
from pathlib import Path
import json,re,hashlib
from native_user_authorization import native_sessions_root
ROLE='发布来源语义授权复核'
MARKER='dbcodebook-published-source-scope-review'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_semantic_review(record,record_path,policy_path,authority_path,policy,authority):
 from execution_report import validate_stage_review,read_review_log,parse_time
 on_disk=json.loads(Path(record_path).read_text(encoding='utf-8-sig'))
 if json.dumps(on_disk,sort_keys=True,ensure_ascii=False)!=json.dumps(record,sort_keys=True,ensure_ascii=False):raise ValueError('In-memory source record differs from the independently reviewed file')
 report_path=Path(record_path).parent/'execution_report.json'
 if not report_path.is_file():raise ValueError('Current independent published-source semantic-scope review is required')
 report=json.loads(report_path.read_text(encoding='utf-8-sig'))
 if report.get('database')!=record['database'] or str(report.get('topic_id'))!=str(record['topic_id']):raise ValueError('Semantic review report identifies another topic')
 review=validate_stage_review(report,ROLE)
 if review.get('mode')!='independent':raise ValueError('Isolated/self semantic review cannot authorize a policy')
 agent=review.get('prior_agent_record') or next((x for x in report.get('reviews',[]) if x.get('agent_id')==review.get('agent_id') and x.get('role')==ROLE),None)
 if not agent:raise ValueError('Semantic review needs a registered real independent agent')
 log=Path(agent.get('log_path','')).resolve()
 if not log.is_relative_to(native_sessions_root()) or log.suffix!='.jsonl':raise ValueError('Semantic review must have native host reviewer-log provenance')
 live=read_review_log(log,ROLE)
 if live['agent_id']!=agent['agent_id'] or live['parent_thread_id']!=authority['native_user_message']['session_id']:raise ValueError('Independent reviewer identity/parent differs from native user task')
 registered={x['turn_id']:x for x in agent.get('rounds',[])}
 actual={x['turn_id']:x for x in live['rounds']}
 if not registered or any(t not in actual or actual[t].get('outcome')!='completed' or not actual[t].get('finished_at') for t in registered):raise ValueError('Native semantic review has no completed registered turn')
 for stage in report.get('stages',[]):
  own=stage.get('model_evidence',{}).get('log')
  if stage.get('role')=='执行者' and own and Path(own).resolve()==log:raise ValueError('Executor session cannot supply independent scope review')
 expected_files={Path(policy_path).name:digest(policy_path),Path(authority_path).name:digest(authority_path),**policy['package']}
 for name,sha in expected_files.items():
  bound=[Path(p) for p,h in review['inputs'].items() if Path(p).name==name]
  if len(bound)!=1 or digest(bound[0])!=sha:raise ValueError('Semantic review does not bind current exact policy/authority/package: '+name)
 sources=[Path(p) for p in review['inputs'] if Path(p).name=='definition_search_record.json']
 if len(sources)!=1 or digest(sources[0])!=digest(record_path):raise ValueError('Semantic review source snapshot differs')
 expected={'schema_version':1,'review_kind':'published_source_semantic_authorization','decision':'pass','database':record['database'],'topic_id':str(record['topic_id']),'purpose':policy['purpose'],'policy_sha256':digest(policy_path),'source_record_sha256':digest(record_path),'authorization_evidence_sha256':digest(authority_path),'native_user_record_sha256':authority['native_user_message']['record_sha256']}
 verdicts=[]
 with log.open(encoding='utf-8-sig') as stream:
  for line in stream:
   event=json.loads(line);payload=event.get('payload',{})
   if event.get('type')!='response_item' or payload.get('type')!='message' or payload.get('role')!='assistant':continue
   timestamp=event.get('timestamp')
   if not timestamp or parse_time(timestamp)<parse_time(review['started_at']) or parse_time(timestamp)>parse_time(review['finished_at']):continue
   text='\n'.join(c.get('text','') for c in payload.get('content',[]) if c.get('type')=='output_text')
   for match in re.finditer(r'<'+MARKER+r'>\s*(.*?)\s*</'+MARKER+r'>',text,re.S):
    try:value=json.loads(match.group(1))
    except json.JSONDecodeError:continue
    if all(value.get(k)==v for k,v in expected.items()):verdicts.append(value)
 if not verdicts:raise ValueError('No native independent pass verdict binds the exact policy, source, purpose and human words')
 verdict=verdicts[-1]
 for key in ['direct_user_authorization','approved_scope']:
  if not isinstance(verdict.get(key),str) or not verdict[key].strip():raise ValueError('Independent scope explanation absent: '+key)
 if not isinstance(verdict.get('technical_interpretations'),list) or not verdict['technical_interpretations'] or any(not isinstance(x,str) or not x.strip() for x in verdict['technical_interpretations']):raise ValueError('Independent review must distinguish technical interpretation from direct user authorization')
 if verdict.get('unresolved_decisions')!=[]:raise ValueError('Independent semantic scope still has unresolved user decisions')
 return {'status':'pass','role':ROLE,'reviewer_agent_id':agent['agent_id'],'policy_sha256':expected['policy_sha256'],'native_user_record_sha256':expected['native_user_record_sha256']}
