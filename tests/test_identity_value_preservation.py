from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_output.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_output_for_identity_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_output.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    checker = load_checker()
    raw_header = ["ID", "id", "year", "value"]
    analysis_header = ["ID", "id", "year", "defined"]

    with tempfile.TemporaryDirectory(prefix="definition_identity_") as tmp:
        raw_path = Path(tmp) / "raw_data.csv"
        raw_path.write_text(
            "ID,id,year,value\n"
            "010104101001_2011,010104101001,2011,1\n"
            "010104101001_2013,010104101001,2013,2\n"
            "010104101002_2011,010104101002,2011,3\n",
            encoding="utf-8",
        )

        matching = [
            analysis_header,
            ["010104101001_2011", "010104101001", 2011, 1],
        ]
        matching_results: list[dict] = []
        checker.check_identity_values(
            raw_path,
            raw_header,
            matching,
            analysis_header,
            matching_results,
        )
        assert matching_results[-1]["ok"] is True

        reordered_subset = [
            analysis_header,
            ["010104101002_2011", "010104101002", 2011, 1],
            ["010104101001_2013", "010104101001", 2013, 1],
        ]
        reordered_results: list[dict] = []
        checker.check_identity_values(
            raw_path,
            raw_header,
            reordered_subset,
            analysis_header,
            reordered_results,
        )
        assert reordered_results[-1]["ok"] is True

        wide_header = ["id", "defined"]
        wide_rows = [wide_header, ["010104101001", 1], ["010104101002", 0]]
        wide_results: list[dict] = []
        checker.check_identity_values(
            raw_path,
            raw_header,
            wide_rows,
            wide_header,
            wide_results,
        )
        assert wide_results[-1]["ok"] is True

        leading_zero_lost = [
            analysis_header,
            ["010104101001_2011", 10104101001, 2011, 1],
        ]
        mismatch_results: list[dict] = []
        checker.check_identity_values(
            raw_path,
            raw_header,
            leading_zero_lost,
            analysis_header,
            mismatch_results,
        )
        assert mismatch_results[-1]["ok"] is False
        mismatch = mismatch_results[-1]["detail"][0]
        assert mismatch["column"] == "id"
        assert mismatch["raw"] == "010104101001"
        assert mismatch["analysis"] == "10104101001"

        invented_identity = [
            analysis_header,
            ["999999999999_2011", "999999999999", 2011, 1],
        ]
        invented_results: list[dict] = []
        checker.check_identity_values(
            raw_path,
            raw_header,
            invented_identity,
            analysis_header,
            invented_results,
        )
        assert invented_results[-1]["ok"] is False
        assert invented_results[-1]["detail"][0]["reason"] == (
            "identity combination is absent from raw data"
        )

    print("identity value preservation fixture PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
