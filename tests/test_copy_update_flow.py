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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_report as er
from exploration_handoff import POLICY, ROLES, plan_hash
import update_reader_copy as update


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--formal-dir', type=Path)
    parser.add_argument('--process-dir', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--pwsh')
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
            omit_questionnaire='离线验证用户要求省略问卷展示，所有研究证据及必要补值条件仍保留。',
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
        if '## 原始问卷' in text:
            start=text.index('## 原始问卷');end=text.index('## Criteria',start)
            text=text[:start]+text[end:]
        else:
            text=text.replace('## 摘要导读','## 摘要导读\n',1)
        copy.write_text(text,encoding='utf-8')
        try:
            result=update.run(opts)
        except Exception:
            for log in process.glob('copy_updates/*/*.log'):
                print(log.name, log.read_text(encoding='utf-8')[-7000:])
            raise
        assert result['status']=='LOCAL_UPDATE_COMPLETE' and not result['website_submitted']
        current=update.read(process/'execution_report.json')
        assert not current.get('reviews') and current['stage_reviews'][er.COMBINED_REVIEW_ROLE]['reused_from']
        assert all(update.digest(Path(path))==sha for path,sha in original.items())
        print('COPY_UPDATE_FLOW_PASS: prepare, changed R blocked, generation, unchanged data, delivery, no original writes')


if __name__=='__main__':main()
