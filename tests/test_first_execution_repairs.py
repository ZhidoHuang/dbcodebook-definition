"""Regressions from the isolated ADL first execution, without topic answers."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from questionnaire_groups import shared_question_info
from check_definition_source_record import validate_exploration_log, validate_human_record, exploration_action

options, _ = shared_question_info('共同选项（Q1）：1=没有困难；2=有困难。；3=需要帮助。；4=无法完成。', 'Q1')
assert options == ['1 没有困难', '2 有困难。', '3 需要帮助。', '4 无法完成']
try:
    shared_question_info('共同选项（Q1）：1=是；2=否', 'Q1')
except ValueError:
    pass
else:
    raise AssertionError('Unterminated declaration accepted')

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    actions = ['normal_search', 'source_detail', 'direct_research_review', 'primary_merge', 'environment_read']
    log = [dict(step=i, human_step_id=f'S{i:03}', action=a, input='source', observed='fact', decision='choice', reason='reason') for i,a in enumerate(actions,1)]
    record = dict(recording_mode='contemporaneous', exploration_log=log, human_record='探索记录.md')
    assert len(validate_exploration_log(record)) == 5
    assert exploration_action('direct_research_review') == 'literature_review'
    assert exploration_action('environment_read') not in {'official_material_review','literature_review'}
    (p/'探索记录.md').write_text('\n'.join(f'## S{i:03} 查证' for i in range(1,6)),encoding='utf-8')
    validate_human_record(p/'record.json',record,log)
    log[0]['action'] = 'invented_action'
    try:
        validate_exploration_log(record)
    except (ValueError, SystemExit):
        pass
    else:
        raise AssertionError('Unknown action accepted')

    process=p/'process'; doc=p/'文案.md'
    def run(script, *args, succeeds=True):
        result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/script),*map(str,args)],capture_output=True,text=True,encoding='utf-8')
        assert (result.returncode == 0) == succeeds, result.stdout+result.stderr
        return result
    run('execution_report.py','init','--process-dir',process,'--database','test','--topic-id','fixture','--topic-name','fixture','--task','first-copy test','--workflow','general')
    run('execution_report.py','stage-start','--process-dir',process,'--stage-id','copy','--name','copy','--role','test')
    original=(ROOT/'tests/fixtures/writing-inputs/reader-copy.md').read_bytes()
    doc.write_bytes(original.replace('## Criteria'.encode(),'## Wrong'.encode()))
    first_bytes=doc.read_bytes()
    run('check_reader_copy.py','--copy',doc,'--process-dir',process,succeeds=False)
    report=lambda:json.loads((process/'execution_report.json').read_text(encoding='utf-8'))
    first=report()['first_copy']
    assert Path(first['snapshot_path']).read_bytes()==first_bytes
    run('execution_report.py','stage-finish','--process-dir',process,'--stage-id','copy','--status','failed','--copy',doc)
    assert len(report()['copy_history'])==1
    doc.write_bytes(original)
    run('execution_report.py','stage-start','--process-dir',process,'--stage-id','copy','--name','repair','--role','test')
    run('check_reader_copy.py','--copy',doc,'--process-dir',process)
    assert report()['first_copy']==first and len(report()['copy_history'])==2
print('FIRST_EXECUTION_REPAIRS_PASS')
