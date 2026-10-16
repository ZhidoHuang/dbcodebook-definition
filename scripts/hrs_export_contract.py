"""Full HRS Tracker columns exported automatically; scoped by full file identity."""
import csv
import json
import hashlib
from pathlib import Path

TRACKER_FILE = "TRACKER_FILE_HRS_2022_EARLY_RELEASE_TRACKER_FILE_VERSION_2_RESPONDENT"
TRACKER_DEFAULTS = {"OVHHID", "OVPN", "OVRESULT", "OVYEAR"}

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
