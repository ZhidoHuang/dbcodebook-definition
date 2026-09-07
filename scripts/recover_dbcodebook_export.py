"""Install and validate one dbCodeBook download without website-source access."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import time
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


def inspect_archive(archive_path: Path, expected: list[str]) -> dict:
    # Validate outside the destination so a bad download cannot replace good raw.
    with tempfile.TemporaryDirectory(prefix="dbcodebook_check_") as temp:
        staging = Path(temp)
        names, members = install_archive(archive_path, staging)
        return {
            "zip_members": names,
            "codebook": validate_codebook(staging, expected),
            "data": validate_data_members(staging, members, expected),
        }


def download_snapshot(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("download directory is not a directory")
    files = {}
    for path in directory.glob("*.zip"):
        if path.is_file():
            stat = path.stat()
            files[path.name] = [stat.st_size, stat.st_mtime_ns]
    return {"directory": str(directory), "captured_at": time.time(), "files": files}


def wait_for_download(directory: Path, baseline: dict, expected: list[str],
                      timeout: float, poll_interval: float = 0.25) -> dict:
    if str(directory.resolve(strict=True)) != baseline["directory"]:
        raise ValueError("download directory differs from the saved snapshot")
    if timeout < 0 or poll_interval <= 0:
        raise ValueError("download wait must be nonnegative and polling must be positive")
    started = time.monotonic()
    previous = {}
    checked = {}
    rejected = {}
    while True:
        current = download_snapshot(directory)["files"]
        candidates = {name: stat for name, stat in current.items()
                      if baseline["files"].get(name) != stat}
        valid = []
        for name, stat in candidates.items():
            if previous.get(name) != stat:
                continue
            key = (name, *stat)
            if key not in checked:
                try:
                    with contextlib.redirect_stderr(io.StringIO()):
                        report = inspect_archive(directory / name, expected)
                    # A concurrent write invalidates this inspection.
                    after = (directory / name).stat()
                    if [after.st_size, after.st_mtime_ns] != stat:
                        continue
                    checked[key] = report
                except (OSError, ValueError, zipfile.BadZipFile, csv.Error) as error:
                    checked[key] = None
                    rejected[name] = str(error)
            if checked[key] is not None:
                valid.append((name, checked[key]))
        elapsed = round(time.monotonic() - started, 3)
        if len(valid) > 1:
            return {"ok": False, "status": "AMBIGUOUS_DOWNLOADS",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "candidates": [name for name, _ in valid]}
        if valid:
            name, report = valid[0]
            return {"ok": True, "status": "DOWNLOAD_FILE_VERIFIED",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "archive_source": str((directory / name).resolve()), **report}
        if time.monotonic() - started >= timeout:
            return {"ok": False, "status": "CHECK_EXISTING_DOWNLOAD_RECORD",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "rejected": rejected,
                    "message": "No verified new file. Check the existing paid record; do not export again."}
        previous = candidates
        time.sleep(min(poll_interval, max(0, timeout - (time.monotonic() - started))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--snapshot-downloads", type=Path)
    source.add_argument("--watch-downloads", type=Path)
    parser.add_argument("--snapshot-file", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=20)
    parser.add_argument("--database", type=str.lower, choices=("charls", "elsa"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--expect-vars-file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if (args.snapshot_downloads or args.watch_downloads) and not args.snapshot_file:
        parser.error("snapshot and watch modes require --snapshot-file")
    if not args.snapshot_downloads and not all((args.database, args.out, args.expect_vars_file)):
        parser.error("install and watch modes require --database, --out and --expect-vars-file")
    if args.wait_seconds < 0:
        parser.error("--wait-seconds must be nonnegative")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.snapshot_downloads:
            snapshot = download_snapshot(args.snapshot_downloads)
            args.snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            print(json.dumps({"ok": True, "snapshot_file": str(args.snapshot_file),
                              "existing_zip_count": len(snapshot["files"])}))
            return 0
        expected = read_expected_vars_file(args.expect_vars_file)
        archive_path = args.archive
        if args.watch_downloads:
            baseline = json.loads(args.snapshot_file.read_text(encoding="utf-8"))
            observation = wait_for_download(args.watch_downloads, baseline, expected, args.wait_seconds)
            args.snapshot_file.with_name(args.snapshot_file.stem + "_result.json").write_text(
                json.dumps(observation, ensure_ascii=False, indent=2), encoding="utf-8")
            if not observation["ok"]:
                print(json.dumps(observation, ensure_ascii=False))
                return 1
            archive_path = Path(observation["archive_source"])
        validated = ({key: observation[key] for key in ("zip_members", "codebook", "data")}
                     if args.watch_downloads else inspect_archive(archive_path, expected))
        if archive_path.resolve() == (args.out / "bookapp_download.zip").resolve():
            raise ValueError("archive must be outside the managed output files")
        prepare_output_dir(args.out, args.overwrite)
        install_archive(archive_path, args.out)
        report = {
            "ok": True,
            "database": args.database,
            "archive_source": str(archive_path.resolve()),
            **validated,
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
