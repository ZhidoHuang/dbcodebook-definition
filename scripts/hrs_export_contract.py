"""Full HRS Tracker columns exported automatically; scoped by full file identity."""
import csv
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

def validate_defaults(path, header):
    expected = codebook_defaults(path)
    missing = expected - set(header)
    if missing:
        raise ValueError("Missing automatic Tracker columns: " + ", ".join(sorted(missing)))
    return expected
