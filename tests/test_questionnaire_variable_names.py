"""Both writing and publication checks accept only evidenced variable/title mappings."""
import copy
from test_questionnaire_year_aliases import TEXT, RECORD, check
from questionnaire_groups import question_matches

record = copy.deepcopy(RECORD)
for item in record['questionnaire_evidence']:
    item['question_variable'] = 'marri_2' if '-' in item['question_id'] else 'marri_1'
    item['locator'] = 'Synthetic fixture: question-to-variable mapping for this period'
text = TEXT.replace('#### Q7（2001–2002 年）／Q4（2003–2004 年）：主问题','#### marri_1').replace('#### Q7-1（2001–2002 年）／Q4-1（2003–2004 年）：子问题','#### marri_2')
check(text, record)
check(text.replace('#### marri_1','#### marri_wrong'), record, good=False)
check(text, RECORD, good=False)
missing = copy.deepcopy(record)
missing['questionnaire_evidence'][0].pop('locator')
check(text, missing, good=False)
wrong_period = copy.deepcopy(record)
wrong_period['questionnaire_evidence'][0]['question_variable'] = 'older_name'
check(text, wrong_period, good=False)
check(text.replace('### 2001–2004','### 2001–2005'), record, good=False)
# Even an original numeric ID cannot excuse an incorrect parenthetical variable.
annotated = TEXT.replace('#### Q7（2001–2002 年）／Q4（2003–2004 年）：主问题','#### 7（2001–2002 年）／4（2003–2004 年）')
check(annotated, record)
item = record['questionnaire_evidence'][0]
assert question_matches('第 7 题（变量 `marri_1`）','7','2001',item)
assert not question_matches('第 7 题（变量 `wrong`）','7','2001',item)
assert not question_matches('marri_1','7','2003',item)
assert not question_matches('marri_1','7','2001')
print('QUESTIONNAIRE_VARIABLE_NAMES_PASS: both gates, names, evidence, periods, legacy IDs')

# A verified original variable is sufficient when the source question ID is unknown.
variable_only = {'schema_version': 6, 'questionnaire_display_policy': 'chinese_v1',
                 'questionnaire_evidence': [{
    'evidence_id': 'v1', 'question_id': '', 'question_variable': 'dc006_1_s1',
    'locator': '官方代码本第 1 页', 'periods': ['2013'],
    'question_text_mode': 'plain_paraphrase', 'question_text_complete': False,
    'question_text': '请回忆刚才的词语。', 'paraphrase_reason': '官方代码本未列出完整题文。',
    'applicable_population': '受访者本人', 'recall_period': '本次测验',
    'response_type': 'closed_options', 'options': [{'value': '1', 'label': '词语'}, {'value': '2', 'label': '没有'}],
    'skip_logic': [], 'rendered_in_copy': True, 'copy_locator': '问卷 > 2013 > dc006_1_s1',
    'display': {'presentation': 'question', 'question_text': '请回忆刚才的词语。', 'instructions': []},
}]}
variable_copy = "### 2013 年\n#### 问卷设计\n现在回答回忆问题。\n#### dc006_1_s1\n请回忆刚才的词语。\n- 1 词语\n- 2 没有\n"
check(variable_copy, variable_only)
for field, value in [('question_variable', ''), ('question_variable', 'bad variable'),
                     ('locator', ''), ('periods', ['2015'])]:
    bad = copy.deepcopy(variable_only)
    bad['questionnaire_evidence'][0][field] = value
    check(variable_copy, bad, good=False)
check(variable_copy.replace('dc006_1_s1', 'dc006_1_s2'), variable_only, good=False)
check(variable_copy.replace('请回忆刚才的词语。', '请回答问题。'), variable_only, good=False)
check(variable_copy.replace('- 2 没有', '- 2 错误'), variable_only, good=False)
# Distinct variables in one period count as two rendered questions.
two_variables = copy.deepcopy(variable_only)
second = copy.deepcopy(two_variables['questionnaire_evidence'][0])
second.update(evidence_id='v2', question_variable='dc006_1_s2')
second['display']['question_text'] = second['question_text'] = '再回忆另一个词语。'
two_variables['questionnaire_evidence'].append(second)
two_copy = variable_copy + '\n#### dc006_1_s2\n再回忆另一个词语。\n- 1 词语\n- 2 没有\n'
check(two_copy, two_variables)
print('QUESTIONNAIRE_VARIABLE_ONLY_PASS: both gates, strict evidence and distinct variables')
