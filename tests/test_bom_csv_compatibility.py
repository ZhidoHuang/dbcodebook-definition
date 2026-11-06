from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_output.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_output_for_bom_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_output.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    checker = load_checker()
    csv_text = "ID,id,year,value\n100_2011,100,2011,1\n"

    with tempfile.TemporaryDirectory(prefix="definition_bom_regression_") as tmp:
        tmp_dir = Path(tmp)
        plain = tmp_dir / "plain.csv"
        bom = tmp_dir / "bom.csv"
        plain.write_text(csv_text, encoding="utf-8", newline="")
        bom.write_bytes(b"\xef\xbb\xbf" + csv_text.encode("utf-8"))

        expected_header = ["ID", "id", "year", "value"]
        for path in (plain, bom):
            assert checker.read_csv_header(path) == expected_header
            assert checker.count_csv_records(path) == 1

    print(json.dumps({
        "ok": True,
        "python_header_plain": expected_header,
        "python_header_bom": expected_header,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
