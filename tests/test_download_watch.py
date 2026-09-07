import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import recover_dbcodebook_export as recovery


def make_zip(path, variable="value"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("raw_data.csv", f"ID,id,year,{variable}\n1_2011,1,2011,7\n")
        archive.writestr("raw_codebook.csv", f"Variable,newname\n{variable},{variable}\n")


def wait(directory, baseline, timeout=0.03):
    return recovery.wait_for_download(directory, baseline, ["value"], timeout, 0.001)


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    downloads = root / "downloads"
    downloads.mkdir()
    old = downloads / "old.zip"
    make_zip(old)
    baseline = recovery.download_snapshot(downloads)
    assert wait(downloads, baseline)["status"] == "CHECK_EXISTING_DOWNLOAD_RECORD"
    make_zip(downloads / "wrong.zip", "other")
    wrong = wait(downloads, baseline)
    assert not wrong["ok"] and "wrong.zip" in wrong["rejected"]
    assert wrong["allow_new_export"] is False

    # Simulate a completed browser file with no download notification at all.
    make_zip(downloads / "new.zip")
    accepted = wait(downloads, baseline)
    assert accepted["ok"] and accepted["archive_source"].endswith("new.zip")
    assert accepted["data"]["raw_data.csv"]["rows"] == 1
    make_zip(downloads / "duplicate.zip")
    assert wait(downloads, baseline)["status"] == "AMBIGUOUS_DOWNLOADS"

    fresh = root / "fresh"
    fresh.mkdir()
    baseline = recovery.download_snapshot(fresh)
    partial = fresh / "later.zip.crdownload"
    partial.write_bytes(b"partial")
    assert not wait(fresh, baseline)["ok"]

    def finish_file():
        time.sleep(0.04)
        make_zip(partial)
        partial.rename(fresh / "later.zip")

    writer = threading.Thread(target=finish_file)
    writer.start()
    try:
        assert wait(fresh, baseline, timeout=2)["ok"]
    finally:
        writer.join()
    try:
        wait(downloads, baseline)
    except ValueError as error:
        assert "differs" in str(error)
    else:
        raise AssertionError("snapshot from another directory was accepted")

    # Invalid replacements must leave an existing successful output untouched.
    out = root / "out"
    out.mkdir()
    sentinel = out / "raw_data.csv"
    sentinel.write_text("original", encoding="utf-8")
    selection = root / "selection.txt"
    selection.write_text("value\n", encoding="utf-8")
    failed = subprocess.run([
        sys.executable, str(Path(recovery.__file__)), "--archive", str(downloads / "wrong.zip"),
        "--database", "CHARLS", "--out", str(out), "--expect-vars-file", str(selection), "--overwrite",
    ], capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
    assert failed.returncode != 0 and sentinel.read_text() == "original"

    snap_file = root / "snapshot.json"
    baseline = recovery.download_snapshot(fresh)
    snap_file.write_text(json.dumps(baseline), encoding="utf-8")
    shutil.copyfile(old, fresh / "cli.zip")
    installed = subprocess.run([
        sys.executable, str(Path(recovery.__file__)), "--watch-downloads", str(fresh),
        "--snapshot-file", str(snap_file), "--database", "CHARLS", "--out", str(out),
        "--expect-vars-file", str(selection), "--overwrite", "--wait-seconds", "2",
    ], capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    assert installed.returncode == 0, installed.stderr
    assert (out / recovery.MANAGED_REPORT).exists()
    assert json.loads((root / "snapshot_result.json").read_text())["allow_new_export"] is False

print("download file observation fixtures PASS")
