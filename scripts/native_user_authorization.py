"""Read native human-message evidence; never treat process JSON as human authority.

This verifies provenance and exact words, not the semantics of an arbitrary policy.
Current policy-scope review remains an independent formal-run prerequisite.
"""
from pathlib import Path
from functools import lru_cache
import hashlib,json,re,os,itertools

def native_sessions_root():
    if os.name == 'nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,40,None,0,buffer)!=0:
            raise ValueError('Native OS profile cannot be resolved')
        profile=Path(buffer.value)
    else:
        import pwd
        profile=Path(pwd.getpwuid(os.getuid()).pw_dir)
    return (profile/'.codex/sessions').resolve()

@lru_cache(maxsize=16)
def _read(path,line,size,mtime):
    with Path(path).open(encoding='utf-8') as stream:
        first=json.loads(next(stream))
    with Path(path).open(encoding='utf-8') as stream:
        raw=next(itertools.islice(stream,line-1,line),None)
    if raw is None:raise ValueError('Native user-message line absent')
    return first,raw.rstrip('\r\n'),json.loads(raw)

def verify_native_user_message(authority,policy):
    if authority.get('authority_kind')!='native_user_message':
        raise ValueError('Delegated/self-authored authority is not native human-message evidence')
    ref=authority.get('native_user_message')
    if not isinstance(ref,dict):raise ValueError('Missing native human-message reference')
    path=Path(ref.get('path','')).resolve();root=native_sessions_root()
    if not path.is_relative_to(root) or path.suffix!='.jsonl':
        raise ValueError('Human authority must be read from the native host sessions directory')
    line=ref.get('line')
    if type(line) is not int or line<2:raise ValueError('Invalid native-message line')
    stat=path.stat();first,raw,event=_read(str(path),line,stat.st_size,stat.st_mtime_ns)
    meta=first.get('payload',{})
    if first.get('type')!='session_meta' or meta.get('session_id',meta.get('id'))!=ref.get('session_id'):
        raise ValueError('Native session identity differs')
    if ref['session_id'] not in path.stem:raise ValueError('Native session file identity differs')
    if hashlib.sha256(raw.encode('utf-8')).hexdigest()!=ref.get('record_sha256'):
        raise ValueError('Native user-message bytes changed')
    payload=event.get('payload',{});retained=event.get('metadata',{}).get('retained_source',{})
    if event.get('type')!='response_item' or payload.get('type')!='message' or payload.get('role')!='user':
        raise ValueError('Referenced native message is not a human user message')
    if payload.get('id')!=ref.get('message_id') or event.get('timestamp')!=ref.get('timestamp'):
        raise ValueError('Native user-message identity/time differs')
    if retained.get('id',{}).get('role')!='user' or retained.get('complete') is not True:
        raise ValueError('Native human retention/provenance is incomplete')
    if event.get('metadata',{}).get('client_authored') is not False:
        raise ValueError('Native human-message provenance is not verified')
    content=payload.get('content',[])
    text='\n'.join(part.get('text','') for part in content if part.get('type')=='input_text')
    match=re.fullmatch(r'\s*<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>\s*',text,re.S)
    if not match:raise ValueError('Unsupported native authorization form; do not infer approval')
    replies=json.loads(match.group(1))
    matches=[x for x in replies if x.get('questionItemId')==ref.get('question_item_id')]
    if len(matches)!=1:raise ValueError('Native question/answer identity missing or duplicated')
    reply=matches[0]
    if reply.get('question')!=ref.get('question') or reply.get('answer')!=ref.get('answer'):
        raise ValueError('Declared question/answer differs from actual native human words')
    if not isinstance(reply.get('answer'),str) or not reply['answer'].strip():raise ValueError('Native human answer is empty')
    topic=re.sub(r'\s+','',policy['database']+str(policy['topic_id'])).casefold()
    if topic not in re.sub(r'\s+','',reply['question']).casefold():raise ValueError('Native question does not identify this exact database/topic')
    return {'provenance':'native_human_question_answer_verified','scope_semantics':'requires_current_independent_policy_review','question':reply['question'],'answer':reply['answer']}
