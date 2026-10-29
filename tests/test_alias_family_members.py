"""Explicit nonnumeric source families retain the same complete-selection gate."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_definition_source_record import validate_alias_families

def main():
    aliases=['AM251A_other_adams','AM251B_other_adams','AM251J_other_adams']
    assert validate_alias_families({'alias_families':[{'members':aliases}]},aliases)==1
    assert validate_alias_families({'alias_families':[{'template':'a{n}','start':1,'end':3}]},['a1','a2','a3'])==1
    bad=[({'members':[]},aliases),({'members':'a1'},aliases),({'members':['']},aliases),
         ({'members':['AM251A_other_adams','AM251A_other_adams']},aliases),
         ({'members':aliases},aliases[:-1]),({'members':aliases,'template':'a{n}','start':1,'end':3},aliases),
         ({'members':[False]},aliases)]
    for family,selected in bad:
        try:validate_alias_families({'alias_families':[family]},selected)
        except ValueError:pass
        else:raise AssertionError(family)
    try:validate_alias_families({'alias_families':[{'members':aliases},{'members':[aliases[0]]}]},aliases)
    except ValueError:pass
    else:raise AssertionError('overlap accepted')
    print('PASS: explicit alphabetic families, legacy numeric families, eight negative cases')

if __name__=='__main__':main()
