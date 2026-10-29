from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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
    checker, record, log, periods, message: str, require_rendered: bool = False,
    record_dir: Path | None = None,
) -> None:
    try:
        checker.validate_questionnaire_evidence(
            record, log, periods, require_rendered=require_rendered, record_dir=record_dir
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

        # Unknown routing is not the same assertion as verified no routing.
        # It may be carried only when the current definition does not use it.
        unknown = copy.deepcopy(record)
        unknown_item = unknown["questionnaire_evidence"][0]
        unknown_item.update(
            skip_logic_status="unknown", skip_logic=[],
            unverified_nonessential_routes=(
                "材料未记载否/未知后的现场退出题号；当前定义仅用合法直接回答，"
                "其余留缺失，不通过该未知路线补0。"),
            publication_coding_notes=["官方发布：是=1、否=2；不把编码约定当作跳题。"],
        )
        assert checker.validate_questionnaire_evidence(unknown, exploration_log, source_periods) == result
        paraphrased_unknown = copy.deepcopy(unknown)
        paraphrased_unknown["questionnaire_evidence"][0].update(
            question_text_mode="plain_paraphrase", question_text_complete=False,
            paraphrase_reason="官方材料支持必要题义和编码，未取得完整提问原句。",
            applicable_population="本期成年人", recall_period="过去一周",
        )
        assert checker.validate_questionnaire_evidence(paraphrased_unknown, exploration_log, source_periods) == result
        from questionnaire_display import display_answers
        assert display_answers(unknown_item, {})[1] == []
        translated_empty = copy.deepcopy(unknown_item)
        translated_empty["display"] = {"skip_logic": []}
        assert display_answers(translated_empty, {})[1] == []
        for reason in (None, "", "   ", [], {}):
            bad = copy.deepcopy(unknown)
            bad["questionnaire_evidence"][0]["unverified_nonessential_routes"] = reason
            expect_failure(checker, bad, exploration_log, source_periods, "unverified_nonessential_routes")
        bad = copy.deepcopy(unknown)
        bad["questionnaire_evidence"][0]["skip_logic"] = [{"when":"是=1", "destination":"FB001"}]
        expect_failure(checker, bad, exploration_log, source_periods, "unknown must use an empty list")
        for status, jumps, message in (
            ("recorded", [], "recorded skip logic must not be empty"),
            ("none", [{"when":"是=1", "destination":"FB001"}], "with no skip logic"),
            ("pending", [], "skip_logic_status"),
        ):
            bad = copy.deepcopy(record)
            bad["questionnaire_evidence"][0].update(skip_logic_status=status, skip_logic=jumps)
            expect_failure(checker, bad, exploration_log, source_periods, message)
        none = copy.deepcopy(record)
        none["questionnaire_evidence"][0].update(skip_logic_status="none", skip_logic=[])
        assert checker.validate_questionnaire_evidence(none, exploration_log, source_periods) == result
        known_entry = copy.deepcopy(record)
        known_entry["questionnaire_evidence"][0].update(
            skip_logic_status="recorded",
            skip_logic=[{"kind":"entry_condition", "when":"已核实成人对象", "destination":"FA002", "evidence":"fixture对象说明"}],
            unverified_nonessential_routes="仅题后非必要退出路线未知，不用于补值。",
        )
        assert checker.validate_questionnaire_evidence(known_entry, exploration_log, source_periods) == result
        print("unknown routing: evidence reason, empty display, and legacy status fixtures PASS")

        # Default and explicit skill scope retain relative and legacy absolute paths.
        for scope in (None, "skill"):
            for material_path in (
                questionnaire.name, str(questionnaire),
                str(Path(tmp) / "old_checkout" / "CHARLS" / questionnaire.name),
            ):
                skill_record = copy.deepcopy(record)
                skill_question = skill_record["questionnaire_evidence"][0]
                skill_question["local_material_path"] = material_path
                if scope is not None:
                    skill_question["local_material_scope"] = scope
                assert checker.validate_questionnaire_evidence(
                    skill_record, exploration_log, source_periods
                ) == result

        topic_dir = Path(tmp) / "topic"
        topic_materials = topic_dir / "materials"
        topic_materials.mkdir(parents=True)
        topic_material = topic_materials / "official_question.txt"
        topic_material.write_text("FA002", encoding="utf-8")
        topic_record = copy.deepcopy(record)
        topic_record["questionnaire_evidence"][0].update(
            local_material_scope="topic",
            local_material_path="materials/official_question.txt",
        )
        for relative_path in (
            "materials/official_question.txt",
            r"materials\official_question.txt",
            "materials/../materials/official_question.txt",
        ):
            valid_topic = copy.deepcopy(topic_record)
            valid_topic["questionnaire_evidence"][0]["local_material_path"] = relative_path
            assert checker.validate_questionnaire_evidence(
                valid_topic, exploration_log, source_periods, record_dir=topic_dir
            ) == result
        expect_failure(
            checker, topic_record, exploration_log, source_periods,
            "topic material scope requires record_dir",
        )

        # An existing topic file must not silently become a fallback for skill paths.
        implicit_topic = copy.deepcopy(topic_record)
        del implicit_topic["questionnaire_evidence"][0]["local_material_scope"]
        expect_failure(
            checker, implicit_topic, exploration_log, source_periods,
            "verified local material does not exist", record_dir=topic_dir,
        )
        for invalid_scope in ("unknown", "", None, [], {}):
            invalid = copy.deepcopy(topic_record)
            invalid["questionnaire_evidence"][0]["local_material_scope"] = invalid_scope
            expect_failure(
                checker, invalid, exploration_log, source_periods,
                "local_material_scope must be skill or topic", record_dir=topic_dir,
            )
        for absolute_path in (
            str(topic_material), "/absolute/question.txt", r"C:\materials\question.txt",
            r"C:materials\question.txt", r"\\server\share\question.txt",
            r"\materials\question.txt",
        ):
            invalid = copy.deepcopy(topic_record)
            invalid["questionnaire_evidence"][0]["local_material_path"] = absolute_path
            expect_failure(
                checker, invalid, exploration_log, source_periods,
                "must be relative for topic scope", record_dir=topic_dir,
            )
        # Use existing files outside both roots so failure proves boundary checking.
        for scope, outside_path in (
            ("topic", "../CHARLS/" + questionnaire.name),
            ("topic", "..\\CHARLS\\" + questionnaire.name),
            ("skill", "../topic/materials/official_question.txt"),
        ):
            invalid = copy.deepcopy(topic_record)
            invalid["questionnaire_evidence"][0].update(
                local_material_scope=scope, local_material_path=outside_path,
            )
            expect_failure(
                checker, invalid, exploration_log, source_periods,
                "local_material_path must be under", record_dir=topic_dir,
            )
        for missing_file in ("materials/absent.txt", "materials"):
            invalid = copy.deepcopy(topic_record)
            invalid["questionnaire_evidence"][0]["local_material_path"] = missing_file
            expect_failure(
                checker, invalid, exploration_log, source_periods,
                "verified local material does not exist", record_dir=topic_dir,
            )
        outside_link = topic_dir / "outside_link"
        try:
            outside_link.symlink_to(local_root, target_is_directory=True)
        except OSError as error:
            if os.name != "nt":
                print(f"SKIP topic material symlink escape: {error}")
            else:
                # Junctions exercise resolved directory escapes without symlink privileges.
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command",
                     "New-Item -ItemType Junction -Path $env:TEST_MATERIAL_LINK "
                     "-Value $env:TEST_MATERIAL_TARGET -ErrorAction Stop | Out-Null"],
                    env={**os.environ, "TEST_MATERIAL_LINK": str(outside_link),
                         "TEST_MATERIAL_TARGET": str(local_root)},
                    check=True, capture_output=True,
                )
                print("Windows directory junction escape fixture enabled")
        if outside_link.is_dir():
            invalid = copy.deepcopy(topic_record)
            invalid["questionnaire_evidence"][0]["local_material_path"] = (
                "outside_link/" + questionnaire.name
            )
            expect_failure(
                checker, invalid, exploration_log, source_periods,
                "local_material_path must be under", record_dir=topic_dir,
            )

        omitted = copy.deepcopy(record)
        omitted['questionnaire_evidence'][0].update(display_required=False,
            display_omission_reason='直接保留已发布结果，定义逻辑已足以解释。',
            rendered_in_copy=False, copy_locator='不展示：直接保留已发布结果')
        assert checker.validate_questionnaire_evidence(omitted, exploration_log, source_periods,
            require_rendered=True) == result
        omitted['questionnaire_evidence'][0]['question_text'] = ''
        expect_failure(checker, omitted, exploration_log, source_periods, 'question_text', require_rendered=True)

        lexical_codes = copy.deepcopy(record)
        lexical_question = lexical_codes["questionnaire_evidence"][0]
        lexical_question["options"] = [{"value": "01", "label": "是"}, {"value": "02", "label": "否"}]
        lexical_question["skip_logic"][0]["when"] = "01 是"
        roundtrip = json.loads(json.dumps(lexical_codes))
        checker.validate_questionnaire_evidence(roundtrip, exploration_log, source_periods)
        assert [x["value"] for x in roundtrip["questionnaire_evidence"][0]["options"]] == ["01", "02"]
        roundtrip["questionnaire_evidence"][0]["options"][0]["value"] = 1
        expect_failure(checker, roundtrip, exploration_log, source_periods, ".value")

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

        # A result may cover fewer periods than its shared sources.
        scoped = copy.deepcopy(record)
        scoped["questionnaire_path_closure"] = scoped["questionnaire_path_closure"][:1]
        scoped_plan = copy.deepcopy(definition_plan)
        scoped_plan[0]["periods"] = ["2011"]
        assert checker.validate_questionnaire_path_closure(
            scoped, exploration_log, source_groups, approved_names, scoped_plan,
        ) == {"variable_periods": 1, "branches": 1}
        # Omitting scope retains legacy coverage; missing an in-scope path still fails.
        expect_path_failure(checker, scoped, exploration_log, source_groups,
                            approved_names, definition_plan, "does not match")
        missing_scoped = copy.deepcopy(scoped)
        missing_scoped["questionnaire_path_closure"] = []
        expect_path_failure(checker, missing_scoped, exploration_log, source_groups,
                            approved_names, scoped_plan, "questionnaire_path_closure")
        for periods, message in [([], "nonempty"), (["1900"], "outside"),
                                 (["2011", "2011"], "duplicates")]:
            invalid_plan = copy.deepcopy(scoped_plan)
            invalid_plan[0]["periods"] = periods
            expect_path_failure(checker, scoped, exploration_log, source_groups,
                                approved_names, invalid_plan, message)

        auxiliary = copy.deepcopy(record)
        auxiliary_groups = source_groups + [
            {"concept": "访谈身份", "periods": ["cross-wave"], "raw_variables": ["self_status"]},
            {"concept": "无关来源", "periods": ["cross-wave"], "raw_variables": ["unrelated"]},
        ]
        auxiliary_plan = copy.deepcopy(definition_plan)
        auxiliary_plan[0]["source_groups"].append("访谈身份")
        for path in auxiliary["questionnaire_path_closure"]:
            path["branches"][0]["required_raw_variables"].append("self_status")
        assert checker.validate_questionnaire_path_closure(
            auxiliary, exploration_log, auxiliary_groups, approved_names, auxiliary_plan,
        ) == path_result
        expect_path_failure(
            checker, auxiliary, exploration_log, auxiliary_groups, approved_names,
            definition_plan, "outside the relevant source groups",
        )
        auxiliary["questionnaire_path_closure"][0]["branches"][0]["required_raw_variables"].append("unrelated")
        expect_path_failure(
            checker, auxiliary, exploration_log, auxiliary_groups, approved_names,
            auxiliary_plan, "outside the relevant source groups",
        )

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
            "recording_mode": "contemporaneous",
            "dbcodebook_url": "http://localhost:8000/home/charls/", "searched_at": "2026-09-22",
            "directory_entries": [{"full_path": "Core data > Work", "verified_in_ui": True,
                "purpose": "Locate work questions"}],
            "normal_searches": [{"performed": True, "keyword": "work", "result": "FA002 and FA003"}],
            "logic_review": {**dict.fromkeys((*checker.REQUIRED_LOGIC_CHECKS, *checker.REQUIRED_V3_LOGIC_CHECKS, *checker.REQUIRED_V7_LOGIC_CHECKS), True), "result": "clear"},
            "logic_issues": [],
            "human_record": "exploration.md", "source_groups": source_groups,
            "approved_analysis_vars": approved_names, "definition_plan": definition_plan,
            "exploration_log": [{**exploration_log[0], "human_step_id": "S001",
                "input": "Official questionnaire FA002", "observed": "Two options and an exit route",
                "decision": "Retain both options", "reason": "Needed for the definition"}],
            "alias_families": [],
            "candidate_decisions": [{"concept": "work", "decision": "include",
                "selected_raw": ["fa002_p", "fa003_p"], "excluded_raw": [],
                "reason": "Direct work questions", "evidence_steps": [1]}],
            "evidence_reviews": [{
                "source_type": "official_questionnaire", "title": "Questionnaire",
                "locator": "FA002", "reviewed_at": "2026-09-04",
                "supports": "Question and routes", "does_not_support": "Observed counts",
                "decision_effect": "Plan the source list", "evidence_steps": [1],
            }],
        })
        download_record["source_groups"] = [{**source_groups[0],
            "detail_verified": True, "selection_reason": "Direct work evidence", "evidence_steps": [1],
            "period_comparison": [{"periods": ["2011", "2013"], "question_meaning": "Worked last week",
                "population": "Respondents", "reference_period": "Last week", "recording_and_coding": "Yes or no"}],
            "common_meaning": "Work status", "material_differences": [],
            "handling_decision": "merge", "handling_reason": "Same question and codes",
            "discovery": {"mode": "ordinary_search", "value": "work"}}]
        download_record["definition_plan"] = [{**definition_plan[0], "meaning": "Worked last week",
            "construction": "Combine direct work responses", "missing_and_jump": "Preserve nonresponse"}]
        record_path = Path(tmp) / "record.json"
        selection_path = Path(tmp) / "selection.txt"
        (Path(tmp) / "exploration.md").write_text("### S001\nReviewed question.\n", encoding="utf-8")
        record_path.write_text(json.dumps(download_record), encoding="utf-8")
        selection_path.write_text("fa002_p\nfa003_p\n", encoding="utf-8")
        assert checker.validate_download_selection(record_path, selection_path, "001")["ok"]

        # The public entrypoint supplies the record's own directory for topic scope.
        topic_download = copy.deepcopy(download_record)
        topic_download["questionnaire_evidence"] = copy.deepcopy(
            topic_record["questionnaire_evidence"]
        )
        topic_record_path = topic_dir / "definition_search_record.json"
        (topic_dir / "exploration.md").write_text(
            "### S001\nReviewed question.\n", encoding="utf-8"
        )
        topic_record_path.write_text(json.dumps(topic_download), encoding="utf-8")
        assert checker.validate_download_selection(
            topic_record_path, selection_path, "001"
        )["ok"]

        shared = copy.deepcopy(download_record)
        shared["candidate_decisions"].append({**copy.deepcopy(shared["candidate_decisions"][0]), "concept": "shared_work_source"})
        shared["source_groups"].append({**copy.deepcopy(shared["source_groups"][0]), "concept": "shared_work_source"})
        for question in download_record["questionnaire_evidence"]:
            shared["questionnaire_evidence"].append({**copy.deepcopy(question),
                "source_group": "shared_work_source", "evidence_id": question["evidence_id"] + "_shared"})
        for coverage in download_record["questionnaire_coverage"]:
            shared["questionnaire_coverage"].append({**copy.deepcopy(coverage),
                "source_group": "shared_work_source",
                "evidence_ids": [value + "_shared" for value in coverage.get("evidence_ids", [])]})
        record_path.write_text(json.dumps(shared), encoding="utf-8")
        assert checker.validate_download_selection(record_path, selection_path, "001")["variables"] == 2

        duplicate = copy.deepcopy(shared)
        duplicate["candidate_decisions"][0]["selected_raw"] *= 2
        record_path.write_text(json.dumps(duplicate), encoding="utf-8")
        try:
            checker.validate_download_selection(record_path, selection_path, "001")
        except ValueError as error:
            assert "within one concept" in str(error)
        else:
            raise AssertionError("Within-concept duplicates were accepted")

        invalid_action = copy.deepcopy(download_record)
        invalid_action["exploration_log"][0]["action"] = "normal_search_and_detail"
        record_path.write_text(json.dumps(invalid_action), encoding="utf-8")
        try:
            checker.validate_download_selection(record_path, selection_path, "001")
        except ValueError as error:
            assert "exploration_log[1].action" in str(error)
        else:
            raise AssertionError("Invalid action was deferred until the post-download check")

        invalid_discovery = copy.deepcopy(download_record)
        invalid_discovery["source_groups"][0]["discovery"]["mode"] = "normal_search"
        record_path.write_text(json.dumps(invalid_discovery), encoding="utf-8")
        try:
            checker.validate_download_selection(record_path, selection_path, "001")
        except ValueError as error:
            assert "discovery.mode" in str(error)
        else:
            raise AssertionError("Invalid discovery was deferred until the post-download check")

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

        # Unknown nonessential field routing does not remove result closure gates.
        unknown_closed = copy.deepcopy(record)
        unknown_closed["questionnaire_evidence"][0].update(
            skip_logic_status="unknown", skip_logic=[],
            unverified_nonessential_routes="当前仅采用直接值，未记录的现场退出不参与定义。",
        )
        checker.validate_questionnaire_path_closure(
            unknown_closed, exploration_log, source_groups, approved_names, definition_plan)
        no_observed = copy.deepcopy(unknown_closed)
        no_observed["questionnaire_path_closure"][0]["branches"][0]["observed_count"] = None
        expect_path_failure(checker, no_observed, exploration_log, source_groups,
                            approved_names, definition_plan, "observed_count")
        no_plan_branch = copy.deepcopy(unknown_closed)
        no_plan_branch["questionnaire_path_closure"][0]["branches"] = []
        expect_path_failure(checker, no_plan_branch, exploration_log, source_groups,
                            approved_names, definition_plan, "branches must not be empty")
        print("unknown routing: actual counts and planned branch closure remain required PASS")

    print("questionnaire evidence gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
