"""Explicit household exception must not weaken personal identity checks."""
from pathlib import Path
import csv, json, os, subprocess, sys, tempfile, zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_definition_source_record import analysis_identity_contract, validate_render_identity_contract, validate_download_package, primary_raw_name
from check_definition_output import check_long_table, check_identity_values
from source_record_binding import research_record

RECORD = {"database": "CHARLS", "analysis_unit": "household_period", "identity_keys": ["householdid", "year"]}
def check(rows, record=RECORD):
    results = []
    return check_long_table(rows, rows[0], results, "charls", record)

def main():
    rows = [["householdid", "year"], ["001", "2011"], ["001", "2013"]]
    assert check(rows)
    good = 'render_definition_bundle(database="CHARLS", analysis_unit="household_period", identity_keys=c("householdid", "year"))'
    validate_render_identity_contract(good, RECORD, "CHARLS")
    for bad, record in ((good, {}), ('render_definition_bundle()', RECORD), (good.replace('"year"', '"id"'), RECORD)):
        try:
            validate_render_identity_contract(bad, record, "CHARLS")
            raise AssertionError("source/code contract mismatch accepted")
        except ValueError:
            pass
    assert research_record(RECORD)["identity_keys"] == ["householdid", "year"]
    assert research_record(RECORD)["analysis_unit"] == "household_period"
    assert not check(rows, None)  # No personal id: default still fails.
    assert check_long_table([["id", "year"], ["001", 2011]], ["id", "year"], [], "charls")
    assert not check(rows + [rows[1]])
    assert not check([rows[0], [" ", "2011"]])
    assert not check([rows[0], ["001", 2011]])
    assert not check([rows[0], [1, "2011"]])
    for bad in ({**RECORD, "identity_keys": ["id", "year"]}, {**RECORD, "database": "ELSA"}, {"analysis_unit": "other"}):
        assert not check(rows, bad)
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        raw = temp / "raw_data_household.csv"
        with raw.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(rows)
        for body, expected in ((rows, True), ([rows[0], rows[1]], False), ([rows[0], rows[2], rows[1]], False), (rows + [rows[1]], False)):
            results = []
            check_identity_values(raw, rows[0], body, rows[0], results, "charls", source_record=RECORD)
            assert all(x["ok"] for x in results) == expected, results
        # Only the original filename changes; identity/value expectations above stay unchanged.
        codebook = temp / "raw_codebook.csv"
        codebook.write_text("newname\nhouseholdid\n", encoding="utf-8")
        with zipfile.ZipFile(temp / "bookapp_download.zip", "w") as archive:
            for path in (raw, codebook):
                archive.write(path, path.name)
        assert primary_raw_name(RECORD, "CHARLS") == raw.name
        assert validate_download_package(temp, RECORD)["files"] == ["raw_codebook.csv", raw.name]

        def rejects_package():
            try:
                validate_download_package(temp, RECORD)
            except ValueError:
                return
            raise AssertionError("invalid household original package accepted")

        original = raw.read_bytes()
        legacy = temp / "raw_data.csv"
        legacy.write_bytes(original)
        rejects_package()  # A historical alias beside the native file is forbidden.
        raw.unlink()
        rejects_package()  # A missing native file cannot fall back to that alias.
        legacy.unlink()
        raw.write_bytes(original + b"002,2015\n")
        rejects_package()  # Extracted content must still match the unchanged zip.
        raw.write_bytes(original)
        archive_path = temp / "bookapp_download.zip"
        original_archive = archive_path.read_bytes()
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(raw.name, original + b"002,2015\n")
            archive.write(codebook, codebook.name)
        rejects_package()  # Changed zip content must not match an unchanged native CSV.
        archive_path.write_bytes(original_archive)
        assert validate_download_package(temp, RECORD)["files"] == ["raw_codebook.csv", raw.name]

        person = temp / "person"
        person.mkdir()
        (person / "raw_data.csv").write_bytes(original)
        (person / "raw_codebook.csv").write_bytes(codebook.read_bytes())
        with zipfile.ZipFile(person / "bookapp_download.zip", "w") as archive:
            for name in ("raw_data.csv", "raw_codebook.csv"):
                archive.write(person / name, name)
        assert primary_raw_name(None, "CHARLS") == "raw_data.csv"
        assert validate_download_package(person)["files"] == ["raw_codebook.csv", "raw_data.csv"]
        record = temp / "record.json"
        record.write_text(json.dumps(RECORD), encoding="utf-8")
        rscript = os.environ.get("RSCRIPT")
        if rscript:
            wrapper = temp / "identity-test.R"
            literal = lambda path: json.dumps(str(path).replace("\\", "/"), ensure_ascii=True)
            wrapper.write_text('Sys.setlocale("LC_CTYPE", ".UTF-8")\nargs <- c(' + literal(ROOT) + ',' + literal(record) + ')\nsource(' + literal(ROOT / "tests/test_household_identity.R") + ', encoding="UTF-8")\n', encoding="ascii")
            subprocess.run([rscript, "--vanilla", str(wrapper)], check=True)
    print("HOUSEHOLD_IDENTITY_PASS")

if __name__ == "__main__":
    main()

