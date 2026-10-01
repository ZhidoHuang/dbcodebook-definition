"""Regression boundaries observed in the CASP task; no live browser or production writes."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_report import input_hashes, read_review_log, validate_stage_review
from execution_metrics import find_logs
from check_reader_copy import summary_markup_errors, validate_summary_marks
from check_definition_output import check_public_code_outline

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    script = root/'CASP.R'
    script.write_text('score <- x + 1\n# 输出\nrender()\n', encoding='utf-8')
    bound = input_hashes([script], 'public')
    full = input_hashes([script])
    script.write_text('score <- x + 1\n# 输出\nrender(color="green")\n', encoding='utf-8')
    assert bound == input_hashes([script], 'public')
    assert full != input_hashes([script])
    script.write_text('score <- x + 2\n# 输出\nrender()\n', encoding='utf-8')
    assert bound != input_hashes([script], 'public')
    script.write_text('score <- x + 1\n# 输出\nrender()\n# 输出\n', encoding='utf-8')
    try:
        input_hashes([script], 'public')
    except ValueError:
        pass
    else:
        raise AssertionError('Ambiguous code boundary accepted')

    script.write_text('score <- x + 1\n# 输出\nrender()\n', encoding='utf-8')
    (root/'define_wrong.R').write_text('wrong <- TRUE', encoding='utf-8')
    checks = []
    note = '### 2-代码材料\n```r\nscore <- x + 1\n```'
    check_public_code_outline(root, note, checks, 'elsa', script)
    assert any(c['check'] == 'public R source synchronization' and c['ok'] for c in checks), checks

    log = root/'session-reviewer.jsonl'
    events = [
        {'type':'session_meta','payload':{'id':'reviewer','forked_from_id':'parent','source':'exec','timestamp':'2026-01-01T00:00:00Z'}},
        {'timestamp':'2026-01-01T00:00:01Z','type':'event_msg','payload':{'type':'task_started','turn_id':'one'}},
        {'timestamp':'2026-01-01T00:00:03Z','type':'event_msg','payload':{'type':'task_complete','turn_id':'one'}},
    ]
    log.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
    review = read_review_log(log,'logic')
    assert review['parent_thread_id'] == 'parent' and review['running_seconds'] == 2
    assert find_logs(root,'reviewer','parent') == [str(log.resolve())]
    assert find_logs(root,'reviewer','unrelated') == []
    del events[0]['payload']['forked_from_id']
    log.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
    try:
        read_review_log(log,'logic')
    except ValueError:
        pass
    else:
        raise AssertionError('Unrelated session accepted as reviewer')

assert summary_markup_errors('只有数量，得到 **5** 个结果。')
assert summary_markup_errors('得到生活质量总分。')
assert not summary_markup_errors('“**总分**”由“**生活掌控**”等维度组成。')
assert summary_markup_errors('“**总分**”以及 **未闭合')
validate_summary_marks('**总分**，共 **5** 个', '<span data-summary-concept="true">总分</span>，共 <span data-summary-count="true">5</span> 个')
try:
    validate_summary_marks('**总分**', '总分')
except ValueError:
    pass
else:
    raise AssertionError('Rendering silently dropped semantic marks')
print('CASP_EXECUTION_CONTRACTS_PASS: R identity, scoped binding, fork identity, summary markup')
