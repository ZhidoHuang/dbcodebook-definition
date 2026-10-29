"""Full HRS Tracker columns exported automatically; scoped by full file identity."""
import csv
import json
import hashlib
import re
import html
from pathlib import Path

TRACKER_FILE = "TRACKER_FILE_HRS_2022_EARLY_RELEASE_TRACKER_FILE_VERSION_2_RESPONDENT"
TRACKER_DEFAULTS = {"OVHHID", "OVPN", "OVRESULT", "OVYEAR"}


def documented_lowercase_periods(directory):
    """Use only periods whose same-package note declares the lowercase keys."""
    path = Path(directory) / '连接说明.html'
    if not path.is_file():
        return set()
    text = html.unescape(re.sub(r'<[^>]+>', ' ', path.read_text(encoding='utf-8-sig')))
    periods = set()
    for match in re.finditer(r'ID\s*=\s*Wave_id\s*\|\s*hhid\s*\|\s*pn\s*\[([^\]]+)\]', text):
        parts = re.split(r'[、,，\s]+', match[1].strip())
        if not all(re.fullmatch(r'\d{4}', part) for part in parts):
            raise ValueError('Unsupported period in HRS lowercase identity declaration')
        periods.update(parts)
    return periods


def person_identity(row, lowercase_periods=()):
    """Resolve a missing default pair only from an explicitly documented ID."""
    household, person = str(row.get('HHID') or ''), str(row.get('PN') or '')
    if household.strip() and person.strip():
        return household, person
    period = str(row.get('Wave_id') or '')
    if household.strip() or person.strip() or period not in lowercase_periods:
        raise ValueError('HRS missing person keys without a complete documented fallback')
    match = re.fullmatch(r'(\d{4})\|(\d{6})\|(\d{3})', str(row.get('ID') or ''))
    if not match or match[1] != period:
        raise ValueError('HRS ID does not match its documented period and person-key shape')
    return match[2], match[3]

def record_defaults(record):
    if str(record.get("database", "")).lower() != "hrs":
        return set()
    pairs = [(i, a) for g in record.get("source_groups", [])
             for i, a in zip(g.get("source_identities", []), g.get("raw_variables", []))]
    defaults = {a for i, a in pairs if a in TRACKER_DEFAULTS and i == f"{a} ({TRACKER_FILE})"}
    if defaults and not any(i.endswith(f" ({TRACKER_FILE})") and a not in defaults for i,a in pairs):
        raise ValueError("Tracker default columns require a selected Tracker source")
    return defaults

def codebook_defaults(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as h:
        rows = list(csv.DictReader(h))
    tracker = [x for x in rows if x.get("Variable", "").endswith(f" ({TRACKER_FILE})")]
    # Old packages explicitly selected these fields and remain readable as old packages.
    manual = {x["Variable"].split(" ",1)[0] for x in tracker} & TRACKER_DEFAULTS
    return TRACKER_DEFAULTS - manual if tracker else set()

def accepts_legacy_package(process_dir, formal_dir):
    if process_dir is None:
        return False
    report_path = Path(process_dir) / 'execution_report.json'
    if not report_path.is_file():
        return False
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    binding = report.get('copy_update', {})
    legacy = binding.get('legacy_evidence', {})
    if not legacy or Path(binding.get('formal_dir', '')).resolve() != Path(formal_dir).resolve():
        return False
    old = Path(legacy['path'])
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()
    if not old.is_file() or sha(old) != legacy.get('sha256', '').upper():
        raise ValueError('Historical package evidence has changed')
    artifacts = binding.get('result', {}).get('artifacts', {})
    required = ['raw_data.csv', 'raw_codebook.csv']
    required += [name for name in artifacts if name.lower().endswith('.zip')]
    if not all(name in artifacts and sha(Path(formal_dir) / name) == artifacts[name].upper()
               for name in required):
        raise ValueError('Historical raw package no longer matches the accepted baseline')
    return True


def validate_defaults(path, header, *, legacy_package=False):
    expected = codebook_defaults(path)
    missing = expected - set(header)
    if missing and not legacy_package:
        raise ValueError("Missing automatic Tracker columns: " + ", ".join(sorted(missing)))
    return expected & set(header) if legacy_package else expected


# These repeated condition files have exporter provenance columns, not observations.
ADAMS_CONDITION_FILES = {
    "ADAMS_MEDICAL_CONDITIONS_INITIAL_VISIT_CONDITION": {"A": "2001-2003"},
    "ADAMS_MEDICAL_CONDITIONS_FOLLOW_UP_VISIT_CONDITION": {
        "B": "2002-2005", "C": "2006-2008", "D": "2008-2009"},
}
ADAMS_PROVENANCE = {"RowIndex", "source_file", "source_row"}


def validate_adams_repeat(directory, member, header):
    prefix, suffix = "raw_data_repeat_", ".csv"
    if not member.startswith(prefix) or not member.endswith(suffix):
        return set()
    family = member[len(prefix):-len(suffix)]
    if family not in ADAMS_CONDITION_FILES:
        return set()
    directory = Path(directory)
    with (directory / "raw_codebook.csv").open(encoding="utf-8-sig", newline="") as handle:
        sources = [row for row in csv.DictReader(handle)
                   if row.get("Variable", "").endswith(f" ({family})")]
    if not sources or any(row.get("File type") != "rePersonID" for row in sources):
        raise ValueError("ADAMS repeat requires its full rePersonID dictionary identity")
    required = ADAMS_PROVENANCE | {"ID", "HHID", "PN", "Wave_id"}
    if not required <= set(header):
        raise ValueError("ADAMS repeat missing identity or provenance columns")
    if set(header) - required != {row.get("newname", row["Variable"]) for row in sources}:
        raise ValueError("ADAMS repeat columns do not match its dictionary family")
    row_indexes, source_rows = set(), set()
    with (directory / member).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not re.fullmatch(r"[0-9]{6}", row["HHID"]) or not re.fullmatch(r"[0-9]{3}", row["PN"]):
                raise ValueError("ADAMS repeat invalid person keys")
            if row["ID"] != "|".join([row["Wave_id"], row["HHID"], row["PN"]]):
                raise ValueError("ADAMS repeat ID disagrees with person and period")
            allowed = {f"ADAMS1{visit}H_C": period
                       for visit, period in ADAMS_CONDITION_FILES[family].items()}
            if allowed.get(row["source_file"]) != row["Wave_id"]:
                raise ValueError("ADAMS repeat source file and original period disagree")
            if any(not re.fullmatch(r"[1-9][0-9]*", row[key]) for key in ("RowIndex", "source_row")):
                raise ValueError("ADAMS repeat provenance row numbers must be positive integers")
            source_key = (row["source_file"], row["source_row"])
            if row["RowIndex"] in row_indexes or source_key in source_rows:
                raise ValueError("ADAMS repeat duplicated provenance row")
            row_indexes.add(row["RowIndex"])
            source_rows.add(source_key)
    return ADAMS_PROVENANCE


# Internet questionnaires can have repeated complete forms, not condition rows.
# This validates transport provenance only; the topic must decide how to resolve
# repeated answers before making one row per person and period.
INTERNET_RESPONDENT_FILE = "INTERNET_SURVEY_INTERNET_QUESTIONNAIRE_RESPONDENT"
INTERNET_SOURCE_PERIODS = {"net03_r": "2003", "net06_r": "2006", "NET07_R": "2007",
                           "NET09_R": "2009", "NET11_R": "2011", "NET13I_R": "2013"}
HRS_REPEAT_FILES = set(ADAMS_CONDITION_FILES) | {INTERNET_RESPONDENT_FILE}


def validate_internet_repeat(directory, member, header):
    if member != "raw_data_repeat_" + INTERNET_RESPONDENT_FILE + ".csv":
        return set()
    directory = Path(directory)
    with (directory / "raw_codebook.csv").open(encoding="utf-8-sig", newline="") as handle:
        sources = [row for row in csv.DictReader(handle)
                   if row.get("Variable", "").endswith(f" ({INTERNET_RESPONDENT_FILE})")]
    if not sources or any(row.get("File type") != "rePersonID" for row in sources):
        raise ValueError("Internet repeat requires its full rePersonID dictionary identity")
    required = ADAMS_PROVENANCE | {"ID", "HHID", "PN", "Wave_id"}
    if not required <= set(header):
        raise ValueError("Internet repeat missing identity or provenance columns")
    if set(header) - required != {row.get("newname", row["Variable"]) for row in sources}:
        raise ValueError("Internet repeat columns do not match its dictionary family")
    note_path = directory / "连接说明.html"
    note = html.unescape(re.sub(r'<[^>]+>', ' ', note_path.read_text(encoding='utf-8-sig'))) if note_path.is_file() else ''
    # Bind mixed-case fallback to this file's own transport section, not a
    # declaration for a different file in the same package.
    marker = "合并文件（官方）：net03_r.da、net06_r.da、NET07_R.da、NET09_R.da、NET11_R.da、NET13I_R.da"
    section = note.split(marker, 1)[1].split("变量来源", 1)[0] if marker in note else ''
    section = section.split("raw_data_repeat_ADAMS", 1)[0]
    lower_2011 = bool(re.search(r'ID\s*=\s*Wave_id\s*\|\s*hhid\s*\|\s*PN\s*\[2011\]', section))
    row_indexes, source_rows = set(), set()
    with (directory / member).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            match = re.fullmatch(r"(\d{4})\|(\d{6})\|(\d{3})", row["ID"])
            if not match or match[1] != row["Wave_id"] or match[3] != row["PN"]:
                raise ValueError("Internet repeat ID disagrees with person and period")
            if row["HHID"] != match[2] and not (row["HHID"] == '' and row["Wave_id"] == '2011' and lower_2011):
                raise ValueError("Internet repeat missing household key without its documented mixed-case fallback")
            if INTERNET_SOURCE_PERIODS.get(row["source_file"]) != row["Wave_id"]:
                raise ValueError("Internet repeat source file and original period disagree")
            if any(not re.fullmatch(r"[1-9][0-9]*", row[key]) for key in ("RowIndex", "source_row")):
                raise ValueError("Internet repeat provenance row numbers must be positive integers")
            source_key = (row["source_file"], row["source_row"])
            if row["RowIndex"] in row_indexes or source_key in source_rows:
                raise ValueError("Internet repeat duplicated provenance row")
            row_indexes.add(row["RowIndex"]); source_rows.add(source_key)
    return ADAMS_PROVENANCE


def validate_hrs_repeat(directory, member, header):
    if member == "raw_data_repeat_" + INTERNET_RESPONDENT_FILE + ".csv":
        return validate_internet_repeat(directory, member, header)
    return validate_adams_repeat(directory, member, header)
