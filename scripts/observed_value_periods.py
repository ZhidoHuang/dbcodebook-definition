"""Locate an exact raw value by explicitly supplied period field; no recoding."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def observed_value_periods(raw, variable, value, period_column, id_separator=None):
    raw = Path(raw)
    counts = Counter()
    rows = 0
    with raw.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {variable, period_column} <= set(reader.fieldnames):
            raise ValueError("Variable or period column is missing")
        for row in reader:
            rows += 1
            period = row[period_column]
            if not period:
                raise ValueError(f"Empty period at CSV row {rows + 1}")
            if id_separator is not None:
                if not id_separator or id_separator not in period:
                    raise ValueError(f"ID does not contain the supplied separator at CSV row {rows + 1}")
                period, identity = period.rsplit(id_separator, 1)
                if not period or not identity:
                    raise ValueError(f"Incomplete period/ID at CSV row {rows + 1}")
            if row[variable] == value:
                counts[period] += 1
    return {"raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "rows_scanned": rows, "variable": variable, "value": value,
            "period_column": period_column, "id_separator": id_separator,
            "observed_counts": dict(counts), "total_matches": sum(counts.values()),
            "scope": "Exact observed value only; absence does not establish questionnaire coverage or missingness cause."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--variable", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--period-column", required=True)
    parser.add_argument("--id-separator", help="Only if the verified ID is period + separator + identity; split at last separator")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.raw.resolve() == args.out.resolve():
        parser.error("Output must not overwrite raw")
    result = observed_value_periods(args.raw, args.variable, args.value, args.period_column, args.id_separator)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
