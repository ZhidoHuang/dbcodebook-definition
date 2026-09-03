from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_readability.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_readability_for_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_readability.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def complete_impact(checker, formal: Path, process: Path) -> None:
    checker.initialize_impact(process, "025")
    copy = formal / checker.READER_COPY_NAME
    question = "过去一年，您或您的配偶从父母那里得到过经济支持吗？"
    copy.write_text(
        "## 摘要导读\n"
        f"问卷询问：\"{question}\"这道题用于判断家庭是否从父母获得支持。\n\n"
        "## Criteria\n逐项说明定义规则、缺失和适用范围。\n\n"
        "## 小book提示\n说明同时影响多个变量的调查边界。\n\n"
        "## 参考资料说明\n说明每份材料支持的事实和边界。\n",
        encoding="utf-8",
    )
    impact_path = process / checker.IMPACT_NAME
    impact = checker.json.loads(impact_path.read_text(encoding="utf-8"))
    impact["status"] = checker.IMPACT_PASS_STATUS
    impact["reviewed_at"] = "2026-08-12T03:00:00+08:00"
    impact["reviewer"] = "definition change reviewer"
    impact["change_summary"] = (
        "新增父母支持定义变量，并同步调整综合支持的组成和跨期解释范围。"
    )
    impact["changed_dimensions"] = [
        "variable_set",
        "questionnaire_scope",
        "public_r",
    ]
    impact["question_groups"] = [
        {
            "name": "从父母获得经济支持",
            "periods": ["2011"],
            "respondent": "家庭问卷答题人与配偶",
            "official_source": "2011 年官方家户问卷，第 48 页",
            "question_mode": "verified_quote",
            "question_text": question,
            "paraphrase_reason": "",
            "definition_use": "用于判断家庭是否从父母获得支持",
            "draft_location": "摘要导读 > 2011 年",
            "result": "pass",
        }
    ]
    for surface in impact["surfaces"]:
        surface["result"] = "pass"
        surface["evidence"] = (
            f"已核对 {surface['label']}，并记录本次变更的实际影响和同步结果。"
        )
    checker.write_json(impact_path, impact)


def complete_audit(checker, audit_path: Path) -> None:
    audit = checker.json.loads(audit_path.read_text(encoding="utf-8"))
    audit["status"] = checker.PASS_STATUS
    audit["audited_at"] = "2026-08-12T03:30:00+08:00"
    audit["reviewer"] = "definition task full-text pass"
    audit["full_read_confirmation"] = (
        "已按最终拼装顺序从标题读到文献引用，并重新核对公开 R 注释。"
    )
    for scope in audit["scopes"]:
        scope["result"] = "pass"
        scope["evidence"] = f"已逐段核对 {scope['label']}，当前表述可以独立理解。"
        if scope["name"] == "public_r_comments":
            scope["code_walkthrough"] = [
                {
                    "location": "读取原始数据并检查回答",
                    "input": "问卷原始回答和原始金额列",
                    "action": "先用 table 查看回答，再按问卷编码逐项转换",
                    "output": "含义明确的中间变量",
                    "plain_paraphrase": "先看清原始答案，再把每种答案翻译成分析值。",
                    "result": "pass",
                },
                {
                    "location": "生成定义变量并保存结果",
                    "input": "已经整理好的中间变量",
                    "action": "按照 Criteria 合并并生成最终定义结果",
                    "output": "正式分析表和变量字典",
                    "plain_paraphrase": "把前面整理好的答案按规则合成最终变量。",
                    "result": "pass",
                },
            ]
    audit["scopes"][0]["findings"] = [
        {
            "location": "摘要第一段",
            "problem": "来源和结果之间缺少衔接",
            "resolution": "补充先定义什么、再说明来源组成的过渡句",
        }
    ]
    checker.write_json(audit_path, audit)


def complete_reader_review(
    checker,
    formal: Path,
    process: Path,
    reviewer: str = "ordinary reader task",
) -> None:
    review_path = process / checker.READER_REVIEW_NAME
    review = checker.json.loads(review_path.read_text(encoding="utf-8"))
    note_path = formal / review["note"]["path"]
    note_text = note_path.read_text(encoding="utf-8")
    sources = {
        item["name"]: checker.normalized_visible_text(item["review_text"])
        for item in checker.reader_review_block_sources(note_text)
    }
    review["status"] = checker.READER_REVIEW_PASS_STATUS
    review["reviewed_at"] = "2026-08-12T04:00:00+08:00"
    review["reviewer"] = reviewer
    review["reader_only_confirmation"] = (
        "我只阅读最终笔记的可见文字，没有先看代码、数据、探索记录或作者说明。"
    )
    for block in review["blocks"]:
        source = sources[block["name"]]
        block["result"] = "pass"
        block["original_excerpt"] = source[: min(40, len(source))]
        block["plain_paraphrase"] = (
            "这段说明调查具体问了什么，以及这些回答最后怎样变成分析变量。"
        )
        block["who_when_what"] = (
            "答题人在相应调查时期回答问题，项目据此生成对应的分析结果。"
        )
        block["possible_confusion"] = (
            "读者可能分不清调查原题和项目后续处理之间的关系。"
        )
        block["resolution"] = (
            "当前文字已经分别交代原题、适用条件和最终处理。"
        )
    checker.write_json(review_path, review)


def expect_failure(action, contains: str) -> None:
    try:
        action()
    except ValueError as error:
        assert contains in str(error), str(error)
    else:
        raise AssertionError(f"Expected failure containing: {contains}")


def main() -> int:
    checker = load_checker()
    with tempfile.TemporaryDirectory(prefix="readability_gate_") as tmp:
        root = Path(tmp)
        formal = root / "formal"
        process = root / "process"
        formal.mkdir()
        files = {
            "note": "note.md",
            "public_r": "define.R",
            "analysis_db": "analysis_db.xlsx",
            "analysis_codebook": "analysis_codebook.xlsx",
        }
        for role, name in files.items():
            content = (
                "## 摘要导读\n"
                "本主题说明家庭是否从父母获得经济支持，以及最后怎样生成分析变量。\n\n"
                "## 定义\n"
                if role == "note"
                else f"fixture for {role}\n"
            )
            (formal / name).write_text(content, encoding="utf-8")

        complete_impact(checker, formal, process)
        checker.initialize_audit(formal, process, "025", files)
        audit_path = process / checker.AUDIT_NAME
        complete_audit(checker, audit_path)
        checker.initialize_reader_review(
            formal, process, "025", files["note"]
        )
        complete_reader_review(checker, formal, process)
        result = checker.validate_audit(formal, process, "025")
        assert result["status"] == "PUBLISH_READY"
        assert result["scope_count"] == len(checker.REQUIRED_SCOPES)
        assert result["finding_count"] == 1
        verified = checker.verify_existing_readiness(formal, process, "025")
        assert verified["status"] == "PUBLISH_READY_VERIFIED"

        (formal / files["note"]).write_text(
            "## 摘要导读\n"
            "修改后的笔记仍然完整说明调查对象、问题内容和分析变量的生成方式。\n\n"
            "## 定义\n",
            encoding="utf-8",
        )
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "audit is stale",
        )
        expect_failure(
            lambda: checker.verify_existing_readiness(formal, process, "025"),
            "audit is stale",
        )

        checker.initialize_audit(formal, process, "025", files, overwrite=True)
        complete_audit(checker, audit_path)
        audit = checker.json.loads(audit_path.read_text(encoding="utf-8"))
        public_r_scope = next(
            scope
            for scope in audit["scopes"]
            if scope["name"] == "public_r_comments"
        )
        public_r_scope["code_walkthrough"] = []
        checker.write_json(audit_path, audit)
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "public R code walkthrough is required",
        )

        checker.initialize_audit(formal, process, "025", files, overwrite=True)
        complete_audit(checker, audit_path)
        audit = checker.json.loads(audit_path.read_text(encoding="utf-8"))
        audit["scopes"] = audit["scopes"][:-1]
        checker.write_json(audit_path, audit)
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "scopes mismatch",
        )

        checker.initialize_audit(formal, process, "025", files, overwrite=True)
        complete_audit(checker, audit_path)
        audit = checker.json.loads(audit_path.read_text(encoding="utf-8"))
        audit["unresolved_issues"] = ["文献边界仍未核清"]
        checker.write_json(audit_path, audit)
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "unresolved_issues must be empty",
        )

        checker.initialize_audit(formal, process, "025", files, overwrite=True)
        complete_audit(checker, audit_path)
        checker.initialize_reader_review(
            formal, process, "025", files["note"]
        )
        complete_reader_review(
            checker,
            formal,
            process,
            reviewer="definition task full-text pass",
        )
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "must differ from the author reviewer",
        )

        complete_reader_review(checker, formal, process)
        reader_path = process / checker.READER_REVIEW_NAME
        reader = checker.json.loads(reader_path.read_text(encoding="utf-8"))
        reader["blocks"] = reader["blocks"][:-1]
        checker.write_json(reader_path, reader)
        expect_failure(
            lambda: checker.validate_audit(formal, process, "025"),
            "blocks must match the final visible note in order",
        )

        checker.initialize_impact(process, "025", overwrite=True)
        bad_copy = formal / checker.READER_COPY_NAME
        bad_copy.write_text(
            "## 摘要导读\n这里只有概括，没有核对过的原题。\n\n"
            "## Criteria\n定义规则。\n\n"
            "## 小book提示\n主题边界。\n\n"
            "## 参考资料说明\n材料支持的事实和边界。\n",
            encoding="utf-8",
        )
        bad_impact_path = process / checker.IMPACT_NAME
        bad_impact = checker.json.loads(
            bad_impact_path.read_text(encoding="utf-8")
        )
        bad_impact["status"] = checker.IMPACT_PASS_STATUS
        bad_impact["reviewed_at"] = "2026-08-12T05:00:00+08:00"
        bad_impact["reviewer"] = "definition change reviewer"
        bad_impact["change_summary"] = "新增父母支持问卷题组并改变综合变量的组成范围。"
        bad_impact["changed_dimensions"] = ["questionnaire_scope"]
        bad_impact["question_groups"] = [
            {
                "name": "从父母获得经济支持",
                "periods": ["2011"],
                "respondent": "家庭问卷答题人与配偶",
                "official_source": "2011 年官方家户问卷，第 48 页",
                "question_mode": "verified_quote",
                "question_text": "过去一年是否从父母获得经济支持？",
                "paraphrase_reason": "",
                "definition_use": "用于判断是否发生父母支持",
                "draft_location": "摘要导读 > 2011 年",
                "result": "pass",
            }
        ]
        for surface in bad_impact["surfaces"]:
            surface["result"] = "pass"
            surface["evidence"] = (
                f"已核对 {surface['label']}，并记录实际影响和同步范围。"
            )
        checker.write_json(bad_impact_path, bad_impact)
        expect_failure(
            lambda: checker.validate_impact(formal, process, "025"),
            "text is not present",
        )

    print("definition readability gate fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
