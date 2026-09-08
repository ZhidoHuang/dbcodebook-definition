"""Verify author review and artifact identity before website synchronization."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


AUDIT_NAME = "readability_audit.json"
READER_REVIEW_NAME = "reader_comprehension_review.json"
READER_INPUT_NAME = "ordinary_reader_input.md"
REPORT_NAME = "publish_readiness.json"
IMPACT_NAME = "definition_change_impact.json"
READER_COPY_NAME = "文案.md"
SOURCE_RECORD_NAME = "definition_search_record.json"
PASS_STATUS = "FULL_TEXT_READABILITY_PASS"
IMPACT_PASS_STATUS = "CHANGE_IMPACT_PASS"
READER_REVIEW_PASS_STATUS = "READER_COMPREHENSION_PASS"
AUDIT_SCHEMA_VERSION = 5
IMPACT_SCHEMA_VERSION = 2
READER_REVIEW_SCHEMA_VERSION = 2
LEGACY_READER_REVIEW_SCHEMA_VERSION = 1
REQUIRED_ARTIFACTS = (
    "note",
    "public_r",
    "analysis_db",
    "analysis_codebook",
)
REQUIRED_SCOPES = (
    ("title_summary", "标题、摘要导读与全文开场"),
    ("definition_logic", "定义关系、共同背景、问卷变化与逐项判定"),
    ("criteria", "全部变量的 Criteria 与跳题、补零、缺失边界"),
    ("insight_card", "小book提示的实际语义"),
    ("references", "文献逐条支持边界"),
    ("public_r_comments", "公开 R 的大框架、局部说明与零基础读者理解链"),
    (
        "labels_charts",
        "定义表、标签、Easy.label、mapping、codebook、定义卡与图表文字",
    ),
    ("full_note_flow", "按最终顺序从头到尾完整通读"),
)
REQUIRED_IMPACT_SURFACES = (
    ("title_summary", "标题与摘要"),
    ("source_questions", "问卷原题"),
    ("definition_table", "定义表与变量顺序"),
    ("criteria", "全部 Criteria"),
    ("insight_card", "小book提示"),
    ("public_r", "公开 R"),
    ("mapping_codebook", "mapping 与 codebook"),
    ("cards_charts_attachments", "定义卡、图表与附件"),
)


def fail(message: str) -> None:
    raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalized_evidence_text(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value)).casefold()


def normalized_period(value: object) -> str:
    return normalized_evidence_text(value).replace("年", "").replace("期", "")


class QuestionnaireMarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[dict] = []
        self.current_section: dict | None = None
        self.section_depth = 0
        self.current_line: dict | None = None
        self.line_depth = 0
        self.question_id_depth: int | None = None
        self.question_id_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if self.current_section is None:
            if tag == "section" and values.get("data-raw-source-period"):
                self.current_section = {
                    "period": values["data-raw-source-period"],
                    "label": values.get("data-label", ""),
                    "lines": [],
                }
                self.section_depth = 1
            return

        self.section_depth += 1
        if self.current_line is None:
            if values.get("data-summary-questionnaire-line") == "true":
                self.current_line = {
                    "text_parts": [],
                    "question_ids": [],
                    "option_count": 0,
                    "instruction_count": 0,
                }
                self.line_depth = 1
        else:
            self.line_depth += 1

        if self.current_line is None:
            return
        if values.get("data-summary-question-id") == "true":
            self.question_id_depth = self.line_depth
            self.question_id_parts = []
        if values.get("data-summary-question-option") == "true":
            self.current_line["option_count"] += 1
        if values.get("data-summary-question-instruction") == "true":
            self.current_line["instruction_count"] += 1

    def handle_data(self, data: str) -> None:
        if self.current_line is None:
            return
        self.current_line["text_parts"].append(data)
        if self.question_id_depth is not None:
            self.question_id_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current_section is None:
            return
        if self.current_line is not None:
            if self.question_id_depth == self.line_depth:
                question_id = "".join(self.question_id_parts).strip()
                if question_id:
                    self.current_line["question_ids"].append(question_id)
                self.question_id_depth = None
                self.question_id_parts = []
            self.line_depth -= 1
            if self.line_depth == 0:
                self.current_line["text"] = "".join(
                    self.current_line.pop("text_parts")
                ).strip()
                self.current_section["lines"].append(self.current_line)
                self.current_line = None

        self.section_depth -= 1
        if self.section_depth == 0:
            self.sections.append(self.current_section)
            self.current_section = None


def validate_questionnaire_rendering(
    formal_dir: Path,
    process_dir: Path,
    note_relative_path: str,
) -> dict:
    record_path = process_dir / SOURCE_RECORD_NAME
    if not record_path.is_file():
        return {"status": "not_applicable", "reason": "source record not present"}
    record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    if record.get("schema_version", 0) < 6:
        return {"status": "not_applicable", "reason": "legacy source record"}
    evidence = record.get("questionnaire_evidence")
    if not isinstance(evidence, list):
        fail("source record questionnaire_evidence must be a list")

    note_path = (formal_dir / note_relative_path).resolve()
    try:
        note_path.relative_to(formal_dir.resolve())
    except ValueError:
        fail("questionnaire note path leaves the formal directory")
    parser = QuestionnaireMarkupParser()
    parser.feed(note_path.read_text(encoding="utf-8-sig"))
    sections: dict[str, list[dict]] = {}
    for section in parser.sections:
        keys = {
            normalized_period(value)
            for value in (section["period"], section["label"])
            if normalized_period(value)
        }
        for key in keys:
            sections.setdefault(key, []).append(section)

    rendered_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(evidence, start=1):
        field = f"questionnaire_evidence[{index}]"
        if item.get("rendered_in_copy") is not True:
            fail(f"{field} is not marked as rendered in the final copy")
        locator = str(item.get("copy_locator", ""))
        if not locator.strip():
            fail(f"{field}.copy_locator is empty")
        if re.search(
            r"待写入|待补|尚未写入|未写入|\bTODO\b|\bTBD\b|\bpending\b",
            locator,
            re.IGNORECASE,
        ):
            fail(f"{field}.copy_locator still describes unfinished copy")
        question_id = str(item.get("question_id", "")).strip()
        question_text = normalized_evidence_text(item.get("question_text", ""))
        periods = item.get("periods")
        if not question_id or not question_text or not isinstance(periods, list):
            fail(f"{field} lacks question id, question text, or periods")
        expected_options = item.get("options", [])
        expected_jumps = item.get("skip_logic", [])

        for period in periods:
            matches = sections.get(normalized_period(period), [])
            if not matches:
                fail(f"final note has no questionnaire period section for {period}")
            question_lines = [
                line
                for section in matches
                for line in section["lines"]
                if question_id in line["question_ids"]
            ]
            if not question_lines:
                fail(f"final note period {period} does not render question {question_id}")
            matching_lines = [
                line
                for line in question_lines
                if question_text in normalized_evidence_text(line["text"])
            ]
            if not matching_lines:
                fail(f"final note period {period} does not contain the complete text of {question_id}")
            if len(matching_lines) > 1:
                fail(f"final note period {period} renders question {question_id} more than once")
            line = matching_lines[0]
            if item.get("response_type") == "closed_options" and (
                line["option_count"] < len(expected_options)
            ):
                fail(f"final note period {period} omits options for {question_id}")
            if expected_jumps and line["instruction_count"] < 1:
                fail(f"final note period {period} omits jump instructions for {question_id}")
            rendered_pairs.add((question_id, str(period)))

    return {
        "status": "QUESTIONNAIRE_RENDERING_PASS",
        "source_record": {
            "path": SOURCE_RECORD_NAME,
            "sha256": sha256_file(record_path),
        },
        "question_count": len(evidence),
        "rendered_question_periods": len(rendered_pairs),
    }


def relative_artifact(formal_dir: Path, value: str, role: str) -> dict:
    path = Path(value)
    if not path.is_absolute():
        path = formal_dir / path
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(formal_dir.resolve())
    except ValueError:
        fail(f"{role} must be inside the formal topic directory")
    if not resolved.is_file():
        fail(f"{role} does not exist: {resolved}")
    return {
        "path": relative.as_posix(),
        "sha256": sha256_file(resolved),
    }


def initialize_impact(
    process_dir: Path,
    topic_id: str,
    overwrite: bool = False,
) -> dict:
    process_dir = process_dir.resolve()
    process_dir.mkdir(parents=True, exist_ok=True)
    impact_path = process_dir / IMPACT_NAME
    if impact_path.exists() and not overwrite:
        fail(f"{IMPACT_NAME} already exists; use --overwrite for a new change")
    payload = {
        "schema_version": IMPACT_SCHEMA_VERSION,
        "topic_id": topic_id.zfill(3),
        "status": "DRAFT",
        "reviewed_at": "",
        "reviewer": "",
        "change_summary": "",
        "changed_dimensions": [],
        "question_groups": [],
        "question_groups_not_applicable_reason": "",
        "surfaces": [
            {
                "name": name,
                "label": label,
                "result": "pending",
                "evidence": "",
            }
            for name, label in REQUIRED_IMPACT_SURFACES
        ],
        "unresolved_issues": [],
    }
    write_json(impact_path, payload)
    for stale_name in (AUDIT_NAME, REPORT_NAME):
        stale_path = process_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()
    return {
        "ok": True,
        "status": "CHANGE_IMPACT_DRAFT_CREATED",
        "impact": str(impact_path),
    }


def validate_impact(formal_dir: Path, process_dir: Path, topic_id: str) -> dict:
    formal_dir = formal_dir.resolve()
    process_dir = process_dir.resolve()
    impact_path = process_dir / IMPACT_NAME
    if not impact_path.is_file():
        fail(
            f"{IMPACT_NAME} does not exist; initialize and complete the change "
            "impact checklist before formal generation"
        )
    with impact_path.open("r", encoding="utf-8-sig") as handle:
        impact = json.load(handle)
    expected_topic = topic_id.zfill(3)
    if impact.get("schema_version") != IMPACT_SCHEMA_VERSION:
        fail(
            "definition change impact schema_version must be "
            f"{IMPACT_SCHEMA_VERSION}"
        )
    if str(impact.get("topic_id", "")).zfill(3) != expected_topic:
        fail(f"definition change impact topic_id must be {expected_topic}")
    if impact.get("status") != IMPACT_PASS_STATUS:
        fail(f"definition change impact status must be {IMPACT_PASS_STATUS}")
    reviewed_at = validate_iso_datetime(impact.get("reviewed_at"))
    reviewer = nonempty_text(impact.get("reviewer"), "impact reviewer", 3)
    change_summary = nonempty_text(
        impact.get("change_summary"), "change_summary", 20
    )
    dimensions = impact.get("changed_dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        fail("changed_dimensions must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in dimensions):
        fail("every changed_dimensions item must be non-empty text")

    copy_path = formal_dir / READER_COPY_NAME
    if not copy_path.is_file():
        fail(f"{READER_COPY_NAME} does not exist in the formal topic directory")
    copy_text = copy_path.read_text(encoding="utf-8-sig")
    for heading in (
        "## 摘要导读",
        "## Criteria",
        "## 小book提示",
        "## 参考资料说明",
    ):
        if heading not in copy_text:
            fail(f"reader copy is missing required heading: {heading}")

    groups = impact.get("question_groups")
    if not isinstance(groups, list):
        fail("question_groups must be a list")
    if not groups:
        nonempty_text(
            impact.get("question_groups_not_applicable_reason"),
            "question_groups_not_applicable_reason",
            20,
        )
    seen_groups: set[tuple[str, tuple[str, ...]]] = set()
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            fail(f"question group {index} must be an object")
        name = nonempty_text(group.get("name"), f"question group {index} name", 2)
        periods = group.get("periods")
        if not isinstance(periods, list) or not periods:
            fail(f"question group {index} periods must be a non-empty list")
        normalized_periods = tuple(str(item).strip() for item in periods)
        if any(not item for item in normalized_periods):
            fail(f"question group {index} periods contain empty values")
        key = (name, normalized_periods)
        if key in seen_groups:
            fail(f"duplicate question group: {name} / {normalized_periods}")
        seen_groups.add(key)
        nonempty_text(group.get("respondent"), f"question group {index} respondent", 2)
        nonempty_text(
            group.get("official_source"), f"question group {index} official_source", 8
        )
        nonempty_text(
            group.get("definition_use"), f"question group {index} definition_use", 8
        )
        nonempty_text(
            group.get("draft_location"), f"question group {index} draft_location", 4
        )
        mode = group.get("question_mode")
        if mode not in ("verified_quote", "plain_paraphrase"):
            fail(
                f"question group {index} question_mode must be verified_quote "
                "or plain_paraphrase"
            )
        question_text = nonempty_text(
            group.get("question_text"), f"question group {index} question_text", 8
        )
        if question_text not in copy_text:
            fail(
                f"question group {index} text is not present in {READER_COPY_NAME}: "
                f"{name}"
            )
        if mode == "plain_paraphrase":
            nonempty_text(
                group.get("paraphrase_reason"),
                f"question group {index} paraphrase_reason",
                12,
            )
        if group.get("result") != "pass":
            fail(f"question group {index} result must be pass")

    surfaces = impact.get("surfaces")
    if not isinstance(surfaces, list):
        fail("impact surfaces must be a list")
    surface_names = [item.get("name") for item in surfaces if isinstance(item, dict)]
    required_names = [name for name, _ in REQUIRED_IMPACT_SURFACES]
    if len(surface_names) != len(set(surface_names)) or set(surface_names) != set(
        required_names
    ):
        fail("impact surfaces do not match the required change surfaces")
    for item in surfaces:
        name = item["name"]
        if item.get("result") != "pass":
            fail(f"impact surface {name} result must be pass")
        nonempty_text(item.get("evidence"), f"impact surface {name} evidence", 20)
    unresolved = impact.get("unresolved_issues")
    if not isinstance(unresolved, list):
        fail("impact unresolved_issues must be a list")
    if unresolved:
        fail("impact unresolved_issues must be empty before formal generation")
    return {
        "path": IMPACT_NAME,
        "sha256": sha256_file(impact_path),
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        "change_summary": change_summary,
        "changed_dimensions": [item.strip() for item in dimensions],
        "question_group_count": len(groups),
        "reader_copy": {
            "path": READER_COPY_NAME,
            "sha256": sha256_file(copy_path),
        },
    }


def normalized_visible_text(text: str) -> str:
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def first_complete_sentence(text: str) -> str:
    visible = normalized_visible_text(text)
    match = re.match(r".*?[。！？]", visible)
    return match.group(0).strip() if match else visible


def flow_review_text(blocks: list[dict[str, str]]) -> str:
    """Keep one complete ordered anchor per block without duplicating the note."""
    anchors = []
    for block in blocks:
        sentence = first_complete_sentence(block["review_text"])
        if sentence:
            anchors.append(sentence)
    return "\n".join(anchors)


def reader_review_block_sources(
    note_text: str,
    *,
    include_materials: bool = False,
) -> list[dict[str, str]]:
    summary_match = re.search(r"(?m)^##\s+摘要导读\s*$", note_text)
    summary_start = summary_match.end() if summary_match else 0
    summary_end_candidates = [
        position
        for marker in (
            '<div class="raw-source-structure"',
            '<!-- summary-insight-card:start -->',
            '<div class="raw-source-link"',
            "## 定义",
        )
        if (position := note_text.find(marker, summary_start + 1)) >= 0
    ]
    summary_end = min(summary_end_candidates) if summary_end_candidates else len(note_text)
    blocks = [
        {
            "name": "summary_opening",
            "label": "摘要导读首段",
            "review_text": note_text[summary_start:summary_end],
        }
    ]
    period_matches = list(re.finditer(
        r'(?s)<section\s+class="raw-source-period"[^>]*data-label="([^"]+)"[^>]*>(.*?)</section>',
        note_text,
    ))
    seen: set[str] = set()
    for match in period_matches:
        clean_label = html.unescape(match.group(1)).strip()
        if clean_label and clean_label not in seen:
            blocks.append(
                {
                    "name": f"period:{clean_label}",
                    "label": f"时期：{clean_label}",
                    "review_text": match.group(2),
                }
            )
            seen.add(clean_label)
    if not period_matches and 'data-raw-source-structure="true"' in note_text:
        source_match = re.search(
            r'(?s)<div\s+class="raw-source-structure".*?</div>', note_text
        )
        blocks.append({
            "name": "source_structure",
            "label": "原始问卷与来源说明",
            "review_text": source_match.group(0) if source_match else note_text,
        })
    if 'data-summary-insight-card="true"' in note_text:
        insight_match = re.search(
            r'(?s)<!-- summary-insight-card:start -->(.*?)<!-- summary-insight-card:end -->',
            note_text,
        )
        blocks.append({
            "name": "insight_card",
            "label": "小book提示",
            "review_text": insight_match.group(1) if insight_match else note_text,
        })
    if 'class="raw-source-link"' in note_text:
        source_entry_match = re.search(
            r'(?s)<div\s+class="raw-source-link".*?</div>', note_text
        )
        blocks.append({
            "name": "source_entry",
            "label": "dbCodeBook 来源入口",
            "review_text": source_entry_match.group(0) if source_entry_match else note_text,
        })
    definition_matches = list(re.finditer(
        r'<td\s+class="plain-cell">\s*([^<]+?)\s*</td>', note_text
    ))
    for index, match in enumerate(definition_matches):
        clean_variable = html.unescape(match.group(1)).strip()
        if clean_variable and clean_variable not in seen:
            end_candidates = [
                position
                for position in (
                    definition_matches[index + 1].start()
                    if index + 1 < len(definition_matches)
                    else -1,
                    note_text.find("## 参考资料说明", match.end()),
                    note_text.find("## 定义的组分概览", match.end()),
                    note_text.find("## 材料", match.end()),
                )
                if position >= 0
            ]
            end = min(end_candidates) if end_candidates else len(note_text)
            blocks.append(
                {
                    "name": f"definition:{clean_variable}",
                    "label": f"定义变量：{clean_variable}",
                    "review_text": note_text[match.start():end],
                }
            )
            seen.add(clean_variable)
    reader_blocks = list(blocks)
    if include_materials:
        reader_end = len(note_text)
        materials_start = note_text.find("## 材料")
        if materials_start >= 0:
            reader_blocks.append({
                "name": "materials",
                "label": "材料",
                "review_text": note_text[materials_start:reader_end],
            })
    blocks.append({
        "name": "full_note_flow",
        "label": "全文衔接",
        "review_text": flow_review_text(reader_blocks),
    })
    return blocks


def reader_review_blocks(
    note_text: str,
    *,
    include_materials: bool = False,
) -> list[dict[str, str]]:
    return [
        {"name": block["name"], "label": block["label"]}
        for block in reader_review_block_sources(
            note_text,
            include_materials=include_materials,
        )
    ]


def build_reader_input(topic_id: str, note_text: str) -> str:
    blocks = reader_review_block_sources(note_text)
    lines = [
        f"# {topic_id.zfill(3)} 普通读者审阅输入",
        "",
        "请只根据下面依次列出的读者可见内容判断是否容易理解。",
        "不要推测数据、代码、探索记录或作者没有写出的信息。",
    ]
    for block in blocks:
        if block["name"] == "full_note_flow":
            flow_sources = blocks[:-1]
            flow_sentences = [
                line for line in block["review_text"].splitlines() if line.strip()
            ]
            lines.extend([
                "",
                "## 全文衔接",
                "",
                "请结合前面已经按正式顺序列出的全部内容，检查相邻部分是否衔接清楚。",
                "下面只重复每块开头的顺序锚点，不再复制整篇笔记。",
                "",
                *[
                    f"- {source['label']}: {sentence}"
                    for source, sentence in zip(flow_sources, flow_sentences)
                ],
            ])
            continue
        lines.extend([
            "",
            f"## {block['label']}",
            "",
            normalized_visible_text(block["review_text"]),
        ])
    return "\n".join(lines).rstrip() + "\n"


def initialize_reader_review(
    formal_dir: Path,
    process_dir: Path,
    topic_id: str,
    note: str,
    overwrite: bool = False,
) -> dict:
    formal_dir = formal_dir.resolve()
    process_dir = process_dir.resolve()
    process_dir.mkdir(parents=True, exist_ok=True)
    audit_path = process_dir / AUDIT_NAME
    if not audit_path.is_file():
        fail(f"{AUDIT_NAME} does not exist; the author review must be completed first")
    with audit_path.open("r", encoding="utf-8-sig") as handle:
        audit = json.load(handle)
    if audit.get("schema_version") != AUDIT_SCHEMA_VERSION:
        fail(
            f"author review schema_version must be {AUDIT_SCHEMA_VERSION}; "
            "initialize a new author review first"
        )
    if audit.get("status") != PASS_STATUS:
        fail(f"author review status must be {PASS_STATUS} before reader review")

    note_artifact = relative_artifact(formal_dir, note, "note")
    audited_note = audit.get("artifacts", {}).get("note", {})
    if audited_note != note_artifact:
        fail("author review and reader review must bind the same final note")

    review_path = process_dir / READER_REVIEW_NAME
    if review_path.exists() and not overwrite:
        fail(f"{READER_REVIEW_NAME} already exists; use --overwrite for a new review")
    note_path = formal_dir / note_artifact["path"]
    note_text = note_path.read_text(encoding="utf-8-sig")
    reader_input_path = process_dir / READER_INPUT_NAME
    reader_input_path.write_text(
        build_reader_input(topic_id, note_text),
        encoding="utf-8",
    )
    payload = {
        "schema_version": READER_REVIEW_SCHEMA_VERSION,
        "topic_id": topic_id.zfill(3),
        "status": "DRAFT",
        "reviewed_at": "",
        "reviewer": "",
        "reader_only_confirmation": "",
        "note": note_artifact,
        "blocks": [
            {
                "name": block["name"],
                "label": block["label"],
                "source_text": normalized_visible_text(block["review_text"]),
                "result": "pending",
                "original_excerpt": normalized_visible_text(block["review_text"])[:160],
                "plain_paraphrase": "",
                "who_when_what": "",
                "possible_confusion": "",
                "resolution": "",
            }
            for block in reader_review_block_sources(note_text)
        ],
        "unresolved_issues": [],
    }
    write_json(review_path, payload)
    readiness_path = process_dir / REPORT_NAME
    if readiness_path.exists():
        readiness_path.unlink()
    return {
        "ok": True,
        "status": "READER_REVIEW_DRAFT_CREATED",
        "review": str(review_path),
        "review_input": str(reader_input_path),
        "allowed_inputs": [str(reader_input_path)],
        "reviewer_prompt": (
            f"只读取 {reader_input_path}，逐块用自己的话复述并报告疑问；"
            "不要读取正式目录、公开R、数据、探索记录或作者审阅。"
        ),
        "block_count": len(payload["blocks"]),
    }


def validate_reader_review(
    formal_dir: Path,
    process_dir: Path,
    topic_id: str,
    note_artifact: dict,
    author_reviewer: str,
) -> dict:
    review_path = process_dir / READER_REVIEW_NAME
    if not review_path.is_file():
        fail(f"{READER_REVIEW_NAME} does not exist; ordinary-reader review is required")
    with review_path.open("r", encoding="utf-8-sig") as handle:
        review = json.load(handle)
    reader_schema = review.get("schema_version")
    if reader_schema not in {
        LEGACY_READER_REVIEW_SCHEMA_VERSION,
        READER_REVIEW_SCHEMA_VERSION,
    }:
        fail(
            "reader review schema_version must be "
            f"{LEGACY_READER_REVIEW_SCHEMA_VERSION} or {READER_REVIEW_SCHEMA_VERSION}"
        )
    expected_topic = topic_id.zfill(3)
    if str(review.get("topic_id", "")).zfill(3) != expected_topic:
        fail(f"reader review topic_id must be {expected_topic}")
    if review.get("status") != READER_REVIEW_PASS_STATUS:
        fail(f"reader review status must be {READER_REVIEW_PASS_STATUS}")
    reviewed_at = validate_iso_datetime(review.get("reviewed_at"))
    reviewer = nonempty_text(review.get("reviewer"), "reader reviewer", 3)
    if reviewer.casefold() == author_reviewer.casefold():
        fail("ordinary-reader reviewer must differ from the author reviewer")
    confirmation = nonempty_text(
        review.get("reader_only_confirmation"),
        "reader_only_confirmation",
        30,
    )
    if review.get("note") != note_artifact:
        fail("reader review is stale because the final note changed")

    note_path = formal_dir / note_artifact["path"]
    note_text = note_path.read_text(encoding="utf-8-sig")
    visible_note = normalized_visible_text(note_text)
    block_sources = reader_review_block_sources(
        note_text,
        include_materials=(reader_schema == LEGACY_READER_REVIEW_SCHEMA_VERSION),
    )
    expected_blocks = [
        {"name": block["name"], "label": block["label"]}
        for block in block_sources
    ]
    source_by_name = {
        block["name"]: normalized_visible_text(block["review_text"])
        for block in block_sources
    }
    expected_names = [item["name"] for item in expected_blocks]
    blocks = review.get("blocks")
    if not isinstance(blocks, list):
        fail("reader review blocks must be a list")
    names = [item.get("name") for item in blocks if isinstance(item, dict)]
    if names != expected_names:
        fail(
            "reader review blocks must match the final visible note in order; "
            f"expected={expected_names}, actual={names}"
        )
    for block in blocks:
        name = block["name"]
        if block.get("result") != "pass":
            fail(f"reader review block {name} result must be pass")
        excerpt = nonempty_text(
            block.get("original_excerpt"), f"{name}.original_excerpt", 8
        )
        normalized_excerpt = normalized_visible_text(excerpt)
        if normalized_excerpt not in visible_note:
            fail(f"reader review block {name} excerpt is not in the final note")
        if normalized_excerpt not in source_by_name[name]:
            fail(f"reader review block {name} excerpt comes from a different block")
        paraphrase = nonempty_text(
            block.get("plain_paraphrase"), f"{name}.plain_paraphrase", 20
        )
        if normalized_visible_text(paraphrase) == normalized_visible_text(excerpt):
            fail(f"reader review block {name} paraphrase cannot copy the excerpt")
        nonempty_text(block.get("who_when_what"), f"{name}.who_when_what", 16)
        nonempty_text(
            block.get("possible_confusion"), f"{name}.possible_confusion", 12
        )
        nonempty_text(block.get("resolution"), f"{name}.resolution", 12)
    unresolved = review.get("unresolved_issues")
    if not isinstance(unresolved, list):
        fail("reader review unresolved_issues must be a list")
    if unresolved:
        fail("reader review unresolved_issues must be empty before publication")
    return {
        "path": READER_REVIEW_NAME,
        "sha256": sha256_file(review_path),
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        "confirmation": confirmation,
        "block_count": len(blocks),
    }


def initialize_audit(
    formal_dir: Path,
    process_dir: Path,
    topic_id: str,
    artifact_paths: dict[str, str],
    overwrite: bool = False,
    preserve_reader: bool = False,
) -> dict:
    formal_dir = formal_dir.resolve()
    process_dir = process_dir.resolve()
    if not formal_dir.is_dir():
        fail(f"formal directory does not exist: {formal_dir}")
    process_dir.mkdir(parents=True, exist_ok=True)
    audit_path = process_dir / AUDIT_NAME
    if audit_path.exists() and not overwrite:
        fail(f"{AUDIT_NAME} already exists; use --overwrite after a new regeneration")

    change_impact = validate_impact(formal_dir, process_dir, topic_id)

    artifacts = {
        role: relative_artifact(formal_dir, artifact_paths[role], role)
        for role in REQUIRED_ARTIFACTS
    }
    questionnaire_rendering = validate_questionnaire_rendering(
        formal_dir,
        process_dir,
        artifacts["note"]["path"],
    )
    if preserve_reader:
        if not audit_path.is_file():
            fail("preserving a reader review requires an existing author audit")
        previous = json.loads(audit_path.read_text(encoding="utf-8-sig"))
        if previous.get("status") != PASS_STATUS:
            fail("preserving a reader review requires a passed author audit")
        validate_reader_review(
            formal_dir, process_dir, topic_id, artifacts["note"],
            previous.get("reviewer", ""),
        )
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "topic_id": topic_id.zfill(3),
        "status": "DRAFT",
        "audited_at": "",
        "reviewer": "",
        "full_read_confirmation": "",
        "artifacts": artifacts,
        "change_impact": {
            "path": change_impact["path"],
            "sha256": change_impact["sha256"],
        },
        "reader_copy": change_impact["reader_copy"],
        "questionnaire_rendering": questionnaire_rendering,
        "scopes": [
            {
                "name": name,
                "label": label,
                "result": "pending",
                "evidence": "",
                "findings": [],
                **({"code_walkthrough": []} if name == "public_r_comments" else {}),
            }
            for name, label in REQUIRED_SCOPES
        ],
        "unresolved_issues": [],
    }
    write_json(audit_path, payload)
    reader_review_path = process_dir / READER_REVIEW_NAME
    if reader_review_path.exists() and not preserve_reader:
        reader_review_path.unlink()
    reader_input_path = process_dir / READER_INPUT_NAME
    if reader_input_path.exists() and not preserve_reader:
        reader_input_path.unlink()
    readiness_path = process_dir / REPORT_NAME
    if readiness_path.exists():
        readiness_path.unlink()
    return {
        "ok": True,
        "status": "DRAFT_CREATED",
        "audit": str(audit_path),
        "artifacts": artifacts,
        "change_impact": change_impact,
        "questionnaire_rendering": questionnaire_rendering,
        "reader_review_preserved": preserve_reader,
    }


def nonempty_text(value: object, field: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        fail(f"{field} must contain at least {minimum} characters")
    return value.strip()


def validate_iso_datetime(value: object) -> str:
    text = nonempty_text(value, "audited_at")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        fail(f"audited_at must be ISO 8601: {error}")
    return text


def validate_audit(
    formal_dir: Path,
    process_dir: Path,
    topic_id: str,
    report_path: Path | None = None,
    write_report: bool = True,
) -> dict:
    formal_dir = formal_dir.resolve()
    process_dir = process_dir.resolve()
    audit_path = process_dir / AUDIT_NAME
    with audit_path.open("r", encoding="utf-8-sig") as handle:
        audit = json.load(handle)

    expected_topic = topic_id.zfill(3)
    if audit.get("schema_version") != AUDIT_SCHEMA_VERSION:
        fail(
            f"readability audit schema_version must be {AUDIT_SCHEMA_VERSION}; "
            "initialize a new audit for the current workflow"
        )
    if str(audit.get("topic_id", "")).zfill(3) != expected_topic:
        fail(f"readability audit topic_id must be {expected_topic}")
    if audit.get("status") != PASS_STATUS:
        fail(f"readability audit status must be {PASS_STATUS}")
    audited_at = validate_iso_datetime(audit.get("audited_at"))
    reviewer = nonempty_text(audit.get("reviewer"), "reviewer", 3)
    confirmation = nonempty_text(
        audit.get("full_read_confirmation"), "full_read_confirmation", 20
    )

    current_impact = validate_impact(formal_dir, process_dir, expected_topic)
    recorded_impact = audit.get("change_impact")
    if not isinstance(recorded_impact, dict):
        fail("readability audit change_impact is missing")
    if recorded_impact.get("path") != current_impact["path"]:
        fail("readability audit change_impact path differs from the current checklist")
    if str(recorded_impact.get("sha256", "")).upper() != current_impact["sha256"]:
        fail(
            "readability audit is stale because definition_change_impact.json changed"
        )
    recorded_copy = audit.get("reader_copy")
    if not isinstance(recorded_copy, dict):
        fail("readability audit reader_copy is missing")
    if recorded_copy.get("path") != current_impact["reader_copy"]["path"]:
        fail("readability audit reader_copy path differs from the current copy")
    if str(recorded_copy.get("sha256", "")).upper() != current_impact[
        "reader_copy"
    ]["sha256"]:
        fail(
            f"readability audit is stale because {READER_COPY_NAME} changed"
        )

    artifacts = audit.get("artifacts")
    if not isinstance(artifacts, dict):
        fail("artifacts must be an object")
    current_hashes: dict[str, dict] = {}
    for role in REQUIRED_ARTIFACTS:
        item = artifacts.get(role)
        if not isinstance(item, dict):
            fail(f"artifacts.{role} is missing")
        relative = nonempty_text(item.get("path"), f"artifacts.{role}.path")
        expected_hash = nonempty_text(
            item.get("sha256"), f"artifacts.{role}.sha256", 64
        ).upper()
        path = (formal_dir / relative).resolve()
        try:
            path.relative_to(formal_dir)
        except ValueError:
            fail(f"artifacts.{role}.path leaves the formal directory")
        if not path.is_file():
            fail(f"audited artifact is missing: {path}")
        current_hash = sha256_file(path)
        if current_hash != expected_hash:
            fail(
                f"readability audit is stale because {role} changed; "
                "create a new DRAFT audit and read the final version again"
            )
        current_hashes[role] = {"path": relative, "sha256": current_hash}

    questionnaire_rendering = validate_questionnaire_rendering(
        formal_dir,
        process_dir,
        current_hashes["note"]["path"],
    )
    if audit.get("questionnaire_rendering") != questionnaire_rendering:
        fail(
            "readability audit is stale because questionnaire evidence or its "
            "final rendering changed"
        )

    scopes = audit.get("scopes")
    if not isinstance(scopes, list):
        fail("scopes must be a list")
    scope_names = [item.get("name") for item in scopes if isinstance(item, dict)]
    required_names = [name for name, _ in REQUIRED_SCOPES]
    if len(scope_names) != len(set(scope_names)):
        fail("scopes contain duplicate names")
    if set(scope_names) != set(required_names):
        missing = sorted(set(required_names) - set(scope_names))
        unexpected = sorted(set(scope_names) - set(required_names))
        fail(f"readability scopes mismatch; missing={missing}, unexpected={unexpected}")

    finding_count = 0
    for item in scopes:
        if not isinstance(item, dict):
            fail("every readability scope must be an object")
        name = item["name"]
        if item.get("result") != "pass":
            fail(f"scope {name} result must be pass")
        nonempty_text(item.get("evidence"), f"scope {name} evidence", 20)
        findings = item.get("findings")
        if not isinstance(findings, list):
            fail(f"scope {name} findings must be a list")
        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                fail(f"scope {name} finding {index} must be an object")
            nonempty_text(finding.get("location"), f"{name} finding {index} location")
            nonempty_text(finding.get("problem"), f"{name} finding {index} problem")
            nonempty_text(
                finding.get("resolution"), f"{name} finding {index} resolution"
            )
            finding_count += 1

        if (
            name == "public_r_comments"
            and "public_r" in current_impact["changed_dimensions"]
        ):
            walkthrough = item.get("code_walkthrough")
            if not isinstance(walkthrough, list) or not walkthrough:
                fail(
                    "public R code walkthrough is required when public_r changed; "
                    "comments-only review cannot pass"
                )
            for index, block in enumerate(walkthrough, start=1):
                if not isinstance(block, dict):
                    fail(f"public R code walkthrough block {index} must be an object")
                for field in (
                    "location",
                    "input",
                    "action",
                    "output",
                    "plain_paraphrase",
                ):
                    nonempty_text(
                        block.get(field),
                        f"public R code walkthrough block {index} {field}",
                        5,
                    )
                if block.get("result") != "pass":
                    fail(
                        f"public R code walkthrough block {index} result must be pass"
                    )

    unresolved = audit.get("unresolved_issues")
    if not isinstance(unresolved, list):
        fail("unresolved_issues must be a list")
    if unresolved:
        fail("unresolved_issues must be empty before publication")

    reader_review = validate_reader_review(
        formal_dir,
        process_dir,
        expected_topic,
        current_hashes["note"],
        reviewer,
    )

    result = {
        "ok": True,
        "status": "PUBLISH_READY",
        "topic_id": expected_topic,
        "audited_at": audited_at,
        "reviewer": reviewer,
        "full_read_confirmation": confirmation,
        "scope_count": len(scopes),
        "finding_count": finding_count,
        "audit": str(audit_path),
        "audit_sha256": sha256_file(audit_path),
        "artifacts": current_hashes,
        "change_impact": current_impact,
        "questionnaire_rendering": questionnaire_rendering,
        "reader_review": reader_review,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if write_report:
        if report_path is None:
            report_path = process_dir / REPORT_NAME
        else:
            report_path = report_path.resolve()
        write_json(report_path, result)
        result["report"] = str(report_path)
    return result


def verify_existing_readiness(
    formal_dir: Path,
    process_dir: Path,
    topic_id: str,
) -> dict:
    process_dir = process_dir.resolve()
    report_path = process_dir / REPORT_NAME
    if not report_path.is_file():
        fail(
            f"{REPORT_NAME} does not exist; publication cannot begin without a "
            "current PUBLISH_READY report"
        )
    with report_path.open("r", encoding="utf-8-sig") as handle:
        recorded = json.load(handle)
    current = validate_audit(
        formal_dir,
        process_dir,
        topic_id,
        write_report=False,
    )
    if recorded.get("status") != "PUBLISH_READY":
        fail("publish readiness status must be PUBLISH_READY")
    comparisons = (
        ("topic_id", recorded.get("topic_id"), current.get("topic_id")),
        ("audit_sha256", recorded.get("audit_sha256"), current.get("audit_sha256")),
        ("artifacts", recorded.get("artifacts"), current.get("artifacts")),
        (
            "change_impact",
            recorded.get("change_impact"),
            current.get("change_impact"),
        ),
        (
            "reader_review",
            recorded.get("reader_review"),
            current.get("reader_review"),
        ),
        (
            "questionnaire_rendering",
            recorded.get("questionnaire_rendering"),
            current.get("questionnaire_rendering"),
        ),
    )
    for label, old_value, current_value in comparisons:
        if old_value != current_value:
            fail(
                f"{REPORT_NAME} is stale because {label} differs from the "
                "current reviewed version"
            )
    note_path = (formal_dir / current["artifacts"]["note"]["path"]).resolve()
    note_text = note_path.read_text(encoding="utf-8-sig")
    upload = {
        "note": str(note_path),
        "body_check": {
            "newline": "LF",
            "length_utf16": len(note_text.encode("utf-16-le")) // 2,
            "head": note_text[:160],
            "tail": note_text[-150:],
        },
        "attachments": [
            {"role": role, "path": str((formal_dir / current["artifacts"][role]["path"]).resolve())}
            for role in ("analysis_db", "analysis_codebook")
        ],
        "attachment_location": "侧栏文档",
    }
    return {
        "ok": True,
        "status": "PUBLISH_READY_VERIFIED",
        "topic_id": current["topic_id"],
        "report": str(report_path),
        "report_sha256": sha256_file(report_path),
        "artifacts": current["artifacts"],
        "change_impact": current["change_impact"],
        "questionnaire_rendering": current["questionnaire_rendering"],
        "reader_review": current["reader_review"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "upload": upload,
    }


def build_cua_sync_action(
    upload: dict,
    base_url: str,
    post_id: str,
    database: str,
    topic_id: str,
    topic_name: str,
    website_title: str | None = None,
    sync_started_at: str | None = None,
    include_preload: bool = True,
    create: bool = False,
    directory_tag: str | None = None,
    sync_run_id: str | None = None,
    sync_attempt: int | None = None,
) -> dict:
    base_url = base_url.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        fail("--base-url must be an absolute http or https URL")
    post_id = (post_id or "").strip()
    if create and post_id:
        fail("--create cannot be combined with --post-id")
    if create and not (website_title and directory_tag and directory_tag.strip()):
        fail("--create requires --website-title and --directory-tag")
    if not create and not re.fullmatch(r"[1-9][0-9]*", post_id):
        fail("--post-id must be a positive integer")

    attachments = [
        {"role": item["role"], "path": item["path"], "name": Path(item["path"]).name}
        for item in upload["attachments"]
    ]
    expected_title_parts = [topic_id.zfill(3), database, topic_name]
    website_title = website_title.strip() if website_title else None
    if website_title:
        folded_title = website_title.casefold()
        missing_parts = [
            part for part in expected_title_parts if part.casefold() not in folded_title
        ]
        if missing_parts:
            fail(
                "--website-title must contain the topic id, database and topic name; "
                f"missing: {', '.join(missing_parts)}"
            )
    payload = {
        "create": create,
        "database": database,
        "directory_tag": directory_tag.strip() if directory_tag else None,
        "post_id": post_id,
        "post_url": None if create else f"{base_url}/nodes/post/{post_id}/",
        "post_url_prefix": f"{base_url}/nodes/post/",
        "edit_url": f"{base_url}/nodes/edit/" if create else f"{base_url}/nodes/edit/{post_id}/",
        "success_url_pattern": "**/nodes/post/*/" if create else f"**/nodes/post/{post_id}/**",
        "identity_title_parts": (
            [topic_id.zfill(3), database] if website_title else expected_title_parts
        ),
        "expected_title_parts": expected_title_parts,
        "desired_title": website_title,
        "note": upload["note"],
        "body_check": upload["body_check"],
        "attachments": attachments,
        "sync_started_at": sync_started_at,
        "sync_run_id": sync_run_id,
        "sync_attempt": sync_attempt,
        "dispatch_limit_ms": 60000,
    }
    existing_tab_match = [url for url in (payload["post_url"], payload["edit_url"]) if url]
    existing_tab_match_json = json.dumps(existing_tab_match, ensure_ascii=False)
    helper_script = rf'''async function resolveDbCodeBookTab(expectedUrls) {{
  const browsers = (await agent.browsers.list()).filter(item => item.type === "iab");
  if (browsers.length !== 1) {{
    throw new Error(`需要且只能有一个 Codex 内置浏览器，当前找到 ${{browsers.length}} 个`);
  }}
  const browser = await agent.browsers.get(browsers[0].id);
  const normalize = value => {{
    const url = new URL(value);
    url.hash = "";
    return url.href.replace(/\/$/, "");
  }};
  const expected = new Set(expectedUrls.map(normalize));
  const selected = await browser.tabs.selected();
  if (expected.has(normalize(await selected.url()))) return selected;
  const tabs = await browser.tabs.list();
  const matches = tabs.filter(item => expected.has(normalize(item.url)));
  if (matches.length !== 1) {{
    throw new Error(`未找到唯一匹配的网站标签页，当前找到 ${{matches.length}} 个`);
  }}
  return browser.tabs.get(matches[0].id);
}}
async function chooseVisibleFile(tab, selector, filePath) {{
  const chooserPromise = tab.playwright.waitForEvent("filechooser");
  await tab.playwright.locator(selector).click();
  const chooser = await chooserPromise;
  await chooser.setFiles([filePath]);
}}
async function syncDbCodeBookPost(tab, payload) {{
  const startedAt = Date.now();
  const syncStartedAt = payload.sync_started_at
    ? Date.parse(payload.sync_started_at)
    : null;
  if (payload.sync_started_at && Number.isNaN(syncStartedAt)) {{
    throw new Error("网站同步开始时间无效；未操作网站");
  }}
  const dispatchLatencyMs = syncStartedAt === null
    ? null
    : startedAt - syncStartedAt;
  if (dispatchLatencyMs !== null &&
      dispatchLatencyMs > payload.dispatch_limit_ms) {{
    throw new Error(
      `网站同步启动后 ${{dispatchLatencyMs}} 毫秒仍未执行固定程序；未操作网站`
    );
  }}
  const timings = {{}};
  let submissionStarted = false;
  try {{
    let stepStarted = Date.now();
    if (await tab.url() !== payload.edit_url) await tab.goto(payload.edit_url);
    await tab.playwright.waitForLoadState({{ state: "domcontentloaded" }});
    const currentUrl = await tab.playwright.evaluate(() => location.href);
    if (currentUrl !== payload.edit_url) {{
      throw new Error(`未进入指定编辑页：${{currentUrl}}`);
    }}
    timings.open_edit_ms = Date.now() - stepStarted;

    stepStarted = Date.now();
    const title = tab.playwright.locator("#title");
    await title.waitFor({{ state: "visible" }});
    let titleValue = "";
    const titleDeadline = Date.now() + 5000;
    while (!payload.create && Date.now() < titleDeadline) {{
      titleValue = await title.evaluate(el => el.value);
      if (payload.identity_title_parts.every(
        part => titleValue.toLocaleLowerCase().includes(String(part).toLocaleLowerCase())
      )) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }}
    if (payload.create) {{
      const blank = await tab.playwright.evaluate(() => ({{
        title: document.querySelector("#title").value,
        body: document.querySelector("#editor").value,
        attachments: document.querySelector("#documents-sidebar-list").innerText.trim()
      }}));
      if (blank.title || blank.body || blank.attachments) {{
        throw new Error("新建表单不是空白；未覆盖现有草稿");
      }}
    }}
    for (const part of payload.create ? [] : payload.identity_title_parts) {{
      if (!titleValue.toLocaleLowerCase().includes(String(part).toLocaleLowerCase())) {{
        throw new Error(`文章身份不符，标题缺少：${{part}}`);
      }}
    }}
    timings.identity_check_ms = Date.now() - stepStarted;

    stepStarted = Date.now();
    if (payload.desired_title && titleValue !== payload.desired_title) {{
      await title.fill(payload.desired_title);
      titleValue = await title.evaluate(el => el.value);
      if (titleValue !== payload.desired_title) {{
        throw new Error("文章标题未更新为指定值");
      }}
    }}
    for (const part of payload.expected_title_parts) {{
      if (!titleValue.toLocaleLowerCase().includes(String(part).toLocaleLowerCase())) {{
        throw new Error(`最终标题缺少：${{part}}`);
      }}
    }}
    timings.title_update_ms = Date.now() - stepStarted;
    if (payload.create) {{
      const categoryOptions = await tab.playwright.evaluate(() =>
        Array.from(document.querySelector("#category").options, option => ({{
          label: option.textContent.trim(), value: option.value
        }}))
      );
      const matchingCategories = categoryOptions.filter(option =>
        option.label.toLocaleLowerCase() === payload.database.trim().toLocaleLowerCase()
      );
      if (matchingCategories.length !== 1) throw new Error("未找到唯一匹配的数据库选项");
      await tab.playwright.locator("#category").selectOption({{ value: matchingCategories[0].value }});
      await tab.playwright.locator("#tags-input").fill(payload.directory_tag);
      await tab.playwright.locator("#tags-input").press("Enter");
      const metadata = await tab.playwright.evaluate(() => ({{
        database: document.querySelector("#category").selectedOptions[0].textContent.trim(),
        tags: document.querySelector("#tags-container").innerText
      }}));
      if (metadata.database.toLocaleLowerCase() !== payload.database.trim().toLocaleLowerCase() ||
          !metadata.tags.includes(payload.directory_tag)) {{
        throw new Error("数据库或目录标签未设置成功");
      }}
    }}

    stepStarted = Date.now();
    const editor = tab.playwright.locator("#editor");
    if (!payload.create) await tab.playwright.getByRole("button", {{ name: "清空内容" }}).click();
    const emptyLength = await editor.evaluate(el => el.value.length);
    if (emptyLength !== 0) throw new Error("清空正文后编辑器仍非空");
    await chooseVisibleFile(tab, "#content-import-input", payload.note);

    const body = await editor.evaluate(el => ({{
      length: el.value.length,
      head: el.value.slice(0, 160),
      tail: el.value.slice(-150)
    }}));
    if (body.length !== payload.body_check.length_utf16 ||
        body.head !== payload.body_check.head ||
        body.tail !== payload.body_check.tail) {{
      throw new Error("导入正文与发布入口核对值不一致");
    }}
    timings.body_import_ms = Date.now() - stepStarted;

    stepStarted = Date.now();
    const sidebar = tab.playwright.locator("#documents-sidebar-list");
    let deleteButtons = sidebar.locator('button[title="删除"]');
    while (await deleteButtons.count()) {{
      await deleteButtons.last().click();
      deleteButtons = sidebar.locator('button[title="删除"]');
    }}
    for (const attachment of payload.attachments) {{
      await chooseVisibleFile(tab, "#documents-sidebar-input", attachment.path);
    }}
    const sidebarText = await sidebar.innerText();
    const actualNames = sidebarText.split(/\r?\n/)
      .map(line => line.trim())
      .filter(line => /\.(xlsx|xls|csv|docx?|txt|pdf)$/i.test(line));
    const expectedNames = payload.attachments.map(item => item.name);
    if (JSON.stringify(actualNames) !== JSON.stringify(expectedNames)) {{
      throw new Error(`侧栏附件顺序不符：${{actualNames.join(", ")}}`);
    }}
    timings.attachments_ms = Date.now() - stepStarted;

    stepStarted = Date.now();
    const returned = tab.playwright.waitForURL(
      payload.success_url_pattern, {{ timeoutMs: 30000 }}
    );
    submissionStarted = true;
    if (payload.create) {{
      await tab.playwright.getByRole("button", {{ name: /发布文章/ }}).click();
    }} else {{
      await tab.playwright.getByRole("button", {{ name: "更新文章" }}).click();
    }}
    await returned;
    const postUrl = await tab.url();
    const postSuffix = postUrl.slice(payload.post_url_prefix.length);
    if (!postUrl.startsWith(payload.post_url_prefix) || !/^[1-9][0-9]*\/$/.test(postSuffix)) {{
      throw new Error(`提交后未返回文章地址：${{postUrl}}`);
    }}
    timings.submit_and_return_ms = Date.now() - stepStarted;
    const finishedAt = Date.now();
    return {{
      ok: true,
      status: "ARTICLE_PAGE_RETURNED",
      sync_started_at: payload.sync_started_at,
      sync_run_id: payload.sync_run_id,
      sync_attempt: payload.sync_attempt,
      preload_sha256: payload.preload_sha256,
      post_url: postUrl,
      browser_elapsed_ms: finishedAt - startedAt,
      dispatch_latency_ms: dispatchLatencyMs,
      sync_elapsed_to_browser_return_ms: syncStartedAt !== null
        ? finishedAt - syncStartedAt
        : null,
      timing_breakdown_ms: timings,
      quality_checks: {{
        edit_url_verified: true,
        title_verified: true,
        body_verified: true,
        attachment_order_verified: true,
        article_page_returned: true
      }},
      body_length_utf16: body.length,
      attachments: actualNames
    }};
  }} catch (error) {{
    if (!submissionStarted) {{
      try {{ await tab.goto(payload.edit_url); }} catch {{}}
    }}
    throw error;
  }}
}}'''
    preload_script = helper_script + rf'''
var dbCodeBookSyncPreflightTab = await resolveDbCodeBookTab({existing_tab_match_json});
nodeRepl.write(JSON.stringify({{
  ok: true,
  status: "SYNC_TAB_READY",
  url: await dbCodeBookSyncPreflightTab.url()
}}));'''
    action = {
        "existing_tab_match": existing_tab_match,
        "payload": payload,
        "preload_sha256": hashlib.sha256(
            helper_script.encode("utf-8")
        ).hexdigest(),
    }
    if include_preload:
        action["preload_script"] = preload_script
    payload["preload_sha256"] = action["preload_sha256"]
    if sync_started_at is not None:
        payload_json = json.dumps(payload, ensure_ascii=False)
        existing_tab_match_json = json.dumps(existing_tab_match, ensure_ascii=False)
        action["run_script"] = rf'''var dbCodeBookSyncPayload = {payload_json};
var dbCodeBookSyncTab = await resolveDbCodeBookTab({existing_tab_match_json});
var dbCodeBookSyncResult = await syncDbCodeBookPost(dbCodeBookSyncTab, dbCodeBookSyncPayload);
nodeRepl.write(JSON.stringify(dbCodeBookSyncResult));'''
    return action


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--formal-dir", required=True, type=Path)
    parser.add_argument("--process-dir", required=True, type=Path)
    parser.add_argument("--topic-id", required=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize or verify the full-text readability publication gate."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    impact_parser = subparsers.add_parser("init-impact")
    impact_parser.add_argument("--process-dir", required=True, type=Path)
    impact_parser.add_argument("--topic-id", required=True)
    impact_parser.add_argument("--overwrite", action="store_true")

    init_parser = subparsers.add_parser("init")
    add_common_arguments(init_parser)
    init_parser.add_argument("--note", required=True)
    init_parser.add_argument("--r-script", required=True)
    init_parser.add_argument("--analysis-db", required=True)
    init_parser.add_argument("--analysis-codebook", required=True)
    init_parser.add_argument("--overwrite", action="store_true")
    init_parser.add_argument("--preserve-reader", action="store_true")

    reader_parser = subparsers.add_parser("init-reader")
    add_common_arguments(reader_parser)
    reader_parser.add_argument("--note", required=True)
    reader_parser.add_argument("--overwrite", action="store_true")

    check_parser = subparsers.add_parser("check")
    add_common_arguments(check_parser)
    check_parser.add_argument("--report", type=Path)

    verify_parser = subparsers.add_parser("verify-ready")
    add_common_arguments(verify_parser)
    verify_parser.add_argument("--start-sync", action="store_true")
    verify_parser.add_argument("--database")
    verify_parser.add_argument("--topic-name")
    verify_parser.add_argument("--post-id")
    verify_parser.add_argument("--create", action="store_true")
    verify_parser.add_argument("--directory-tag")
    verify_parser.add_argument("--base-url")
    verify_parser.add_argument("--website-title")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sync = None
    sync_requested = args.command == "verify-ready" and args.start_sync
    browser_target_requested = args.command == "verify-ready" and any(
        (args.database, args.topic_name, args.post_id, args.base_url, args.create)
    )
    try:
        if browser_target_requested:
            if not all((args.database, args.topic_name, args.post_id or args.create, args.base_url)):
                fail(
                    "browser sync preparation requires --database, --topic-name, "
                    "--post-id and --base-url"
                )
        if args.command == "init-impact":
            result = initialize_impact(
                args.process_dir,
                args.topic_id,
                overwrite=args.overwrite,
            )
        elif args.command == "init":
            result = initialize_audit(
                args.formal_dir,
                args.process_dir,
                args.topic_id,
                {
                    "note": args.note,
                    "public_r": args.r_script,
                    "analysis_db": args.analysis_db,
                    "analysis_codebook": args.analysis_codebook,
                },
                overwrite=args.overwrite,
                preserve_reader=args.preserve_reader,
            )
        elif args.command == "init-reader":
            result = initialize_reader_review(
                args.formal_dir,
                args.process_dir,
                args.topic_id,
                args.note,
                overwrite=args.overwrite,
            )
        elif args.command == "check":
            result = validate_audit(
                args.formal_dir,
                args.process_dir,
                args.topic_id,
                report_path=args.report,
            )
        else:
            result = verify_existing_readiness(
                args.formal_dir,
                args.process_dir,
                args.topic_id,
            )
            if browser_target_requested:
                prepared_action = build_cua_sync_action(
                    result["upload"], args.base_url, args.post_id, args.database,
                    args.topic_id, args.topic_name, args.website_title,
                    create=args.create, directory_tag=args.directory_tag,
                )
                if sync_requested:
                    import execution_report

                    sync = execution_report.begin_website_sync(
                        args.process_dir, args.database, args.topic_id,
                        args.topic_name,
                    )
                    browser_action = build_cua_sync_action(
                        result["upload"], args.base_url, args.post_id,
                        args.database, args.topic_id, args.topic_name,
                        args.website_title, sync["started_at"], include_preload=False,
                        create=args.create, directory_tag=args.directory_tag,
                        sync_run_id=sync["run_id"], sync_attempt=sync["attempt"],
                    )
                    result = {"ok": True, "status": result["status"],
                              "topic_id": result["topic_id"],
                              "browser_action": browser_action,
                              "execution": sync}
                else:
                    result = {"ok": True, "status": result["status"],
                              "topic_id": result["topic_id"],
                              "browser_action": prepared_action}
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if sync:
            execution_report.command_issue(argparse.Namespace(
                process_dir=str(args.process_dir), stage_id="website_sync",
                kind="abnormal", description=str(error),
                impact="发布前检查未通过，没有开始网站写入。",
                resolution="修正对应成果或审核记录后再执行同步。", status="open",
            ))
            execution_report.command_stage_finish(argparse.Namespace(
                process_dir=str(args.process_dir), stage_id="website_sync",
                status="failed", summary=["发布前检查未通过；未操作网站。"], output=[],
            ))
            execution_report.command_finish(argparse.Namespace(
                process_dir=str(args.process_dir), status="stopped",
                summary=["网站未更新；发布前检查失败，原因已记录。"],
            ))
        print(f"READABILITY_GATE_FAIL: {error}", file=sys.stderr)
        return 1
    # Keep machine-consumed stdout code-page independent on Windows shells.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
