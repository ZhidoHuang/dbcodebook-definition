from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import zipfile


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

    print("download package gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
