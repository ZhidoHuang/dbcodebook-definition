from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tempfile
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
RECOVER_PATH = REPO_ROOT / "scripts" / "recover_dbcodebook_export.py"


def load_recover():
    spec = importlib.util.spec_from_file_location(
        "recover_dbcodebook_export_for_test", RECOVER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load recover_dbcodebook_export.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ZipResponse:
    status_code = 200

    def __init__(self, content: bytes):
        self.content = content

    def get(self, key: str, default: str = "") -> str:
        if key == "Content-Type":
            return "application/zip"
        return default


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def main() -> int:
    recover = load_recover()
    bom = b"\xef\xbb\xbf"

    with tempfile.TemporaryDirectory(prefix="recover_multitable_") as tmp:
        out_dir = Path(tmp)
        files = {
            "raw_data.csv": bom + b"ID,id,year,householdid\n1_2011,1,2011,10\n",
            "raw_data_household.csv": (
                bom
                + b"householdid,year,respondent_id,ce007\n10,2011,1,1 Yes\n"
            ),
            "raw_codebook.csv": (
                bom
                + b"Easy label,Variable,File type,newname\n"
                + b"Household id,householdid (demographic),uniqID,householdid\n"
                + b"Any transfer,ce007 (family transfer),householdID,ce007\n"
            ),
        }
        response = ZipResponse(build_zip(files))
        names, data_members = recover.write_zip_and_extract(response, out_dir)

        selection_path = out_dir / "download_selection.txt"
        selection_path.write_bytes(bom + b"householdid\nce007\n")
        assert recover.read_expected_vars_file(selection_path) == [
            "householdid",
            "ce007",
        ]

        assert data_members == ["raw_data.csv", "raw_data_household.csv"]
        assert set(names) == set(files)
        for name, expected in files.items():
            assert (out_dir / name).read_bytes() == expected

        reports = recover.validate_data_members(
            out_dir,
            data_members,
            ["householdid", "ce007"],
        )
        assert reports["raw_data.csv"]["data_vars"] == ["householdid"]
        assert reports["raw_data_household.csv"]["data_vars"] == ["ce007"]

        recover.prepare_output_dir(out_dir, overwrite=True)
        assert not (out_dir / "raw_data.csv").exists()
        assert not (out_dir / "raw_data_household.csv").exists()
        assert not (out_dir / "raw_codebook.csv").exists()
        assert not (out_dir / "bookapp_download.zip").exists()

    print("recover multitable fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
