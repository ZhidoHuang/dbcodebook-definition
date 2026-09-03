"""Install and validate one dbCodeBook download without website-source access."""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path


REQUIRED_ZIP_MEMBERS = {"raw_codebook.csv"}
MANAGED_REPORT = "recover_dbcodebook_export_QA.json"


def fail(message: str, *, detail: object | None = None) -> None:
    payload: dict[str, object] = {"ok": False, "error": message}
    if detail is not None:
        payload["detail"] = detail
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    raise ValueError(message)


def validate_expected_vars(values: Iterable[str], source: str) -> list[str]:
    cleaned = [item.strip() for item in values if item.strip()]
    if not cleaned:
        fail(f"{source} is empty")
    duplicates = sorted({item for item in cleaned if cleaned.count(item) > 1})
    if duplicates:
        fail(f"{source} contains duplicated variables", detail=duplicates)
    return cleaned


def read_expected_vars_file(path: Path) -> list[str]:
    return validate_expected_vars(
        path.read_text(encoding="utf-8-sig").splitlines(), "--expect-vars-file"
    )


def prepare_output_dir(out_dir: Path, overwrite: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    managed = [
        out_dir / "bookapp_download.zip",
        out_dir / "raw_codebook.csv",
        out_dir / MANAGED_REPORT,
        *sorted(out_dir.glob("raw_data*.csv")),
    ]
    existing = [path for path in managed if path.exists()]
    if existing and not overwrite:
        fail(
            "output files already exist; use --overwrite only for an intentional replacement",
            detail=[str(path) for path in existing],
        )
    for path in existing:
        path.unlink()


def select_data_zip_members(names: list[str]) -> list[str]:
    members = sorted(
        name for name in names if Path(name).name == name and name.startswith("raw_data") and name.endswith(".csv")
    )
    if not members:
        fail("download zip does not contain raw_data*.csv", detail=names)
    return members


def _safe_csv_members(archive: zipfile.ZipFile) -> tuple[list[str], list[str]]:
    names = archive.namelist()
    nested_or_unsafe = [
        name
        for name in names
        if Path(name).name != name or Path(name).is_absolute() or ".." in Path(name).parts
    ]
    if nested_or_unsafe:
        fail("download zip contains nested or unsafe paths", detail=nested_or_unsafe)
    missing = sorted(REQUIRED_ZIP_MEMBERS.difference(names))
    if missing:
        fail("download zip is missing required files", detail=missing)
    return names, select_data_zip_members(names)


def install_archive(archive_path: Path, out_dir: Path) -> tuple[list[str], list[str]]:
    payload = archive_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names, data_members = _safe_csv_members(archive)
        for name in ["raw_codebook.csv", *data_members]:
            (out_dir / name).write_bytes(archive.read(name))
    (out_dir / "bookapp_download.zip").write_bytes(payload)
    return names, data_members


def write_zip_and_extract(response, out_dir: Path) -> tuple[list[str], list[str]]:
    """Compatibility helper for fixture responses; it does not access a website."""

    if getattr(response, "status_code", None) != 200:
        fail("download response failed", detail=getattr(response, "status_code", None))
    if "application/zip" not in response.get("Content-Type", ""):
        fail("download response is not a zip archive")
    temp = out_dir / ".dbcodebook_download.tmp"
    temp.write_bytes(response.content)
    try:
        return install_archive(temp, out_dir)
    finally:
        temp.unlink(missing_ok=True)


def identity_columns_for_member(data_member: str) -> set[str]:
    if data_member == "raw_data.csv":
        return {"ID", "id", "year", "idauniq", "Wave"}
    if data_member == "raw_data_household.csv":
        return {"ID", "id", "year", "householdid", "respondent_id"}
    if data_member == "raw_data_psu.csv":
        return {"communityid", "year"}
    return {
        "ID", "id", "year", "idauniq", "Wave", "householdid",
        "respondent_id", "communityid",
    }


def read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            fail("CSV is empty", detail=str(path))
    raise AssertionError("unreachable")


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def validate_data_members(
    out_dir: Path,
    data_members: Iterable[str],
    expected_vars: Iterable[str],
) -> dict[str, dict]:
    expected = list(expected_vars)
    expected_set = set(expected)
    found_in: dict[str, list[str]] = {name: [] for name in expected}
    reports: dict[str, dict] = {}
    for member in data_members:
        path = out_dir / member
        header = read_csv_header(path)
        duplicates = sorted({name for name in header if header.count(name) > 1})
        if duplicates:
            fail(f"{member} contains duplicated columns", detail=duplicates)
        identities = identity_columns_for_member(member)
        data_vars = [name for name in header if name not in identities]
        unexpected = [name for name in data_vars if name not in expected_set]
        if unexpected:
            fail(f"{member} contains variables outside the selection", detail=unexpected)
        for name in data_vars:
            found_in[name].append(member)
        reports[member] = {
            "header": header,
            "rows": count_csv_rows(path),
            "cols": len(header),
            "identity_columns": [name for name in header if name in identities],
            "data_vars": data_vars,
        }
    missing = [name for name, members in found_in.items() if not members]
    repeated = {name: members for name, members in found_in.items() if len(members) > 1}
    if missing or repeated:
        fail(
            "raw data files do not cover the selected variables exactly once",
            detail={"missing": missing, "repeated": repeated},
        )
    return reports


def read_codebook_aliases(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            fail("raw_codebook.csv has no header")
        field = "newname" if "newname" in reader.fieldnames else "Variable"
        if field not in reader.fieldnames:
            fail("raw_codebook.csv has neither newname nor Variable")
        aliases = [str(row.get(field, "")).strip() for row in reader]
    if any(not value for value in aliases):
        fail(f"raw_codebook.csv contains empty {field}")
    duplicates = sorted({name for name in aliases if aliases.count(name) > 1})
    if duplicates:
        fail(f"raw_codebook.csv contains duplicated {field}", detail=duplicates)
    return aliases


def validate_codebook(out_dir: Path, expected_vars: list[str]) -> dict[str, object]:
    aliases = read_codebook_aliases(out_dir / "raw_codebook.csv")
    missing = [name for name in expected_vars if name not in aliases]
    unexpected = [name for name in aliases if name not in expected_vars]
    if missing or unexpected:
        fail(
            "raw_codebook.csv does not match the selected variables",
            detail={"missing": missing, "unexpected": unexpected},
        )
    return {"rows": len(aliases), "aliases": aliases}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--database", required=True, choices=("charls", "elsa"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expect-vars-file", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected = read_expected_vars_file(args.expect_vars_file)
        prepare_output_dir(args.out, args.overwrite)
        names, data_members = install_archive(args.archive, args.out)
        report = {
            "ok": True,
            "database": args.database,
            "archive_source": str(args.archive.resolve()),
            "zip_members": names,
            "codebook": validate_codebook(args.out, expected),
            "data": validate_data_members(args.out, data_members, expected),
        }
        (args.out / MANAGED_REPORT).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError, zipfile.BadZipFile, csv.Error) as error:
        if not isinstance(error, ValueError):
            print(f"RECOVER_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
