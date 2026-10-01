import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from observed_value_periods import observed_value_periods

with tempfile.TemporaryDirectory() as directory:
    raw = Path(directory) / "raw.csv"
    with raw.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID", "year", "answer"])
        writer.writerows([["Wave 2_001", "2010", "typo"], ["Wave 3_002", "2011", "typo"],
                         ["Wave 4_003", "2012", "typo"], ["Wave 6_004", "2014", "typo"],
                         ["Wave 6_005", "2014", "typo"], ["Wave 7_006", "2015", "TyPo"]])
    result = observed_value_periods(raw, "answer", "typo", "ID", "_")
    assert result["observed_counts"] == {"Wave 2": 1, "Wave 3": 1, "Wave 4": 1, "Wave 6": 2}
    assert result["total_matches"] == 5 and result["rows_scanned"] == 6
    assert observed_value_periods(raw, "answer", "absent", "year")["observed_counts"] == {}
    assert observed_value_periods(raw, "answer", "typo", "year")["observed_counts"]["2014"] == 2
    for column, separator in [("missing", None), ("ID", "!")]:
        try:
            observed_value_periods(raw, "answer", "typo", column, separator)
            raise AssertionError("Invalid input accepted")
        except ValueError:
            pass
print("OBSERVED_VALUE_PERIODS_PASS")
