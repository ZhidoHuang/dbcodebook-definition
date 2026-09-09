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
from xml.etree import ElementTree as ET


NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
READER_COPY_NAME = "文案.md"


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


def normalize_var(value: str) -> str:
    return value.split(" (", 1)[0].strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check definition output artifacts.")
    parser.add_argument(
        "--db",
        choices=["charls", "elsa"],
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
    parser.add_argument("--analysis-db", help="Analysis db xlsx file name in formal dir.")
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
    if db == "elsa":
        return ["ID", "idauniq", *raw_vars]
    return ["ID", "id", "year", *raw_vars]


def charls_layered_raw_headers(raw_vars: list[str]) -> list[list[str]]:
    """Return the supported CHARLS export identities by data layer."""
    return [
        ["ID", "id", "year", *raw_vars],
        ["householdid", "year", "respondent_id", *raw_vars],
        ["householdid", "year", "id", *raw_vars],
        ["communityid", "year", *raw_vars],
    ]


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
    with zipfile.ZipFile(path) as zf:
        shared_strings = load_shared_strings(zf)
        sheet_xml = zf.read(first_sheet_path(zf))
    root = ET.fromstring(sheet_xml)
    rows: list[list[object]] = []
    for row in root.iter(f"{NS_MAIN}row"):
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
        rows.append(values)
    return rows


def check_identity_values(
    raw_path: Path,
    raw_header: list[str],
    analysis_rows: list[list[object]],
    analysis_header: list[str],
    results: list[dict],
) -> None:
    identity_candidates = [
        "ID",
        "id",
        "year",
        "householdid",
        "respondent_id",
        "communityid",
        "idauniq",
    ]
    identity_columns = [
        name
        for name in identity_candidates
        if name in raw_header and name in analysis_header
    ]
    if not identity_columns:
        ok(results, "analysis identity values", "no shared identity columns")
        return

    raw_indexes = [raw_header.index(name) for name in identity_columns]
    analysis_indexes = [analysis_header.index(name) for name in identity_columns]

    def identity(row: list[object], indexes: list[int]) -> tuple[str, ...]:
        return tuple(
            "" if index >= len(row) or row[index] is None else str(row[index])
            for index in indexes
        )

    raw_identities: Counter[tuple[str, ...]] = Counter()
    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for raw_row in reader:
            raw_identities[identity(raw_row, raw_indexes)] += 1

    remaining = raw_identities.copy()
    mismatches: list[dict] = []
    for row_number, analysis_row in enumerate(analysis_rows[1:], start=2):
        analysis_identity = identity(analysis_row, analysis_indexes)
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
                "relation": "analysis identity combinations occur in raw data",
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


def check_summary_prose(note_text: str, results: list[dict]) -> None:
    section = re.search(
        r"(?ms)^## 摘要导读\s*$\n(.*?)^## 定义\s*$",
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
            expected_titles = {"问卷设计", "构建数据库"}
        elif period_style == "constructed":
            expected_titles = {"构建数据库变化"}
        else:
            expected_titles = {"问卷设计"}
        title_match = re.search(
            r'(?s)<[^>]*data-summary-period-note-title="true"[^>]*>(.*?)</[^>]+>',
            body,
        )
        actual_title = visible_text(title_match.group(1)) if title_match else ""
        if period_index == 0 and actual_title == "构建数据库":
            period_style = "constructed"
        elif period_index == 0 and actual_title == "问卷设计":
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
        or source_count != 1
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


def check_public_code_outline(
    formal_dir: Path,
    note_text: str,
    results: list[dict],
    db: str,
) -> None:
    scripts = sorted(formal_dir.glob("define*.R"))
    if len(scripts) != 1:
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
        raw_data_path = formal_dir / "raw_data.csv"
        if raw_data_path.exists():
            raw_header = read_csv_header(raw_data_path)
            duplicate_header = sorted({
                name for name in raw_header if raw_header.count(name) > 1
            })
            if duplicate_header:
                structural_issues.append(
                    "raw_data.csv contains duplicate columns; assign unique aliases "
                    f"in dbCodeBook before download: {', '.join(duplicate_header)}"
                )
        simple_codebook_read = 'name_z <- read.csv("raw_codebook.csv")' in source_public
        if not simple_codebook_read:
            structural_issues.append(
                "CHARLS public R must read raw_codebook.csv without extra options"
            )
        simple_data_read = 'dt <- read.csv("raw_data.csv")' in source_public
        household_data_read = (
            'colClasses = c(householdid = "character", id = "character")'
            in source_public
        )
        person_data_read = (
            'colClasses = c(id = "character")' in source_public
        )
        community_data_read = (
            'colClasses = c(communityid = "character")' in source_public
        )
        if not (
            simple_data_read
            or person_data_read
            or household_data_read
            or community_data_read
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
    labels = [match.group(1) for match in sorted(label_matches, key=lambda item: item.start())]
    pairs: list[tuple[str, str]] = []
    for label in labels:
        normalized = " ".join(label.split())
        match = re.fullmatch(
            r"(?:(.+?)\s+)?(source|defined) variables?",
            normalized,
            flags=re.I,
        )
        if match:
            category = match.group(1).strip().lower() if match.group(1) else ""
            pairs.append((category, match.group(2).lower()))
    return pairs


def check_category_order(formal_dir: Path, note_text: str, results: list[dict]) -> None:
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
                valid = valid and roles in (["defined"], ["source", "defined"])
        if not valid:
            failures[name] = pairs
    if failures:
        fail(results, "detail/note category order", failures)
    else:
        ok(results, "detail/note category order", {name: extract_category_pairs(text) for name, text in materials.items()})

def check_summary_facts(
    formal_dir: Path,
    analysis_db_name: str | None,
    analysis_codebook_name: str | None,
    results: list[dict],
    db: str,
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

    check_summary_prose(note_text, results)
    try:
        definition_variables = parse_definition_table(note_text)
    except ValueError as exc:
        fail(results, "definition table structure", str(exc))
        return

    db_rows = read_xlsx_rows(formal_dir / analysis_db_name)
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

    check_public_code_outline(formal_dir, note_text, results, db)
    check_category_order(formal_dir, note_text, results)


def visible_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def check_required_user_text(formal_dir: Path, required: list[str], results: list[dict]) -> None:
    if not required:
        return
    notes = formal_note_files(formal_dir)
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


def check_criteria_evolution(formal_dir: Path, required: list[str], results: list[dict]) -> None:
    if not required:
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

    if not formal_dir.exists():
        fail(results, "formal dir exists", str(formal_dir))
        print(json.dumps({"ok": False, "checks": results}, ensure_ascii=False, indent=2))
        return 1
    ok(results, "formal dir exists", str(formal_dir))

    expected_files = split_csv(args.expected_files)
    if args.complete:
        required_names = {"raw_data.csv", "raw_codebook.csv", args.analysis_db, args.analysis_codebook}
        missing = required_names - set(expected_files)
        roles = {"public_r": any(name.lower().endswith(".r") for name in expected_files),
                 "note": any(name.endswith(".md") and name != READER_COPY_NAME for name in expected_files),
                 "db": any(name.startswith("db_") and name.endswith(".xlsx") for name in expected_files),
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

    raw_vars = split_csv(args.raw_vars)
    forbid_vars = set(split_csv(args.forbid_vars))
    required_user_text = split_csv(args.required_user_text)
    criteria_evolution_text = split_csv(args.criteria_evolution_text)
    if raw_vars:
        raw_data = formal_dir / "raw_data.csv"
        raw_codebook = formal_dir / "raw_codebook.csv"
        expected_header = expected_raw_header(args.db, raw_vars)
        header = read_csv_header(raw_data)
        layered_headers = (
            charls_layered_raw_headers(raw_vars)
            if args.db == "charls"
            else [expected_header]
        )
        if header in layered_headers:
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
        ok(results, "raw_data rows", count_csv_records(raw_data))

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
        rows = read_xlsx_rows(formal_dir / args.analysis_db)
        header = [str(item) if item is not None else "" for item in rows[0]]
        expected_columns = split_csv(args.analysis_columns)
        if expected_columns and header != expected_columns:
            fail(results, "analysis_db columns", {"expected": expected_columns, "actual": header})
        else:
            ok(results, "analysis_db columns", header)
        ok(results, "analysis_db dimensions", {"rows": len(rows) - 1, "cols": len(header)})

        raw_data_path = formal_dir / "raw_data.csv"
        if raw_data_path.exists():
            check_identity_values(
                raw_data_path,
                read_csv_header(raw_data_path),
                rows,
                header,
                results,
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

    if args.check_summary_facts:
        check_summary_facts(
            formal_dir,
            args.analysis_db,
            args.analysis_codebook,
            results,
            args.db,
        )
    if args.complete:
        from check_definition_source_record import load_json
        record = load_json(args.process_dir / "definition_search_record.json")
        if record.get("approved_analysis_vars") != split_csv(args.analysis_vars):
            fail(results, "approved result scope", "analysis vars differ from the settled source plan")
        if str(record.get("database", "")).lower() != args.db:
            fail(results, "approved database", "database differs from the source plan")
    check_required_user_text(formal_dir, required_user_text, results)
    check_criteria_evolution(formal_dir, criteria_evolution_text, results)
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
