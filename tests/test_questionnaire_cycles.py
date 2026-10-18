"""Registered survey cycles remain distinct from annual periods."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from questionnaire_groups import period_keys, unverified_question_periods

cycles = ['1999-2000', '2001-2002', '2003-2004', '2017-2018', '2017-2020']
assert period_keys('1999–2000 年', cycles) == ['19992000']
assert period_keys('1999–2004 年', cycles) == ['19992000', '20012002', '20032004']
assert period_keys('2017–2018、2017–2020 年', cycles) == ['20172018', '20172020']
assert period_keys('1999–2000 年') == ['1999', '2000']
assert period_keys('Wave 1–3') == ['wave1', 'wave2', 'wave3']
for label in ['1999–2003 年', '1999–2020 年']:
    try:
        period_keys(label, cycles)
    except ValueError:
        pass
    else:
        raise AssertionError(label)
evidence = [{'question_id': 'SMQ020', 'periods': ['2017-2018']}]
assert not unverified_question_periods('2017–2018 年', ['SMQ020'], evidence, survey_periods=cycles)
assert unverified_question_periods('2017–2020 年', ['SMQ020'], evidence, survey_periods=cycles)
print('Questionnaire cycle checks passed')
