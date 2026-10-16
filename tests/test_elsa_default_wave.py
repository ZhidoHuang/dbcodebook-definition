"""ELSA optional platform Wave_id must remain an identity column."""
import csv
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_definition_output import check_elsa_raw_contract

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
print("ELSA_DEFAULT_WAVE_PASS: legacy/new, mismatch, missing, invalid period, extra and misplaced columns")
