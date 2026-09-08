from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_source_record.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_source_record_for_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_source_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    checker = load_checker()
    record = {
        "schema_version": 3,
        "topic_id": "037",
        "status": "READY",
        "logic_review": {**dict.fromkeys((*checker.REQUIRED_LOGIC_CHECKS, *checker.REQUIRED_V3_LOGIC_CHECKS), True), "result": "clear"},
        "logic_issues": [],
        "source_groups": [
            {"raw_variables": ["raw_a", "raw_b", "family_1_early"]},
            {"raw_variables": ["family_2_early"]},
            {"raw_variables": ["raw_c"]},
        ],
        "alias_families": [
            {"template": "family_{n}_early", "start": 1, "end": 2}
        ],
        "candidate_decisions": [
            {
                "selected_raw": [
                    "raw_a",
                    "raw_b",
                    "family_1_early",
                    "family_2_early",
                    "raw_c",
                ],
                "excluded_raw": ["raw_unused"],
            }
        ],
    }

    with tempfile.TemporaryDirectory(prefix="download_selection_gate_") as tmp:
        root = Path(tmp)
        record_path = root / "definition_search_record.json"
        selection_path = root / "download_selection.txt"
        record_path.write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )

        # Page order may differ from the source-group order; completeness must not.
        selection_path.write_text(
            "raw_c\nfamily_2_early\nraw_a\nfamily_1_early\nraw_b\n",
            encoding="utf-8",
        )
        result = checker.validate_download_selection(
            record_path, selection_path, "037"
        )
        assert result["ok"] is True
        assert result["variables"] == 5
        assert result["alias_families"] == 1

        record["logic_review"]["result"] = "pending"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        try:
            checker.validate_download_selection(record_path, selection_path, "037")
        except ValueError as error:
            assert "logic_review.result" in str(error)
        else:
            raise AssertionError("Unfinished logic review passed the download gate")
        record["logic_review"]["result"] = "clear"
        record_path.write_text(json.dumps(record), encoding="utf-8")

        selection_path.write_text(
            "raw_a\nraw_b\nfamily_1_early\nfamily_2_early\n", encoding="utf-8"
        )
        try:
            checker.validate_download_selection(record_path, selection_path, "037")
        except ValueError as error:
            assert "missing=['raw_c']" in str(error)
        else:
            raise AssertionError("Missing source variable was not rejected")

        # A family cannot change suffix partway through merely because only
        # some original names collided on the download page.
        record["source_groups"][1]["raw_variables"] = ["family_2_"]
        record["candidate_decisions"][0]["selected_raw"][3] = "family_2_"
        record_path.write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        selection_path.write_text(
            "raw_c\nfamily_2_\nraw_a\nfamily_1_early\nraw_b\n",
            encoding="utf-8",
        )
        try:
            checker.validate_download_selection(record_path, selection_path, "037")
        except ValueError as error:
            assert "inconsistent suffixes" in str(error)
            assert "family_2_early" in str(error)
        else:
            raise AssertionError("Split alias family was not rejected")

    print("download selection gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
