from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_source_record.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_source_record_questionnaire_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_source_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_failure(
    checker, record, log, periods, message: str, require_rendered: bool = False
) -> None:
    try:
        checker.validate_questionnaire_evidence(
            record, log, periods, require_rendered=require_rendered
        )
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"Expected questionnaire evidence failure: {message}")


def expect_path_failure(
    checker, record, log, source_groups, approved_names, definition_plan, message: str
) -> None:
    try:
        checker.validate_questionnaire_path_closure(
            record, log, source_groups, approved_names, definition_plan
        )
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"Expected questionnaire path failure: {message}")


def main() -> int:
    checker = load_checker()
    exploration_log = [{"step": 1, "action": "official_material_review"}]
    source_periods = {"就业状态": {"2011", "2013"}}

    with tempfile.TemporaryDirectory(prefix="questionnaire_evidence_gate_") as tmp:
        local_root = Path(tmp) / "CHARLS"
        local_root.mkdir()
        questionnaire = local_root / "2011_问卷.txt"
        questionnaire.write_text("FA002", encoding="utf-8")
        checker.LOCAL_EVIDENCE_ROOTS["CHARLS"] = local_root

        record = {
            "database": "CHARLS",
            "questionnaire_evidence": [
                {
                    "evidence_id": "Q001",
                    "source_group": "就业状态",
                    "periods": ["2011", "2013"],
                    "question_id": "FA002",
                    "question_text": "上周您工作了至少一个小时吗？",
                    "question_text_complete": True,
                    "response_type": "closed_options",
                    "options": [
                        {"value": "1", "label": "是"},
                        {"value": "2", "label": "否"},
                    ],
                    "options_complete": True,
                    "skip_logic_status": "recorded",
                    "skip_logic": [
                        {"when": "1 是", "destination": "FB001"}
                    ],
                    "local_material_status": "verified",
                    "local_material_path": str(questionnaire),
                    "locator": "FA002",
                    "missing_reason": "",
                    "supplemental_official_url": "",
                    "evidence_steps": [1],
                    "rendered_in_copy": True,
                    "copy_locator": "文案.md > 问卷设计 > 2011-2013",
                }
            ],
            "questionnaire_coverage": [
                {
                    "source_group": "就业状态",
                    "period": "2011",
                    "status": "questionnaire",
                    "evidence_ids": ["Q001"],
                    "reason": "FA002 覆盖该期工作状态入口",
                },
                {
                    "source_group": "就业状态",
                    "period": "2013",
                    "status": "questionnaire",
                    "evidence_ids": ["Q001"],
                    "reason": "FA002 覆盖该期工作状态入口",
                },
            ],
        }

        result = checker.validate_questionnaire_evidence(
            record, exploration_log, source_periods
        )
        assert result == {"questions": 1, "covered_periods": 2}

        not_rendered = copy.deepcopy(record)
        not_rendered["questionnaire_evidence"][0]["rendered_in_copy"] = False
        not_rendered["questionnaire_evidence"][0]["copy_locator"] = (
            "待写入文案.md > 摘要导读 > 2011-2013"
        )
        checker.validate_questionnaire_evidence(
            not_rendered, exploration_log, source_periods
        )
        expect_failure(
            checker,
            not_rendered,
            exploration_log,
            source_periods,
            "rendered_in_copy must be true before final validation",
            require_rendered=True,
        )

        pending_locator = copy.deepcopy(record)
        pending_locator["questionnaire_evidence"][0]["copy_locator"] = (
            "待写入文案.md > 摘要导读 > 2011-2013"
        )
        expect_failure(
            checker,
            pending_locator,
            exploration_log,
            source_periods,
            "copy_locator still describes unfinished copy",
            require_rendered=True,
        )

        incomplete_options = copy.deepcopy(record)
        incomplete_options["questionnaire_evidence"][0]["options"] = []
        expect_failure(
            checker,
            incomplete_options,
            exploration_log,
            source_periods,
            "closed question must include all options",
        )

        vague_skip = copy.deepcopy(record)
        vague_skip["questionnaire_evidence"][0]["skip_logic"][0][
            "destination"
        ] = ""
        expect_failure(
            checker,
            vague_skip,
            exploration_log,
            source_periods,
            "destination must be non-empty text",
        )

        incomplete_coverage = copy.deepcopy(record)
        incomplete_coverage["questionnaire_coverage"].pop()
        expect_failure(
            checker,
            incomplete_coverage,
            exploration_log,
            source_periods,
            "questionnaire_coverage does not match all source-group periods",
        )

        source_groups = [
            {
                "concept": "就业状态",
                "periods": ["2011", "2013"],
                "raw_variables": ["fa002_p", "fa003_p"],
            }
        ]
        approved_names = ["work_status"]
        definition_plan = [
            {
                "analysis_var": "work_status",
                "source_groups": ["就业状态"],
            }
        ]
        record["questionnaire_path_closure"] = [
            {
                "analysis_var": "work_status",
                "period": period,
                "source_groups": ["就业状态"],
                "branches": [
                    {
                        "path_id": "P001",
                        "entry_condition": "进入就业状态题组",
                        "route": ["FA002: 1 -> FB001", "FB001: 结束本主题分支"],
                        "terminal_outcome": "确认受访者上周工作",
                        "definition_result": "work_status = 1",
                        "required_raw_variables": ["fa002_p"],
                        "observed_count": 10,
                        "unexplained_count": 0,
                    }
                ],
                "all_observed_paths_mapped": True,
                "structural_missing_explained": True,
                "evidence_steps": [1],
            }
            for period in ("2011", "2013")
        ]

        path_result = checker.validate_questionnaire_path_closure(
            record,
            exploration_log,
            source_groups,
            approved_names,
            definition_plan,
        )
        assert path_result == {"variable_periods": 2, "branches": 2}

        pending = copy.deepcopy(record)
        for path in pending["questionnaire_path_closure"]:
            path["branches"][0]["observed_count"] = None
            path["branches"][0]["unexplained_count"] = None
            path["all_observed_paths_mapped"] = None
            path["structural_missing_explained"] = None
        assert checker.validate_questionnaire_path_closure(
            pending, exploration_log, source_groups, approved_names,
            definition_plan, require_observed=False,
        ) == path_result
        expect_path_failure(
            checker, pending, exploration_log, source_groups, approved_names,
            definition_plan, "observed_count must be a non-negative integer",
        )

        # Exercise the real download entrypoint without replacing its validators.
        download_record = copy.deepcopy(pending)
        download_record.update({
            "schema_version": 7, "topic_id": "001", "status": "READY",
            "logic_review": {**dict.fromkeys((*checker.REQUIRED_LOGIC_CHECKS, *checker.REQUIRED_V3_LOGIC_CHECKS, *checker.REQUIRED_V7_LOGIC_CHECKS), True), "result": "clear"},
            "logic_issues": [],
            "human_record": "exploration.md", "source_groups": source_groups,
            "approved_analysis_vars": approved_names, "definition_plan": definition_plan,
            "exploration_log": [{**exploration_log[0], "human_step_id": "S001"}],
            "alias_families": [],
            "candidate_decisions": [{"selected_raw": ["fa002_p", "fa003_p"]}],
            "evidence_reviews": [{
                "source_type": "official_questionnaire", "title": "Questionnaire",
                "locator": "FA002", "reviewed_at": "2026-09-04",
                "supports": "Question and routes", "does_not_support": "Observed counts",
                "decision_effect": "Plan the source list", "evidence_steps": [1],
            }],
        })
        record_path = Path(tmp) / "record.json"
        selection_path = Path(tmp) / "selection.txt"
        (Path(tmp) / "exploration.md").write_text("### S001\nReviewed question.\n", encoding="utf-8")
        record_path.write_text(json.dumps(download_record), encoding="utf-8")
        selection_path.write_text("fa002_p\nfa003_p\n", encoding="utf-8")
        assert checker.validate_download_selection(record_path, selection_path, "001")["ok"]

        for flag in ("all_observed_paths_mapped", "structural_missing_explained"):
            for missing_field in ("observed_count", "unexplained_count"):
                premature = copy.deepcopy(download_record)
                path = premature["questionnaire_path_closure"][0]
                path["branches"][0].update(observed_count=10, unexplained_count=0)
                path["branches"][0][missing_field] = None
                path[flag] = True
                record_path.write_text(json.dumps(premature), encoding="utf-8")
                try:
                    checker.validate_download_selection(record_path, selection_path, "001")
                except ValueError as error:
                    assert "cannot be true while observations are pending" in str(error)
                else:
                    raise AssertionError("Unobserved paths were marked as measured and closed")

        # Deferring observations must not weaken source, period or route checks.
        mutations = [
            ("source", "outside the relevant source groups"),
            ("period", "does not match all questionnaire-backed"),
            ("route", "route must not be empty"),
            ("count", "observed_count must be a non-negative integer"),
        ]
        for mutation, message in mutations:
            invalid = copy.deepcopy(download_record)
            path = invalid["questionnaire_path_closure"][0]
            if mutation == "source":
                path["branches"][0]["required_raw_variables"] = ["not_selected"]
            elif mutation == "period":
                invalid["questionnaire_path_closure"].pop()
            elif mutation == "route":
                path["branches"][0]["route"] = []
            else:
                path["branches"][0]["observed_count"] = -1
            record_path.write_text(json.dumps(invalid), encoding="utf-8")
            try:
                checker.validate_download_selection(record_path, selection_path, "001")
            except ValueError as error:
                assert message in str(error), str(error)
            else:
                raise AssertionError(f"Pre-download failed to reject {mutation}")

        unmapped = copy.deepcopy(record)
        unmapped["questionnaire_path_closure"][0]["all_observed_paths_mapped"] = False
        expect_path_failure(
            checker, unmapped, exploration_log, source_groups, approved_names,
            definition_plan, "all_observed_paths_mapped must be true",
        )

        missing_path = copy.deepcopy(record)
        missing_path["questionnaire_path_closure"].pop()
        expect_path_failure(
            checker,
            missing_path,
            exploration_log,
            source_groups,
            approved_names,
            definition_plan,
            "questionnaire_path_closure does not match all questionnaire-backed",
        )

        unexplained_path = copy.deepcopy(record)
        unexplained_path["questionnaire_path_closure"][0]["branches"][0][
            "unexplained_count"
        ] = 1
        expect_path_failure(
            checker,
            unexplained_path,
            exploration_log,
            source_groups,
            approved_names,
            definition_plan,
            "unexplained_count must be 0",
        )

        outside_source = copy.deepcopy(record)
        outside_source["questionnaire_path_closure"][0]["branches"][0][
            "required_raw_variables"
        ] = ["fb001"]
        expect_path_failure(
            checker,
            outside_source,
            exploration_log,
            source_groups,
            approved_names,
            definition_plan,
            "outside the relevant source groups",
        )

    print("questionnaire evidence gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
