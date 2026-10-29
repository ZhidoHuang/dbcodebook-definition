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

mixed = ['2001-2003', '2002-2005', '2006-2008', '2008-2009', '2008', '2010', '2012']
core = [{'question_id':'C240', 'periods':[year]} for year in ('2008', '2010', '2012')]
assert period_keys('2008–2010 年', mixed) == ['2008', '2009', '2010']
assert not unverified_question_periods('2008–2010 年', ['C240'], core, survey_periods=mixed)
assert unverified_question_periods('2008–2010 年', ['C240'], core[:1], survey_periods=mixed)
assert period_keys('2008–2009 年', mixed) == ['20082009']
irregular = mixed + ['2016']
assert unverified_question_periods('2008–2016 年', ['C240'], core, survey_periods=irregular)
try:
    period_keys('2001–2004 年', mixed)
except ValueError:
    pass
else:
    raise AssertionError('Partial multi-year intervals must remain rejected')
print('Questionnaire cycle checks passed')


# A registered original cycle remains one cycle even when its endpoints also
# occur as annual sources elsewhere in a broad questionnaire module.
mixed_calendar = ['2006','2008','2011','2013','2016','2018','2019','2020','2022',
                  '2006-2008','2008-2009']
cycle_evidence = [{'question_id':'153','periods':[p]} for p in ('2006-2008','2008-2009')]
assert unverified_question_periods('2006-2008、2008-2009',['153'],cycle_evidence,
                                  survey_periods=mixed_calendar) == []
assert unverified_question_periods('2006-2008、2008-2009',['153'],cycle_evidence[:1],
                                  survey_periods=mixed_calendar)
assert unverified_question_periods('2006-2008',['154'],cycle_evidence,
                                  survey_periods=mixed_calendar)
assert any('irregular survey periods' in error for error in unverified_question_periods(
    '2016-2020',['153'],cycle_evidence,survey_periods=mixed_calendar))
