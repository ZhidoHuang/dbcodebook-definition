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
