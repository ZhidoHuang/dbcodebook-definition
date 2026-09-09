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
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit


REQUIRED_ZIP_MEMBERS = {"raw_codebook.csv"}
MANAGED_REPORT = "recover_dbcodebook_export_QA.json"
PARTIAL_SUFFIXES = {".crdownload", ".part", ".download"}


def database_page_url(base_url: str, database: str) -> str:
    base_url = base_url.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        fail("--base-url must be an absolute http or https URL")
    return f"{base_url}/home/{database}/"


def build_download_browser_action(
    base_url: str,
    database: str,
    attempt_id: str,
    expected_variable_count: int,
    attempt_file: Path,
) -> dict:
    page_url = database_page_url(base_url, database)
    page_url_json = json.dumps(page_url, ensure_ascii=False)
    attempt_id_json = json.dumps(attempt_id, ensure_ascii=False)
    attempt_file_json = json.dumps(str(attempt_file.resolve()), ensure_ascii=False)
    run_script = rf'''async function resolveDbCodeBookDownloadTab(expectedPageUrl) {{
  if (typeof dbCodeBookBrowser === "undefined" || !dbCodeBookBrowser?.tabs) {{
    throw new Error("请先按浏览器技能连接选定的 Chrome 或 Edge，并绑定 dbCodeBookBrowser");
  }}
  const browser = dbCodeBookBrowser;
  const parseUrl = async value => typeof dbCodeBookParseUrl === "function"
    ? dbCodeBookParseUrl(value) : new URL(value);
  const page = await parseUrl(expectedPageUrl);
  const isMatch = async value => {{
    try {{
      const current = await parseUrl(value);
      return current.origin === page.origin && current.pathname === page.pathname;
    }} catch {{ return false; }}
  }};
  const selected = await browser.tabs.selected();
  if (selected && await isMatch(await selected.url())) return selected;
  const tabs = await browser.tabs.list();
  const matches = [];
  for (const item of tabs) if (await isMatch(item.url)) matches.push(item);
  if (matches.length !== 1) {{
    throw new Error(`未找到唯一匹配的变量选择页，当前找到 ${{matches.length}} 个`);
  }}
  return browser.tabs.get(matches[0].id);
}}
async function triggerDbCodeBookExport(
  tab,
  expectedPageUrl,
  attemptId,
  expectedVariableCount,
  attemptFile
) {{
  const attemptClaimed = typeof dbCodeBookAttemptClaimed !== "undefined" && dbCodeBookAttemptClaimed;
  const fs = attemptClaimed ? null : await import("node:fs/promises");
  if (!attemptClaimed) {{
  try {{
    await fs.stat(attemptFile);
    throw new Error("本次下载已经触发或已登记；请检查本地文件或账号下载记录，不得再次导出");
  }} catch (error) {{
    if (error.code !== "ENOENT") throw error;
  }}
  }}
  const parseUrl = async value => typeof dbCodeBookParseUrl === "function"
    ? dbCodeBookParseUrl(value) : new URL(value);
  const current = await parseUrl(await tab.url());
  const expected = await parseUrl(expectedPageUrl);
  if (current.origin !== expected.origin || current.pathname !== expected.pathname) {{
    throw new Error(`当前标签页不是指定变量选择页：${{current.href}}`);
  }}
  const selectedCount = await tab.playwright.locator("#tag-area .tag").count();
  if (selectedCount < 1) throw new Error("变量选择区为空；未触发下载");
  if (selectedCount !== expectedVariableCount) {{
    throw new Error(
      `网页已选 ${{selectedCount}} 个变量，下载清单为 ${{expectedVariableCount}} 个；未触发下载`
    );
  }}

  const openButton = tab.playwright.locator('button[aria-label="下载数据"]');
  if (await openButton.count() !== 1) throw new Error("未找到唯一的下载入口；未触发下载");
  const modal = tab.playwright.locator("#download-modal");
  const modalStyle = await modal.getAttribute("style");
  if (!modalStyle || !/display\s*:\s*block/i.test(modalStyle)) {{
    await openButton.click();
  }}
  await modal.waitFor({{ state: "visible" }});
  const finalButton = modal.locator("button.bili-btn.confirm");
  if (await finalButton.count() !== 1) throw new Error("未找到唯一的最终下载按钮；未触发下载");

  if (!attemptClaimed) {{
  try {{
    await fs.writeFile(attemptFile, JSON.stringify({{
      attempt_id: attemptId, claimed_at: new Date().toISOString(), page_url: current.href
    }}), {{ flag: "wx" }});
  }} catch (error) {{
    if (error.code === "EEXIST") {{
      throw new Error("本次下载已经触发或已登记；请检查本地文件或账号下载记录，不得再次导出");
    }}
    throw error;
  }}
  }}
  const clickedAt = Date.now();
  const downloadPromise = tab.playwright.waitForEvent("download", {{ timeoutMs: 30000 }});
  let clickWarning = "";
  try {{
    await finalButton.click({{ timeoutMs: 10000 }});
  }} catch (error) {{
    clickWarning = String(error);
  }}
  let download;
  try {{
    download = await downloadPromise;
  }} catch (error) {{
    return {{
      ok: false,
      status: "DOWNLOAD_EVENT_NOT_RECEIVED",
      next_action: "run_watch_command",
      allow_new_export: false,
      attempt_id: attemptId,
      selected_variable_count: selectedCount,
      click_warning: clickWarning,
      message: String(error)
    }};
  }}
  if (!download || typeof download.path !== "function") {{
    return {{
      ok: false,
      status: "DOWNLOAD_PATH_NOT_SUPPORTED",
      next_action: "run_watch_command",
      allow_new_export: false,
      attempt_id: attemptId,
      selected_variable_count: selectedCount,
      click_warning: clickWarning,
      message: "浏览器未提供下载路径接口；请使用已准备的实际下载目录观察命令"
    }};
  }}
  let downloadPath;
  try {{
    downloadPath = await download.path({{ timeoutMs: 120000 }});
  }} catch (error) {{
    return {{
      ok: false,
      status: "DOWNLOAD_PATH_UNAVAILABLE",
      next_action: "run_watch_command",
      allow_new_export: false,
      attempt_id: attemptId,
      selected_variable_count: selectedCount,
      click_warning: clickWarning,
      message: String(error)
    }};
  }}
  return {{
    ok: true,
    status: "DOWNLOAD_FILE_READY",
    next_action: "install_download_path",
    allow_new_export: false,
    attempt_id: attemptId,
    selected_variable_count: selectedCount,
    download_path: downloadPath,
    click_warning: clickWarning,
    browser_elapsed_ms: Date.now() - clickedAt
  }};
}}
var dbCodeBookDownloadPageUrl = {page_url_json};
var dbCodeBookDownloadAttemptId = {attempt_id_json};
var dbCodeBookDownloadAttemptFile = {attempt_file_json};
var dbCodeBookDownloadTab = await resolveDbCodeBookDownloadTab(dbCodeBookDownloadPageUrl);
var dbCodeBookDownloadResult = await triggerDbCodeBookExport(
  dbCodeBookDownloadTab,
  dbCodeBookDownloadPageUrl,
  dbCodeBookDownloadAttemptId,
  {expected_variable_count},
  dbCodeBookDownloadAttemptFile
);
nodeRepl.write(JSON.stringify(dbCodeBookDownloadResult));'''
    return {
        "existing_tab_path": page_url,
        "timeout_ms": 165000,
        "attempt_id": attempt_id,
        "attempt_file": str(attempt_file.resolve()),
        "browser_binding": "dbCodeBookBrowser",
        "run_script": run_script,
    }


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


def managed_output_paths(out_dir: Path) -> list[Path]:
    return [
        out_dir / "bookapp_download.zip",
        out_dir / "raw_codebook.csv",
        out_dir / MANAGED_REPORT,
        *sorted(out_dir.glob("raw_data*.csv")),
    ]


def check_output_replacement(out_dir: Path, overwrite: bool) -> list[Path]:
    existing = [path for path in managed_output_paths(out_dir) if path.exists()]
    if existing and not overwrite:
        fail(
            "output files already exist; use --overwrite only for an intentional replacement",
            detail=[str(path) for path in existing],
        )
    return existing


def prepare_output_dir(out_dir: Path, overwrite: bool) -> None:
    existing = check_output_replacement(out_dir, overwrite)
    out_dir.mkdir(parents=True, exist_ok=True)
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
    partial_files = {}
    for path in directory.iterdir():
        if path.suffix.lower() not in {".zip", *PARTIAL_SUFFIXES}:
            continue
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except FileNotFoundError:
            continue  # The browser may rename a completed partial file during the scan.
        target = files if path.suffix.lower() == ".zip" else partial_files
        target[path.name] = [stat.st_size, stat.st_mtime_ns]
    return {"directory": str(directory), "captured_at": time.time(),
            "files": files, "partial_files": partial_files}


def prepare_download(args: argparse.Namespace) -> dict:
    expected = read_expected_vars_file(args.expect_vars_file)
    from check_definition_source_record import load_json, validate_download_selection
    record_path = args.expect_vars_file.parent / "definition_search_record.json"
    record = load_json(record_path)
    if str(record.get("database", "")).casefold() != args.database.casefold():
        raise ValueError("source record database differs from the requested download")
    validate_download_selection(record_path, args.expect_vars_file, str(record["topic_id"]).zfill(3))
    from execution_report import load, validate_stage_review
    validate_stage_review(load(record_path.parent / "execution_report.json"), "定义逻辑复核")
    check_output_replacement(args.out, args.overwrite)
    snapshot = download_snapshot(args.prepare_download)
    snapshot["expected_vars"] = expected
    attempt_id = str(uuid.uuid4())
    snapshot["attempt_id"] = attempt_id
    args.snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
               "--watch-downloads", snapshot["directory"],
               "--snapshot-file", str(args.snapshot_file.resolve()),
               "--database", args.database, "--out", str(args.out.resolve()),
               "--expect-vars-file", str(args.expect_vars_file.resolve()),
               "--wait-seconds", str(args.wait_seconds)]
    if args.overwrite:
        command.append("--overwrite")
    return {"ok": True, "next_action": "run_browser_action_once",
            "snapshot_file": str(args.snapshot_file.resolve()),
            "browser_action": build_download_browser_action(
                args.base_url, args.database, attempt_id, len(expected),
                args.snapshot_file.with_name(f"download_attempt_{attempt_id}.json"),
            ),
            "watch_command": "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in command)}


def wait_for_download(directory: Path, baseline: dict, expected: list[str],
                      timeout: float, poll_interval: float = 0.25) -> dict:
    if str(directory.resolve(strict=True)) != baseline["directory"]:
        raise ValueError("download directory differs from the saved snapshot")
    if timeout < 0 or poll_interval <= 0:
        raise ValueError("download wait must be nonnegative and polling must be positive")
    if "expected_vars" in baseline and baseline["expected_vars"] != expected:
        raise ValueError("selection changed after download preparation")
    started = time.monotonic()
    previous = {}
    checked = {}
    rejected = {}
    while True:
        observed = download_snapshot(directory)
        current = observed["files"]
        partial = {name: stat for name, stat in observed["partial_files"].items()
                   if baseline.get("partial_files", {}).get(name) != stat}
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
                except OSError as error:
                    rejected[name] = str(error)
                    continue  # A transient browser file lock can clear without changing size.
                except (ValueError, zipfile.BadZipFile, csv.Error) as error:
                    checked[key] = None
                    rejected[name] = str(error)
            if checked[key] is not None:
                valid.append((name, checked[key]))
        elapsed = round(time.monotonic() - started, 3)
        if len(valid) > 1:
            return {"ok": False, "status": "AMBIGUOUS_DOWNLOADS",
                    "next_action": "identify_download_file",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "candidates": [name for name, _ in valid]}
        if valid:
            name, report = valid[0]
            return {"ok": True, "status": "DOWNLOAD_FILE_VERIFIED",
                    "next_action": "continue_definition",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "archive_source": str((directory / name).resolve()), **report}
        if time.monotonic() - started >= timeout:
            if partial:
                return {"ok": False, "status": "DOWNLOAD_FILE_INCOMPLETE",
                        "next_action": "check_download_progress",
                        "allow_new_export": False, "elapsed_seconds": elapsed,
                        "partial_files": sorted(partial), "rejected": rejected,
                        "message": "A new partial file exists. Check its progress before recovery or another export."}
            return {"ok": False, "status": "CHECK_EXISTING_DOWNLOAD_RECORD",
                    "next_action": "check_existing_download_record",
                    "allow_new_export": False, "elapsed_seconds": elapsed,
                    "rejected": rejected,
                    "message": "No verified new file. Check the existing paid record; do not export again."}
        previous = candidates
        time.sleep(min(poll_interval, max(0, timeout - (time.monotonic() - started))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--prepare-download", type=Path)
    source.add_argument("--snapshot-downloads", type=Path)
    source.add_argument("--watch-downloads", type=Path)
    parser.add_argument("--snapshot-file", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=20)
    parser.add_argument("--database", type=str.lower, choices=("charls", "elsa"))
    parser.add_argument("--base-url")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--expect-vars-file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if (args.prepare_download or args.snapshot_downloads or args.watch_downloads) and not args.snapshot_file:
        parser.error("snapshot and watch modes require --snapshot-file")
    if not args.snapshot_downloads and not all((args.database, args.out, args.expect_vars_file)):
        parser.error("install and watch modes require --database, --out and --expect-vars-file")
    if args.prepare_download and not args.base_url:
        parser.error("--prepare-download requires --base-url")
    if args.wait_seconds < 0:
        parser.error("--wait-seconds must be nonnegative")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.prepare_download:
            print(json.dumps(prepare_download(args), ensure_ascii=True))
            return 0
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
                print(json.dumps(observation, ensure_ascii=True))
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
            "status": "DOWNLOAD_FILE_VERIFIED",
            "next_action": "continue_definition",
            "allow_new_export": False,
            "database": args.database,
            "archive_source": str(archive_path.resolve()),
            **validated,
        }
        (args.out / MANAGED_REPORT).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError, zipfile.BadZipFile, csv.Error) as error:
        print(f"RECOVER_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
