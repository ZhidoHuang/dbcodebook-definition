"""Historical HRS packages remain readable without starting an update workflow."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from legacy_delivery_checks import digest
from types import SimpleNamespace
u=SimpleNamespace(digest=digest,write=lambda p,v:p.write_text(json.dumps(v),encoding='utf-8'))
def reject(fn,fragment):
 try:fn()
 except ValueError as e:assert fragment in str(e),str(e)
 else:raise AssertionError('Expected rejection: '+fragment)
from hrs_export_contract import accepts_legacy_package, validate_defaults, TRACKER_FILE
with TemporaryDirectory(prefix='legacy_tracker_fixture_') as tmp:
    root=Path(tmp);formal=root/'formal';process=root/'process';formal.mkdir();process.mkdir()
    (formal/'raw_data.csv').write_text('ID,HHID,PN,Wave_id,BIRTHYR\na,001,01,1992-2022,1940\n',encoding='utf8')
    (formal/'raw_codebook.csv').write_text('Variable,newname\nBIRTHYR ('+TRACKER_FILE+'),BIRTHYR\n',encoding='utf8')
    legacy=process/'legacy.json';u.write(legacy,{'status':'completed'})
    reject(lambda:validate_defaults(formal/'raw_codebook.csv',['BIRTHYR']), 'Missing automatic')
    assert not accepts_legacy_package(process,formal)
    u.write(process/'execution_report.json',{'copy_update':{'formal_dir':str(formal),'legacy_evidence':{'path':str(legacy),'sha256':u.digest(legacy)},'result':{'artifacts':{p.name:u.digest(p) for p in formal.iterdir()}}}})
    assert accepts_legacy_package(process,formal)
    assert validate_defaults(formal/'raw_codebook.csv',['BIRTHYR'],legacy_package=True)==set()
    (formal/'raw_data.csv').write_text('changed',encoding='utf8')
    reject(lambda:accepts_legacy_package(process,formal),'baseline')
print('COPY_UPDATE_OLD_TRACKER_PASS: only explicit unchanged historical packages; current exports retain default-column checks')
