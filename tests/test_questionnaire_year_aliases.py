"""Annual ranges and visible question-number changes require per-year evidence."""
import copy
from html import escape
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors, route_matches
from check_definition_readability import validate_questionnaire_rendering
from questionnaire_groups import period_keys, question_identifiers

TEXT = '''### 2001–2004 年
#### 问卷设计
前题回答是时进入子题；两组年份仅题号及编码写法变化。
#### Q7（2001–2002 年）／Q4（2003–2004 年）：主问题
曾经做过这件事吗？
原问卷选项编码（2001–2002 年）：①=是；②=否。
原问卷选项编码（2003–2004 年）：1=是；2=否。
- 是 → 跳至 Q7-1（2001–2002 年）／Q4-1（2003–2004 年）
- 否
#### Q7-1（2001–2002 年）／Q4-1（2003–2004 年）：子问题
当前处于何种状态？
适用对象：前一题回答是的人。
原问卷选项编码（2001–2002 年）：①、②。
原问卷选项编码（2003–2004 年）：1、2。
- 第一种状态
- 第二种状态
'''
RECORD = {'schema_version': 6, 'questionnaire_display_policy': 'chinese_v1', 'questionnaire_evidence': []}
for year in range(2001, 2005):
    number, codes = ('7', ['①','②']) if year < 2003 else ('4', ['1','2'])
    for sub in [False, True]:
        identifier = number + ('-1' if sub else '')
        labels = ['第一种状态','第二种状态'] if sub else ['是','否']
        options = [{'value':code,'label':label} for code,label in zip(codes,labels)]
        jumps = [] if sub else [{'when':codes[0]+' 是', 'destination':number+'-1'}]
        RECORD['questionnaire_evidence'].append({'question_id':identifier, 'periods':[str(year)],
          'question_text':'当前处于何种状态？' if sub else '曾经做过这件事吗？',
          'options':options, 'skip_logic':jumps, 'response_type':'closed_options',
          'rendered_in_copy':True, 'copy_locator':'文案.md > '+str(year)+' > '+identifier,
          'display':{'question_text':'当前处于何种状态？' if sub else '曾经做过这件事吗？',
            'instructions':['前一题回答是的人。'] if sub else []}})


def markup(text):
    sections = []
    for key, block in read_questionnaire_copy(text).items():
        lines = []
        for q in block['questions']:
            rows = ''.join('<div data-summary-question-detail="true"><span data-summary-question-option="true">'
              + escape(o['text']) + '</span><span data-summary-question-instruction="true">'
              + escape(o['jump']) + '</span></div>' for o in q['options'])
            lines.append('<div data-summary-questionnaire-line="true"><b data-summary-question-id="true">'
              + escape(q['id']) + '</b>' + escape(q['text'])
              + ''.join('<span data-summary-question-instruction="true">' + escape(n) + '</span>' for n in q.get('notes', []))
              + ''.join('<span data-summary-question-instruction="true">' + escape(n) + '</span>' for n in q.get('instructions', []))
              + '<span data-summary-question-condition="true">' + escape(q['condition']) + '</span>' + rows + '</div>')
        sections.append('<section data-raw-source-period="'+key+'" data-label="'+escape(block['label'])+'">'
          + '<div data-summary-period-note="true"><b data-summary-period-note-title="true">问卷设计</b>'
          + escape(block['design']) + '</div>' + ''.join(lines) + '</section>')
    return ''.join(sections)


def check(text=TEXT, record=RECORD, good=True):
    try:
        errors = questionnaire_copy_errors({'questionnaire':read_questionnaire_copy(text)},record)
    except ValueError:
        assert not good
    else:
        assert bool(errors) != good, errors
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root/'definition_search_record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        try:
            (root/'note.md').write_text(markup(text),encoding='utf-8')
            result = validate_questionnaire_rendering(root,root,'note.md')
        except (ValueError,SystemExit):
            assert not good
        else:
            assert good, result
            assert result['rendered_question_periods'] == len(record['questionnaire_evidence'])


check()
for bad in [TEXT.replace('### 2001–2004','### 2001–2005'),
            TEXT.replace('Q7（2001–2002','Q70（2001–2002'),
            TEXT.replace('Q4（2003–2004','Q4（2002–2004'),
            TEXT.replace('①、②','①、③'),
            TEXT.replace('①、②','①'),
            TEXT.replace('跳至 Q7-1','跳至 Q70-1'),
            TEXT.replace('适用对象：前一题回答是的人。','适用对象：所有人。'),
            TEXT.replace('曾经做过这件事吗？','简化问题。')]:
    check(bad,good=False)
missing = copy.deepcopy(RECORD); missing['questionnaire_evidence'] = missing['questionnaire_evidence'][2:]
check(record=missing,good=False)
assert period_keys('1980–1983 年') == ['1980','1981','1982','1983']
assert period_keys('2001年–2002年；2004年') == ['2001','2002','2004']
assert question_identifiers('Q7（2001–2002 年）／Q4（2003–2004 年）：描述','2003') == ['Q4']
assert route_matches('7-1（当前状态）','跳至 Q7-1（2001–2002 年）／Q4-1（2003–2004 年）','2001')
assert not route_matches('7-1','跳至 Q7-1（2001–2002 年）／Q4-1（2003–2004 年）','2003')
assert not route_matches('Q7-1','跳至 Q7-1（2001–2002 年）／Q4-1（2003–2004 年）','2003')
for bad in ['2004–2001 年','2001–2003 年；2002年']:
    try: period_keys(bad)
    except ValueError: pass
    else: raise AssertionError('Invalid range accepted: '+bad)
print('QUESTIONNAIRE_YEAR_ALIASES_PASS: copy/rendered ranges, verified coverage, scoped IDs, ordered codes, conditions and routes')

# Merged periods show first-period IDs, but routes retain their real period IDs.
merged = {'schema_version': 6, 'questionnaire_display_policy': 'chinese_v1', 'questionnaire_evidence': []}
for wave, prefix in [(1, 'C10'), (2, 'C20')]:
    for number in [1, 2, 3]:
        identifier = prefix + str(number)
        merged['questionnaire_evidence'].append({
            'evidence_id': f'w{wave}q{number}', 'question_id': identifier,
            'periods': [f'Wave {wave}'], 'question_text': f'第{number}个问题。',
            'response_type': 'closed_options' if number == 1 else 'open_value',
            'options': [{'value': '1', 'label': '是'}, {'value': '5', 'label': '否'}] if number == 1 else [],
            'skip_logic': [{'when': '1 是', 'destination': prefix + '3'}] if number == 1 else [],
            'rendered_in_copy': True, 'copy_locator': identifier,
            'display': {'question_text': f'第{number}个问题。',
                        'question_title': 'C10' + str(number),
                        'question_title_source': f'w1q{number}'}})
merged_text = '''### Wave 1–2
#### 问卷设计
三道问题，回答是时跳过第二题。
#### C101
第1个问题。
- 1 是 → 跳至 C103
- 5 否
#### C102
第2个问题。
#### C103
第3个问题。
'''
snapshot = copy.deepcopy(merged)
check(merged_text, merged)
assert merged == snapshot
check(merged_text.replace('跳至 C103', '跳至 C102'), merged, False)
check(merged_text.replace('1 是 →', '5 否 →'), merged, False)
for field, value in [('question_title_source', 'missing'), ('question_title_source', 'w1q2')]:
    bad = copy.deepcopy(merged)
    bad['questionnaire_evidence'][-1]['display'][field] = value
    check(merged_text, bad, False)
bad = copy.deepcopy(merged)
bad['questionnaire_evidence'][-1]['questionnaire_module'] = '另一题组'
check(merged_text, bad, False)
bad = copy.deepcopy(merged)
bad['questionnaire_evidence'][-1]['periods'] = ['Wave 3']
check(merged_text, bad, False)

# A classified entry note can stay internal; a real outgoing branch still must appear.
entry = copy.deepcopy(merged)
for item in entry['questionnaire_evidence']:
    if item['question_id'] not in ['C101', 'C201']:
        continue
    item['skip_logic'].insert(0, {'when': '本题不受前题筛查限制',
        'destination': item['question_id'], 'kind': 'entry_condition',
        'evidence': '本期官方问卷入口与相邻筛查分支已核实；本题位于该分支之外。'})
    item['display']['skip_logic'] = [
        {'source_index': 0, 'when': '本题不受前题筛查限制',
         'destination': '进入 ' + item['question_id'], 'presentation': 'entry_condition',
         'presentation_reason': '入口说明，不是本题回答后跳向另一题。'},
        {'source_index': 1, 'when': '1 是', 'destination': '跳至 ' + item['skip_logic'][1]['destination']}]
snapshot = copy.deepcopy(entry)
check(merged_text, entry)
assert entry == snapshot
check(merged_text.replace(' → 跳至 C103', ''), entry, False)
for field in ['kind', 'evidence']:
    bad = copy.deepcopy(entry)
    bad['questionnaire_evidence'][0]['skip_logic'][0].pop(field)
    check(merged_text, bad, False)
bad = copy.deepcopy(entry)
bad['questionnaire_evidence'][0]['skip_logic'][0]['destination'] = 'C103'
bad['questionnaire_evidence'][0]['display']['skip_logic'][0]['destination'] = '进入 C103'
check(merged_text, bad, False)
bad = copy.deepcopy(entry)
bad['questionnaire_evidence'][0]['display']['skip_logic'][0]['when'] = '本题回答 5 时'
check(merged_text, bad, False)
print('MERGED_ROUTES_ENTRY_NOTES_PASS: copy/rendered targets, conditions, periods, groups and source preservation')
