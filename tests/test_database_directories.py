"""Recorded UI paths need not share the CHARLS directory root."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from check_definition_source_record import validate_directory_entries
paths={"SHARE":"SHARE core data > Coverscreen respondents", "KLOSA":"Structured Version", "KNHANES":"1 人口统计学与社会因素", "CHNS":"2 教育与就业", "CHARLS":"Core data > Health", "ELSA":"Core data > Health", "HRS":"Full HRS > Demographics"}
for database,path in paths.items():
    row={"full_path":path,"verified_in_ui":True,"purpose":"Verified candidate location"}
    assert validate_directory_entries([row],database)=={path}
    for field,value in [("full_path",""),("verified_in_ui",False),("purpose","")]:
        try: validate_directory_entries([{**row,field:value}],database)
        except ValueError: pass
        else: raise AssertionError((database,field))
try: validate_directory_entries([{"full_path":"Fake root > Health","verified_in_ui":True,"purpose":"x"}],"CHARLS")
except ValueError: pass
else: raise AssertionError("Existing CHARLS root contract was lost")
print("DATABASE_DIRECTORY_TESTS_PASS: four real hierarchies and existing roots; empty/unverified rejected")
