"""Verify historical component-display receipts; no preparation or generation."""
import hashlib,json
from pathlib import Path
MARKER='component_display_update.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def inputs(f,p):
 receipt=read(p/MARKER);bp=Path(receipt['baseline']).resolve();bp.relative_to((p/'component_updates').resolve())
 if sha(bp)!=receipt['baseline_hash']:raise ValueError('baseline modified')
 b=read(bp);folder=bp.parent
 if b['scope']!='component_display' or Path(b['formal'])!=f:raise ValueError('scope or target differ')
 for n,h in b['history'].items():
  if sha(folder/n)!=h:raise ValueError('history changed')
 if sha(p/'definition_search_record.json')!=b['history']['definition_search_record.json']:raise ValueError('plan changed')
 if sha(p/'website_sync_result.json')!=b['history']['website_sync_result.json']:raise ValueError('previous attachment decision changed')
 for n,h in b['proof_files'].items():
  if not Path(n).is_file() or sha(n)!=h:raise ValueError('previous metadata proof changed')
 from legacy_delivery_checks import verify_metadata_update
 verify_metadata_update(Path(b['proof_formal']),Path(b['proof_process']),b['topic'])
 prior=read(Path(b['proof_process'])/'definition_metadata_update.json')['candidate_hashes']
 if {n:h.upper() for n,h in b['hashes'].items()}!={n:h.upper() for n,h in prior.items()}:raise ValueError('previous proof does not bind baseline')
 if set(x.name for x in f.iterdir() if x.is_file())!=set(b['hashes']):raise ValueError('artifact set changed')
 for n,h in b['hashes'].items():
  q=folder/n if n in (b['r'],b['note'],b['detail']) else f/n
  if sha(q)!=h:raise ValueError('outside-scope change: '+n)
 return receipt,b,folder

def verify(f,p,topic):
 f=f.resolve();p=p.resolve();r,b,folder=inputs(f,p)
 if r['status']!='verified' or str(topic).zfill(3)!=b['topic']:raise ValueError('no verified component scope')
 if r['files']!={x.name:sha(x) for x in f.iterdir() if x.is_file()}:raise ValueError('candidate changed')
 if any(not Path(n).is_file() or sha(n)!=h for n,h in r['evidence'].items()):raise ValueError('generation evidence changed')
 names={'note':b['note'],'public_r':b['r'],'analysis_codebook':next(n for n in b['four'] if n.startswith('analysis_codebook_')),'analysis_db':next(n for n in b['four'] if n.startswith('analysis_db_')),'full_codebook':next(n for n in b['four'] if n.startswith('codebook_')),'full_db':next(n for n in b['four'] if n.startswith('db_'))}
 return {'ok':True,'scope':'component_display','status':'PUBLISH_READY','topic_id':b['topic'],'validation_basis':'Retained R AST and generation evidence, four unchanged workbooks and unchanged verified candidate; historical generation, research and calculations not rerun','audit':str(p/MARKER),'audit_sha256':sha(p/MARKER),'artifacts':{k:{'path':n,'sha256':sha(f/n)} for k,n in names.items()},'change_impact':{'path':MARKER,'sha256':sha(p/MARKER),'changed_dimensions':['component_display']},'result_check':{'scope':'component_display','status':'EXACT_COMPONENT_DISPLAY_PASS','historical_validation':'PRESERVED_NOT_REVALIDATED'},'reader_review':{'status':'UNCHANGED_OUTSIDE_DETAIL'},'questionnaire_rendering':{'status':'UNCHANGED'}}
