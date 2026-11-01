"""Retained proof checks; no topic rewriting or optional replay."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_report as er
from exploration_handoff import POLICY, ROLES, plan_hash
import legacy_delivery_checks as update


def fragment_guards():
    import definition_summary as summary
    plain = '# Title\n\n## 摘要导读\n\nold\n\n```text\ntree\n```\n\n## Criteria\n\nformula'
    rendered = plain.replace('old', '<div data-summary-entry-paragraph="true">old <span>text</span></div>')
    assert summary.replacement(plain, 'new') == plain.replace('old', 'new')
    assert summary.replacement(rendered, '<div>new</div>', True) == rendered.replace('<div data-summary-entry-paragraph="true">old <span>text</span></div>', '<div>new</div>')
    assert summary.visible('<div>①**name** &amp; value</div>') == '①name&value'
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp); formal = home/'formal'; process = home/'process'; before = home/'before'
        for p in (formal, process, before): p.mkdir()
        artifacts = {'copy':'文案.md', 'note':'note.md', 'public_r':'define.R',
                     'analysis_db':'data.xlsx', 'analysis_codebook':'dictionary.xlsx'}
        for role, name in artifacts.items():
            (formal/name).write_text(rendered if role=='note' else plain if role=='copy' else role, encoding='utf-8')
        hashes = {p.name:summary.digest(p) for p in formal.iterdir()}
        for role in ('copy','note'): shutil.copy2(formal/artifacts[role], before/artifacts[role])
        draft = {'database':'Test', 'topic':'001', 'path':str(formal), 'proposed':'new', 'count':1,
                 'numbered_results':[{'variable':'x'}], 'variables':['x'],
                 'formal_bindings':{str(formal/artifacts[k]): hashes[artifacts[k]] for k in ('copy','note')}}
        drafts=home/'drafts.json';drafts.write_text(json.dumps([draft]),encoding='utf-8')
        review=home/'review.md';review.write_text('User-approved new introduction',encoding='utf-8')
        receipt={'database':'Test','topic':'001','before':str(before),'before_hashes':hashes,
                 'changed_files':[artifacts[k] for k in ('copy','note')], 'artifacts':artifacts,
                 'rendered_summary':'<div>new</div>', 'approval':{'review':str(review), 'review_sha256':summary.digest(review),
                 'drafts':str(drafts), 'drafts_sha256':summary.digest(drafts)}}
        (process/summary.RECEIPT).write_text(json.dumps(receipt),encoding='utf-8')
        (formal/'文案.md').write_text(summary.replacement(plain,'new'),encoding='utf-8')
        (formal/'note.md').write_text(summary.replacement(rendered,'<div>new</div>',True),encoding='utf-8')
        assert summary.verify(formal,process,'001')['scope']=='summary_only'
        for target in (formal/'note.md', formal/'define.R', review):
            original=target.read_bytes();target.write_bytes(original+b' changed outside scope')
            try: summary.verify(formal,process,'001')
            except ValueError: pass
            else: raise AssertionError('Summary-only update accepted changed input: '+str(target))
            target.write_bytes(original)
    text = 'before\n<old>\nafter'
    assert update.apply_fragment_patches(text, [{'field':'references','before':'<old>','after':'<new>'}]) == 'before\n<new>\nafter'
    for value, patches in [
        (text, [{'field':'references','before':'','after':'x'}]),
        ('old old', [{'field':'references','before':'old','after':'x'}]),
        ('abc', [{'field':'summary','before':'abc','after':'x'}, {'field':'insight','before':'bc','after':'y'}])]:
        try: update.apply_fragment_patches(value, patches)
        except ValueError: pass
        else: raise AssertionError('Unsafe fragment replacement accepted')
    sample = '# Title\n\n## 摘要导读\n\nold\n\n## Criteria\n\nformula\n\n## 参考资料说明\n\nold'
    assert update.outside_text_sections(sample) == update.outside_text_sections(sample.replace('old','new'))
    for changed in (sample.replace('# Title','# Changed'), sample.replace('formula','changed'), sample+'\n## Other\nnew'):
        assert update.outside_text_sections(sample) != update.outside_text_sections(changed)
    constraints = {'checks': [
        {'check':'forbidden formal content','ok':True,'detail':['FORBIDDEN']},
        {'check':'required user text','ok':True,'detail':['Required']} ]}
    assert all(c['ok'] for c in update.text_constraints(constraints,'copy','<p>Required</p>'))
    for copy_text, note in [('copy &emsp;','Required'), ('FORBIDDEN','Required'), ('copy','missing')]:
        try: update.text_constraints(constraints,copy_text,note)
        except ValueError: pass
        else: raise AssertionError('Changed text bypassed inherited constraint')
    print('COPY_FRAGMENT_GUARDS_PASS: unique nonempty matches, nonoverlap and unchanged outside scope')



def metadata_guards():
    rows=[['Variable','Label'],['Weight','体重（kg）'],['Height','身高（cm）']]
    record={'definition_plan':[]}
    before='## 摘要导读\n\n```text\n[[result:体重]][[meta:（kg）]]\n[[result:身高]][[meta:（cm）]]\n```\n'
    after=before.replace('result:体重','result:Weight|体重').replace('result:身高','result:Height|身高')
    assert update.metadata_tree_identity(before,after,rows,record)['variables']==['Weight','Height']
    for candidate in [after.replace('Weight|体重','Height|体重'), after+'changed prose',after.replace('体重','体脂')]:
        try: update.metadata_tree_identity(before,candidate,rows,record)
        except ValueError: pass
        else: raise AssertionError('Out-of-scope tree metadata accepted')

fragment_guards()
metadata_guards()
print("LEGACY_DELIVERY_GUARDS_PASS")


# Synthetic retained tree receipt. Spreadsheet parsing is supplied as a fixture;
# this exercises historical bindings and read-only validation, not R generation.
from unittest.mock import patch
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); formal=root/'formal'; process=root/'process'
    folder=process/'copy_updates'/'retained'; formal.mkdir(); folder.mkdir(parents=True)
    art={'copy':'文案.md','note':'note.md','public_r':'define.R',
         'analysis_codebook':'analysis_codebook_x.xlsx','full_codebook':'codebook_x.xlsx',
         'analysis_db':'analysis_db_x.xlsx','full_db':'db_x.xlsx'}
    before='## 摘要导读\n\n```text\n[[result:体重]][[meta:（kg）]]\n```\n'
    after=before.replace('result:体重','result:Weight|体重')
    write=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
    for role,name in art.items():
        (formal/name).write_text(before if role=='copy' else '<old>' if role=='note' else 'synthetic '+role,encoding='utf-8')
        shutil.copy2(formal/name,folder/name)
    source=process/'definition_search_record.json'
    write(source,{'approved_analysis_vars':['Weight'],'definition_plan':[]})
    shutil.copy2(source,folder/source.name)
    baseline={'scope':'metadata_only','subscope':'tree_identity','formal_dir':str(formal),
              'topic_id':'999','artifacts':art,'before_hashes':{p.name:update.digest(p) for p in formal.iterdir()},
              'analysis_vars':['Weight'],'source_sha256':update.digest(source),'historical_evidence':[]}
    bp=folder/'baseline.json'; write(bp,baseline)
    fragments=folder/'fragments.json'
    generated='<span data-tree-variable="Weight">体重</span>'
    write(fragments,{'before':{'summary':'<old>'},'after':{'summary':generated}})
    (formal/'文案.md').write_text(after,encoding='utf-8');(formal/'note.md').write_text(generated,encoding='utf-8')
    receipt={'status':'verified','scope':'metadata_only','baseline':str(bp),'baseline_sha256':update.digest(bp),
             'tools':update.metadata_tools(),'generation':{'exit_code':0,'files':{str(fragments):update.digest(fragments)},'fragments':str(fragments)},
             'candidate_hashes':{p.name:update.digest(p) for p in formal.iterdir()}}
    rp=process/update.METADATA_RECEIPT;write(rp,receipt)
    with patch('check_definition_output.read_xlsx_rows',return_value=[['Variable','Label'],['Weight','体重（kg）']]):
        snapshot=lambda:{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        original=snapshot()
        assert update.verify_metadata_update(formal,process,'999')['scope']=='metadata_only'
        assert snapshot()==original
        for target in (source,formal/'define.R',formal/'note.md',fragments):
            saved=target.read_bytes();target.write_bytes(saved+b' changed')
            observed=snapshot()
            try:update.verify_metadata_update(formal,process,'999')
            except (ValueError,KeyError):pass
            else:raise AssertionError('Changed historical proof accepted: '+str(target))
            assert snapshot()==observed
            target.write_bytes(saved)
        receipt['tools']['update_reader_copy.py']='unrecognized revision';write(rp,receipt)
        try:update.verify_metadata_update(formal,process,'999')
        except ValueError:pass
        else:raise AssertionError('Unrecognized historical tools accepted')
print('LEGACY_RECEIPT_PASS: valid proof read-only; changed inputs, artifacts, evidence and unknown tools rejected')
