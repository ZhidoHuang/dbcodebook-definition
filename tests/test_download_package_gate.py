from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import zipfile
import json
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_source_record.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_source_record_for_package_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_source_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_package(formal: Path, raw_data: bytes, raw_codebook: bytes) -> None:
    formal.mkdir()
    (formal / "raw_data.csv").write_bytes(raw_data)
    (formal / "raw_codebook.csv").write_bytes(raw_codebook)
    with zipfile.ZipFile(formal / "bookapp_download.zip", "w") as archive:
        archive.writestr("raw_data.csv", raw_data)
        archive.writestr("raw_codebook.csv", raw_codebook)


def expect_failure(checker, formal: Path, expected_text: str) -> None:
    try:
        checker.validate_download_package(formal)
    except ValueError as error:
        assert expected_text in str(error), str(error)
    else:
        raise AssertionError("A changed download package was accepted")



def check_charls_psu_headers(root):
    from copy import deepcopy
    from check_definition_output import check_charls_person_multifile_contract
    folder=root/'charls_psu';folder.mkdir()
    files={'raw_data.csv':b'ID,id,year,communityid,a\n2011_001,001,2011,01,1\n',
           'raw_data_psu.csv':b'communityid,year,b\n01,2011,2\n',
           'raw_codebook.csv':b'Variable,File type,newname\ncommunityid (demographic),uniqID,communityid\na (demographic),uniqID,a\nb (psu),communityID,b\n'}
    record={'schema_version':7,'status':'READY','database':'CHARLS','approved_analysis_vars':['x'],
            'definition_plan':[{'analysis_var':'x'}], 'source_groups':[
       {'raw_variables':['communityid'],'source_identities':['communityid (demographic)'],'source_role':'join_identity'},
       {'raw_variables':['a'],'source_identities':['a (demographic)']},
       {'raw_variables':['b'],'source_identities':['b (psu)']}]}
    def restore(updates=None):
        for path in folder.glob('raw_data*.csv'):path.unlink()
        current={**files,**(updates or {})}
        for name,value in current.items():(folder/name).write_bytes(value)
        with zipfile.ZipFile(folder/'bookapp_download.zip','w') as archive:
            for name,value in current.items():archive.writestr(name,value)
    def verify(rec=record):return check_charls_person_multifile_contract(folder,['communityid','a','b'],rec,list(files))
    def reject(fn):
        try:fn()
        except ValueError:return
        raise AssertionError('Invalid PSU/identity contract accepted')
    restore();assert verify()['join_identity_columns']==['communityid']
    reject(lambda:verify(None))
    wrong=deepcopy(record);wrong['source_groups'][1]['source_identities']=['a (other file)'];reject(lambda:verify(wrong))
    wrong=deepcopy(record);wrong['source_groups'][2]['source_role']='join_identity';reject(lambda:verify(wrong))
    restore({'raw_data_psu.csv':b'communityid,year,b\n01,2011,2\n01,2011,2\n'});reject(verify)
    restore();(folder/'raw_data_psu.csv').write_bytes(b'communityid,year,b\n01,2011,3\n');reject(verify)
    restore({'raw_data_extra.csv':b'year,c\n2011,3\n'});reject(verify)
    restore()

def check_charls_multifile_headers(root: Path) -> None:
    from check_definition_output import check_charls_person_multifile_contract
    folder = root / "charls_person_multifile"
    folder.mkdir()
    files = {
        "raw_data.csv": b"ID,id,year,a\n2011_001,001,2011,1\n",
        "raw_data_household.csv": b"householdid,year,respondent_id,b\n01,2011,001,2\n",
        "raw_codebook.csv": b"Variable,File type,newname\na,uniqID,a\nb,householdID,b\n",
    }

    def restore(updates=None):
        current = {**files, **(updates or {})}
        for path in folder.glob("raw_data*.csv"):
            path.unlink()
        for name, value in current.items():
            (folder / name).write_bytes(value)
        with zipfile.ZipFile(folder / "bookapp_download.zip", "w") as archive:
            for name, value in current.items():
                archive.writestr(name, value)

    def rejects(expected):
        try:
            check_charls_person_multifile_contract(folder, ["a", "b"])
        except ValueError as exc:
            assert expected in str(exc), str(exc)
        else:
            raise AssertionError("Invalid CHARLS multi-file headers accepted")

    restore()
    value = check_charls_person_multifile_contract(folder, ["a", "b"], expected_files=list(files))
    assert value["raw_variables"] == 2
    assert value["files"]["raw_data.csv"]["variables"] == ["a"]
    assert value["files"]["raw_data_household.csv"]["variables"] == ["b"]
    output = subprocess.run([sys.executable, str(REPO_ROOT / "scripts/check_definition_output.py"),
                             "--formal-dir", str(folder), "--raw-vars", "a,b"],
                            capture_output=True, text=True, encoding="utf-8")
    checks = json.loads(output.stdout)["checks"]
    for name in ("CHARLS personal multi-file source contract", "raw_data header", "raw_codebook vars"):
        assert any(item["check"] == name and item["ok"] for item in checks), output.stdout + output.stderr
    assert [item["check"] for item in checks if not item["ok"]] == ["single final log"]
    try:
        check_charls_person_multifile_contract(folder, ["a", "b"], expected_files=["raw_data.csv"])
    except ValueError as exc:
        assert "omits source files" in str(exc)
    else:
        raise AssertionError("Incomplete artifact scope accepted")
    # Unknown source files/types, unplanned fields and missing/reordered fields
    # must fail even when the modified CSVs match a modified original package.
    restore({"raw_data_extra.csv": b"id,year,c\n001,2011,3\n"})
    rejects("source files differ")
    restore({"raw_codebook.csv": b"Variable,File type,newname\na,uniqID,a\nb,other,b\n"})
    rejects("Unsupported")
    restore({"raw_data_household.csv": b"householdid,year,respondent_id\n01,2011,001\n"})
    rejects("header differs")
    restore({"raw_data_household.csv": b"householdid,year,respondent_id,b,c\n01,2011,001,2,3\n"})
    rejects("header differs")
    restore({"raw_data.csv": b"ID,id,year,a,a\n2011_001,001,2011,1,1\n"})
    rejects("header differs")
    restore({"raw_codebook.csv": b"Variable,File type,newname\na,householdID,a\nb,uniqID,b\n"})
    rejects("header differs")
    restore({"raw_codebook.csv": b"Variable,File type,newname\na,uniqID,a\nb,householdID,b\nc,householdID,c\n",
             "raw_data_household.csv": b"householdid,year,respondent_id,c,b\n01,2011,001,3,2\n"})
    try:
        check_charls_person_multifile_contract(folder, ["a", "b", "c"])
    except ValueError as exc:
        assert "header differs" in str(exc)
    else:
        raise AssertionError("Reordered household fields accepted")
    restore()
    (folder / "raw_data_household.csv").unlink()
    rejects("source files differ")
    restore()
    (folder / "raw_data_household.csv").write_bytes(files["raw_data_household.csv"].replace(b",2\n", b",3\n"))
    rejects("changed after download")
    restore()
    try:
        check_charls_person_multifile_contract(folder, ["a"])
    except ValueError as exc:
        assert "aliases differ" in str(exc)
    else:
        raise AssertionError("Reduced raw-variable union accepted")


def main() -> int:
    checker = load_checker()
    raw_data = b"ID,id,year,raw_a\n1_2011,1,2011,1\n"
    raw_codebook = (
        b"Easy label,Variable,File type,newname\n"
        b"A,raw_a (test),individual,raw_a\n"
    )

    with tempfile.TemporaryDirectory(prefix="download_package_gate_") as tmp:
        root = Path(tmp)
        matching = root / "matching"
        write_package(matching, raw_data, raw_codebook)
        result = checker.validate_download_package(matching)
        assert result["files"] == ["raw_codebook.csv", "raw_data.csv"]

        rebuilt = root / "rebuilt"
        write_package(rebuilt, raw_data, raw_codebook)
        (rebuilt / "raw_data.csv").write_bytes(
            b"ID,id,year,raw_a\n1_2011,1,2011,2\n"
        )
        expect_failure(checker, rebuilt, "filtered, supplemented, reordered, or changed")

        filtered = root / "filtered"
        old_data = b"ID,id,year,raw_a,raw_b\n1_2011,1,2011,1,2\n"
        write_package(filtered, old_data, raw_codebook)
        (filtered / "raw_data.csv").write_bytes(raw_data)
        expect_failure(checker, filtered, "filtered, supplemented, reordered, or changed")

        bom_only = root / "bom_only"
        write_package(bom_only, raw_data, raw_codebook)
        (bom_only / "raw_data.csv").write_bytes(b"\xef\xbb\xbf" + raw_data)
        checker.validate_download_package(bom_only)

        renamed = root / "999_any_topic_name"
        write_package(renamed, raw_data, raw_codebook)
        checker.validate_download_package(renamed)
        check_charls_multifile_headers(root)
        check_charls_psu_headers(root)

    print("download package gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
