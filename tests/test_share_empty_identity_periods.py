"""SHARE source periods constrain business values, not empty identity rows."""
import csv
import sys
import tempfile
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from share_export_contract import validate_unique_package


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)


def main():
    with tempfile.TemporaryDirectory(prefix="share_empty_identity_") as tmp:
        directory = Path(tmp)
        header = ["ID", "Wave_id", "mergeid", "answer", "second"]
        note = (
            'SHARE 连接说明\n记录单位：受访者 × 调查时期\n'
            '连接键：ID = Wave_id + "_" + mergeid\n'
            'sharew2_ph.dta [Wave 2]\n └─ x → answer\n'
            'sharew4_ph.dta [Wave 4]\n └─ y → second\n'
            'sharew1_unrelated.dta [Wave 1]\n └─ unrelated\n'
        )
        (directory / "连接说明.html").write_text(
            "<div>" + escape(note) + "</div>", encoding="utf-8"
        )
        write_csv(directory / "raw_codebook.csv", [
            ["Variable", "Label", "File type", "newname"],
            ["x (PH)", "First", "uniqID", "answer"],
            ["y (PH)", "Second", "uniqID", "second"],
        ])
        valid = [
            ["a", "Wave 2", "01", "Yes", ""],
            ["b", "Wave 4", "01", "", "No"],
            ["c", "Wave 1", "01", "", ""],
        ]

        def validate(rows):
            write_csv(directory / "raw_data.csv", [header, *rows])
            return validate_unique_package(
                directory, ["raw_data.csv"], ["answer", "second"]
            )

        result = validate(valid)
        assert result["rows"] == 3
        assert result["source_periods"] == ["Wave 2", "Wave 4"]
        assert result["empty_record_periods"] == ["Wave 1"]

        def fails(rows, fragment):
            try:
                validate(rows)
            except ValueError as error:
                assert fragment in str(error), str(error)
            else:
                raise AssertionError("Invalid source-period fixture was accepted")

        # Neither an unrelated file nor another selected variable can authorize x.
        for value in ["Unexpected", " ", "NA"]:
            fails(valid[:2] + [["c", "Wave 1", "01", value, ""]], "raw periods differ")
        fails([valid[0], ["b", "Wave 4", "01", "Unexpected", "No"]], "raw periods differ")
        fails([["a", "Wave 2", "01", "Yes", "Unexpected"]], "raw periods differ")
        fails(valid + [valid[0]], "duplicate")
        fails([["a", "Wave 10", "01", "", ""]], "unsupported period")
        fails([["a", "Wave 2", "", "Yes", ""]], "empty identity")
        print("SHARE_EMPTY_IDENTITY_PERIODS_PASS")


if __name__ == "__main__":
    main()
