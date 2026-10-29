"""Opt-in offline integration replay on copies of an accepted topic.

Usage: --formal-dir ... --process-dir ... --config ... [--pwsh ...]
Role records below are explicitly synthetic test fixtures, not new acceptance.
No original file, browser, or website is modified.
"""
import argparse
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
import update_reader_copy as update


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
    assert update.previous_check_options(constraints) == [
        '--forbid-vars', 'FORBIDDEN', '--required-user-text', 'Required']
    assert update.previous_check_options({'checks': [
        {'check':'Criteria evolution structure','ok':True,'detail':['early','later']} ]}) == [
        '--criteria-evolution-text','early,later']
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
    from skill_config import load_config, configured_executable
    if not (configured_executable(load_config(None),'rscript') or shutil.which('Rscript')):
        return  # Parser integration is also exercised in the real-topic maintenance evidence.
    with tempfile.TemporaryDirectory() as tmp:
        home=Path(tmp);before_dir=home/'before';formal=home/'formal'
        before_dir.mkdir();formal.mkdir()
        base='data <- 1\n# ----------- 变量字典 -----------\ncodebook <- data.frame()\ncodebook$Label[codebook$Variable == "Weight"] <- "weight"\n# 输出\nrender_definition_bundle(summary_groups=c(Weight="Mass"))\n'
        valid=base.replace('"weight"','"体重"').replace('summary_groups=', 'component_groups=c(Weight="Mass"), summary_groups=')
        (before_dir/'define.R').write_text(base,encoding='utf-8')
        baseline={'artifacts':{'public_r':'define.R'},'analysis_vars':['Weight']}
        candidates=[(valid,True),(valid.replace('data <- 1','data <- 2'),False),
                    (valid.replace('"体重"','paste("体重")'),False),
                    (valid.replace('codebook <- data.frame()','codebook <- data.frame(x=2)'),False)]
        for index,(candidate,allowed) in enumerate(candidates):
            (formal/'define.R').write_text(candidate,encoding='utf-8')
            attempt=home/str(index);attempt.mkdir()
            try: result=update.metadata_label_source(formal,before_dir,baseline,None,attempt)
            except ValueError:
                if allowed: raise
            else:
                if not allowed: raise AssertionError('Calculation or executable metadata change accepted')
                assert update.read(result['metadata'])['labels'][0]['after']=='体重'


def main():
    fragment_guards()
    metadata_guards()
    parser = argparse.ArgumentParser()
    parser.add_argument('--formal-dir', type=Path)
    parser.add_argument('--process-dir', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--pwsh')
    parser.add_argument('--text-only', action='store_true', help='Replay reference-only edits without data regeneration')
    args = parser.parse_args()
    if not args.formal_dir:
        print('COPY_UPDATE_FLOW_SKIP: supply an accepted offline topic for integration replay')
        return
    with tempfile.TemporaryDirectory(prefix='copy_update_replay_') as tmp:
        home = Path(tmp); formal = home/'formal'; process = home/'process'
        formal.mkdir(); process.mkdir()
        for f in args.formal_dir.iterdir():
            if f.is_file(): shutil.copy2(f, formal/f.name)
        for name in ['definition_search_record.json', 'definition_change_impact.json',
                     'result_check.json', 'readability_audit.json']:
            shutil.copy2(args.process_dir/name, process/name)
        for f in args.process_dir.glob('*.md'):
            shutil.copy2(f, process/f.name)
        source = process/'definition_search_record.json'
        record = update.read(source); result = update.read(process/'result_check.json')
        # Only synthetic lifecycle records are constructed; production content,
        # raw archive, R, generation, workbooks and validators are real copies.
        request = process/'request.txt';request.write_text('Synthetic replay research input',encoding='utf-8')
        decision = process/'decision.txt';decision.write_text('Synthetic replay settled plan',encoding='utf-8')
        report = {'schema_version':1,'run_id':'fixture','database':record['database'],
                  'topic_id':record['topic_id'],'topic_name':record['topic_name'],
                  'status':'completed','workflow':'general','review_policy':er.REVIEW_POLICY,
                  'exploration_policy':POLICY,'primary_agent_id':'fixture-primary',
                  'stage_reviews':{},'reviews':[],'stages':[],'issues':[],
                  'exploration':{'inputs':er.input_hashes([request]),'branches':{}}}
        def role(name, identity, inputs):
            report['reviews'].append({'agent_id':identity,'role':name,'unfinished_turns':0,'closed':True,
                'rounds':[{'started_at':'2026-01-01T00:01:00Z','outcome':'completed'}]})
            report['stage_reviews'][name]={'status':'pass','mode':'independent','agent_id':identity,
                'started_at':'2026-01-01T00:00:00Z','finished_at':'2026-01-01T00:02:00Z',
                'inputs':er.input_hashes(inputs),'evidence':'SYNTHETIC lifecycle fixture; not actual review'}
        for branch,name in ROLES.items():
            output=process/(branch+'.txt');output.write_text(branch,encoding='utf-8')
            role(name,branch,[request])
            report['exploration']['branches'][branch]={'agent_id':branch,'outputs':er.input_hashes([output]),
                'review_started_at':'2026-01-01T00:00:00Z','review_finished_at':'2026-01-01T00:02:00Z'}
        report['exploration']['merge']={'status':'ready','unresolved':[],'record':str(source.resolve()),
            'plan_hash':plan_hash(source),'decision':er.input_hashes([decision])}
        r=next(formal.glob('define_*.R'))
        role(er.COMBINED_REVIEW_ROLE,'fixture-r',[r,source,formal/'raw_codebook.csv'])
        update.write(process/'execution_report.json',report)
        original={str(f):update.digest(f) for directory in [args.formal_dir,args.process_dir]
                  for f in directory.iterdir() if f.is_file()}
        opts=argparse.Namespace(formal_dir=formal,process_dir=process,
            reason='离线验证只删除问卷展示，研究事实、变量与计算程序全部保持不变。',
            omit_questionnaire=None if args.text_only else '离线验证用户要求省略问卷展示，所有研究证据及必要补值条件仍保留。',
            config=args.config,pwsh=args.pwsh)
        update.prepare(opts)
        # Exercise the guard with real baseline hashes before the allowed edit.
        content=r.read_bytes();r.write_bytes(content+b'\n# changed\n')
        try:
            update.run(opts)
        except ValueError as exc:
            assert '变化' in str(exc)
        else:raise AssertionError('Changed R was accepted')
        r.write_bytes(content)
        copy=formal/'文案.md';text=copy.read_text(encoding='utf-8-sig')
        heading = '## 问卷' if '## 问卷' in text else None
        if args.text_only:
            before, refs = text.split('## 参考资料说明', 1)
            text = before + '## 参考资料说明\n\n材料说明（离线验证）：' + refs.lstrip()
        elif heading:
            start=text.index(heading);end=text.index('## Criteria',start)
            text=text[:start]+text[end:]
        else:
            text=text.replace('## 摘要导读','## 摘要导读\n',1)
        copy.write_text(text,encoding='utf-8')
        try:
            started = time.monotonic()
            result=update.run(opts)
        except Exception:
            for log in process.glob('copy_updates/*/*.log'):
                print(log.name, log.read_text(encoding='utf-8')[-7000:])
            raise
        assert result['status']=='LOCAL_UPDATE_COMPLETE' and not result['website_submitted']
        if args.text_only:
            result_record = update.read(process/'result_check.json')
            assert result_record['validation_mode'] == 'copy_sections'
            update.validate_text_result(result_record, formal, process)
            attempt = Path(update.read(process/'execution_report.json')['copy_update']['attempts'][-1]['folder'])
            assert not (attempt/'generate.log').exists(), 'Full R generation was invoked'
            assert not (attempt/'result-check.log').exists(), 'Full data checker was invoked'
            snapshot = (formal/next(n for n in result_record['artifacts'] if n.endswith('.xlsx')))
            original_bytes = snapshot.read_bytes(); snapshot.write_bytes(original_bytes+b'tamper')
            try: update.validate_text_result(result_record, formal, process)
            except ValueError: pass
            else: raise AssertionError('Changed data accepted as unchanged')
            snapshot.write_bytes(original_bytes)
            print(f'COPY_TEXT_ONLY_PASS: no calculation/data-table parsing; dictionary checked; elapsed={time.monotonic()-started:.3f}s')
            incomplete = deepcopy(result_record); incomplete.pop('copy_sections')
            try: update.validate_text_result(incomplete, formal, process)
            except ValueError: pass
            else: raise AssertionError('Missing inherited evidence accepted')
            # Exercise all three supported sections in the second update.
            update.prepare(opts)
            second_text = copy.read_text(encoding='utf-8').replace('材料说明（离线验证）：','资料说明（第二次离线验证）：',1)
            second_text = second_text.replace('本主题定义', '本主题提供', 1)
            start = second_text.index('## 小book提示')
            end = second_text.index('## 参考资料说明', start)
            insight = second_text[start:end]
            assert '。' in insight, 'Integration fixture needs an existing insight sentence'
            second_text = second_text[:start] + insight.replace('。', '。（离线检查副本。）', 1) + second_text[end:]
            copy.write_text(second_text,encoding='utf-8')
            second = update.run(opts)
            assert second['status'] == 'LOCAL_UPDATE_COMPLETE'
            latest = update.read(process/'result_check.json')
            assert latest['validation_mode'] == 'copy_sections'
            assert set(latest['copy_sections']['changed_fields']) == {'summary', 'insight', 'references'}
            update.validate_text_result(latest, formal, process)
            original_checks = update.original_result(latest, process)['checks']
            assert any(c['check']=='analysis_db columns' for c in original_checks)
            assert any(c['check']=='raw_codebook vars' for c in original_checks)
            assert not update.original_result(latest, process).get('copy_sections')
            print('COPY_TEXT_CHAIN_PASS: summary/insight/references updated; complete-check fallback retained; incomplete evidence rejected')
        current=update.read(process/'execution_report.json')
        assert not current.get('reviews') and current['stage_reviews'][er.COMBINED_REVIEW_ROLE]['reused_from']
        assert all(update.digest(Path(path))==sha for path,sha in original.items())
        print('COPY_UPDATE_FLOW_PASS: prepare, changed R blocked, generation, unchanged data, delivery, no original writes')


if __name__=='__main__':main()
