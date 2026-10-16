import sys
from pathlib import Path
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from questionnaire_display import display_answers

item = {'question_id': 'G014', 'options': [],
        'skip_logic': [{'when': 'INAP (Inapplicable); Partial Interview',
                        'destination': 'G014 发布为空白'}],
        'display': {'skip_logic': [{'source_index': 0, 'when': '不适用；部分访谈',
                    'destination': 'G014 发布为空白', 'presentation': 'record_note',
                    'presentation_reason': '原代码本为空白类别，无前置回答条件或去向。'}]}}
assert display_answers(item, {})[1] == []
for source, display in [
        ('IF G001=5', 'G001 为 5 时'),
        ('INAP (Inapplicable); [Q123] = 5', '不适用；Q123 为 5 时')]:
    bad = deepcopy(item)
    bad['skip_logic'][0]['when'] = source
    bad['display']['skip_logic'][0]['when'] = display
    try:
        display_answers(bad, {})
    except ValueError:
        pass
    else:
        raise AssertionError('conditional route must not be omitted')
bad = deepcopy(item)
bad['skip_logic'][0]['destination'] = 'G015 发布为空白'
bad['display']['skip_logic'][0]['destination'] = 'G015 发布为空白'
try:
    display_answers(bad, {})
except ValueError:
    pass
else:
    raise AssertionError('another target must not be omitted')
print('PASS: record notes preserve conditional and cross-question routes')

note = 'Blank 是发布空白，-8 是网页未回答，均不是作答选项。'
options = {'options': [{'value':'1','label':'YES'}, {'value':'Blank','label':'INAP'},
                       {'value':'-8','label':'Web non-response'}], 'skip_logic': [],
           'display': {'record_only_option_values':['Blank','-8'],
                       'record_only_options_note':note, 'instructions':[note]}}
assert display_answers(options,{})[0] == [{'value':'1','label':'YES'}]
missing_note = deepcopy(options)
missing_note['display']['instructions'] = []
try:
    display_answers(missing_note,{})
except ValueError:
    pass
else:
    raise AssertionError('record-only options require visible explanation')
options['display']['record_only_option_values']=['1']
try:
    display_answers(options,{})
except ValueError:
    pass
else:
    raise AssertionError('valid response must remain displayed')
