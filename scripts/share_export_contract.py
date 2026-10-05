"""Ordinary SHARE Wave 1–9 personal uniqID files only; IDs stay opaque."""
import csv
import re
from pathlib import Path

ORDINARY_WAVES = {f"Wave {i}" for i in range(1, 10)}
IDENTIFIERS = {"ID", "Wave_id", "Record_id", "mergeid", "hhid", "country", "intid", "intidwX"}
REQUIRED_KEYS = {"ID", "Wave_id", "mergeid"}
CODEBOOK_COLUMNS = {"Variable", "Label", "Period", "File type", "Match key", "newname"}


def read_unique_codebook(path: Path) -> tuple[list[str], set[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not CODEBOOK_COLUMNS.issubset(reader.fieldnames or []):
            raise ValueError("SHARE codebook requires Variable, Label, Period, File type, Match key, newname")
        rows = list(reader)
    aliases, sources, files = [], set(), set()
    for row in rows:
        if any(row.get(k) is None for k in CODEBOOK_COLUMNS):
            raise ValueError("SHARE codebook has malformed rows")
        match = re.fullmatch(r"([^()\s]+) \((.+)\)", row["Variable"])
        alias = row["newname"].strip()
        if not match or not alias or alias in aliases or row["Variable"] in sources:
            raise ValueError("SHARE codebook has invalid or duplicate identity/alias")
        if row["File type"] != "uniqID" or row["Match key"] != "Wave_id + mergeid（ID）":
            raise ValueError("SHARE adapter supports personal uniqID sources only")
        periods = {s.strip() for s in row["Period"].split(",") if s.strip()}
        if not periods or not periods.issubset(ORDINARY_WAVES):
            raise ValueError("SHARE adapter supports ordinary Wave 1–9 only")
        aliases.append(alias); sources.add(row["Variable"]); files.add(match[2])
    if not aliases:
        raise ValueError("SHARE codebook is empty")
    return aliases, IDENTIFIERS | {f"intid ({name})" for name in files}


def validate_unique_csv(path: Path, expected: list[str], identities: set[str]) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not REQUIRED_KEYS.issubset(header):
            raise ValueError("SHARE raw requires unique columns and ID, Wave_id, mergeid")
        business = [s for s in header if s not in identities]
        if len(business) != len(expected) or set(business) != set(expected):
            raise ValueError("SHARE raw business columns differ from selection")
        ids, keys, periods = set(), set(), set()
        count = 0
        for row in reader:
            if None in row or any(v is None for v in row.values()) or any(row.get(k) in (None, "") for k in REQUIRED_KEYS):
                raise ValueError("SHARE raw has malformed rows or empty identity")
            rid, wave, person = (row[k] for k in ("ID", "Wave_id", "mergeid"))
            if wave not in ORDINARY_WAVES:
                raise ValueError("SHARE raw contains an unsupported period/product")
            if rid in ids or (wave, person) in keys:
                raise ValueError("SHARE raw has duplicate ID or person-wave key")
            ids.add(rid); keys.add((wave, person)); periods.add(wave); count += 1
    return {"rows": count, "key": ["Wave_id", "mergeid"], "platform_id": "opaque character ID", "periods": sorted(periods)}


def validate_unique_package(directory: Path, members: list[str], expected: list[str]) -> dict:
    if members != ["raw_data.csv"]:
        raise ValueError("SHARE adapter supports one personal raw_data.csv only; other record levels unsupported")
    aliases, identities = read_unique_codebook(directory / "raw_codebook.csv")
    if set(aliases) != set(expected) or len(aliases) != len(expected):
        raise ValueError("SHARE codebook aliases differ from selection")
    return validate_unique_csv(directory / "raw_data.csv", expected, identities)


def validate_unique_preview(payload: dict, selected: dict[str, str]) -> dict:
    """Check a captured normal-UI response; never request the preview endpoint.

    Only sampled rows are checked, so this is not full-download/key acceptance.
    """
    import tempfile
    files = payload.get("files", [])
    if payload.get("variables_limited") is not False or len(selected) > 50:
        raise ValueError("SHARE preview is limited; cannot verify all selected sources")
    if (payload.get("selected_variables") != len(selected) or
            payload.get("preview_variables") != len(selected) or
            payload.get("total_files") != 2 or len(files) != 2):
        raise ValueError("SHARE preview selection/file counts differ")
    personal = [f for f in files if f.get("file_type") == "uniqID"]
    dictionaries = [f for f in files if f.get("file_type") == "dictionary"]
    if len(personal) != 1 or len(dictionaries) != 1:
        raise ValueError("SHARE preview includes unsupported file types")
    data, dictionary = personal[0], dictionaries[0]
    for f in files:
        columns, rows = f.get("columns", []), f.get("rows", [])
        total, sample = f.get("total_rows"), f.get("preview_rows")
        if (isinstance(total, bool) or not isinstance(total, int) or total < 0 or
                isinstance(sample, bool) or not isinstance(sample, int) or
                sample != len(rows) or sample > total or
                any(len(row) != len(columns) for row in rows)):
            raise ValueError("SHARE preview row/column dimensions are inconsistent")
    if dictionary["total_rows"] != len(selected) or dictionary["preview_rows"] != len(selected):
        raise ValueError("SHARE preview dictionary is incomplete")
    if data["preview_rows"] != min(data["total_rows"], 10):
        raise ValueError("SHARE preview sample is incomplete")
    if data.get("match_key") != "Wave_id + mergeid（ID）":
        raise ValueError("SHARE preview personal match key differs")
    source_parts = [re.fullmatch(r"([^()\s]+) \((.+)\)", identity) for identity in selected]
    if any(match is None for match in source_parts):
        raise ValueError("SHARE selection has invalid full source identities")
    source_files = {match[2] for match in source_parts}
    if set(data.get("file_list", [])) != source_files:
        raise ValueError("SHARE preview source file list differs")
    if sorted(data.get("variables", [])) != sorted(match[1] for match in source_parts):
        raise ValueError("SHARE preview original variables differ")
    observed = {dict(zip(dictionary["columns"], row)).get("Variable"):
                dict(zip(dictionary["columns"], row)).get("newname") for row in dictionary["rows"]}
    if observed != selected:
        raise ValueError("SHARE preview source identities/aliases differ")
    key_indexes = [data["columns"].index(key) for key in REQUIRED_KEYS if key in data["columns"]]
    if any(not isinstance(row[index], str) for row in data["rows"] for index in key_indexes):
        raise ValueError("SHARE preview identities must remain strings")
    with tempfile.TemporaryDirectory(prefix="share_preview_check_") as temp:
        directory = Path(temp)
        for f, name in ((dictionary, "raw_codebook.csv"), (data, "raw_data.csv")):
            with (directory/name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle); writer.writerow(f["columns"]); writer.writerows(f["rows"])
        contract = validate_unique_package(directory, ["raw_data.csv"], list(selected.values()))
    return {"scope": "captured preview sample only", "sample_contract": contract,
            "reported_total_rows": data["total_rows"], "full_file_verified": False}
