"""Grouped copy and rendered-note checks must retain per-period evidence checks."""
from pathlib import Path
from html import escape
import copy
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors
from check_definition_readability import validate_questionnaire_rendering
from questionnaire_groups import period_keys

design = ('共同问卷。原问卷选项编码（Wave 1）：1=Yes；2=No。'
          '原问卷选项编码（Wave 2）：01=Yes；02=No。')
questionnaire = '### Wave 1–2\n\n' + design + '\n\n#### Q1\n\n感到孤独吗？\n\n- Yes\n- No\n'
record = {'schema_version': 6, 'questionnaire_evidence': [
    {'question_id': 'Q1', 'question_text': '感到孤独吗？', 'periods': ['Wave ' + str(w)],
     'response_type': 'closed_options', 'options': [{'value': codes[0], 'label': 'Yes'}, {'value': codes[1], 'label': 'No'}],
     'skip_logic': [], 'rendered_in_copy': True, 'copy_locator': '文案.md > Wave 1–2 > Q1'}
    for w, codes in [(1, ['1', '2']), (2, ['01', '02'])]]}


def rendered(text):
    blocks = []
    for key, group in read_questionnaire_copy(text).items():
        body = ''.join('<div data-summary-questionnaire-line="true"><b data-summary-question-id="true">'
                       + escape(q['id']) + '</b>' + escape(q['text'])
                       + ''.join('<span data-summary-question-option="true">' + escape(o['text']) + '</span>' for o in q['options'])
                       + '</div>' for q in group['questions'])
        blocks.append('<section data-raw-source-period="' + key + '" data-label="' + escape(group['label']) + '">'
                      '<div data-summary-period-note="true"><b data-summary-period-note-title="true">问卷设计</b>'
                      + escape(group['design']) + '</div>' + body + '</section>')
    return ''.join(blocks)


def check(text, evidence, good):
    errors = questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(text)}, evidence)
    assert bool(errors) != good, errors
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / 'definition_search_record.json').write_text(json.dumps(evidence, ensure_ascii=False), encoding='utf-8')
        (root / 'note.md').write_text(rendered(text), encoding='utf-8')
        try:
            result = validate_questionnaire_rendering(root, root, 'note.md')
        except (ValueError, SystemExit):
            assert not good
        else:
            assert good, result
            assert result['rendered_question_periods'] == 2


check(questionnaire, record, True)
check(questionnaire.replace('Wave 1–2', 'Wave 1'), record, False)
check(questionnaire.replace('01=Yes', '02=Yes'), record, False)
check(questionnaire.replace('- No', '- Maybe'), record, False)
check(questionnaire.replace('感到孤独吗？', '感到快乐吗？'), record, False)
check(questionnaire + questionnaire.replace('### Wave 1–2', '### Wave 2'), record, False)
changed = copy.deepcopy(record)
changed['questionnaire_evidence'][1]['question_text'] = '过去一个月感到孤独吗？'
check(questionnaire, changed, False)
assert period_keys('2011年；2015年') == ['2011', '2015']
assert period_keys('Wave 1–11') == ['wave' + str(i) for i in range(1, 12)]
assert period_keys('Wave 1、Wave 2、Wave 4–9：出生国与国籍的共同问题') == ['wave1','wave2'] + ['wave'+str(i) for i in range(4,10)]
assert period_keys('Wave 4–5：模块说明含 Wave 9') == ['wave4','wave5']
assert period_keys('Wave 2：全日制教育年数') == ['wave2']
assert period_keys('Wave 1、Wave 4–5: 不连续时期') == ['wave1','wave4','wave5']
print('GROUPED_QUESTIONNAIRE_PASS: copy/rendered scope, text, codes, labels, overlap and real differences')
