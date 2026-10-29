"""Self-check a variable-definition output directory before validation.

This tool is intentionally generic. It checks the repeated mechanical issues
that should not reach the validation thread: forbidden files, raw headers,
analysis workbook columns, codebook variables, and final log status.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import fnmatch
import hashlib
import html
import json
import re
import sys
import zipfile
from pathlib import Path
from html.parser import HTMLParser
from xml.etree import ElementTree as ET


NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
READER_COPY_NAME = "文案.md"


def display_policy(formal_dir: Path, analysis_vars: list[str] | None = None, record: dict | None = None) -> dict:
    """Resolve the explicit copy/plan contract, never infer a module from its prose."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from definition_display import resolve_display_policy
    copy_path = formal_dir / READER_COPY_NAME
    text = copy_path.read_text(encoding="utf-8-sig") if copy_path.is_file() else ""
    return resolve_display_policy(text, analysis_vars=analysis_vars, record=record)


class DefinedSurfaceParser(HTMLParser):
    """Read renderer-owned variable identifiers independently of visible labels."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.variables: list[str] = []
        self.invalid_detail_markers: list[dict] = []
        self.overview_variables: list[str] = []
        self.overview_count = 0
        self.overview_depth = 0
        self.current_overview_group = ""
        self.current_detail_group = ""
        self.current_overview_role = ""
        self.component_overview_variables = []
        self.overview_groups: list[tuple[str, str]] = []
        self.detail_groups: list[tuple[str, str]] = []
        self.group_titles: list[tuple[str, str, str]] = []
        self._title = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        group = values.get("data-component-group")
        if group is not None and values.get("data-variable-role") in {"source", "component", "defined"}:
            if tag == "a":
                self.current_overview_group = group
                self.current_overview_role = values["data-variable-role"]
            elif tag == "summary":
                self.current_detail_group = group
            self._title = (tag, group, values["data-variable-role"], [])
        if tag == "table":
            if (values.get("data-defined-overview") == "true"
                    or "heatmap-table" in (values.get("class", "") or "").split()):
                self.overview_count += 1
                self.overview_depth = 1
            elif self.overview_depth:
                self.overview_depth += 1
        href = values.get("href", "") or ""
        if self.overview_depth and tag == "a" and href.startswith("#var-"):
            self.overview_variables.append(href[len("#var-"):])
            if self.current_overview_role == "component":
                self.component_overview_variables.append(href[len("#var-"):])
            self.overview_groups.append((href[len("#var-"):], self.current_overview_group))
        variable = values.get("data-defined-variable")
        is_detail = tag == "span" and "var-name" in (values.get("class", "") or "").split()
        if variable is not None or is_detail:
            if not is_detail or not variable or values.get("id") != f"var-{variable}":
                self.invalid_detail_markers.append(values)
        if variable:
            self.variables.append(variable)
        if is_detail and (values.get("id", "") or "").startswith("var-"):
            self.detail_groups.append((values["id"][4:], self.current_detail_group))

    def handle_data(self, data: str) -> None:
        if self._title is not None:
            self._title[3].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._title is not None and self._title[0] == tag:
            _, group, role, chunks = self._title
            self.group_titles.append((group, role, "".join(chunks).strip()))
            self._title = None
        if tag == "table" and self.overview_depth:
            self.overview_depth -= 1


def check_compact_surfaces(formal_dir: Path, note_text: str, variables: list[str], results: list[dict]) -> None:
    """Compact modules omit Criteria but retain a complete Defined display."""
    forbidden = sorted(path.name for path in formal_dir.glob("*_definition.html"))
    if forbidden:
        fail(results, "compact module omitted definition artifact", forbidden)
    else:
        ok(results, "compact module omitted definition artifact")
    detail_files = sorted(formal_dir.glob("*_detail.html"))
    if len(detail_files) != 1:
        fail(results, "compact module detail artifact", [path.name for path in detail_files])
        return
    for label, text in (("note", note_text), ("detail", detail_files[0].read_text(encoding="utf-8-sig"))):
        if (re.search(r"(?mi)^##\s+(?:定义|Definition|Criteria)\s*$", text)
                or re.search(r'<td\b[^>]*\bclass=[\"\'][^\"\']*\bplain-cell\b', text, re.I)
                or re.search(r'<th\b[^>]*>\s*(?:Definition|Criteria)\s*</th>', text, re.I)):
            fail(results, f"compact module {label} omitted definition table", "Definition/Criteria table remains")
        else:
            ok(results, f"compact module {label} omitted definition table")
        pairs = extract_category_pairs(text)
        if not pairs or any(role not in {"component", "defined"} for _, role in pairs):
            fail(results, f"compact module {label} categories", pairs)
        else:
            ok(results, f"compact module {label} categories", pairs)
        parser = DefinedSurfaceParser()
        parser.feed(text)
        if parser.invalid_detail_markers or parser.variables != variables:
            fail(results, f"compact module {label} variable coverage", {"expected": variables, "actual": parser.variables, "invalid_markers": parser.invalid_detail_markers})
        else:
            ok(results, f"compact module {label} variable coverage", variables)
        result_overview = [v for v in parser.overview_variables if v in variables or v not in parser.component_overview_variables]
        if parser.overview_count != 1 or result_overview != variables:
            fail(results, f"compact module {label} overview coverage", {"expected": variables, "actual": parser.overview_variables, "overview_tables": parser.overview_count})
        else:
            ok(results, f"compact module {label} overview coverage", variables)


def formal_note_files(formal_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in formal_dir.glob("*.md")
        if path.name != READER_COPY_NAME
    )


def split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]



def include_formal_r(formal_dir, expected_files):
    if any(name.lower().endswith(".r") for name in expected_files):
        return expected_files
    candidates = sorted(path.name for path in formal_dir.glob("define_*.R"))
    if len(candidates) != 1:
        raise ValueError(f"Include the intended formal R in --expected-files; expected one define_*.R, found {candidates}")
    return [*expected_files, candidates[0]]


def normalize_var(value: str) -> str:
    return value.split(" (", 1)[0].strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check definition output artifacts.")
    parser.add_argument('--language', choices=['en', 'ko'])
    parser.add_argument('--dataset-id')
    parser.add_argument(
        "--db",
        choices=["charls", "elsa", "hrs", "share", "knhanes", "klosa", "chns", "mhas", "nhanes", "nhanesiii", "nhis"],
        default="charls",
        help="Database identity mode. Defaults to charls for backward compatibility.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--formal-dir", type=Path)
    mode.add_argument("--public-r-script", type=Path,
                      help="Check dictionary and outline before executing R; no outputs are written.")
    parser.add_argument("--process-dir", type=Path)
    parser.add_argument("--complete", action="store_true", help="Require and bind the full output-check scope; partial checks cannot authorize publication.")
    parser.add_argument("--expected-files", help="Comma-separated required file names.")
    parser.add_argument("--raw-vars", help="Comma-separated expected raw variables after database identity columns.")
    parser.add_argument("--analysis-db", help="Analysis data table file name in formal dir (xlsx, or explicitly planned csv).")
    parser.add_argument("--analysis-columns", help="Comma-separated expected analysis db columns.")
    parser.add_argument("--analysis-codebook", help="Analysis codebook xlsx file name in formal dir.")
    parser.add_argument("--analysis-vars", help="Comma-separated expected analysis variables.")
    parser.add_argument(
        "--check-summary-facts",
        action="store_true",
        help=(
            "Check the current summary structure, definition-table variable order, "
            "analysis workbooks, and summary indentation."
        ),
    )
    parser.add_argument("--forbid-vars", help="Comma-separated variables that must not appear.")
    parser.add_argument(
        "--required-user-text",
        help="Comma-separated reader-facing facts required in both the note and definition HTML.",
    )
    parser.add_argument(
        "--criteria-evolution-text",
        help="Comma-separated cross-period identity lines required in Criteria 注意点, in display order with br separation.",
    )
    parser.add_argument("--log-prefix", help="Expected final log prefix, e.g. CHARLS_drinking_status.")
    parser.add_argument("--require-log-exit-code", action="store_true")
    parser.add_argument("--max-md", type=int, default=1)
    parser.add_argument("--report", type=Path, help="Optional QA report path.")
    args = parser.parse_args()
    if args.complete and args.report is None and args.process_dir is not None:
        args.report = args.process_dir / "result_check.json"
    if args.complete:
        required = ("formal_dir", "process_dir", "expected_files", "raw_vars", "analysis_db",
                    "analysis_columns", "analysis_codebook", "analysis_vars",
                    "check_summary_facts", "require_log_exit_code", "report")
        missing = [name for name in required if not getattr(args, name)]
        if missing:
            parser.error("--complete requires: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    if args.public_r_script is not None:
        output_options = {key: value for key, value in vars(args).items()
                          if key not in {"formal_dir", "public_r_script", "db", "max_md"} and value}
        if output_options or args.db != "charls" or args.max_md != 1:
            parser.error("--public-r-script is a standalone preflight; do not combine it with output-check options")
    return args


def fail(results: list[dict], check: str, detail: object) -> None:
    results.append({"ok": False, "check": check, "detail": detail})


def ok(results: list[dict], check: str, detail: object = None) -> None:
    payload = {"ok": True, "check": check}
    if detail is not None:
        payload["detail"] = detail
    results.append(payload)


def read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader)


def count_csv_records(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def read_codebook_vars(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        candidates = ["newname", "Variable", "variable", "name"]
        column = next((item for item in candidates if item in reader.fieldnames), reader.fieldnames[0])
        return [normalize_var(row.get(column, "")) for row in reader if row.get(column, "").strip()]


def expected_raw_header(db: str, raw_vars: list[str]) -> list[str]:
    if db == 'nhis':
        return ['ID','Wave_id','Survey_year',*raw_vars]
    if db == "nhanesiii":
        return ["SEQN", *raw_vars]
    if db == "nhanes":
        return ["SEQN", "YEAR", *raw_vars]
    if db == "chns":
        return ["ID", "IDind", "WAVE", *raw_vars]
    if db == "klosa":
        return ["ID", "Harmonized_id", "Wave_id", *raw_vars]
    if db == "elsa":
        return ["ID", "idauniq", *raw_vars]
    if db == "share":
        return ["ID", "Wave_id", "mergeid", *raw_vars]
    if db == "hrs":
        return ["ID", "HHID", "PN", "Wave_id", *raw_vars]
    if db == "knhanes":
        return ["ID", "id", "year", *raw_vars]
    return ["ID", "id", "year", *raw_vars]


def check_elsa_raw_contract(path: Path, raw_vars: list[str]) -> dict:
    """Accept the optional default Wave_id without treating it as a source variable."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        legacy = ["ID", "idauniq", *raw_vars]
        current = ["ID", "idauniq", "Wave_id", *raw_vars]
        if header not in (legacy, current):
            raise ValueError(f"ELSA raw header must be {legacy} or {current}; actual={header}")
        if header == legacy:
            return {"header": header, "default_wave_id": False}
        rows = 0
        for number, row in enumerate(reader, start=2):
            record = row.get("ID") or ""
            wave = row.get("Wave_id") or ""
            if (None in row or not re.fullmatch(r"Wave [1-9]\d*", wave)
                    or record.split("_", 1)[0] != wave):
                raise ValueError(f"ELSA Wave_id must equal the valid Wave prefix of ID; CSV row {number}")
            rows += 1
        return {"header": header, "default_wave_id": True, "verified_rows": rows}


def charls_layered_raw_headers(raw_vars: list[str]) -> list[list[str]]:
    """Return the supported CHARLS export identities by data layer."""
    return [
        ["ID", "id", "year", *raw_vars],
        ["householdid", "year", "respondent_id", *raw_vars],
        ["householdid", "year", "id", *raw_vars],
        ["communityid", "year", *raw_vars],
    ]


def check_charls_person_multifile_contract(formal_dir, raw_vars, source_record=None,
                                         expected_files=None):
    """Check native personal/household or personal/PSU layers without joining them."""
    from check_definition_source_record import analysis_identity_contract, validate_download_package
    if analysis_identity_contract(source_record, "CHARLS")["analysis_unit"] != "person_period":
        raise ValueError("CHARLS personal multi-file contract requires person_period")
    paths = {path.name: path for path in formal_dir.glob("raw_data*.csv")}
    psu_layer = "raw_data_psu.csv" in paths
    required = {"raw_data.csv", "raw_data_psu.csv" if psu_layer else "raw_data_household.csv"}
    if set(paths) != required:
        raise ValueError("CHARLS personal multi-file source files differ; expected=" +
                         repr(sorted(required)) + ", actual=" + repr(sorted(paths)))
    if expected_files is not None and not required <= set(expected_files):
        raise ValueError("CHARLS complete artifact scope omits source files: " +
                         ", ".join(sorted(required - set(expected_files))))
    package = validate_download_package(formal_dir, source_record)
    with (formal_dir / "raw_codebook.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"newname", "File type"} <= set(reader.fieldnames):
            raise ValueError("CHARLS multi-file dictionary requires newname and File type")
        rows = list(reader)
    aliases = [row["newname"] for row in rows]
    if aliases != raw_vars or len(set(aliases)) != len(aliases):
        raise ValueError("CHARLS multi-file dictionary aliases differ from planned raw variables")
    file_types = {row["File type"] for row in rows}
    if file_types != {"uniqID", "communityID" if psu_layer else "householdID"}:
        raise ValueError("Unsupported CHARLS personal multi-file File type: " + repr(sorted(file_types)))
    join_identities = []
    if psu_layer:
        if not (isinstance(source_record, dict) and source_record.get("schema_version") == 7
                and source_record.get("status") == "READY" and source_record.get("database", "").upper() == "CHARLS"
                and source_record.get("approved_analysis_vars") and source_record.get("definition_plan")):
            raise ValueError("CHARLS PSU contract requires the current READY schema7 source record")
        pairs = [(a, i) for g in source_record.get("source_groups", [])
                 for a, i in zip(g.get("raw_variables", []), g.get("source_identities", []))]
        if any(len(g.get("raw_variables", [])) != len(g.get("source_identities", [])) for g in source_record.get("source_groups", [])):
            raise ValueError("CHARLS PSU source identities require positional full identities")
        if set(pairs) != {(r["newname"], r.get("Variable")) for r in rows}:
            raise ValueError("CHARLS PSU source record differs from complete dictionary identities")
        personal_key = [r for r in rows if r["newname"] == "communityid" and r["File type"] == "uniqID"
                        and r.get("Variable", "").startswith("communityid (")]
        if len(personal_key) != 1:
            raise ValueError("CHARLS PSU contract requires the actual personal communityid source identity")
        for group in source_record.get("source_groups", []):
            if group.get("source_role") == "join_identity":
                if group.get("raw_variables") != ["communityid"] or group.get("source_identities") != [personal_key[0]["Variable"]]:
                    raise ValueError("Unsupported CHARLS PSU join_identity declaration")
                join_identities.append("communityid")
        if len(join_identities) > 1 or "communityid" in source_record["approved_analysis_vars"]:
            raise ValueError("CHARLS PSU connection identity is not an analysis result")
    contracts = {}
    for name, file_type in (("raw_data.csv", "uniqID"),
                            ("raw_data_psu.csv", "communityID") if psu_layer else ("raw_data_household.csv", "householdID")):
        variables = [row["newname"] for row in rows if row["File type"] == file_type]
        header = read_csv_header(paths[name])
        prefixes = [["ID", "id", "year"]] if file_type == "uniqID" else [
            ["householdid", "year", "respondent_id"], ["householdid", "year", "id"]]
        if file_type == "communityID":
            prefixes = [["communityid", "year"]]
        if not any(header == [*prefix, *variables] for prefix in prefixes):
            raise ValueError("CHARLS multi-file header differs for " + name +
                             "; expected ordered " + file_type + " dictionary subset")
        contracts[name] = {"header": header, "variables": variables, "file_type": file_type}
    if psu_layer:
        with paths["raw_data_psu.csv"].open(encoding="utf-8-sig", newline="") as handle:
            keys = [(r["communityid"], r["year"]) for r in csv.DictReader(handle)]
        if any(not all(k) for k in keys) or len(keys) != len(set(keys)):
            raise ValueError("CHARLS PSU communityid/year keys must be nonempty and unique")
    return {"files": contracts, "raw_variables": len(aliases), "download_package": package,
            "join_identity_columns": join_identities}


def check_charls_household_identifier(path: Path) -> dict:
    rows = 0
    keys: set[tuple[str, str]] = set()
    bad_suffix_rows: list[int] = []
    duplicated_rows: list[int] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for csv_row, row in enumerate(reader, start=2):
            rows += 1
            record_id = (row.get("ID") or "").strip()
            year = (row.get("year") or "").strip()
            suffix = f"_{year}"
            if not record_id or not year or not record_id.endswith(suffix):
                bad_suffix_rows.append(csv_row)
                continue
            derived_id = record_id[: -len(suffix)]
            if not derived_id:
                bad_suffix_rows.append(csv_row)
                continue
            key = (derived_id, year)
            if key in keys:
                duplicated_rows.append(csv_row)
            keys.add(key)
    return {
        "ok": not bad_suffix_rows and not duplicated_rows,
        "mode": "derived_from_ID_suffix",
        "rows": rows,
        "unique_id_year": len(keys),
        "bad_suffix_rows": bad_suffix_rows[:20],
        "duplicated_id_year_rows": duplicated_rows[:20],
    }


def read_elsa_codebook(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [name for name in ["Variable", "newname"] if name not in fieldnames]
        if missing_columns:
            raise ValueError(f"ELSA codebook missing columns: {', '.join(missing_columns)}")
        rows = list(reader)

    exported_names = [(row.get("newname") or "").strip() for row in rows]
    if any(not name for name in exported_names):
        raise ValueError("ELSA codebook newname must not be empty")
    if len(exported_names) != len(set(exported_names)):
        raise ValueError("ELSA codebook newname must be unique")

    return exported_names


def col_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    total = 0
    for ch in letters:
        total = total * 26 + (ord(ch.upper()) - ord("A") + 1)
    return total - 1


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.findall(f"{NS_MAIN}si"):
        pieces = [node.text or "" for node in si.iter(f"{NS_MAIN}t")]
        values.append("".join(pieces))
    return values


def first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rel_id = workbook.find(f"{NS_MAIN}sheets/{NS_MAIN}sheet").attrib[f"{NS_REL}id"]
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f"{NS_PACKAGE_REL}Relationship"):
        if rel.attrib["Id"] == rel_id:
            target = rel.attrib["Target"]
            return "xl/" + target.lstrip("/")
    raise ValueError("First worksheet relationship not found.")


def read_xlsx_rows(path: Path) -> list[list[object]]:
    rows: list[list[object]] = []
    with zipfile.ZipFile(path) as zf:
        shared_strings = load_shared_strings(zf)
        # Large sparse exports can have multi-GB worksheet XML. Parse one row
        # at a time; do not retain the XML tree or trust the dimension hint.
        with zf.open(first_sheet_path(zf)) as stream:
            sheet_data = None
            for event, element in ET.iterparse(stream, events=("start", "end")):
                if event == "start" and element.tag == f"{NS_MAIN}sheetData":
                    sheet_data = element
                if event != "end" or element.tag != f"{NS_MAIN}row":
                    continue
                rows.append(_xlsx_row_values(element, shared_strings))
                element.clear()
                if sheet_data is not None:
                    sheet_data.remove(element)
    return rows


def read_table_rows(path: Path) -> list[list[object]]:
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig',newline='') as stream:
            rows = [[value if value != '' else None for value in row] for row in csv.reader(stream)]
        if rows and (any(value is None for value in rows[0]) or len(rows[0]) != len(set(rows[0]))
                     or any(len(row) != len(rows[0]) for row in rows[1:])):
            raise ValueError('Malformed final CSV table: '+path.name)
        return rows
    if path.suffix.lower() != '.xlsx':
        raise ValueError('Unsupported final table format: '+path.name)
    return read_xlsx_rows(path)


def _xlsx_row_values(row, shared_strings) -> list[object]:
        values: list[object] = []
        for cell in row.findall(f"{NS_MAIN}c"):
            idx = col_to_index(cell.attrib.get("r", "A1"))
            while len(values) <= idx:
                values.append(None)
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                inline_node = cell.find(f"{NS_MAIN}is")
                value = (
                    "".join(
                        text_node.text or ""
                        for text_node in inline_node.iter(f"{NS_MAIN}t")
                    )
                    if inline_node is not None
                    else None
                )
            else:
                value_node = cell.find(f"{NS_MAIN}v")
                if value_node is None:
                    value = None
                elif cell_type == "s":
                    value = shared_strings[int(value_node.text)]
                else:
                    raw = value_node.text or ""
                    if re.fullmatch(r"-?\d+(\.\d+)?", raw):
                        number = float(raw)
                        value = int(number) if number.is_integer() else number
                    else:
                        value = raw
            values[idx] = value
        return values


def check_long_table(rows, header, results, db="", source_record=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_definition_source_record import analysis_identity_contract
    try:
        contract = analysis_identity_contract(source_record, db or "charls")
    except ValueError as exc:
        fail(results, "analysis identity contract", str(exc))
        return False
    household = contract["analysis_unit"] == "household_period"
    label = "analysis household-period rows" if household else "analysis person-period rows"
    keys = {
        "charls": ["id", "year"], "elsa": ["idauniq", "Wave"],
        "hrs": ["HHID", "PN", "year"], "share": ["mergeid", "Wave_id"],
        "klosa": ["Harmonized_id", "Wave_id"], "chns": ["IDind", "WAVE"],
        "knhanes": ["id", "year"], "mhas": ["ID", "Wave_id"], "nhanes": ["SEQN", "YEAR"], "nhanesiii": ["SEQN", "YEAR"], "nhis": ['ID','Wave_id'],
    }[(db or "charls").lower()]
    if contract.get("identity_keys"):
        keys = contract["identity_keys"]
    if db.lower() == "mhas" and "source_module" in header and "source_module" not in keys:
        keys = ["source_module", *keys]
    if db.lower() == "knhanes" and "sample_source" in header:
        keys = ["sample_source", *keys]
    if any(key not in header for key in keys):
        fail(results, label, {"required_keys": keys, "actual": header})
        return False
    indexes = [header.index(key) for key in keys]
    seen = set()
    for number, row in enumerate(rows[1:], 2):
        if any(index >= len(row) or not is_nonmissing(row[index]) for index in indexes):
            fail(results, label, {"row": number, "reason": "missing household or year" if household else "missing person or period"})
            return False
        if household and any(not isinstance(row[index], str) for index in indexes):
            fail(results, label, {"row": number, "reason": "householdid and year must remain string cells"})
            return False
        key = tuple(str(row[index]) for index in indexes)
        # Numeric-equivalent period spellings do not create additional periods.
        period = key[-1] if household else re.sub(r"^Wave\s+", "", key[-1])
        period = period if household else re.sub(r"\.0+$", "", period)
        key = (*key[:-1], period)
        if db.lower() in {"nhanes", "nhanesiii"}:
            key = (re.sub(r"\.0+$", "", key[0]).lstrip("0") or "0", period)
        if key in seen:
            fail(results, label, {"row": number, "reason": "duplicate household-year" if household else "duplicate person-period", "key": key})
            return False
        seen.add(key)
    ok(results, label, {"keys": keys, "rows": len(rows) - 1})
    return True


def workbook_source_columns(formal, raw_vars, analysis_vars, summaries):
    """Resolve explicitly planned summaries of repeated sources; raw stays unchanged."""
    if not summaries:
        return list(raw_vars), {}
    with (formal / "raw_codebook.csv").open(encoding="utf-8-sig", newline="") as handle:
        repeated = {row["newname"] for row in csv.DictReader(handle)
                    if row.get("File type") == "reID"}
    mapping = {}
    for item in summaries:
        variable = item.get("variable")
        sources = item.get("source_variables", [])
        if (not isinstance(variable, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", variable)
                or variable in set(raw_vars) | set(analysis_vars) | {"SEQN", "YEAR"}
                or variable in mapping or not isinstance(sources, list) or not sources
                or len(set(sources)) != len(sources)
                or not set(sources) <= repeated.intersection(raw_vars)
                or not isinstance(item.get("method"), str) or not item["method"].strip()):
            raise ValueError("Invalid repeated-source summary: " + repr(item))
        mapping[variable] = sources
    replaced = set().union(*(set(sources) for sources in mapping.values()))
    return [name for name in raw_vars if name not in replaced] + list(mapping), mapping


def source_result_label_roles(formal, dictionary, analysis_dictionary, raw_vars, analysis_vars, plan):
    """Accept distinct Labels only when both source and approved result roles match."""
    full = {row[dictionary[0].index("Variable")]: dict(zip(dictionary[0], row))
            for row in dictionary[1:]}
    analysis = {row[analysis_dictionary[0].index("Variable")]: dict(zip(analysis_dictionary[0], row))
                for row in analysis_dictionary[1:]}
    mismatched = [name for name in analysis_vars if full[name].get("Label") != analysis[name].get("Label")]
    if not mismatched:
        return []
    with (formal / "raw_codebook.csv").open(encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    accepted = []
    for name in mismatched:
        sources = [row for row in raw if row.get("newname") == name]
        results = [row for row in (plan or []) if isinstance(row, dict) and row.get("analysis_var") == name]
        if name not in raw_vars or len(sources) != 1 or len(results) != 1:
            raise ValueError("Label role lacks a unique selected source and approved result: " + name)
        source, result, entry = sources[0], results[0], full[name]
        source_label = next((source[key] for key in ("Label", "Easy label", "Easy.label") if key in source), None)
        result_label = result.get("meaning")
        if (not source.get("Variable") or not isinstance(source_label, str) or not source_label.strip()
                or not isinstance(result_label, str) or not result_label.strip()
                or entry.get("original_vars") != source["Variable"]
                or entry.get("processed_vars") != name or str(entry.get("count")) not in ("1", "1.0")
                or entry.get("Label") != source_label or analysis[name].get("Label") != result_label):
            raise ValueError("Source/result Label or identity differs from its declared role: " + name)
        accepted.append({"variable": name, "source_identity": source["Variable"],
                         "source_Label": source_label, "result_Label": result_label})
    return accepted


def check_workbook_contract(formal, expected_files, analysis_db, analysis_codebook, raw_vars, analysis_vars, results, source_summaries=None, medicine_record=None, charls_multifile_contract=None, result_label_plan=None):
    """Compare actual cells, not file existence or declared argument lists."""
    full = [n for n in expected_files if n.startswith("db_") and n.endswith((".xlsx",'.csv'))]
    dictionaries = [n for n in expected_files if n.startswith("codebook_") and n.endswith(".xlsx")]
    if len(full) != 1 or len(dictionaries) != 1:
        fail(results, "four workbook contents", "expected one full table and one full dictionary")
        return
    files = [full[0], dictionaries[0], analysis_db, analysis_codebook]
    if any(not name or not (formal / name).is_file() for name in files):
        fail(results, "four workbook contents", "missing workbook")
        return
    full_rows, dictionary, analysis_rows, analysis_dictionary = [read_table_rows(formal / n) for n in files]
    if not all((full_rows, dictionary, analysis_rows, analysis_dictionary)):
        fail(results, "four workbook contents", "empty workbook")
        return
    full_header, analysis_header = full_rows[0], analysis_rows[0]
    identities = [name for name in analysis_header if name not in analysis_vars]
    try:
        source_columns, summary_mapping = workbook_source_columns(formal, raw_vars, analysis_vars, source_summaries)
        if medicine_record:
            from nhanes_export_contract import medicine_source_columns
            extra = medicine_source_columns(formal, medicine_record)
            if set(extra) & (set(source_columns) | set(analysis_vars) | set(identities)):
                raise ValueError('Medicine source columns conflict with other fields')
            source_columns += extra
    except (ValueError, KeyError, TypeError) as exc:
        fail(results, "four workbook contents", str(exc))
        return
    join_identities = (charls_multifile_contract or {}).get("join_identity_columns", [])
    if join_identities:
        if "processed_vars" not in analysis_dictionary[0]:
            fail(results, "four workbook contents", "PSU connection identity requires actual result source mapping")
            return
        lineage_index = analysis_dictionary[0].index("processed_vars")
        measurement = {v for row in analysis_dictionary[1:] for v in split_csv(row[lineage_index] if lineage_index < len(row) else None)}
        if set(join_identities) & (set(analysis_vars) | measurement):
            fail(results, "four workbook contents", "PSU join_identity is mapped as a measurement or result")
            return
        source_columns = [v for v in source_columns if v not in join_identities or v in full_header]
    full_only_identities = []
    if charls_multifile_contract:
        household = charls_multifile_contract.get("files", {}).get("raw_data_household.csv", {})
        if (household.get("file_type") == "householdID"
                and household.get("header", [])[:3] == ["householdid", "year", "respondent_id"]):
            if "respondent_id" in analysis_vars:
                fail(results, "four workbook contents", "CHARLS household respondent_id is an identity, not a definition result")
                return
            if "respondent_id" in full_header:
                full_only_identities.append("respondent_id")
    expected = set(identities) | set(source_columns) | set(analysis_vars) | set(full_only_identities)
    if len(full_header) != len(set(full_header)) or set(full_header) != expected:
        fail(results, "four workbook contents", {"expected_full_columns": sorted(expected), "actual": full_header})
        return
    if analysis_header != identities + analysis_vars:
        fail(results, "four workbook contents", "analysis table must contain identities followed by final results")
        return
    if [name for name in full_header if name in analysis_vars] != analysis_vars:
        fail(results, "four workbook contents", "full table result columns differ from analysis_vars order")
        return
    if len(full_rows) != len(analysis_rows):
        fail(results, "four workbook contents", "full and analysis tables have different row counts")
        return
    indexes = [full_header.index(name) for name in analysis_header]
    if [[row[i] if i < len(row) else None for i in indexes] for row in full_rows[1:]] != analysis_rows[1:]:
        fail(results, "four workbook contents", "shared identities/results or row order differ")
        return
    for name, rows, expected_variables in ((dictionaries[0], dictionary, full_header),
                                           (analysis_codebook, analysis_dictionary, analysis_vars)):
        if "Variable" not in rows[0]:
            fail(results, "four workbook contents", name + " lacks Variable")
            return
        index = rows[0].index("Variable")
        variables = [row[index] if index < len(row) else None for row in rows[1:]]
        if variables != expected_variables:
            fail(results, "four workbook contents", {"dictionary": name, "expected": expected_variables, "actual": variables})
            return
    label_roles = []
    if "Label" in dictionary[0] and "Label" in analysis_dictionary[0]:
        try:
            label_roles = source_result_label_roles(formal, dictionary, analysis_dictionary,
                                                    raw_vars, analysis_vars, result_label_plan)
        except (ValueError, OSError) as exc:
            fail(results, "four workbook contents", str(exc))
            return
    if summary_mapping:
        entries = [dict(zip(dictionary[0], row)) for row in dictionary[1:]]
        for variable, sources in summary_mapping.items():
            entry = next(row for row in entries if row.get("Variable") == variable)
            if set(split_csv(entry.get("processed_vars"))) != set(sources):
                fail(results, "four workbook contents", "Summary lineage differs: " + variable)
                return
    ok(results, "four workbook contents", {"rows": len(analysis_rows) - 1, "source_columns": source_columns,
                                           "source_summaries": summary_mapping,
                                           "result_columns": analysis_vars, "source_result_label_roles": label_roles})


def check_identity_values(
    raw_path: Path,
    raw_header: list[str],
    analysis_rows: list[list[object]],
    analysis_header: list[str],
    results: list[dict],
    db: str = "",
    raw_paths: list[Path] | None = None,
    source_record: dict | None = None,
) -> None:
    if db == 'mhas':
        from mhas_export_contract import CORE, SCOPED_MODULES, validate_scoped_analysis
        members = raw_paths or [raw_path]
        if (source_record or {}).get('mhas_analysis_scope') is not None or any(p.stem.removeprefix('raw_data_') in SCOPED_MODULES - {CORE} for p in members):
            try:
                fact = validate_scoped_analysis(members, analysis_rows, analysis_header, source_record)
                ok(results, 'analysis identity values', fact)
            except ValueError as exc:
                fail(results, 'analysis identity values', str(exc))
            return
    if not check_long_table(analysis_rows, analysis_header, results, db, source_record):
        return
    if (source_record or {}).get("analysis_unit") == "household_period":
        # Preserve the actual household-year export, including row order.  No
        # respondent id is required; an optional respondent column is checked
        # by the existing shared-identity comparison below.
        keys = ["householdid", "year"]
        with raw_path.open(encoding="utf-8-sig", newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
        expected = [tuple(row.get(name, "") for name in keys) for row in raw_rows]
        actual = [tuple(row[analysis_header.index(name)] for name in keys) for row in analysis_rows[1:]]
        if (any(any(not value.strip() for value in key) for key in expected)
                or len(set(expected)) != len(expected) or actual != expected):
            fail(results, "household source row preservation", "household-year keys must be nonempty, unique and equal to the original source sequence")
            return
        ok(results, "household source row preservation", {"keys": keys, "rows": len(expected)})
    identity_candidates = [
        "ID",
        "id",
        "year",
        "HHID",
        "PN",
        "householdid",
        "respondent_id",
        "communityid",
        "idauniq",
    ]
    if db == "knhanes":
        required = ["ID", "id", "year"]
        if any(name not in raw_header or name not in analysis_header for name in required):
            fail(results, "analysis identity values", "KNHANES requires ID,id,year in raw and analysis")
            return
        if any(len(row) <= analysis_header.index(name) or not isinstance(row[analysis_header.index(name)], str)
               for row in analysis_rows[1:] for name in ["ID", "id"]):
            fail(results, "analysis identity values", "KNHANES ID and id must remain string cells")
            return
        if raw_paths and len(raw_paths) > 1 and (source_record or {}).get("knhanes_person_aggregation"):
            try:
                from knhanes_export import validate_person_package
                from knhanes_person_aggregation import expected_person_summaries, KEYS
                contract = validate_person_package(raw_path.parent, source_record=source_record)
                expected, _, _ = expected_person_summaries(raw_path.parent, source_record, contract)
                indexes = [analysis_header.index(name) for name in KEYS]
                actual = [tuple(str(row[i]) for i in indexes) for row in analysis_rows[1:]]
                if actual != list(expected):
                    raise ValueError("Primary person-year rows/order changed in repeated-source analysis")
                ok(results, "analysis identity values", {"primary_rows":len(actual), "all_primary_rows_preserved":True})
            except (ValueError, OSError) as exc:
                fail(results, "analysis identity values", str(exc))
            return
        if raw_paths and len(raw_paths) > 1:
            from knhanes_export import PERSON_SAMPLES
            if "sample_source" not in analysis_header or {p.name for p in raw_paths} != set(PERSON_SAMPLES):
                fail(results, "analysis identity values", "Mixed KNHANES samples require sample_source and both original files")
                return
            expected = Counter()
            for member in raw_paths:
                with member.open(encoding="utf-8-sig", newline="") as handle:
                    expected.update((PERSON_SAMPLES[member.name], r["ID"], r["id"], r["year"]) for r in csv.DictReader(handle))
            indexes = [analysis_header.index(n) for n in ["sample_source", "ID", "id", "year"]]
            actual = Counter(tuple(str(row[i]) for i in indexes) for row in analysis_rows[1:])
            excess = actual - expected
            if excess:
                fail(results, "analysis identity values", {"unexpected_sample_identities": list(excess.items())[:10]})
            else:
                ok(results, "analysis identity values", {"sample_scoped_rows": sum(actual.values()), "scope": "subset of each original sample; no cross-sample join"})
            return
    if db == "chns":
        identity_columns = ["ID", "IDind", "WAVE"]
        if not all(name in raw_header and name in analysis_header for name in identity_columns):
            fail(results, "analysis identity values", "CHNS requires ID, IDind and WAVE in raw and analysis")
            return
        if any(len(row) <= analysis_header.index(name) or not isinstance(row[analysis_header.index(name)], str)
               for row in analysis_rows[1:] for name in ["ID", "IDind"]):
            fail(results, "analysis identity values", "CHNS ID and IDind must remain string cells")
            return
    elif db == 'nhis':
        from nhis_export_contract import DEFAULTS, OPTIONAL_DEFAULTS
        identity_columns = [n for n in (*DEFAULTS,*OPTIONAL_DEFAULTS) if n in raw_header]
        if not set(DEFAULTS).issubset(analysis_header) or not set(identity_columns).issubset(analysis_header):
            fail(results,'analysis identity values','NHIS default identities must all be preserved')
            return
        if any(not isinstance(row[analysis_header.index(n)],str) for row in analysis_rows[1:] for n in DEFAULTS):
            fail(results,'analysis identity values','NHIS identities must remain original character cells')
            return
    elif db == "nhanesiii":
        identity_columns = [x for x in ('SEQN', '_survey_period', '_period') if x in raw_header]
        retained = ['YEAR' if x == '_survey_period' else x for x in identity_columns]
        if ('SEQN' not in identity_columns or not set(retained).issubset(analysis_header)
                or 'YEAR' not in analysis_header):
            fail(results, "analysis identity values", "NHANES III requires original SEQN/default periods plus explicit YEAR")
            return
        if any(not isinstance(row[analysis_header.index('SEQN')], str)
               or row[analysis_header.index('YEAR')] not in {'1988-1994','1988-1991','1991-1994'} for row in analysis_rows[1:]):
            fail(results, "analysis identity values", "NHANES III requires character SEQN and confirmed survey/phase periods")
            return
    elif db == "nhanes":
        identity_columns = ["SEQN", "YEAR"]
        if any(name not in raw_header or name not in analysis_header for name in identity_columns):
            fail(results, "analysis identity values", "NHANES requires SEQN,YEAR")
            return
        if any(not isinstance(row[analysis_header.index(name)], str) for row in analysis_rows[1:] for name in identity_columns):
            fail(results, "analysis identity values", "NHANES identities must remain character cells")
            return
    elif db == "mhas":
        from mhas_export_contract import IDENTIFIERS
        identity_columns = [x for x in raw_header if x in IDENTIFIERS]
        if not set(identity_columns).issubset(analysis_header):
            fail(results, "analysis identity values", "MHAS default identities must be preserved")
            return
        for key in ["ID", "Wave_id"]:
            if any(not isinstance(row[analysis_header.index(key)], str) for row in analysis_rows[1:]):
                fail(results, "analysis identity values", "MHAS keys must remain character cells")
                return
    elif db == "share":
        identity_columns = ["ID", "Wave_id", "mergeid"]
        if not all(name in raw_header and name in analysis_header for name in identity_columns):
            fail(results, "analysis identity values", "SHARE requires ID, Wave_id, mergeid in raw and analysis")
            return
    elif db == "klosa":
        from klosa_adapter_contract import identity_columns as klosa_identity_columns
        identity_columns = klosa_identity_columns(raw_header)
        if not set(identity_columns).issubset(raw_header) or not set(identity_columns).issubset(analysis_header):
            fail(results, "analysis identity values", "KLoSA identities must all be preserved")
            return
    elif db == "hrs":
        identity_columns = [name for name in ["HHID", "PN"] if name in raw_header and name in analysis_header]
    else:
        identity_columns = [
            name
            for name in identity_candidates
            if name in raw_header and name in analysis_header
        ]
    if not identity_columns:
        ok(results, "analysis identity values", "no shared identity columns")
        return

    raw_indexes = [raw_header.index(name) for name in identity_columns]
    analysis_indexes = [analysis_header.index('YEAR' if db == 'nhanesiii' and name == '_survey_period' else name)
                        for name in identity_columns]

    def identity(row: list[object], indexes: list[int]) -> tuple[str, ...]:
        values = [
            "" if index >= len(row) or row[index] is None else str(row[index])
            for index in indexes
        ]
        if db == "chns":
            from chns_export_contract import normalize_year
            try:
                values[2] = normalize_year(values[2])
            except ValueError:
                # Invalid periods retain their text and fail the identity/package comparison.
                pass
        return tuple(values)

    raw_identities: Counter[tuple[str, ...]] = Counter()
    if db == "hrs":
        from hrs_export_contract import documented_lowercase_periods, person_identity
        lowercase_periods = documented_lowercase_periods(raw_path.parent)
    for raw_member in raw_paths or [raw_path]:
        with raw_member.open("r", encoding="utf-8-sig", newline="") as handle:
            for values in csv.DictReader(handle):
                raw_row = [values.get(name, "") for name in raw_header]
                if db == "hrs":
                    try:
                        pair = person_identity(values, lowercase_periods)
                    except ValueError as exc:
                        fail(results, "analysis identity values", str(exc))
                        return
                    raw_identities[tuple(pair[["HHID", "PN"].index(name)] for name in identity_columns)] += 1
                else:
                    raw_identities[identity(raw_row, raw_indexes)] += 1

    if db == "hrs":
        # Supported repeat files may contain respondents absent from the main
        # table. Validate their complete transport contract before admitting keys.
        from hrs_export_contract import HRS_REPEAT_FILES, validate_hrs_repeat
        for family in sorted(HRS_REPEAT_FILES):
            member = raw_path.parent / f"raw_data_repeat_{family}.csv"
            if not member.is_file():
                continue
            try:
                validate_hrs_repeat(member.parent, member.name, read_csv_header(member))
            except ValueError as exc:
                fail(results, "analysis identity values", str(exc))
                return
            with member.open(encoding="utf-8-sig", newline="") as handle:
                for values in csv.DictReader(handle):
                    # The validated Internet contract alone permits its documented
                    # 2011 blank HHID; PN and period have already been cross-checked.
                    pair = (values["HHID"] or values["ID"].split("|")[1], values["PN"])
                    raw_identities[tuple(pair[["HHID", "PN"].index(name)] for name in identity_columns)] += 1

    remaining = raw_identities.copy()
    mismatches: list[dict] = []
    for row_number, analysis_row in enumerate(analysis_rows[1:], start=2):
        analysis_identity = identity(analysis_row, analysis_indexes)
        if raw_identities[analysis_identity] > 0 and db == "hrs":
            continue
        if remaining[analysis_identity] > 0:
            remaining[analysis_identity] -= 1
            continue

        detail: dict[str, object] = {
            "row": row_number,
            "analysis_identity": dict(zip(identity_columns, analysis_identity)),
            "reason": "identity combination is absent from raw data",
        }
        for raw_identity in raw_identities:
            differences = [
                index
                for index, (raw_value, analysis_value) in enumerate(
                    zip(raw_identity, analysis_identity)
                )
                if raw_value != analysis_value
            ]
            if len(differences) == 1:
                index = differences[0]
                detail.update({
                    "column": identity_columns[index],
                    "raw": raw_identity[index],
                    "analysis": analysis_identity[index],
                })
                break
        mismatches.append(detail)
        if len(mismatches) >= 20:
            break

    if mismatches:
        fail(results, "analysis identity values", mismatches)
    else:
        ok(
            results,
            "analysis identity values",
            {
                "columns": identity_columns,
                "raw_rows": sum(raw_identities.values()),
                "analysis_rows": len(analysis_rows) - 1,
                "relation": (
                    "analysis persons occur in raw data"
                    if db == "hrs"
                    else "analysis identity combinations occur in raw data"
                ),
            },
        )


def check_forbidden_files(formal_dir: Path, results: list[dict], max_md: int) -> None:
    files = [path for path in formal_dir.iterdir() if path.is_file()]
    forbidden_patterns = ["*_defined.csv", "*.rds", "*consistency*disclosure*.xlsx"]
    forbidden = [
        path.name
        for path in files
        if any(fnmatch.fnmatch(path.name.lower(), pattern.lower()) for pattern in forbidden_patterns)
    ]
    if forbidden:
        fail(results, "forbidden files", forbidden)
    else:
        ok(results, "forbidden files")

    md_files = [
        path.name
        for path in files
        if path.suffix.lower() == ".md" and path.name != READER_COPY_NAME
    ]
    if len(md_files) > max_md:
        fail(results, "markdown count", md_files)
    else:
        ok(results, "markdown count", md_files)


def check_logs(formal_dir: Path, log_prefix: str | None, require_exit_code: bool, results: list[dict]) -> None:
    logs = sorted(formal_dir.glob("*.log"))
    if len(logs) != 1:
        fail(results, "single final log", [path.name for path in logs])
        return
    log = logs[0]
    if log_prefix and not log.name.startswith(f"{log_prefix}_run_"):
        fail(results, "log prefix", log.name)
    else:
        ok(results, "log prefix", log.name)

    text = log.read_text(encoding="utf-8", errors="replace")
    problems = [item for item in ["NativeCommandError", "Execution halted"] if item in text]
    if problems:
        fail(results, "log error markers", problems)
    else:
        ok(results, "log error markers")

    if require_exit_code and "Rscript exit code: 0" not in text:
        fail(results, "log exit code", "Rscript exit code: 0 not found")
    else:
        ok(results, "log exit code")


def is_nonmissing(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def period_text(periods: list[int], prefix: str = "Wave", all_periods: list[int] | None = None) -> str:
    values = sorted(set(periods))
    if all_periods is not None and values == sorted(set(all_periods)):
        return "全周期"
    ranges: list[str] = []
    start = previous = values[0]
    for value in values[1:] + [None]:
        if value is not None and value == previous + 1:
            previous = value
            continue
        if prefix:
            ranges.append(f"{prefix} {start}" if start == previous else f"{prefix} {start}-{previous}")
        else:
            ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
        if value is not None:
            start = previous = value
    return "、".join(ranges)


def object_text(
    period_stats: list[tuple[int, int, int]],
    threshold: float = 0.85,
    split_gap: float = 0.20,
    prefix: str = "Wave",
) -> str:
    rates = [(period, nonmissing / total) for period, nonmissing, total in period_stats if nonmissing > 0 and total > 0]
    if not rates:
        raise ValueError("summary variable has no covered period")
    if all(rate >= threshold for _, rate in rates):
        return "全样本"

    low = [(period, rate) for period, rate in rates if rate < threshold]
    high = [(period, rate) for period, rate in rates if rate >= threshold]
    parts: list[str] = []
    if high:
        parts.append(f"{period_text([period for period, _ in high], prefix)} 全样本")
    rounded_groups: dict[float, list[int]] = {}
    for period, rate in low:
        rounded_groups.setdefault(round(rate * 10) * 10, []).append(period)
    for percent in sorted(rounded_groups, reverse=True):
        parts.append(f"{period_text(rounded_groups[percent], prefix)} 约 {percent:g}% 样本")
    return "；<br>".join(parts)


def precise_object_text(
    period_stats: list[tuple[int, int, int]],
    threshold: float = 0.85,
    prefix: str = "Wave",
) -> str:
    """Describe partial coverage without rounding small rates down to zero."""
    rates = [(period, nonmissing / total) for period, nonmissing, total in period_stats if nonmissing > 0 and total > 0]
    if not rates:
        raise ValueError("summary variable has no covered period")
    if all(rate >= threshold for _, rate in rates):
        return "全样本"

    low = [(period, rate) for period, rate in rates if rate < threshold]
    high = [(period, rate) for period, rate in rates if rate >= threshold]
    parts: list[str] = []
    if high:
        parts.append(f"{period_text([period for period, _ in high], prefix)} 全样本")
    if low:
        low_percentages = [int(rate * 100 + 0.5) for _, rate in low]
        low_min = min(low_percentages)
        low_max = max(low_percentages)
        percentage = str(low_min) if low_min == low_max else f"{low_min}%-{low_max}"
        parts.append(
            f"{period_text([period for period, _ in low], prefix)} 约 {percentage}% 样本"
        )
    return "；<br>".join(parts)


def parse_definition_table(note_text: str) -> list[str]:
    variables = [
        html.unescape(value).strip()
        for value in re.findall(
            r'<td\s+class="plain-cell">\s*([^<]+?)\s*</td>', note_text
        )
    ]
    if not variables:
        raise ValueError("Definition / Criteria / detail table variables were not found")
    if len(variables) != len(set(variables)):
        raise ValueError("definition table contains duplicate variables")
    return variables


def check_summary_prose(note_text: str, results: list[dict], compact_module: bool = False) -> None:
    end_heading = r"(?:定义的组分概览|定义的组分详情|材料)" if compact_module else "定义"
    section = re.search(
        r"(?ms)^## 摘要导读\s*$\n(.*?)^## " + end_heading + r"\s*$",
        note_text,
    )
    if not section:
        fail(results, "summary prose structure", "content between 摘要导读 and 定义 not found")
        return
    prose = section.group(1).strip()
    opening_end = min(
        [
            position
            for marker in (
                '<div class="raw-source-structure"',
                '<div data-questionnaire-module=',
                '## 定义依据',
                '<!-- summary-insight-card:start -->',
                '<div class="raw-source-link"',
            )
            if (position := prose.find(marker)) >= 0
        ]
        or [len(prose)]
    )
    opening_text = visible_text(prose[:opening_end])
    periods = re.findall(
        r'(?s)<section\s+class="raw-source-period"[^>]*data-label="([^"]+)"[^>]*>(.*?)</section>',
        prose,
    )
    period_issues = []
    period_style = None
    for period_index, (label, body) in enumerate(periods):
        body_text = visible_text(body)
        has_period_note = 'data-summary-period-note="true"' in body
        if period_index == 0:
            expected_titles = {"问卷设计", "问卷设计变化", "构建数据库"}
        elif period_style == "constructed":
            expected_titles = {"构建数据库变化"}
        else:
            expected_titles = {"问卷设计", "问卷设计变化"}
        title_match = re.search(
            r'(?s)<[^>]*data-summary-period-note-title="true"[^>]*>(.*?)</[^>]+>',
            body,
        )
        actual_title = visible_text(title_match.group(1)) if title_match else ""
        if period_index == 0 and actual_title == "构建数据库":
            period_style = "constructed"
        elif period_index == 0 and actual_title in {"问卷设计", "问卷设计变化"}:
            period_style = "questionnaire"
        if not has_period_note or actual_title not in expected_titles or len(body_text) < 80:
            period_issues.append(html.unescape(label))
    card_blocks = re.findall(
        r"(?s)<!-- summary-insight-card:start -->(.*?)<!-- summary-insight-card:end -->",
        prose,
    )
    card_ok = len(card_blocks) <= 1
    if card_blocks:
        card_text = visible_text(card_blocks[0])
        card_ok = (
            'data-summary-insight-card="true"' in card_blocks[0]
            and "小book提示" in card_text
            and len(card_text) > len("小book提示")
        )
    source_count = prose.count('class="raw-source-link"')
    legacy_table = "| 定义变量 | 含义 | 组成 | 覆盖周期 | 对象 |" in prose
    details = {
        "opening_text_length": len(opening_text),
        "period_count": len(periods),
        "period_issues": period_issues,
        "insight_card_count": len(card_blocks),
        "insight_card_ok": card_ok,
        "source_entry_count": source_count,
        "legacy_five_column_table": legacy_table,
    }
    if (
        len(opening_text) < 30
        or period_issues
        or not card_ok
        or source_count != 0
        or legacy_table
    ):
        fail(results, "summary prose lint", details)
    else:
        ok(results, "summary prose lint", details)


def extract_public_r_code(note_text: str) -> str:
    marker = "### 2-代码材料"
    marker_pos = note_text.find(marker)
    if marker_pos < 0:
        raise ValueError("public R section not found")
    fenced = re.search(r"```r\s*\n(.*?)\n```", note_text[marker_pos:], flags=re.DOTALL)
    if not fenced:
        raise ValueError("public R fenced code not found after code-material heading")
    return fenced.group(1)


def strip_r_comments_and_strings(source: str) -> str:
    """Mask R comments and quoted text while preserving token positions."""
    masked: list[str] = []
    quote: str | None = None
    escaped = False
    in_comment = False

    for char in source:
        if in_comment:
            if char == "\n":
                in_comment = False
                masked.append(char)
            else:
                masked.append(" ")
            continue

        if quote is not None:
            if char == "\n" and quote != "`":
                quote = None
                escaped = False
                masked.append(char)
                continue
            if escaped:
                escaped = False
                masked.append(" ")
                continue
            if char == "\\" and quote != "`":
                escaped = True
                masked.append(" ")
                continue
            if char == quote:
                quote = None
            masked.append(" ")
            continue

        if char == "#":
            in_comment = True
            masked.append(" ")
        elif char in {'"', "'", "`"}:
            quote = char
            masked.append(" ")
        else:
            masked.append(char)

    return "".join(masked)


def charls_identity_data_read(source: str, raw_name: str, header: list[str], household: bool) -> bool:
    """Check a direct primary read; formatting/order do not change identity semantics."""
    masked = strip_r_comments_and_strings(source)
    assignments = list(re.finditer(r'(?m)^[ \t]*(dt\s*<-\s*read\.csv\s*\()', masked))
    if len(assignments) != 1:
        return False
    start = assignments[0].start(1)
    # Literal filenames/classes only: no arbitrary R expression or extra read options.
    read = re.match(
        r'\s*dt\s*<-\s*read\.csv\s*\(\s*(?:file\s*=\s*)?'
        r'(["\'])' + re.escape(raw_name) + r'\1\s*'
        r'(?:,\s*colClasses\s*=\s*c\(([^()]*)\)\s*)?\)'
        r'(?=\s*(?:#|$))', source[start:], flags=re.M,
    )
    if read is None:
        return False
    classes = read[2]
    if classes is None:
        return not household
    pairs = [part.strip() for part in classes.split(',')]
    identities = []
    for part in pairs:
        pair = re.fullmatch(r'(\w+)\s*=\s*(["\'])character\2', part)
        if pair is None:
            return False
        identities.append(pair[1])
    allowed = {'householdid', 'year', 'id'} if household else {'id', 'householdid', 'communityid'}
    return (bool(identities) and len(identities) == len(set(identities))
            and set(identities) <= allowed
            and (not header or set(identities) <= set(header))
            and (not household or {'householdid', 'year'} <= set(identities)))


def check_public_code_outline(
    formal_dir: Path,
    note_text: str,
    results: list[dict],
    db: str,
    formal_r: Path | None = None,
    record: dict | None = None,
) -> None:
    scripts = [formal_r] if formal_r is not None else sorted(formal_dir.glob("define*.R"))
    if len(scripts) != 1 or not scripts[0].is_file():
        fail(results, "public R outline source", [path.name for path in scripts])
        return
    source = scripts[0].read_text(encoding="utf-8", errors="replace")
    boundary = re.search(r"(?m)^# 输出\s*$", source)
    if not boundary:
        fail(results, "public R outline boundary", "# 输出 not found")
        return
    source_public = source[: boundary.start()].strip()
    try:
        note_public = extract_public_r_code(note_text).strip()
    except ValueError as exc:
        fail(results, "public R outline extraction", str(exc))
        return
    if note_public != source_public:
        fail(results, "public R source synchronization", "note public code differs from formal R before # 输出")
    else:
        ok(results, "public R source synchronization")

    structural_issues: list[str] = []
    redundant_renames = [
        pattern
        for pattern in [
            r'(?m)^names\(dt\)\[1\]\s*<-\s*["\']ID["\']\s*$',
            r'(?m)^names\(name_z\)\[1\]\s*<-\s*["\']Easy\.label["\']\s*$',
        ]
        if re.search(pattern, source_public)
    ]
    if redundant_renames:
        structural_issues.append("redundant first-column renaming")

    uses_check_names_false = bool(re.search(
        r'read\.csv\([^)]*check\.names\s*=\s*FALSE',
        source_public,
        flags=re.I | re.S,
    ))
    if uses_check_names_false:
        structural_issues.append(
            "read.csv(check.names = FALSE) is forbidden; assign unique aliases in dbCodeBook before download"
        )

    if re.search(r'\[\[\s*["\']Easy label["\']\s*\]\]', source_public):
        structural_issues.append(
            'read.csv normalizes "Easy label" to "Easy.label"; use the normalized column name'
        )

    if db == "charls":
        from check_definition_source_record import primary_raw_name
        raw_name = primary_raw_name(record, db)
        raw_data_path = formal_dir / raw_name
        raw_header = []
        if raw_data_path.exists():
            raw_header = read_csv_header(raw_data_path)
            duplicate_header = sorted({
                name for name in raw_header if raw_header.count(name) > 1
            })
            if duplicate_header:
                structural_issues.append(
                    f"{raw_name} contains duplicate columns; assign unique aliases "
                    f"in dbCodeBook before download: {', '.join(duplicate_header)}"
                )
        simple_codebook_read = 'name_z <- read.csv("raw_codebook.csv")' in source_public
        if not simple_codebook_read:
            structural_issues.append(
                "CHARLS public R must read raw_codebook.csv without extra options"
            )
        if not charls_identity_data_read(
            source_public, raw_name, raw_header,
            (record or {}).get("analysis_unit") == "household_period",
        ):
            structural_issues.append(
                "CHARLS public R must use the simple read, except that "
                "person/household/community identity columns may be preserved as character"
            )
        if re.search(r"(?m)^names\((?:data|dt)\)\s*\[[^\]]+\]\s*<-", source_public):
            structural_issues.append(
                "CHARLS public R must not rename raw columns by position; "
                "assign unique aliases in dbCodeBook before download"
            )
        if re.search(
            r'read\.csv\(\s*["\']raw_(?:data|codebook)\.csv["\'][^)]*'
            r'(?:(?<!file)encoding|col\.names)\s*=',
            source_public,
            flags=re.I,
        ):
            structural_issues.append(
                "CHARLS public raw reads must not add encoding or column-name options"
            )
        if re.search(
            r'read\.csv\(\s*["\']raw_(?:data|codebook)\.csv["\'][^)]*?'
            r'(?:fileEncoding|na\.strings)\s*=',
            source_public,
            flags=re.I | re.S,
        ):
            structural_issues.append(
                "CHARLS public raw reads must not add fileEncoding or na.strings; "
                "use the shared empty-string step after reading"
            )
    elif db == "hrs":
        simple_codebook_read = 'name_z <- read.csv("raw_codebook.csv")' in source_public
        if not simple_codebook_read:
            structural_issues.append(
                "HRS public R must read raw_codebook.csv without extra options"
            )
        hrs_classes = re.search(
            r'read\.csv\(\s*["\']raw_data\.csv["\'][^)]*'
            r'colClasses\s*=\s*c\(([^()]*)\)',
            source_public,
            flags=re.I | re.S,
        )
        hrs_identity_read = bool(hrs_classes) and all(
            re.search(r'(?:^|,)\s*' + name + r'\s*=\s*["\']character["\']\s*(?:,|$)',
                      hrs_classes.group(1), flags=re.I)
            for name in ('HHID', 'PN')
        )
        if not hrs_identity_read:
            structural_issues.append(
                "HRS public R must preserve HHID and PN as character when reading raw_data.csv"
            )

    if re.search(r"(?m)^raw_row_count\s*<-\s*nrow\(data\)\s*$", source_public):
        structural_issues.append("background raw_row_count leaked into public R")
    if re.search(r"(?m)^raw_vars\s*<-\s*name_z\$newname\s*$", source_public):
        structural_issues.append("raw_vars detours through raw_codebook in public R")
    if re.search(
        r'(?m)^if\s*\(\s*!"id"\s*%in%\s*names\((?:data|dt)\)\s*\)\s*\{',
        source_public,
    ):
        structural_issues.append("defensive id fallback leaked into public R")
    if re.search(
        r"(?ms)^data\s*<-\s*data\s*%>%\s*\n?\s*filter\(year\s*%in%",
        source_public,
    ):
        structural_issues.append(
            "global target-wave filter belongs at the formal output boundary, not the read block"
        )

    required_header_tokens = [
        'library("openxlsx")',
        'library("dplyr")',
        'library("dbCodeBookr")',
    ]
    missing_header_tokens = [
        token for token in required_header_tokens if token not in source_public
    ]
    if missing_header_tokens:
        structural_issues.append(
            "nonstandard package header: missing " + ", ".join(missing_header_tokens)
        )

    if re.search(
        r'for\s*\(\s*pkg\s+in\s+c\([^)]*["\']dbCodeBookr["\']',
        source_public,
        flags=re.I | re.S,
    ):
        structural_issues.append("dbCodeBookr placed in generic package loop")

    if re.search(
        r"(?mi)^#\s*raw_data\.csv.*dbcodebook\.cn.*Go to.*$",
        source_public,
    ):
        structural_issues.append(
            "reader-facing raw_data.csv guide leaked into formal definition R"
        )

    public_lines = source_public.splitlines()
    recode_comment = re.compile(
        r"^\s*#\s*recode\.(chr|num)\(([^)]+)\)\s*$"
    )
    for index, line in enumerate(public_lines):
        match = recode_comment.match(line)
        if not match:
            continue
        target = match.group(2).strip()
        next_index = index + 1
        while next_index < len(public_lines) and not public_lines[next_index].strip():
            next_index += 1
        if next_index >= len(public_lines):
            structural_issues.append(
                f"orphan recode.{match.group(1)} marker for {target}"
            )
            continue
        assignment = public_lines[next_index].strip()
        if not re.match(rf"^{re.escape(target)}\s*<-", assignment):
            structural_issues.append(
                f"recode.{match.group(1)} marker target differs from assignment: {target}"
            )
            continue
        block_lines = [assignment]
        for block_line in public_lines[next_index + 1:]:
            block_lines.append(block_line)
            if re.match(r"^\s*\)\)?\s*$", block_line):
                break
        block = "\n".join(block_lines)
        if block.count(target) < 2:
            structural_issues.append(
                f"recode.{match.group(1)} marker does not recode its own target: {target}"
            )

    if structural_issues:
        fail(results, "public R structural contract", structural_issues)
    else:
        ok(results, "public R structural contract")

    masked_public = strip_r_comments_and_strings(source_public)
    masked_source = strip_r_comments_and_strings(source)
    assigned_occurrences = re.findall(
        r"(?m)^\s*([A-Za-z.][A-Za-z0-9._]*)\s*<-",
        masked_public,
    )
    assigned_objects = sorted(set(assigned_occurrences))
    unused_objects = [
        name
        for name in assigned_objects
        if len(re.findall(
            rf"(?<![A-Za-z0-9._]){re.escape(name)}(?![A-Za-z0-9._])",
            masked_source,
        )) <= assigned_occurrences.count(name)
    ]
    if unused_objects:
        fail(results, "public R unused objects", unused_objects)
    else:
        ok(results, "public R unused objects", {"assigned_objects": len(assigned_objects)})

    check_public_dictionary(source_public, results)
    check_backend_loader(source, results)


def check_backend_loader(source: str, results: list[dict]) -> None:
    if "DBCODEBOOK_DEFINITION_SKILL_ROOT" not in source:
        return
    boundary = re.search(r"(?m)^# 输出\s*$", source)
    if boundary is None:
        fail(results, "RStudio full-run loader", "# 输出 not found")
        return
    backend = source[boundary.end():]
    required = {
        "runner root": 'Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")',
        "Codex home": 'Sys.getenv("CODEX_HOME")',
        "Windows user home": 'Sys.getenv("USERPROFILE")',
        "user fallback": 'path.expand("~")',
        "default Codex home": 'file.path(user_home, ".codex")',
        "installed skill": 'file.path(codex_home, "skills", "dbcodebook-definition")',
        "helper check": "file.exists(helper_files)",
        "summary helper": '"summary_fact_helpers.R"',
        "renderer helper": '"render_definition_bundle.R"',
    }
    missing = [label for label, token in required.items() if token not in backend]
    if "请通过 dbcodebook-definition 的正式 runner 运行本脚本" in backend or (
        "请通过dbcodebook-definition正式runner运行" in backend
    ):
        missing.append("runner-only stop must be removed")
    if missing:
        fail(results, "RStudio full-run loader", missing)
    else:
        ok(results, "RStudio full-run loader")


def check_public_dictionary(source_public: str, results: list[dict]) -> None:
    note_public = source_public
    heading_pattern = re.compile(
        r"(?m)^#{1,3}\s+(?:(?:-{3,}|={3,})\s+)?(.+?)\s+"
        r"(?:-{3,}|={3,}|#{4})\s*$"
    )
    heading_matches = list(heading_pattern.finditer(note_public))
    headings = [match.group(1) for match in heading_matches]

    def normalize_heading(heading: str) -> str:
        return re.sub(
            r"^(?:[一二三四五六七八九十]+、|\d+(?:\.\d+)*\s+)",
            "",
            heading.strip(),
        )

    normalized_headings = [normalize_heading(heading) for heading in headings]
    semantic_patterns = [
        ("packages", r"包|环境"),
        ("read data", r"读取.*数据|数据读取"),
        ("definition", r"重编码|分波次|处理|计分|定义"),
        ("variable dictionary", r"^变量字典$"),
        ("formal output", r"^正式输出$"),
    ]
    matched_positions: list[int] = []
    missing: list[str] = []
    for label, pattern in semantic_patterns:
        position = next(
            (
                i
                for i, heading in enumerate(normalized_headings)
                if re.search(pattern, heading, re.I)
            ),
            None,
        )
        if position is None:
            missing.append(label)
        else:
            matched_positions.append(position)
    if len(headings) < 5 or missing or matched_positions != sorted(matched_positions):
        fail(results, "public R outline", {"headings": headings, "missing": missing})
    else:
        ok(results, "public R outline", headings)

    analysis_match = re.search(r"(?ms)^analysis_vars\s*<-\s*c\((.*?)\)\s*$", source_public)
    analysis_vars = re.findall(r'["\']([^"\']+)["\']', analysis_match.group(1)) if analysis_match else []
    helper_mapped_vars = re.findall(
        r'map\s*<-\s*add_mapping\(\s*map\s*,\s*["\']([^"\']+)["\']\s*,',
        source_public,
    )
    dictionary_start = next(
        (
            match.end()
            for match, heading in zip(heading_matches, normalized_headings)
            if heading == "变量字典"
        ),
        None,
    )
    formal_output_start = next(
        (
            match.start()
            for match, heading in zip(heading_matches, normalized_headings)
            if heading == "正式输出"
            and dictionary_start is not None
            and match.start() > dictionary_start
        ),
        None,
    )
    dictionary = (
        note_public[dictionary_start:formal_output_start]
        if dictionary_start is not None and formal_output_start is not None
        else ""
    )
    bypass = re.findall(
        r"codebook\$(?:original_vars|processed_vars|count)\s*\[.*?\]\s*<-",
        dictionary,
    )
    direct_map_uses_analysis_vars = bool(re.search(
        r"(?ms)map\s*<-\s*data\.frame\s*\(\s*Variable\s*=\s*analysis_vars\s*,",
        dictionary,
    ))
    mapped_vars = (
        analysis_vars if direct_map_uses_analysis_vars else helper_mapped_vars
    )
    mapping_is_built = (
        "add_mapping <- function" in dictionary or direct_map_uses_analysis_vars
    )
    map_drives_codebook = mapping_is_built and all(
        token in dictionary
        for token in [
            "map <- data.frame",
            "codebook <- lapply",
            "map$Variable",
            "map$original_vars",
        ]
    )
    missing_mapping = [variable for variable in analysis_vars if variable not in mapped_vars]
    if not analysis_vars or missing_mapping or bypass or not map_drives_codebook:
        fail(results, "mapping variable dictionary", {
            "analysis_vars": analysis_vars,
            "mapped_vars": mapped_vars,
            "missing": missing_mapping,
            "direct_codebook_bypass": bypass,
            "map_drives_codebook": map_drives_codebook,
            "mapping_style": (
                "direct" if direct_map_uses_analysis_vars else "helper"
            ),
        })
    else:
        ok(results, "mapping variable dictionary", {
            "variables": analysis_vars,
            "style": "direct" if direct_map_uses_analysis_vars else "helper",
        })


def extract_category_pairs(text: str) -> list[tuple[str, str]]:
    marked = []
    for match in re.finditer(r"<(?:a|summary)\b[^>]*>", text, flags=re.I):
        group = re.search(r'\bdata-component-group="([^"]*)"', match[0])
        role = re.search(r'\bdata-variable-role="(source|component|defined)"', match[0])
        if group and role:
            marked.append((match.start(), (html.unescape(group[1]).strip().lower(), role[1])))
    label_matches = [
        *re.finditer(
            r"<summary>\s*((?:[^<]+?\s+)?(?:source|defined) variables?)\s*</summary>",
            text,
            flags=re.I,
        ),
        *re.finditer(
            r"<a\s+href=\"#cat-[^\"]+\"[^>]*>\s*((?:[^<]+?\s+)?(?:source|defined) variables?)\s*</a>",
            text,
            flags=re.I,
        ),
    ]
    labels = [(match.start(), match.group(1)) for match in label_matches
              if "data-variable-role=" not in match.group(0)]
    pairs: list[tuple[str, str]] = []
    positioned = list(marked)
    for position, label in labels:
        normalized = " ".join(label.split())
        match = re.fullmatch(
            r"(?:(.+?)\s+)?(source|defined) variables?",
            normalized,
            flags=re.I,
        )
        if match:
            category = match.group(1).strip().lower() if match.group(1) else ""
            positioned.append((position, (category, match.group(2).lower())))
    return [pair for _, pair in sorted(positioned, key=lambda item: item[0])]


def check_component_group_membership(formal_dir, note_text, variables, results, record=None):
    """Check renderer grouping and its declared plan, not the semantic choice of categories."""
    expected = {p.get("analysis_var", p.get("analysis_variable")): p["display_group"]
                for p in (record or {}).get("definition_plan", []) if p.get("display_group")}
    detail_files = list(formal_dir.glob("*_detail.html"))
    if len(detail_files) != 1:
        return  # The artifact-count check reports this separately.
    for label, text in (("note", note_text), ("detail", detail_files[0].read_text(encoding="utf-8-sig"))):
        parser = DefinedSurfaceParser()
        parser.feed(text)
        if not parser.group_titles:
            if expected:
                fail(results, f"{label} component groups", "declared groups have no rendered titles")
            continue
        overview = [(v, g) for v, g in parser.overview_groups if v in variables]
        detail = [(v, g) for v, g in parser.detail_groups if v in variables]
        valid = overview == detail and [v for v, _ in overview] == variables
        valid = valid and "data-component-title=" not in text
        valid = valid and all(g for _, g in overview)
        if expected:
            valid = valid and set(expected) == set(variables) and all(expected.get(v) in (g, re.sub(r"·Components$", "", g)) for v, g in overview)
        policy = display_policy(formal_dir, variables, record)
        for group, role, visible in parser.group_titles:
            valid = valid and visible == group and role in {"component", "defined"}
            valid = valid and bool(visible.strip()) and not bool(re.search(r"(^|·)(组分|定义)$", visible))
            valid = valid and (bool(re.search(r".+·Components$", visible)) == (role == "component"))
        if valid:
            ok(results, f"{label} component groups", overview)
        else:
            fail(results, f"{label} component groups", dict(expected=expected, overview=overview, detail=detail,
                                                          titles=parser.group_titles))


def check_category_order(formal_dir: Path, note_text: str, results: list[dict], compact_module: bool = False) -> None:
    detail_files = sorted(formal_dir.glob("*_detail.html"))
    if len(detail_files) != 1:
        fail(results, "detail category order source", [path.name for path in detail_files])
        return
    materials = {
        "detail HTML": detail_files[0].read_text(encoding="utf-8", errors="replace"),
        "note": note_text,
    }
    failures: dict[str, object] = {}
    for name, text in materials.items():
        pairs = extract_category_pairs(text)
        valid = bool(pairs) and len(pairs) % 2 == 0
        if valid:
            midpoint = len(pairs) // 2
            visible_order = pairs[:midpoint]
            valid = visible_order == pairs[midpoint:]
        if valid:
            categories = list(dict.fromkeys(category for category, _ in visible_order))
            for category in categories:
                roles = [role for current, role in visible_order if current == category]
                valid = valid and roles in (["defined"], ["component"])
        if not valid:
            failures[name] = pairs
    if failures:
        fail(results, "detail/note category order", failures)
    else:
        ok(results, "detail/note category order", {name: extract_category_pairs(text) for name, text in materials.items()})


def check_result_presentation(formal_dir, note_text, variables, labels, results, record=None):
    """One order across explicit result surfaces, with source columns filtered out."""
    for name, text in [("note", note_text)] + [
            (path.name, path.read_text(encoding="utf-8-sig")) for path in formal_dir.glob("*_detail.html")]:
        parser = DefinedSurfaceParser()
        parser.feed(text)
        raw_book = formal_dir / "raw_codebook.csv"
        raw_names = set()
        if raw_book.is_file():
            with raw_book.open(encoding="utf-8-sig", newline="") as stream:
                raw_names = {row.get("newname", "") for row in csv.DictReader(stream)}
        leaked = (set(parser.overview_variables) | {v for v, _ in parser.detail_groups}) & (raw_names - set(variables))
        if leaked:
            fail(results, f"{name} hidden raw variables", sorted(leaked))
        else:
            ok(results, f"{name} hidden raw variables")
        overview = [v for v in parser.overview_variables if v in variables]
        detail = [v for v, _ in parser.detail_groups if v in variables]
        if overview != variables or detail != variables:
            fail(results, f"{name} final result order", dict(expected=variables, overview=overview, detail=detail))
        else:
            ok(results, f"{name} final result order", variables)
    from check_reader_copy import check_tree_result_order, sections
    plan = (record or {}).get("definition_plan", [])
    planned = {p.get("analysis_var", p.get("analysis_variable")): p.get("display_name") for p in plan}
    path = formal_dir / READER_COPY_NAME
    if not path.is_file():
        fail(results, "tree final result order", "missing 文案.md")
        return
    try:
        summary = sections(path.read_text(encoding="utf-8-sig"), 2).get("摘要导读", "")
        display_names = planned if any("display_name" in p for p in plan) else labels
        evidence = check_tree_result_order(summary, variables, display_names)
        ok(results, "tree final result order", evidence)
    except ValueError as exc:
        fail(results, "tree final result order", str(exc))

def check_summary_facts(
    formal_dir: Path,
    analysis_db_name: str | None,
    analysis_codebook_name: str | None,
    results: list[dict],
    db: str,
    formal_r: Path | None = None,
    record: dict | None = None,
) -> None:
    """Check the current summary and definition table without a legacy five-list."""
    if not analysis_db_name or not analysis_codebook_name:
        fail(
            results,
            "summary facts inputs",
            "--analysis-db and --analysis-codebook are required",
        )
        return

    notes = formal_note_files(formal_dir)
    if len(notes) != 1:
        fail(results, "summary note", [path.name for path in notes])
        return
    note_text = notes[0].read_text(encoding="utf-8", errors="replace")
    user_materials = [
        *sorted(formal_dir.glob("*.md")),
        *sorted(formal_dir.glob("*.html")),
    ]
    indented = [
        path.name
        for path in user_materials
        if "&emsp;" in path.read_text(encoding="utf-8", errors="replace")
    ]
    if indented:
        fail(results, "summary prose indentation", indented)
    else:
        ok(results, "summary prose indentation", "&emsp; indentation entities = 0")

    db_rows = read_table_rows(formal_dir / analysis_db_name)
    cb_rows = read_xlsx_rows(formal_dir / analysis_codebook_name)
    if not db_rows or not cb_rows:
        fail(results, "analysis workbooks", "analysis workbook is empty")
        return
    db_header = [str(value) if value is not None else "" for value in db_rows[0]]
    cb_header = [str(value) if value is not None else "" for value in cb_rows[0]]
    if "Variable" not in cb_header:
        fail(results, "definition codebook fields", "missing Variable")
        return
    var_idx = cb_header.index("Variable")
    codebook_variables = [
        str(row[var_idx])
        for row in cb_rows[1:]
        if len(row) > var_idx and is_nonmissing(row[var_idx])
    ]
    try:
        policy = display_policy(formal_dir, codebook_variables, record)
    except ValueError as exc:
        fail(results, "definition display policy", str(exc))
        return
    check_summary_prose(note_text, results, policy["compact_module"])
    if policy["compact_module"]:
        check_compact_surfaces(formal_dir, note_text, codebook_variables, results)
    else:
        try:
            definition_variables = parse_definition_table(note_text)
        except ValueError as exc:
            fail(results, "definition table structure", str(exc))
            return
        if definition_variables == codebook_variables:
            ok(results, "definition table variables and order", definition_variables)
        else:
            fail(
                results,
                "definition table variables and order",
                {"expected": codebook_variables, "actual": definition_variables},
            )
    missing_from_db = [name for name in codebook_variables if name not in db_header]
    if missing_from_db:
        fail(results, "definition variables in analysis_db", missing_from_db)
    else:
        ok(results, "definition variables in analysis_db", codebook_variables)

    check_public_code_outline(formal_dir, note_text, results, db, formal_r, record)
    check_category_order(formal_dir, note_text, results, policy["compact_module"])
    check_component_group_membership(formal_dir, note_text, codebook_variables, results, record)
    label_idx = cb_header.index("Label") if "Label" in cb_header else None
    labels = {str(row[var_idx]): row[label_idx] if label_idx is not None and len(row) > label_idx else None
              for row in cb_rows[1:] if len(row) > var_idx and is_nonmissing(row[var_idx])}
    check_result_presentation(formal_dir, note_text, codebook_variables, labels, results, record)


def visible_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def check_required_user_text(formal_dir: Path, required: list[str], results: list[dict], policy: dict | None = None) -> None:
    if not required:
        return
    notes = formal_note_files(formal_dir)
    if policy and policy["compact_module"]:
        if len(notes) != 1:
            fail(results, "required user text sources", "Expected one rendered note")
            return
        # Detail HTML contains variable details, not the note's summary prose.
        missing = {path.name: [item for item in required if item not in visible_text(path.read_text(encoding="utf-8-sig"))] for path in notes}
        missing = {name: values for name, values in missing.items() if values}
        if missing:
            fail(results, "required user text", missing)
        else:
            ok(results, "required user text", required)
        return
    definitions = sorted(formal_dir.glob("*definition*.html"))
    if len(notes) != 1 or len(definitions) != 1:
        fail(results, "required user text sources", {
            "notes": [path.name for path in notes],
            "definitions": [path.name for path in definitions],
        })
        return
    note_text = visible_text(notes[0].read_text(encoding="utf-8", errors="replace"))
    definition_text = visible_text(definitions[0].read_text(encoding="utf-8", errors="replace"))
    missing = {
        "note": [item for item in required if item not in note_text],
        "definition": [item for item in required if item not in definition_text],
    }
    missing = {name: values for name, values in missing.items() if values}
    if missing:
        fail(results, "required user text", missing)
    else:
        ok(results, "required user text", required)


def visible_text_with_breaks(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"[ \t]+", " ", value)


def check_criteria_evolution(formal_dir: Path, required: list[str], results: list[dict], policy: dict | None = None) -> None:
    if not required:
        return
    if policy and policy["compact_module"]:
        fail(results, "Criteria evolution scope", "compact modules cannot request omitted Criteria checks")
        return
    definitions = sorted(formal_dir.glob("*definition*.html"))
    notes = formal_note_files(formal_dir)
    if len(definitions) != 1 or len(notes) != 1:
        fail(results, "Criteria evolution sources", {
            "definitions": [path.name for path in definitions],
            "notes": [path.name for path in notes],
        })
        return
    definition_text = visible_text_with_breaks(definitions[0].read_text(encoding="utf-8", errors="replace"))
    note_text = visible_text_with_breaks(notes[0].read_text(encoding="utf-8", errors="replace"))
    positions = [definition_text.find(item) for item in required]
    ordered = all(position >= 0 for position in positions) and positions == sorted(positions)
    first = positions[0] if ordered else -1
    last = positions[-1] + len(required[-1]) if ordered else -1
    evolution_block = definition_text[first:last] if ordered else ""
    separated = ordered and all("\n" in definition_text[positions[index] + len(required[index]):positions[index + 1]] for index in range(len(required) - 1))
    attention_before = ordered and definition_text.rfind("注意点：", 0, first) > definition_text.rfind("定义逻辑：", 0, first)
    note_complete = all(item in note_text for item in required)
    if not ordered or not separated or not attention_before or not note_complete:
        fail(results, "Criteria evolution structure", {
            "ordered": ordered,
            "br_separated": separated,
            "under_attention": attention_before,
            "note_complete": note_complete,
            "block": evolution_block,
        })
    else:
        ok(results, "Criteria evolution structure", required)


def check_forbidden_formal_content(formal_dir: Path, forbidden: set[str], results: list[dict]) -> None:
    if not forbidden:
        return
    findings: list[dict[str, str]] = []
    text_suffixes = {".r", ".md", ".html", ".csv", ".txt", ".log"}
    for path in sorted(formal_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in text_suffixes:
            content = path.read_text(encoding="utf-8-sig", errors="replace")
            for value in forbidden:
                if value in content:
                    findings.append({"file": path.name, "value": value})
        if path.is_file() and path.suffix.lower() == ".xlsx":
            for row in read_xlsx_rows(path):
                row_text = " ".join("" if value is None else str(value) for value in row)
                for value in forbidden:
                    if value in row_text:
                        findings.append({"file": path.name, "value": value})
    if findings:
        fail(results, "forbidden formal content", findings)
    else:
        ok(results, "forbidden formal content", sorted(forbidden))


def main() -> int:
    args = parse_args()
    results: list[dict] = []
    if args.public_r_script is not None:
        source = args.public_r_script.read_text(encoding="utf-8-sig")
        boundary = re.search(r"(?m)^# 输出\s*$", source)
        if boundary is None:
            fail(results, "public R outline boundary", "# 输出 not found")
        else:
            check_public_dictionary(source[:boundary.start()], results)
            check_backend_loader(source, results)
        passed = all(item["ok"] for item in results)
        print(json.dumps({"ok": passed, "checks": results}, ensure_ascii=False))
        return 0 if passed else 1
    formal_dir = args.formal_dir
    from mhas_export_contract import RAW_NAME as MHAS_RAW_NAME, raw_files as mhas_raw_files
    try:
        raw_members = mhas_raw_files(formal_dir) if args.db == "mhas" else []
    except ValueError as exc:
        fail(results, "MHAS source-file contracts", str(exc))
        print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False, indent=2))
        return 1
    primary_raw_name = (raw_members[0].name if raw_members else MHAS_RAW_NAME) if args.db == "mhas" else "raw_data.csv"
    if args.db == "nhanesiii":
        from nhanesiii_export_contract import RAW_NAME
        primary_raw_name = RAW_NAME

    if not formal_dir.exists():
        fail(results, "formal dir exists", str(formal_dir))
        print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False, indent=2))
        return 1
    ok(results, "formal dir exists", str(formal_dir))

    source_record = None
    if args.process_dir is not None:
        source_path = args.process_dir / "definition_search_record.json"
        if source_path.is_file():
            source_record = json.loads(source_path.read_text(encoding="utf-8-sig"))
    knhanes_person_contract = None
    if args.db == "knhanes" and (formal_dir / "raw_codebook.csv").is_file():
        try:
            from knhanes_export import validate_person_package
            knhanes_person_contract = validate_person_package(formal_dir, split_csv(args.raw_vars) or None, source_record)
            primary_raw_name = "raw_data.csv" if "person_aggregation" in knhanes_person_contract else next(iter(knhanes_person_contract["data"]))
            raw_members = [formal_dir / name for name in knhanes_person_contract["data"]]
        except (OSError, ValueError) as exc:
            fail(results, "KNHANES personal source-file contract", str(exc))
            print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False, indent=2))
            return 1

    klosa_package_contract = None
    if args.db == "klosa" and (formal_dir / "raw_codebook.csv").is_file():
        from klosa_adapter_contract import validate_package, REPEAT_MEMBER
        try:
            members = [p.name for p in formal_dir.glob("raw_data*.csv")]
            if REPEAT_MEMBER in members:
                raise ValueError("KLoSA imputation analysis is not supported")
            klosa_package_contract = validate_package(formal_dir, members,
                split_csv(args.raw_vars) or read_codebook_vars(formal_dir / "raw_codebook.csv"), args.language)
            raw_members = [formal_dir / name for name in klosa_package_contract["data"]]
        except (OSError, ValueError) as exc:
            fail(results, "KLoSA source-file contracts", str(exc))
            print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False))
            return 1

    expected_files = split_csv(args.expected_files)
    if args.db == "charls":
        from check_definition_source_record import primary_raw_name as charls_primary_raw_name
        try:
            primary_raw_name = charls_primary_raw_name(source_record, args.db)
        except ValueError as exc:
            fail(results, "analysis identity contract", str(exc))
            print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False))
            return 1
    if args.complete:
        table_format = (source_record or {}).get('data_table_format','xlsx')
        data_files = [n for n in expected_files if n.startswith('db_') or n == args.analysis_db]
        if table_format not in {'xlsx','csv'} or len(data_files) != 2 or any(Path(n).suffix.lower() != '.'+table_format for n in data_files):
            fail(results,'final data table format',{'declared':table_format,'files':data_files})
        else:
            ok(results,'final data table format',{'data':table_format,'codebooks':'xlsx'})
    try:
        policy = display_policy(formal_dir, split_csv(args.analysis_vars) or None, source_record)
    except ValueError as exc:
        fail(results, "definition display policy", str(exc))
        policy = {"compact_module": False}
    if policy["compact_module"]:
        expected_files = [name for name in expected_files if not name.endswith("_definition.html")]
    if args.complete:
        try:
            expected_files = include_formal_r(formal_dir, expected_files)
        except ValueError as error:
            fail(results, "public R discovery", str(error))
    if args.complete:
        required_names = {primary_raw_name, "raw_codebook.csv", args.analysis_db, args.analysis_codebook}
        if args.db in {"mhas", "knhanes", "klosa"}:
            required_names.update(path.name for path in raw_members)
        missing = required_names - set(expected_files)
        roles = {"public_r": any(name.lower().endswith(".r") for name in expected_files),
                 "note": any(name.endswith(".md") and name != READER_COPY_NAME for name in expected_files),
                 "db": any(name.startswith("db_") and name.endswith((".xlsx",'.csv')) for name in expected_files),
                 "codebook": any(name.startswith("codebook_") and name.endswith(".xlsx") for name in expected_files)}
        if missing or not all(roles.values()):
            fail(results, "complete artifact scope", {"missing_files": sorted(missing), "roles": roles})
    for name in expected_files:
        path = formal_dir / name
        if path.exists():
            ok(results, f"required file: {name}")
        else:
            fail(results, f"required file: {name}", str(path))

    check_forbidden_files(formal_dir, results, args.max_md)

    charls_multifile_contract = None
    raw_vars = split_csv(args.raw_vars)
    forbid_vars = set(split_csv(args.forbid_vars))
    required_user_text = split_csv(args.required_user_text)
    criteria_evolution_text = split_csv(args.criteria_evolution_text)
    if raw_vars:
        raw_data = formal_dir / primary_raw_name
        raw_codebook = formal_dir / "raw_codebook.csv"
        expected_header = expected_raw_header(args.db, raw_vars)
        if args.db == "klosa":
            from klosa_adapter_contract import validate_package
            try:
                validate_package(formal_dir, [p.name for p in formal_dir.glob("raw_data*.csv")], raw_vars, args.language)
                ok(results, "KLoSA package contract")
            except ValueError as exc:
                fail(results, "KLoSA package contract", str(exc))
        header = read_csv_header(raw_data)
        if klosa_package_contract:
            header = list(dict.fromkeys(name for path in raw_members for name in read_csv_header(path)))
        charls_multifile = (args.db == "charls" and primary_raw_name == "raw_data.csv"
                            and len(list(formal_dir.glob("raw_data*.csv"))) > 1)
        charls_multifile_matches = False
        if charls_multifile:
            try:
                contract = check_charls_person_multifile_contract(
                    formal_dir, raw_vars, source_record, expected_files if args.complete else None)
                charls_multifile_contract = contract
                charls_multifile_matches = True
                ok(results, "CHARLS personal multi-file source contract", contract)
            except (OSError, ValueError, KeyError) as exc:
                fail(results, "CHARLS personal multi-file source contract", str(exc))
        nhis_header_matches = False
        if args.db == 'nhis':
            try:
                from nhis_export_contract import validate_package, require_context, build_selection
                if source_record is None:
                    raise ValueError('NHIS output verification requires the exact source record in --process-dir')
                require_context(source_record,args.dataset_id)
                selection = build_selection(source_record,source_record['dbcodebook_url'])
                contract = validate_package(formal_dir,[p.name for p in formal_dir.glob('raw_data*.csv')],raw_vars,args.dataset_id,selection)
                nhis_header_matches = True
                ok(results,'NHIS exact-source unique-person contract',contract)
            except (OSError,ValueError,KeyError) as exc:
                fail(results,'NHIS exact-source unique-person contract',str(exc))
        nhanesiii_header_matches = False
        if args.db == "nhanesiii":
            try:
                from nhanesiii_export_contract import validate_package
                contract = validate_package(formal_dir, [p.name for p in formal_dir.glob("raw_data*.csv")], raw_vars)
                nhanesiii_header_matches = True
                ok(results, "NHANES III unique-person contract", contract)
            except (OSError, ValueError) as exc:
                fail(results, "NHANES III unique-person contract", str(exc))
        nhanes_header_matches = False
        if args.db == "nhanes":
            try:
                from nhanes_export_contract import validate_package
                contract = validate_package(formal_dir, [p.name for p in formal_dir.glob("raw_data*.csv")], raw_vars)
                nhanes_header_matches = True
                if args.complete:
                    omitted = set(contract.get('files', {'raw_data.csv': contract})) - set(expected_files)
                    if omitted:
                        raise ValueError("NHANES complete artifact scope omits source files: " + ", ".join(sorted(omitted)))
                ok(results, "NHANES source-file contracts", contract)
            except (OSError, ValueError) as exc:
                fail(results, "NHANES source-file contracts", str(exc))
        mhas_header_matches = False
        if args.db == "mhas":
            try:
                from mhas_export_contract import validate_package
                contract = validate_package(formal_dir, [p.name for p in formal_dir.glob("raw_data*.csv")], raw_vars)
                mhas_header_matches = True
                header = list(dict.fromkeys(name for path in raw_members for name in read_csv_header(path)))
                ok(results, "MHAS person-period file contracts", contract)
            except (OSError, ValueError) as exc:
                fail(results, "MHAS person-period file contracts", str(exc))
        chns_header_matches = False
        if args.db == "chns":
            try:
                from chns_export_contract import validate_person_package
                members = [p.name for p in formal_dir.glob("raw_data*.csv")]
                contract = validate_person_package(formal_dir, members, raw_vars)
                if "raw_data.csv" not in contract:
                    raise ValueError("CHNS definition requires a personal-period main file")
                if args.complete:
                    omitted = set(contract) - set(expected_files)
                    if omitted:
                        raise ValueError("CHNS complete artifact scope omits source files: " + ", ".join(sorted(omitted)))
                chns_header_matches = True
                ok(results, "CHNS personal/static file contract", contract)
            except (OSError, ValueError) as exc:
                fail(results, "CHNS personal/static file contract", str(exc))
        if args.db == "knhanes":
            try:
                if knhanes_person_contract is None:
                    from knhanes_export import validate_person_package
                    knhanes_person_contract = validate_person_package(formal_dir, raw_vars, source_record)
                ok(results, "KNHANES personal source-file contract", knhanes_person_contract)
                header = list(dict.fromkeys(name for path in raw_members for name in read_csv_header(path)))
                if "person_aggregation" in knhanes_person_contract:
                    # Transport has separately checked the preserved RowIndex.
                    header = [name for name in header if name != "RowIndex"]
            except (OSError, ValueError) as exc:
                fail(results, "KNHANES respondent-year contract", str(exc))
        layered_headers = (
            charls_layered_raw_headers(raw_vars)
            if args.db == "charls"
            else [expected_header]
        )
        hrs_defaults = set()
        if args.db == "hrs":
            from hrs_export_contract import validate_defaults, accepts_legacy_package
            try:
                hrs_defaults = validate_defaults(raw_codebook, header, legacy_package=accepts_legacy_package(args.process_dir, formal_dir))
            except ValueError as exc:
                fail(results, "HRS automatic Tracker columns", str(exc))
        hrs_repeat_header_matches = False
        if args.db == "hrs":
            members = [p.name for p in formal_dir.glob("raw_data*.csv")]
            if any(member != "raw_data.csv" for member in members):
                try:
                    from hrs_export_contract import HRS_REPEAT_FILES
                    from recover_dbcodebook_export import validate_data_members
                    supported = {"raw_data.csv"} | {
                        "raw_data_repeat_" + family + ".csv" for family in HRS_REPEAT_FILES}
                    if set(members) - supported or "raw_data.csv" not in members:
                        raise ValueError("Unsupported HRS repeated source files")
                    if header[:4] != ["ID", "HHID", "PN", "Wave_id"]:
                        raise ValueError("HRS main file must retain its four default identity columns")
                    import contextlib, io
                    diagnostic = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(diagnostic):
                            contract = validate_data_members(formal_dir, members, raw_vars)
                    except SystemExit as exc:
                        raise ValueError("HRS package verification failed: " + diagnostic.getvalue().strip()) from exc
                    if args.complete and set(members) - set(expected_files):
                        raise ValueError("Complete HRS artifact scope omits repeated source files")
                    hrs_repeat_header_matches = True
                    ok(results, "HRS repeated person-source file contracts", contract)
                except (OSError, ValueError) as exc:
                    fail(results, "HRS repeated person-source file contracts", str(exc))
        hrs_header_matches = (
            args.db == "hrs"
            and header[:4] == ["ID", "HHID", "PN", "Wave_id"]
            and len(header[4:]) == len(raw_vars) + len(hrs_defaults)
            and set(header[4:]) == set(raw_vars) | hrs_defaults
        ) or hrs_repeat_header_matches
        share_header_matches = False
        if args.db == "share":
            try:
                from share_export_contract import validate_unique_package
                share_contract = validate_unique_package(formal_dir, ["raw_data.csv"], raw_vars)
                share_header_matches = True
                ok(results, "SHARE personal key contract", share_contract)
            except ValueError as exc:
                fail(results, "SHARE personal key contract", str(exc))
        knhanes_header_matches = (args.db == "knhanes" and header[:3] == ["ID", "id", "year"]
                                  and len(header[3:]) == len(raw_vars) and set(header[3:]) == set(raw_vars))
        klosa_header_matches = False
        if args.db == "klosa":
            from klosa_adapter_contract import identity_columns as klosa_identity_columns
            try:
                klosa_keys = klosa_identity_columns(header)
                klosa_header_matches = (len(header[len(klosa_keys):]) == len(raw_vars)
                    and set(header[len(klosa_keys):]) == set(raw_vars))
            except ValueError:
                pass
        elsa_header_matches = False
        if args.db == "elsa":
            try:
                elsa_contract = check_elsa_raw_contract(raw_data, raw_vars)
                elsa_header_matches = True
                ok(results, "ELSA default Wave_id", elsa_contract)
            except ValueError as exc:
                fail(results, "ELSA default Wave_id", str(exc))
        if (args.db not in {"share", "chns", "elsa", "mhas", "nhanes", "nhanesiii", "nhis"} and not charls_multifile and (header in layered_headers or hrs_header_matches or klosa_header_matches)) or charls_multifile_matches or share_header_matches or knhanes_header_matches or chns_header_matches or elsa_header_matches or mhas_header_matches or nhanes_header_matches or nhanesiii_header_matches or nhis_header_matches:
            ok(results, "raw_data header", header)
        elif args.db == "charls" and header == ["ID", "year", *raw_vars]:
            identifier_check = check_charls_household_identifier(raw_data)
            if identifier_check["ok"]:
                ok(
                    results,
                    "raw_data header",
                    {
                        "header": header,
                        "identifier": identifier_check,
                    },
                )
            else:
                fail(
                    results,
                    "raw_data header",
                    {
                        "expected": expected_header,
                        "actual": header,
                        "identifier": identifier_check,
                    },
                )
        else:
            fail(
                results,
                "raw_data header",
                {"expected": layered_headers, "actual": header},
            )
        ok(results, "raw_data rows", sum(count_csv_records(path) for path in raw_members) if args.db in {"mhas", "knhanes", "klosa"} else count_csv_records(raw_data))

        try:
            if args.db == "elsa":
                codebook_vars = read_elsa_codebook(raw_codebook)
            else:
                codebook_vars = read_codebook_vars(raw_codebook)
        except ValueError as exc:
            codebook_vars = []
            fail(results, "raw_codebook structure", str(exc))
        if codebook_vars == raw_vars:
            ok(results, "raw_codebook vars", codebook_vars)
        else:
            fail(results, "raw_codebook vars", {"expected": raw_vars, "actual": codebook_vars})

        forbidden_found = sorted(forbid_vars.intersection(set(header + codebook_vars)))
        if forbidden_found:
            fail(results, "forbidden vars in raw/codebook", forbidden_found)
        else:
            ok(results, "forbidden vars in raw/codebook")

    if args.analysis_db:
        rows = read_table_rows(formal_dir / args.analysis_db)
        header = [str(item) if item is not None else "" for item in rows[0]]
        expected_columns = split_csv(args.analysis_columns)
        if expected_columns and header != expected_columns:
            fail(results, "analysis_db columns", {"expected": expected_columns, "actual": header})
        else:
            ok(results, "analysis_db columns", header)
        ok(results, "analysis_db dimensions", {"rows": len(rows) - 1, "cols": len(header)})

        raw_data_path = formal_dir / primary_raw_name
        if raw_data_path.exists():
            identity_header = list(dict.fromkeys(name for path in raw_members for name in read_csv_header(path))) if args.db in {"mhas", "knhanes", "klosa"} else read_csv_header(raw_data_path)
            check_identity_values(
                raw_data_path,
                identity_header,
                rows,
                header,
                results,
                args.db,
                raw_paths=raw_members if args.db in {"mhas", "knhanes", "klosa"} else None,
                source_record=source_record,
            )

        forbidden_found = sorted(forbid_vars.intersection(set(header)))
        if forbidden_found:
            fail(results, "forbidden vars in analysis_db", forbidden_found)
        else:
            ok(results, "forbidden vars in analysis_db")

    if args.analysis_codebook:
        rows = read_xlsx_rows(formal_dir / args.analysis_codebook)
        header = [str(item) if item is not None else "" for item in rows[0]]
        try:
            var_idx = header.index("Variable")
        except ValueError:
            var_idx = 0
        variables = [str(row[var_idx]) for row in rows[1:] if len(row) > var_idx and row[var_idx] is not None]
        expected_vars = split_csv(args.analysis_vars)
        if expected_vars and variables != expected_vars:
            fail(results, "analysis_codebook vars", {"expected": expected_vars, "actual": variables})
        else:
            ok(results, "analysis_codebook vars", variables)

    if args.complete:
        check_workbook_contract(formal_dir, expected_files, args.analysis_db, args.analysis_codebook,
                                raw_vars, split_csv(args.analysis_vars), results,
                                ([dict(item, method=source_record["knhanes_person_aggregation"]["method"])
                                  for item in source_record["knhanes_person_aggregation"]["source_summaries"]]
                                 if args.db == "knhanes" and "person_aggregation" in (knhanes_person_contract or {})
                                 else (source_record or {}).get("source_summaries") if args.db == "nhanes" else None),
                                source_record if args.db == "nhanes" else None,
                                charls_multifile_contract=charls_multifile_contract,
                                result_label_plan=(source_record or {}).get("definition_plan"))

    if args.complete and args.db == "knhanes" and "person_aggregation" in (knhanes_person_contract or {}):
        try:
            from knhanes_person_aggregation import expected_person_summaries, validate_summary_cells
            expected, summaries, stats = expected_person_summaries(formal_dir, source_record, knhanes_person_contract)
            full_names = [name for name in expected_files if name.startswith("db_") and name.endswith((".xlsx", ".csv"))]
            if len(full_names) != 1:
                raise ValueError("Expected exactly one full person-level table")
            full = read_table_rows(formal_dir / full_names[0])
            checked = validate_summary_cells(full[0], full[1:], expected, summaries)
            ok(results, "KNHANES repeated-source summary cells", dict(checked, aggregation=stats))
        except (ValueError, OSError) as exc:
            fail(results, "KNHANES repeated-source summary cells", str(exc))

    if args.check_summary_facts:
        r_names = [name for name in expected_files if name.lower().endswith('.r')]
        if len(r_names) > 1:
            fail(results, "public R outline source", "Expected one explicitly selected formal R")
        selected_r = formal_dir / r_names[0] if len(r_names) == 1 else None
        check_summary_facts(
            formal_dir,
            args.analysis_db,
            args.analysis_codebook,
            results,
            args.db,
            selected_r,
            source_record,
        )
    if args.complete:
        from check_definition_source_record import load_json
        record = load_json(args.process_dir / "definition_search_record.json")
        if record.get("approved_analysis_vars") != split_csv(args.analysis_vars):
            fail(results, "approved result scope", "analysis vars differ from the settled source plan")
        if args.db == "klosa":
            from klosa_adapter_contract import require_context
            try: require_context(record, args.language)
            except ValueError as exc: fail(results, "approved language", str(exc))
        if args.db == 'nhis':
            from nhis_export_contract import require_context
            try: require_context(record,args.dataset_id)
            except ValueError as exc: fail(results,'approved dataset',str(exc))
        if str(record.get("database", "")).lower() != args.db:
            fail(results, "approved database", "database differs from the source plan")
    check_required_user_text(formal_dir, required_user_text, results, policy)
    check_criteria_evolution(formal_dir, criteria_evolution_text, results, policy)
    check_forbidden_formal_content(formal_dir, forbid_vars, results)

    check_logs(formal_dir, args.log_prefix, args.require_log_exit_code, results)

    passed = all(item["ok"] for item in results)
    payload = {"ok": passed, "scope": "complete" if args.complete else "partial",
               "status": ("MACHINE_CHECK_PASS" if args.complete else "PARTIAL_CHECK_PASS") if passed else "CHECK_FAILED",
               "checks": results}
    if args.complete and passed:
        payload["artifacts"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest().upper()
            for path in sorted(formal_dir.iterdir()) if path.is_file()
        }
        payload["database"] = args.db
        if args.db == 'nhis': payload['dataset_id'] = args.dataset_id
        payload["analysis_vars"] = split_csv(args.analysis_vars)
        payload["source_sha256"] = hashlib.sha256((args.process_dir / "definition_search_record.json").read_bytes()).hexdigest().upper()
        payload["checker_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

