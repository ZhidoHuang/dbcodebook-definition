"""Wave aliases preserve per-period identity, codes, and jump targets."""
import copy
from test_questionnaire_year_aliases import TEXT, RECORD, check
from questionnaire_groups import question_identifiers, question_matches
from check_reader_copy import route_matches

text=TEXT.replace('2001–2004 年','Wave 4–7').replace('2001–2002 年','Wave 4–5').replace('2003–2004 年','Wave 6–7')
record=copy.deepcopy(RECORD)
for item in record['questionnaire_evidence']:
    item['periods']=['Wave '+str(int(item['periods'][0])-1997)]
check(text,record)
assert question_identifiers('37（Wave 4–5）／41（Wave 6–7）','Wave 6') == ['41']
assert question_matches('37（Wave 4）／41（Wave 5）','41','Wave 5')
assert not question_matches('37（Wave 4）／41（Wave 5）','41','Wave 4')
assert route_matches('第 47 题','跳至43（Wave 4）／47（Wave 5）','Wave 5')
assert not route_matches('第 47 题','跳至43（Wave 4）／47（Wave 5）','Wave 4')
for bad in [text.replace('Wave 4–7','Wave 4–8'),text.replace('Q4（Wave 6–7','Q4（Wave 5–7'),text.replace('Q4（Wave 6–7','Q40（Wave 6–7'),text.replace('①、②','①、③')]:
    check(bad,record,good=False)
for title in ['37（Wave 4–5）／41（Wave 5–6）','37（Wave 4）／41（未知）']:
    try:question_identifiers(title)
    except ValueError:pass
    else:raise AssertionError(title)
print('QUESTIONNAIRE_WAVE_ALIASES_PASS: writing/rendering gates, scoped codes/routes, overlap/unverified periods and wrong IDs rejected')
