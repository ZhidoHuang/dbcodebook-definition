"""Validate source-search evidence before running a database definition."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from itertools import zip_longest
from pathlib import Path


READY_STATUS = "READY"
LOGIC_RESULTS = {"clear", "reported_and_resolved"}
RESOLVED_ISSUE_STATUSES = {"resolved", "reported_and_resolved"}
EXPLORATION_ACTIONS = {
    "directory_open",
    "ordinary_search",
    "detail_open",
    "official_material_review",
    "harmonized_review",
    "literature_review",
    "candidate_decision",
}
EVIDENCE_ACTIONS = {
    "official_material_review",
    "harmonized_review",
    "literature_review",
}
EVIDENCE_SOURCE_TYPES = {
    "official_questionnaire",
    "technical_document",
    "harmonized",
    "original_method",
    "guideline",
    "direct_research",
    "application_example",
}
SUPPORTED_SCHEMA_VERSIONS = {1, 2, 3, 4, 5, 6, 7}
QUESTION_RESPONSE_TYPES = {
    "closed_options",
    "open_value",
    "interviewer_instruction",
}
QUESTION_SKIP_STATUSES = {"recorded", "none"}
QUESTION_COVERAGE_STATUSES = {"questionnaire", "not_applicable"}
SKILL_ROOT = Path(__file__).resolve().parents[1]
LOCAL_EVIDENCE_ROOTS = {
    "CHARLS": SKILL_ROOT / "references" / "source-materials" / "charls",
    "ELSA": SKILL_ROOT / "references" / "source-materials" / "elsa",
}
CANDIDATE_DECISIONS = {"include", "exclude", "partial"}
SOURCE_HANDLING_DECISIONS = {"merge", "keep_separate", "single_period"}
REQUIRED_LOGIC_CHECKS = (
    "period_coverage_checked",
    "same_name_drift_checked",
    "meaning_change_checked",
    "formula_or_derivation_checked",
    "naming_checked",
)
REQUIRED_V3_LOGIC_CHECKS = (
    "source_identity_settled",
    "cross_period_handling_settled",
    "coding_and_missing_settled",
)
REQUIRED_V7_LOGIC_CHECKS = ("questionnaire_paths_closed",)


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        fail("source record must be a JSON object")
    return value


def nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be non-empty text")
    return value.strip()


def resolve_material_path(material_text: str, database: str, local_root: Path) -> Path:
    """Resolve current relative paths and older absolute records to bundled evidence."""

    recorded = Path(material_text)
    if not recorded.is_absolute():
        return (local_root / recorded).resolve()
    resolved = recorded.resolve()
    try:
        resolved.relative_to(local_root)
        return resolved
    except ValueError:
        pass

    parts = list(recorded.parts)
    database_index = next(
        (index for index, part in enumerate(parts) if part.casefold() == database.casefold()),
        None,
    )
    if database_index is None:
        fail("absolute material path has no database segment for repository remapping")
    return (local_root.joinpath(*parts[database_index + 1 :])).resolve()


def validate_alias_families(record: dict, recorded_raw: list[str]) -> int:
    """Require every declared repeated family to use one complete alias pattern."""

    families = record.get("alias_families", [])
    if not isinstance(families, list):
        fail("alias_families must be a list")

    recorded = set(recorded_raw)
    declared_members: set[str] = set()
    for index, item in enumerate(families, start=1):
        if not isinstance(item, dict):
            fail(f"alias_families[{index}] must be an object")
        template = nonempty_text(
            item.get("template"), f"alias_families[{index}].template"
        )
        if template.count("{n}") != 1:
            fail(f"alias_families[{index}].template must contain one {{n}}")
        start = item.get("start")
        end = item.get("end")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start > end
        ):
            fail(f"alias_families[{index}] start/end must be ordered integers")

        members = [template.format(n=value) for value in range(start, end + 1)]
        overlap = sorted(set(members) & declared_members)
        if overlap:
            fail(f"alias_families overlap on aliases: {overlap}")
        declared_members.update(members)

        missing = [value for value in members if value not in recorded]
        if missing:
            fail(
                f"alias_families[{index}] is incomplete or uses inconsistent "
                f"suffixes; missing={missing}"
            )
    return len(families)


def validate_human_record(
    record_path: Path,
    record: dict,
    exploration_log: object,
) -> Path:
    """Require each schema v4+ machine step to match the live plain-language record."""

    relative_name = nonempty_text(record.get("human_record"), "human_record")
    relative_path = Path(relative_name)
    if relative_path.is_absolute() or relative_path.name != relative_name:
        fail("human_record must be a file name in the source-record directory")
    human_path = record_path.parent / relative_path
    if not human_path.is_file():
        fail(f"human_record does not exist: {human_path}")
    human_text = human_path.read_text(encoding="utf-8-sig")
    if not isinstance(exploration_log, list) or not exploration_log:
        fail("schema v4+ exploration_log must not be empty")
    for expected_step, item in enumerate(exploration_log, start=1):
        if not isinstance(item, dict):
            fail(f"exploration_log[{expected_step}] must be an object")
        expected_id = f"S{expected_step:03d}"
        actual_id = nonempty_text(
            item.get("human_step_id"),
            f"exploration_log[{expected_step}].human_step_id",
        )
        if actual_id != expected_id:
            fail(
                f"exploration_log[{expected_step}].human_step_id must be {expected_id}"
            )
        if not re.search(rf"(?m)^###\s+{re.escape(expected_id)}(?:\s|$)", human_text):
            fail(f"human_record lacks the matching step heading: {expected_id}")
    return human_path


def validate_evidence_reviews(
    record: dict,
    exploration_log: object,
) -> list[dict]:
    """Require schema v5+ evidence reviews to point to review steps."""

    if not isinstance(exploration_log, list) or not exploration_log:
        fail("schema v5+ exploration_log must not be empty")
    step_actions = {
        item.get("step"): item.get("action")
        for item in exploration_log
        if isinstance(item, dict)
    }
    reviews = record.get("evidence_reviews")
    if not isinstance(reviews, list) or not reviews:
        fail("schema v5+ evidence_reviews must record the reviewed evidence")
    for index, item in enumerate(reviews, start=1):
        if not isinstance(item, dict):
            fail(f"evidence_reviews[{index}] must be an object")
        source_type = item.get("source_type")
        if source_type not in EVIDENCE_SOURCE_TYPES:
            fail(
                f"evidence_reviews[{index}].source_type must be one of "
                f"{sorted(EVIDENCE_SOURCE_TYPES)}"
            )
        for field in (
            "title",
            "locator",
            "reviewed_at",
            "supports",
            "does_not_support",
            "decision_effect",
        ):
            nonempty_text(item.get(field), f"evidence_reviews[{index}].{field}")
        evidence_steps = item.get("evidence_steps")
        if not isinstance(evidence_steps, list) or not evidence_steps:
            fail(f"evidence_reviews[{index}].evidence_steps must not be empty")
        unknown = [step for step in evidence_steps if step not in step_actions]
        if unknown:
            fail(
                f"evidence_reviews[{index}] references unknown exploration steps: "
                f"{unknown}"
            )
        wrong_actions = [
            step for step in evidence_steps if step_actions[step] not in EVIDENCE_ACTIONS
        ]
        if wrong_actions:
            fail(
                f"evidence_reviews[{index}] must reference material or literature "
                f"review steps; invalid={wrong_actions}"
            )
    return reviews


def validate_questionnaire_evidence(
    record: dict,
    exploration_log: object,
    source_periods: dict[str, set[str]],
    require_rendered: bool = False,
) -> dict:
    """Require schema v6+ period copy to have traceable questionnaire evidence."""

    if not isinstance(exploration_log, list) or not exploration_log:
        fail("schema v6+ exploration_log must not be empty")
    step_actions = {
        item.get("step"): item.get("action")
        for item in exploration_log
        if isinstance(item, dict)
    }
    database = nonempty_text(record.get("database"), "database").upper()
    local_root = LOCAL_EVIDENCE_ROOTS.get(database)
    if local_root is None:
        fail(f"schema v6+ has no configured local evidence root for {database}")
    local_root = local_root.resolve()
    if not local_root.is_dir():
        fail(f"configured local evidence root does not exist: {local_root}")

    items = record.get("questionnaire_evidence")
    if not isinstance(items, list):
        fail("schema v6+ questionnaire_evidence must be a list")
    evidence_by_id: dict[str, dict] = {}
    for index, item in enumerate(items, start=1):
        field = f"questionnaire_evidence[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        evidence_id = nonempty_text(item.get("evidence_id"), f"{field}.evidence_id")
        if evidence_id in evidence_by_id:
            fail(f"questionnaire_evidence repeats evidence_id: {evidence_id}")
        source_group = nonempty_text(
            item.get("source_group"), f"{field}.source_group"
        )
        if source_group not in source_periods:
            fail(f"{field} references unknown source_group: {source_group}")
        periods = item.get("periods")
        if not isinstance(periods, list) or not periods:
            fail(f"{field}.periods must not be empty")
        periods = [nonempty_text(value, f"{field}.periods") for value in periods]
        if len(periods) != len(set(periods)):
            fail(f"{field}.periods contains duplicates")
        unknown_periods = sorted(set(periods) - source_periods[source_group])
        if unknown_periods:
            fail(f"{field} references unknown periods: {unknown_periods}")

        nonempty_text(item.get("question_id"), f"{field}.question_id")
        nonempty_text(item.get("question_text"), f"{field}.question_text")
        if item.get("question_text_complete") is not True:
            fail(f"{field}.question_text_complete must be true")
        response_type = item.get("response_type")
        if response_type not in QUESTION_RESPONSE_TYPES:
            fail(
                f"{field}.response_type must be one of "
                f"{sorted(QUESTION_RESPONSE_TYPES)}"
            )
        options = item.get("options")
        if not isinstance(options, list):
            fail(f"{field}.options must be a list")
        if response_type == "closed_options" and not options:
            fail(f"{field} closed question must include all options")
        option_values: list[str] = []
        for option_index, option in enumerate(options, start=1):
            if not isinstance(option, dict):
                fail(f"{field}.options[{option_index}] must be an object")
            option_values.append(
                nonempty_text(
                    option.get("value"), f"{field}.options[{option_index}].value"
                )
            )
            nonempty_text(
                option.get("label"), f"{field}.options[{option_index}].label"
            )
        if len(option_values) != len(set(option_values)):
            fail(f"{field}.options repeats an option value")
        if item.get("options_complete") is not True:
            fail(f"{field}.options_complete must be true")

        skip_status = item.get("skip_logic_status")
        if skip_status not in QUESTION_SKIP_STATUSES:
            fail(
                f"{field}.skip_logic_status must be one of "
                f"{sorted(QUESTION_SKIP_STATUSES)}"
            )
        skip_logic = item.get("skip_logic")
        if not isinstance(skip_logic, list):
            fail(f"{field}.skip_logic must be a list")
        if skip_status == "recorded" and not skip_logic:
            fail(f"{field} recorded skip logic must not be empty")
        if skip_status == "none" and skip_logic:
            fail(f"{field} with no skip logic must use an empty list")
        for skip_index, skip in enumerate(skip_logic, start=1):
            if not isinstance(skip, dict):
                fail(f"{field}.skip_logic[{skip_index}] must be an object")
            nonempty_text(
                skip.get("when"), f"{field}.skip_logic[{skip_index}].when"
            )
            nonempty_text(
                skip.get("destination"),
                f"{field}.skip_logic[{skip_index}].destination",
            )

        material_status = item.get("local_material_status")
        if material_status not in {"verified", "missing"}:
            fail(f"{field}.local_material_status must be verified or missing")
        material_text = nonempty_text(
            item.get("local_material_path"), f"{field}.local_material_path"
        )
        material_path = resolve_material_path(material_text, database, local_root)
        try:
            material_path.relative_to(local_root)
        except ValueError:
            fail(f"{field}.local_material_path must be under {local_root}")
        if material_status == "verified" and not material_path.is_file():
            fail(f"{field} verified local material does not exist: {material_path}")
        if material_status == "missing" and not material_path.exists():
            fail(f"{field} missing-material search path does not exist: {material_path}")
        nonempty_text(item.get("locator"), f"{field}.locator")
        missing_reason = item.get("missing_reason", "")
        supplemental_url = item.get("supplemental_official_url", "")
        if material_status == "missing":
            nonempty_text(missing_reason, f"{field}.missing_reason")
            url = nonempty_text(
                supplemental_url, f"{field}.supplemental_official_url"
            )
            if not re.match(r"^https?://", url):
                fail(f"{field}.supplemental_official_url must be an official URL")
        else:
            if not isinstance(missing_reason, str) or not isinstance(
                supplemental_url, str
            ):
                fail(f"{field} missing_reason and URL must be text")

        evidence_steps = item.get("evidence_steps")
        if not isinstance(evidence_steps, list) or not evidence_steps:
            fail(f"{field}.evidence_steps must not be empty")
        unknown_steps = [step for step in evidence_steps if step not in step_actions]
        if unknown_steps:
            fail(f"{field} references unknown exploration steps: {unknown_steps}")
        wrong_actions = [
            step
            for step in evidence_steps
            if step_actions[step] != "official_material_review"
        ]
        if wrong_actions:
            fail(
                f"{field} must reference official_material_review steps; "
                f"invalid={wrong_actions}"
            )
        rendered_in_copy = item.get("rendered_in_copy")
        if not isinstance(rendered_in_copy, bool):
            fail(f"{field}.rendered_in_copy must be true or false")
        copy_locator = nonempty_text(
            item.get("copy_locator"), f"{field}.copy_locator"
        )
        if require_rendered and rendered_in_copy is not True:
            fail(f"{field}.rendered_in_copy must be true before final validation")
        if require_rendered and re.search(
            r"待写入|待补|尚未写入|未写入|\bTODO\b|\bTBD\b|\bpending\b",
            copy_locator,
            re.IGNORECASE,
        ):
            fail(f"{field}.copy_locator still describes unfinished copy")
        evidence_by_id[evidence_id] = {
            "source_group": source_group,
            "periods": set(periods),
        }

    coverage = record.get("questionnaire_coverage")
    if not isinstance(coverage, list) or not coverage:
        fail("schema v6+ questionnaire_coverage must cover every source period")
    expected_pairs = {
        (source_group, period)
        for source_group, periods in source_periods.items()
        for period in periods
    }
    covered_pairs: set[tuple[str, str]] = set()
    used_evidence: set[str] = set()
    for index, item in enumerate(coverage, start=1):
        field = f"questionnaire_coverage[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        source_group = nonempty_text(
            item.get("source_group"), f"{field}.source_group"
        )
        period = nonempty_text(item.get("period"), f"{field}.period")
        pair = (source_group, period)
        if pair not in expected_pairs:
            fail(f"{field} references an unknown source-group period: {pair}")
        if pair in covered_pairs:
            fail(f"questionnaire_coverage repeats source-group period: {pair}")
        covered_pairs.add(pair)
        status = item.get("status")
        if status not in QUESTION_COVERAGE_STATUSES:
            fail(
                f"{field}.status must be one of "
                f"{sorted(QUESTION_COVERAGE_STATUSES)}"
            )
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            fail(f"{field}.evidence_ids must be a list")
        reason = nonempty_text(item.get("reason"), f"{field}.reason")
        if status == "not_applicable":
            if evidence_ids:
                fail(f"{field} not_applicable coverage cannot reference questions")
            if not reason:
                fail(f"{field} not_applicable coverage requires a reason")
            continue
        if not evidence_ids:
            fail(f"{field} questionnaire coverage must reference evidence")
        for evidence_id in evidence_ids:
            evidence_id = nonempty_text(evidence_id, f"{field}.evidence_ids")
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                fail(f"{field} references unknown evidence_id: {evidence_id}")
            if evidence["source_group"] != source_group or period not in evidence["periods"]:
                fail(
                    f"{field} evidence {evidence_id} does not cover "
                    f"{source_group} / {period}"
                )
            used_evidence.add(evidence_id)

    missing_pairs = sorted(expected_pairs - covered_pairs)
    extra_pairs = sorted(covered_pairs - expected_pairs)
    if missing_pairs or extra_pairs:
        fail(
            "questionnaire_coverage does not match all source-group periods; "
            f"missing={missing_pairs}, extra={extra_pairs}"
        )
    unused_evidence = sorted(set(evidence_by_id) - used_evidence)
    if unused_evidence:
        fail(f"questionnaire_evidence is not used by coverage: {unused_evidence}")
    return {
        "questions": len(evidence_by_id),
        "covered_periods": len(covered_pairs),
    }


def validate_questionnaire_path_closure(
    record: dict,
    exploration_log: object,
    source_groups: object,
    approved_names: object,
    definition_plan: object,
    *,
    require_observed: bool = True,
) -> dict:
    """Check planned paths; require measured closure outside pre-download selection."""

    if not isinstance(exploration_log, list) or not exploration_log:
        fail("schema v7 exploration_log must not be empty")
    exploration_steps = {
        item.get("step")
        for item in exploration_log
        if isinstance(item, dict) and isinstance(item.get("step"), int)
    }
    if not isinstance(source_groups, list) or not source_groups:
        fail("schema v7 source_groups must not be empty")

    periods_by_group: dict[str, set[str]] = {}
    raw_by_group: dict[str, set[str]] = {}
    for index, item in enumerate(source_groups, start=1):
        field = f"source_groups[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        concept = nonempty_text(item.get("concept"), f"{field}.concept")
        periods = item.get("periods")
        raw_variables = item.get("raw_variables")
        if not isinstance(periods, list) or not periods:
            fail(f"{field}.periods must not be empty")
        if not isinstance(raw_variables, list) or not raw_variables:
            fail(f"{field}.raw_variables must not be empty")
        periods_by_group[concept] = {
            nonempty_text(value, f"{field}.periods") for value in periods
        }
        raw_by_group[concept] = {
            nonempty_text(value, f"{field}.raw_variables") for value in raw_variables
        }

    coverage = record.get("questionnaire_coverage")
    if not isinstance(coverage, list) or not coverage:
        fail("schema v7 questionnaire_coverage must not be empty")
    questionnaire_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(coverage, start=1):
        field = f"questionnaire_coverage[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        source_group = nonempty_text(item.get("source_group"), f"{field}.source_group")
        period = nonempty_text(item.get("period"), f"{field}.period")
        if item.get("status") == "questionnaire":
            questionnaire_pairs.add((source_group, period))

    if not isinstance(approved_names, list) or not approved_names:
        fail("schema v7 approved_analysis_vars must not be empty")
    approved = {
        nonempty_text(value, "approved analysis variable") for value in approved_names
    }
    if not isinstance(definition_plan, list) or not definition_plan:
        fail("schema v7 definition_plan must not be empty")

    expected_groups: dict[tuple[str, str], set[str]] = {}
    for index, item in enumerate(definition_plan, start=1):
        field = f"definition_plan[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        analysis_var = nonempty_text(item.get("analysis_var"), f"{field}.analysis_var")
        if analysis_var not in approved:
            fail(f"{field} references an unapproved analysis variable: {analysis_var}")
        planned_groups = item.get("source_groups")
        if not isinstance(planned_groups, list) or not planned_groups:
            fail(f"{field}.source_groups must not be empty")
        for group in planned_groups:
            group = nonempty_text(group, f"{field}.source_groups")
            if group not in periods_by_group:
                fail(f"{field} references unknown source group: {group}")
            for period in periods_by_group[group]:
                if (group, period) in questionnaire_pairs:
                    expected_groups.setdefault((analysis_var, period), set()).add(group)

    closures = record.get("questionnaire_path_closure")
    if not isinstance(closures, list):
        fail("schema v7 questionnaire_path_closure must be a list")
    actual_pairs: set[tuple[str, str]] = set()
    branch_count = 0
    for index, item in enumerate(closures, start=1):
        field = f"questionnaire_path_closure[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        analysis_var = nonempty_text(item.get("analysis_var"), f"{field}.analysis_var")
        period = nonempty_text(item.get("period"), f"{field}.period")
        pair = (analysis_var, period)
        if pair not in expected_groups:
            fail(f"{field} references an unexpected analysis-variable period: {pair}")
        if pair in actual_pairs:
            fail(f"questionnaire_path_closure repeats analysis-variable period: {pair}")
        actual_pairs.add(pair)

        groups = item.get("source_groups")
        if not isinstance(groups, list) or not groups:
            fail(f"{field}.source_groups must not be empty")
        groups = {
            nonempty_text(value, f"{field}.source_groups") for value in groups
        }
        if groups != expected_groups[pair]:
            fail(
                f"{field}.source_groups does not match the questionnaire-backed "
                f"definition sources; expected={sorted(expected_groups[pair])}, "
                f"actual={sorted(groups)}"
            )
        allowed_raw = set().union(*(raw_by_group[group] for group in groups))

        branches = item.get("branches")
        if not isinstance(branches, list) or not branches:
            fail(f"{field}.branches must not be empty")
        path_ids: set[str] = set()
        observations_pending = False
        for branch_index, branch in enumerate(branches, start=1):
            branch_field = f"{field}.branches[{branch_index}]"
            if not isinstance(branch, dict):
                fail(f"{branch_field} must be an object")
            path_id = nonempty_text(branch.get("path_id"), f"{branch_field}.path_id")
            if path_id in path_ids:
                fail(f"{field}.branches repeats path_id: {path_id}")
            path_ids.add(path_id)
            nonempty_text(
                branch.get("entry_condition"), f"{branch_field}.entry_condition"
            )
            route = branch.get("route")
            if not isinstance(route, list) or not route:
                fail(f"{branch_field}.route must not be empty")
            for route_item in route:
                nonempty_text(route_item, f"{branch_field}.route")
            nonempty_text(
                branch.get("terminal_outcome"), f"{branch_field}.terminal_outcome"
            )
            nonempty_text(
                branch.get("definition_result"), f"{branch_field}.definition_result"
            )
            required_raw = branch.get("required_raw_variables")
            if not isinstance(required_raw, list) or not required_raw:
                fail(f"{branch_field}.required_raw_variables must not be empty")
            required_raw = {
                nonempty_text(value, f"{branch_field}.required_raw_variables")
                for value in required_raw
            }
            unknown_raw = sorted(required_raw - allowed_raw)
            if unknown_raw:
                fail(
                    f"{branch_field}.required_raw_variables are outside the relevant "
                    f"source groups: {unknown_raw}"
                )
            observed_count = branch.get("observed_count")
            if (require_observed or observed_count is not None) and (
                isinstance(observed_count, bool)
                or not isinstance(observed_count, int)
                or observed_count < 0
            ):
                fail(f"{branch_field}.observed_count must be a non-negative integer")
            unexplained_count = branch.get("unexplained_count")
            observations_pending |= observed_count is None or unexplained_count is None
            if (require_observed or unexplained_count is not None) and (
                isinstance(unexplained_count, bool) or not isinstance(
                unexplained_count, int
                )
            ):
                fail(f"{branch_field}.unexplained_count must be an integer")
            if unexplained_count is not None and unexplained_count != 0:
                fail(f"{branch_field}.unexplained_count must be 0")
            branch_count += 1

        for flag in ("all_observed_paths_mapped", "structural_missing_explained"):
            value = item.get(flag)
            if require_observed and value is not True:
                fail(f"{field}.{flag} must be true")
            if not require_observed and value is not None and not isinstance(value, bool):
                fail(f"{field}.{flag} must be a boolean or null")
            if not require_observed and observations_pending and value is True:
                fail(f"{field}.{flag} cannot be true while observations are pending")
        evidence_steps = item.get("evidence_steps")
        if not isinstance(evidence_steps, list) or not evidence_steps:
            fail(f"{field}.evidence_steps must not be empty")
        unknown_steps = [step for step in evidence_steps if step not in exploration_steps]
        if unknown_steps:
            fail(f"{field} references unknown exploration steps: {unknown_steps}")

    missing_pairs = sorted(set(expected_groups) - actual_pairs)
    extra_pairs = sorted(actual_pairs - set(expected_groups))
    if missing_pairs or extra_pairs:
        fail(
            "questionnaire_path_closure does not match all questionnaire-backed "
            f"analysis-variable periods; missing={missing_pairs}, extra={extra_pairs}"
        )
    return {"variable_periods": len(actual_pairs), "branches": branch_count}


def read_selection_vars(path: Path) -> list[str]:
    values = [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not values:
        fail("download selection file is empty")
    if len(values) != len(set(values)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        fail(f"download selection file contains duplicates: {duplicates}")
    return values


def validate_download_selection(
    record_path: Path,
    selection_path: Path,
    topic_id: str,
) -> dict:
    """Check the final page selection before any download is started."""

    record = load_json(record_path)
    schema_version = record.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        fail(f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    if str(record.get("topic_id", "")).zfill(3) != topic_id:
        fail(f"topic_id must be {topic_id}")
    if record.get("status") != READY_STATUS:
        fail(f"status must be {READY_STATUS} before download")

    groups = record.get("source_groups")
    if not isinstance(groups, list) or not groups:
        fail("source_groups must contain the final source list")
    recorded_raw: list[str] = []
    source_periods: dict[str, set[str]] = {}
    for index, item in enumerate(groups, start=1):
        if not isinstance(item, dict):
            fail(f"source_groups[{index}] must be an object")
        variables = item.get("raw_variables")
        if not isinstance(variables, list) or not variables:
            fail(f"source_groups[{index}].raw_variables must not be empty")
        recorded_raw.extend(
            nonempty_text(value, f"source_groups[{index}].raw_variables")
            for value in variables
        )
        if schema_version in {6, 7}:
            concept = nonempty_text(
                item.get("concept"), f"source_groups[{index}].concept"
            )
            if concept in source_periods:
                fail(f"source_groups repeats concept: {concept}")
            periods = item.get("periods")
            if not isinstance(periods, list) or not periods:
                fail(f"source_groups[{index}].periods must not be empty")
            source_periods[concept] = {
                nonempty_text(value, f"source_groups[{index}].periods")
                for value in periods
            }
    if len(recorded_raw) != len(set(recorded_raw)):
        fail("source_groups contain duplicate raw variables")
    alias_family_count = validate_alias_families(record, recorded_raw)

    selected = read_selection_vars(selection_path)
    missing = sorted(set(recorded_raw) - set(selected))
    unexpected = sorted(set(selected) - set(recorded_raw))
    if missing or unexpected:
        fail(
            "download selection differs from the final source record; "
            f"missing={missing}, unexpected={unexpected}"
        )

    if schema_version in {4, 5, 6, 7}:
        validate_human_record(record_path, record, record.get("exploration_log"))
    if schema_version in {5, 6, 7}:
        validate_evidence_reviews(record, record.get("exploration_log"))
    if schema_version in {6, 7}:
        validate_questionnaire_evidence(
            record, record.get("exploration_log"), source_periods
        )
    if schema_version == 7:
        validate_questionnaire_path_closure(
            record,
            record.get("exploration_log"),
            groups,
            record.get("approved_analysis_vars"),
            record.get("definition_plan"),
            require_observed=False,
        )
    if schema_version in {2, 3, 4, 5, 6, 7}:
        decisions = record.get("candidate_decisions")
        if not isinstance(decisions, list) or not decisions:
            fail("candidate_decisions must contain the final include/exclude decisions")
        decided_selected: list[str] = []
        for index, item in enumerate(decisions, start=1):
            if not isinstance(item, dict):
                fail(f"candidate_decisions[{index}] must be an object")
            values = item.get("selected_raw")
            if not isinstance(values, list):
                fail(f"candidate_decisions[{index}].selected_raw must be a list")
            decided_selected.extend(
                nonempty_text(value, f"candidate_decisions[{index}].selected_raw")
                for value in values
            )
        if len(decided_selected) != len(set(decided_selected)):
            fail("candidate_decisions select duplicate raw variables")
        missing_decision = sorted(set(selected) - set(decided_selected))
        extra_decision = sorted(set(decided_selected) - set(selected))
        if missing_decision or extra_decision:
            fail(
                "download selection differs from candidate_decisions; "
                f"missing_in_decisions={missing_decision}, "
                f"not_in_selection={extra_decision}"
            )

    return {
        "ok": True,
        "mode": "pre_download_selection",
        "topic_id": topic_id,
        "variables": len(selected),
        "alias_families": alias_family_count,
        "selection_file": str(selection_path),
    }


def read_raw_vars(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "newname" not in reader.fieldnames:
            fail("raw_codebook.csv must contain a newname column")
        values = [
            (row.get("newname") or "").strip()
            for row in reader
            if (row.get("File type") or "").strip().lower() != "structural"
        ]
    if not values or any(not value for value in values):
        fail("raw_codebook.csv contains an empty newname")
    if len(values) != len(set(values)):
        fail("raw_codebook.csv contains duplicate newname values")
    return values


def read_exported_identity_vars(raw_codebook_path: Path) -> set[str]:
    """Return automatic identity columns that are present in exported CSV files."""

    allowed = {
        "ID",
        "id",
        "year",
        "householdid",
        "respondent_id",
        "communityid",
        "sub_commuid",
    }
    exported: set[str] = set()
    for data_path in raw_codebook_path.parent.glob("raw_data*.csv"):
        with data_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
        exported.update(column for column in header if column in allowed)
    return exported


def validate_download_package(formal_dir: Path) -> dict:
    """Confirm that formal CSV content matches one original download zip."""

    archive_path = formal_dir / "bookapp_download.zip"
    if not archive_path.is_file():
        fail(f"bookapp_download.zip does not exist: {archive_path}")

    extracted = [formal_dir / "raw_codebook.csv", *sorted(formal_dir.glob("raw_data*.csv"))]
    missing = [str(path) for path in extracted if not path.is_file()]
    if missing or len(extracted) < 2:
        fail(f"formal download files are incomplete; missing={missing}")

    with zipfile.ZipFile(archive_path) as archive:
        managed_members = [
            name
            for name in archive.namelist()
            if Path(name).name == "raw_codebook.csv"
            or Path(name).name.startswith("raw_data") and Path(name).suffix == ".csv"
        ]
        members_by_name: dict[str, str] = {}
        for member in managed_members:
            basename = Path(member).name
            if basename in members_by_name:
                fail(f"download zip repeats a managed file name: {basename}")
            members_by_name[basename] = member

        extracted_names = {path.name for path in extracted}
        archive_names = set(members_by_name)
        if extracted_names != archive_names:
            fail(
                "formal CSV files differ from the files in bookapp_download.zip; "
                f"missing_from_zip={sorted(extracted_names - archive_names)}, "
                f"not_extracted={sorted(archive_names - extracted_names)}"
            )
        changed: list[str] = []
        for path in extracted:
            with path.open("r", encoding="utf-8-sig", newline="") as disk_handle:
                disk_rows = csv.reader(disk_handle)
                zip_handle = io.TextIOWrapper(
                    archive.open(members_by_name[path.name]),
                    encoding="utf-8-sig",
                    newline="",
                )
                try:
                    zip_rows = csv.reader(zip_handle)
                    if any(left != right for left, right in zip_longest(disk_rows, zip_rows)):
                        changed.append(path.name)
                finally:
                    zip_handle.close()
        if changed:
            fail(
                "formal CSV content was filtered, supplemented, reordered, or changed after download; "
                f"different_from_zip={changed}"
            )

    return {
        "archive": str(archive_path),
        "files": sorted(extracted_names),
    }


def extract_r_vector(source: str, object_name: str) -> list[str]:
    match = re.search(
        rf"(?ms)^\s*{re.escape(object_name)}\s*<-\s*c\((.*?)\)\s*$",
        source,
    )
    if not match:
        fail(f"R script does not define {object_name} <- c(...)")
    values = re.findall(r'["\']([^"\']+)["\']', match.group(1))
    if not values:
        fail(f"{object_name} is empty")
    return values


def extract_summary_paths(source: str) -> list[str]:
    return re.findall(
        r"""summary_path_part\(\s*["']([^"']+)["']\s*\)""",
        source,
    )


def validate_record(
    record_path: Path,
    r_script_path: Path,
    raw_codebook_path: Path,
    topic_id: str,
) -> dict:
    record = load_json(record_path)
    source = r_script_path.read_text(encoding="utf-8")

    schema_version = record.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        fail(f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    if str(record.get("topic_id", "")).zfill(3) != topic_id:
        fail(f"topic_id must be {topic_id}")
    if record.get("status") != READY_STATUS:
        fail(f"status must be {READY_STATUS}")
    url = nonempty_text(record.get("dbcodebook_url"), "dbcodebook_url")
    if not re.match(r"^https?://[^/]+(?:/|$)", url):
        fail("dbcodebook_url must be an HTTP or HTTPS website URL")
    nonempty_text(record.get("searched_at"), "searched_at")

    exploration_steps: set[int] = set()
    exploration_log: object = None
    evidence_reviews: list[dict] = []
    if schema_version in {2, 3, 4, 5, 6, 7}:
        if record.get("recording_mode") != "contemporaneous":
            fail("schema v2+ recording_mode must be contemporaneous")
        exploration_log = record.get("exploration_log")
        if not isinstance(exploration_log, list) or not exploration_log:
            fail("schema v2+ exploration_log must record the actual exploration sequence")
        for expected_step, item in enumerate(exploration_log, start=1):
            if not isinstance(item, dict):
                fail(f"exploration_log[{expected_step}] must be an object")
            step = item.get("step")
            if step != expected_step:
                fail("exploration_log steps must be consecutive and start at 1")
            action = item.get("action")
            if action not in EXPLORATION_ACTIONS:
                fail(
                    f"exploration_log[{expected_step}].action must be one of "
                    f"{sorted(EXPLORATION_ACTIONS)}"
                )
            for field in ("input", "observed", "decision", "reason"):
                nonempty_text(
                    item.get(field), f"exploration_log[{expected_step}].{field}"
                )
            exploration_steps.add(step)
        if schema_version in {4, 5, 6, 7}:
            validate_human_record(record_path, record, exploration_log)
        if schema_version in {5, 6, 7}:
            evidence_reviews = validate_evidence_reviews(record, exploration_log)
        else:
            evidence_reviews = []

    directories = record.get("directory_entries")
    if not isinstance(directories, list) or not directories:
        fail("directory_entries must contain at least one verified directory")
    directory_paths: set[str] = set()
    for index, item in enumerate(directories, start=1):
        if not isinstance(item, dict):
            fail(f"directory_entries[{index}] must be an object")
        full_path = nonempty_text(
            item.get("full_path"), f"directory_entries[{index}].full_path"
        )
        if not full_path.startswith("Core data >"):
            fail(f"directory_entries[{index}].full_path is not a full Core data path")
        if item.get("verified_in_ui") is not True:
            fail(f"directory_entries[{index}] was not verified in the website UI")
        nonempty_text(item.get("purpose"), f"directory_entries[{index}].purpose")
        directory_paths.add(full_path)

    searches = record.get("normal_searches")
    if not isinstance(searches, list) or not searches:
        fail("normal_searches must record the actual ordinary-search step")
    search_keywords: set[str] = set()
    for index, item in enumerate(searches, start=1):
        if not isinstance(item, dict):
            fail(f"normal_searches[{index}] must be an object")
        if item.get("performed") is True:
            keyword = nonempty_text(
                item.get("keyword"), f"normal_searches[{index}].keyword"
            )
            nonempty_text(item.get("result"), f"normal_searches[{index}].result")
            search_keywords.add(keyword)
        else:
            nonempty_text(item.get("reason"), f"normal_searches[{index}].reason")

    groups = record.get("source_groups")
    if not isinstance(groups, list) or not groups:
        fail("source_groups must contain at least one source group")
    recorded_raw: list[str] = []
    source_periods: dict[str, set[str]] = {}
    for index, item in enumerate(groups, start=1):
        if not isinstance(item, dict):
            fail(f"source_groups[{index}] must be an object")
        nonempty_text(item.get("concept"), f"source_groups[{index}].concept")
        variables = item.get("raw_variables")
        if not isinstance(variables, list) or not variables:
            fail(f"source_groups[{index}].raw_variables must not be empty")
        for variable in variables:
            recorded_raw.append(nonempty_text(variable, "raw variable"))
        period_field = "periods" if schema_version in {3, 4, 5, 6, 7} else "years"
        periods = item.get(period_field)
        if not isinstance(periods, list) or not periods:
            fail(f"source_groups[{index}].{period_field} must not be empty")
        periods = [
            nonempty_text(value, f"source_groups[{index}].{period_field}")
            for value in periods
        ]
        if len(periods) != len(set(periods)):
            fail(f"source_groups[{index}].{period_field} contains duplicates")
        if schema_version in {6, 7}:
            concept = nonempty_text(
                item.get("concept"), f"source_groups[{index}].concept"
            )
            if concept in source_periods:
                fail(f"source_groups repeats concept: {concept}")
            source_periods[concept] = set(periods)
        if item.get("detail_verified") is not True:
            fail(f"source_groups[{index}] lacks website detail verification")
        if schema_version in {2, 3, 4, 5, 6, 7}:
            nonempty_text(
                item.get("selection_reason"),
                f"source_groups[{index}].selection_reason",
            )
            evidence_steps = item.get("evidence_steps")
            if not isinstance(evidence_steps, list) or not evidence_steps:
                fail(f"source_groups[{index}].evidence_steps must not be empty")
            if any(step not in exploration_steps for step in evidence_steps):
                fail(f"source_groups[{index}] references an unknown exploration step")
        if schema_version in {3, 4, 5, 6, 7}:
            comparison = item.get("period_comparison")
            if not isinstance(comparison, list) or not comparison:
                fail(f"source_groups[{index}].period_comparison must not be empty")
            compared_periods: list[str] = []
            for comparison_index, period_item in enumerate(comparison, start=1):
                if not isinstance(period_item, dict):
                    fail(
                        f"source_groups[{index}].period_comparison[{comparison_index}] "
                        "must be an object"
                    )
                item_periods = period_item.get("periods")
                if not isinstance(item_periods, list) or not item_periods:
                    fail(
                        f"source_groups[{index}].period_comparison[{comparison_index}]."
                        "periods must not be empty"
                    )
                compared_periods.extend(
                    nonempty_text(
                        value,
                        f"source_groups[{index}].period_comparison[{comparison_index}].periods",
                    )
                    for value in item_periods
                )
                for field in (
                    "question_meaning",
                    "population",
                    "reference_period",
                    "recording_and_coding",
                ):
                    nonempty_text(
                        period_item.get(field),
                        f"source_groups[{index}].period_comparison[{comparison_index}].{field}",
                    )
            if len(compared_periods) != len(set(compared_periods)):
                fail(f"source_groups[{index}].period_comparison repeats a period")
            if set(compared_periods) != set(periods):
                fail(
                    f"source_groups[{index}].period_comparison does not cover "
                    f"all source periods"
                )
            nonempty_text(
                item.get("common_meaning"),
                f"source_groups[{index}].common_meaning",
            )
            differences = item.get("material_differences")
            if not isinstance(differences, list):
                fail(f"source_groups[{index}].material_differences must be a list")
            for difference in differences:
                nonempty_text(
                    difference, f"source_groups[{index}].material_differences"
                )
            handling = item.get("handling_decision")
            if handling not in SOURCE_HANDLING_DECISIONS:
                fail(
                    f"source_groups[{index}].handling_decision must be one of "
                    f"{sorted(SOURCE_HANDLING_DECISIONS)}"
                )
            if len(periods) == 1 and handling != "single_period":
                fail(
                    f"source_groups[{index}] has one period and must use "
                    "single_period"
                )
            if len(periods) > 1 and handling == "single_period":
                fail(
                    f"source_groups[{index}] has multiple periods and cannot use "
                    "single_period"
                )
            nonempty_text(
                item.get("handling_reason"),
                f"source_groups[{index}].handling_reason",
            )
        discovery = item.get("discovery")
        if not isinstance(discovery, dict):
            fail(f"source_groups[{index}].discovery must be an object")
        mode = discovery.get("mode")
        value = nonempty_text(
            discovery.get("value"), f"source_groups[{index}].discovery.value"
        )
        if mode == "directory":
            if value not in directory_paths:
                fail(f"source_groups[{index}] uses an unrecorded directory")
        elif mode == "ordinary_search":
            if value not in search_keywords:
                fail(f"source_groups[{index}] uses an unrecorded search keyword")
        else:
            fail(f"source_groups[{index}].discovery.mode is invalid")

    if len(recorded_raw) != len(set(recorded_raw)):
        fail("source_groups contain duplicate raw variables")
    questionnaire_summary = {"questions": 0, "covered_periods": 0}
    if schema_version in {6, 7}:
        questionnaire_summary = validate_questionnaire_evidence(
            record, exploration_log, source_periods, require_rendered=True
        )
    alias_family_count = validate_alias_families(record, recorded_raw)
    raw_vars = read_raw_vars(raw_codebook_path)
    exported_identity_vars = read_exported_identity_vars(raw_codebook_path)
    if not set(raw_vars).issubset(recorded_raw) or not set(recorded_raw).issubset(
        set(raw_vars) | exported_identity_vars
    ):
        missing = sorted(set(raw_vars) - set(recorded_raw))
        extra = sorted(
            set(recorded_raw) - set(raw_vars) - exported_identity_vars
        )
        fail(f"source_groups/raw_codebook mismatch; missing={missing}, extra={extra}")

    if schema_version in {2, 3, 4, 5, 6, 7}:
        candidate_decisions = record.get("candidate_decisions")
        if not isinstance(candidate_decisions, list) or not candidate_decisions:
            fail("schema v2+ candidate_decisions must not be empty")
        selected_candidates: list[str] = []
        for index, item in enumerate(candidate_decisions, start=1):
            if not isinstance(item, dict):
                fail(f"candidate_decisions[{index}] must be an object")
            nonempty_text(item.get("concept"), f"candidate_decisions[{index}].concept")
            decision = item.get("decision")
            if decision not in CANDIDATE_DECISIONS:
                fail(
                    f"candidate_decisions[{index}].decision must be one of "
                    f"{sorted(CANDIDATE_DECISIONS)}"
                )
            selected = item.get("selected_raw")
            excluded = item.get("excluded_raw")
            if not isinstance(selected, list) or not isinstance(excluded, list):
                fail(
                    f"candidate_decisions[{index}] selected_raw/excluded_raw "
                    "must be lists"
                )
            selected = [
                nonempty_text(value, "selected candidate raw") for value in selected
            ]
            excluded = [
                nonempty_text(value, "excluded candidate raw") for value in excluded
            ]
            if decision == "include" and not selected:
                fail(f"candidate_decisions[{index}] include decision selects no raw")
            if decision == "exclude" and selected:
                fail(f"candidate_decisions[{index}] exclude decision selects raw")
            if set(selected) & set(excluded):
                fail(f"candidate_decisions[{index}] selects and excludes the same raw")
            nonempty_text(item.get("reason"), f"candidate_decisions[{index}].reason")
            evidence_steps = item.get("evidence_steps")
            if not isinstance(evidence_steps, list) or not evidence_steps:
                fail(f"candidate_decisions[{index}].evidence_steps must not be empty")
            if any(step not in exploration_steps for step in evidence_steps):
                fail(
                    f"candidate_decisions[{index}] references an unknown exploration step"
                )
            selected_candidates.extend(selected)
        if len(selected_candidates) != len(set(selected_candidates)):
            fail("candidate_decisions select duplicate raw variables")
        if not set(raw_vars).issubset(selected_candidates) or not set(
            selected_candidates
        ).issubset(set(raw_vars) | exported_identity_vars):
            missing = sorted(set(raw_vars) - set(selected_candidates))
            extra = sorted(
                set(selected_candidates) - set(raw_vars) - exported_identity_vars
            )
            fail(
                "candidate_decisions/raw_codebook mismatch; "
                f"missing={missing}, extra={extra}"
            )

    approved_names = record.get("approved_analysis_vars")
    if not isinstance(approved_names, list) or not approved_names:
        fail("approved_analysis_vars must not be empty")
    approved_names = [
        nonempty_text(value, "approved analysis variable") for value in approved_names
    ]
    if len(approved_names) != len(set(approved_names)):
        fail("approved_analysis_vars contains duplicates")
    r_analysis_vars = extract_r_vector(source, "analysis_vars")
    if approved_names != r_analysis_vars:
        fail(
            "analysis_vars differs from the approved naming list; "
            f"approved={approved_names}, R={r_analysis_vars}"
        )

    definition_plan: list[dict] = []
    if schema_version in {3, 4, 5, 6, 7}:
        group_concepts = {
            nonempty_text(item.get("concept"), "source group concept")
            for item in groups
        }
        definition_plan = record.get("definition_plan")
        if not isinstance(definition_plan, list) or not definition_plan:
            fail("schema v3+ definition_plan must not be empty")
        planned_names: list[str] = []
        for index, item in enumerate(definition_plan, start=1):
            if not isinstance(item, dict):
                fail(f"definition_plan[{index}] must be an object")
            analysis_var = nonempty_text(
                item.get("analysis_var"), f"definition_plan[{index}].analysis_var"
            )
            planned_names.append(analysis_var)
            nonempty_text(item.get("meaning"), f"definition_plan[{index}].meaning")
            planned_groups = item.get("source_groups")
            if not isinstance(planned_groups, list) or not planned_groups:
                fail(f"definition_plan[{index}].source_groups must not be empty")
            planned_groups = [
                nonempty_text(value, f"definition_plan[{index}].source_groups")
                for value in planned_groups
            ]
            unknown_groups = sorted(set(planned_groups) - group_concepts)
            if unknown_groups:
                fail(
                    f"definition_plan[{index}] references unknown source groups: "
                    f"{unknown_groups}"
                )
            nonempty_text(
                item.get("construction"), f"definition_plan[{index}].construction"
            )
            nonempty_text(
                item.get("missing_and_jump"),
                f"definition_plan[{index}].missing_and_jump",
            )
        if planned_names != approved_names:
            fail(
                "definition_plan differs from approved_analysis_vars; "
                f"planned={planned_names}, approved={approved_names}"
            )

    path_closure_summary = {"variable_periods": 0, "branches": 0}
    if schema_version == 7:
        path_closure_summary = validate_questionnaire_path_closure(
            record,
            exploration_log,
            groups,
            approved_names,
            definition_plan,
        )

    r_summary_paths = extract_summary_paths(source)
    unrecorded_paths = sorted(set(r_summary_paths) - directory_paths)
    if unrecorded_paths:
        fail(f"R summary uses directories absent from source evidence: {unrecorded_paths}")

    logic_review = record.get("logic_review")
    if not isinstance(logic_review, dict):
        fail("logic_review must be an object")
    for field in REQUIRED_LOGIC_CHECKS:
        if logic_review.get(field) is not True:
            fail(f"logic_review.{field} must be true")
    if schema_version in {3, 4, 5, 6, 7}:
        for field in REQUIRED_V3_LOGIC_CHECKS:
            if logic_review.get(field) is not True:
                fail(f"logic_review.{field} must be true")
    if schema_version == 7:
        for field in REQUIRED_V7_LOGIC_CHECKS:
            if logic_review.get(field) is not True:
                fail(f"logic_review.{field} must be true")
    result = logic_review.get("result")
    if result not in LOGIC_RESULTS:
        fail(f"logic_review.result must be one of {sorted(LOGIC_RESULTS)}")

    issues = record.get("logic_issues")
    if not isinstance(issues, list):
        fail("logic_issues must be a list")
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            fail(f"logic_issues[{index}] must be an object")
        nonempty_text(issue.get("description"), f"logic_issues[{index}].description")
        nonempty_text(issue.get("impact"), f"logic_issues[{index}].impact")
        status = issue.get("status")
        if status not in RESOLVED_ISSUE_STATUSES:
            fail(f"logic_issues[{index}] is unresolved and must be reported")
        nonempty_text(issue.get("reported_to_user_at"), "reported_to_user_at")
        nonempty_text(issue.get("decision"), f"logic_issues[{index}].decision")
    if issues and result != "reported_and_resolved":
        fail("logic_review.result must be reported_and_resolved when issues exist")

    return {
        "ok": True,
        "topic_id": topic_id,
        "schema_version": schema_version,
        "alias_families": alias_family_count,
        "exploration_steps": len(exploration_steps),
        "directories": len(directory_paths),
        "ordinary_searches": len(search_keywords),
        "evidence_reviews": len(evidence_reviews),
        "questionnaire_evidence": questionnaire_summary,
        "questionnaire_path_closure": path_closure_summary,
        "raw_variables": len(raw_vars),
        "analysis_vars": approved_names,
        "logic_issues": len(issues),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--r-script", type=Path)
    parser.add_argument("--raw-codebook", type=Path)
    parser.add_argument(
        "--formal-dir",
        type=Path,
        help="Verify that formal raw CSV files exactly match bookapp_download.zip.",
    )
    parser.add_argument(
        "--selection-file",
        type=Path,
        help="Run the pre-download gate with one selected variable per line.",
    )
    parser.add_argument("--topic-id", required=True)
    args = parser.parse_args()
    try:
        if args.selection_file is not None:
            if (
                args.r_script is not None
                or args.raw_codebook is not None
                or args.formal_dir is not None
            ):
                parser.error(
                    "--selection-file cannot be combined with full-validation arguments"
                )
            result = validate_download_selection(
                args.record, args.selection_file, args.topic_id.zfill(3)
            )
        else:
            if args.r_script is None or args.raw_codebook is None:
                parser.error(
                    "full validation requires --r-script and --raw-codebook"
                )
            result = validate_record(
                args.record, args.r_script, args.raw_codebook, args.topic_id.zfill(3)
            )
            if args.formal_dir is None:
                parser.error("full validation requires --formal-dir")
            result["download_package"] = validate_download_package(args.formal_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"SOURCE_RECORD_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
