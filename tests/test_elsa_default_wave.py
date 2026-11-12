"""ELSA optional platform Wave_id must remain an identity column."""
import csv
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_definition_output import (check_elsa_raw_contract, check_identity_values,
                                     expected_raw_header, verified_default_sources)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "raw_data.csv"
    def write(header, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer=csv.writer(handle);writer.writerow(header);writer.writerows(rows)
    write(["ID","idauniq","value"], [["Wave 1_001","001","5"]])
    assert not check_elsa_raw_contract(path,["value"])["default_wave_id"]
    write(["ID","idauniq","Wave_id","value"], [["Wave 1_001","001","Wave 1","5"], ["Wave 11_001","001","Wave 11","7"]])
    assert check_elsa_raw_contract(path,["value"])["verified_rows"] == 2
    cases=[
        (["ID","idauniq","Wave_id","value"], [["Wave 1_001","001","Wave 2","5"]]),
        (["ID","idauniq","Wave_id","value"], [["Wave 1_001","001","","5"]]),
        (["ID","idauniq","Wave_id","value"], [["Wave 0_001","001","Wave 0","5"]]),
        (["ID","idauniq","Wave_id","value"], [["Wave 1_001","001","Wave 1","5","extra"]]),
        (["ID","idauniq","Wave_id","value","extra"], [["Wave 1_001","001","Wave 1","5","1"]]),
        (["ID","idauniq","value","Wave_id"], [["Wave 1_001","001","5","Wave 1"]]),
    ]
    for header,rows in cases:
        write(header,rows)
        try:check_elsa_raw_contract(path,["value"])
        except ValueError:pass
        else:raise AssertionError((header,rows))
    assert expected_raw_header("elsa", ["value"]) == ["ID", "idauniq", "Wave_id", "value"]
    raw_header = ["ID", "idauniq", "Wave_id", "value"]
    write(raw_header, [["Wave 1_001", "001", "Wave 1", "5"],
                       ["Wave 11_001", "001", "Wave 11", "7"]])
    assert verified_default_sources(path.parent, "elsa") == {"ID", "idauniq", "Wave_id"}
    header = ["ID", "idauniq", "Wave_id", "result"]
    def check(rows, columns=header):
        results = []
        check_identity_values(path, raw_header, [columns, *rows], columns, results, "elsa")
        return all(item["ok"] for item in results)
    assert check([["Wave 11_001", "001", "Wave 11", 7], ["Wave 1_001", "001", "Wave 1", 5]])
    assert not check([["Wave 1_001", "001", "Wave 11", 5]])
    assert not check([["Wave 1_001", "001", "Wave 1", 5]] * 2)
    assert not check([["Wave 1_001", "001", "Wave 1", "Wave 1", 5]],
                     ["ID", "idauniq", "Wave_id", "Wave", "result"])
    assert not check([["001", "Wave 1", 5]], ["idauniq", "Wave_id", "result"])
    # Historical inputs continue using their existing Wave analysis contract.
    legacy_raw = ["ID", "idauniq", "value"]
    write(legacy_raw, [["Wave 1_001", "001", "5"]])
    legacy_header = ["ID", "idauniq", "Wave", "result"]
    results = []
    check_identity_values(path, legacy_raw, [legacy_header, ["Wave 1_001", "001", 1, 5]],
                          legacy_header, results, "elsa")
    assert all(item["ok"] for item in results), results
print("ELSA_DEFAULT_WAVE_PASS: legacy/new, mismatch, missing, invalid period, extra and misplaced columns")
