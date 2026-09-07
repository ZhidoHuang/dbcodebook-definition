from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
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
    note_text = note_path.read_text(encoding="utf-8-sig")
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


def sync_command(formal: Path, process: Path, *, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "verify-ready", "--formal-dir", str(formal),
         "--process-dir", str(process), "--topic-id", "025", "--start-sync",
         "--database", "charls", "--topic-name", "家庭支持",
         "--website-title", "025 CHARLS — 家庭支持（Family Support）",
         "--post-id", "221", "--base-url", "http://localhost:8000"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert (result.returncode == 0) == ok, result.stderr or result.stdout
    return result


def prepare_sync_command(formal: Path, process: Path) -> subprocess.CompletedProcess[str]:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "execution_report.py"), "website-prepare",
         "--process-dir", str(process), "--database", "charls", "--topic-id", "025",
         "--topic-name", "家庭支持"],
        check=True, capture_output=True,
    )
    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "verify-ready", "--formal-dir", str(formal),
         "--process-dir", str(process), "--topic-id", "025",
         "--database", "charls", "--topic-name", "家庭支持",
         "--website-title", "025 CHARLS — 家庭支持（Family Support）",
         "--post-id", "221", "--base-url", "http://localhost:8000"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result


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
            if role == "note":
                content += "\U0001f4d6\n"
                (formal / name).write_text(content, encoding="utf-8-sig", newline="\r\n")
            else:
                (formal / name).write_text(content, encoding="utf-8")

        complete_impact(checker, formal, process)
        checker.initialize_audit(formal, process, "025", files)
        audit_path = process / checker.AUDIT_NAME
        complete_audit(checker, audit_path)
        checker.initialize_reader_review(
            formal, process, "025", files["note"]
        )
        draft = json.loads((process / checker.READER_REVIEW_NAME).read_text(encoding="utf-8"))
        source_blocks = checker.reader_review_block_sources((formal / files["note"]).read_text(encoding="utf-8-sig"))
        assert draft["status"] == "DRAFT"
        for block, source in zip(draft["blocks"], source_blocks, strict=True):
            assert block["source_text"] == checker.normalized_visible_text(source["review_text"])
            assert block["original_excerpt"] in block["source_text"]
            assert block["result"] == "pending" and not block["plain_paraphrase"]
        expect_failure(lambda: checker.validate_audit(formal, process, "025"), "status")
        complete_reader_review(checker, formal, process)
        result = checker.validate_audit(formal, process, "025")
        assert result["status"] == "PUBLISH_READY"
        assert result["scope_count"] == len(checker.REQUIRED_SCOPES)
        assert result["finding_count"] == 1
        verified = checker.verify_existing_readiness(formal, process, "025")
        assert verified["status"] == "PUBLISH_READY_VERIFIED"
        upload = verified["upload"]
        expected_body = (formal / files["note"]).read_text(encoding="utf-8-sig")
        assert upload["note"] == str((formal / files["note"]).resolve())
        assert upload["body_check"]["length_utf16"] == len(expected_body) + 1
        assert upload["body_check"]["head"] == expected_body[:160]
        assert upload["body_check"]["tail"] == expected_body[-150:]
        assert "\r" not in upload["body_check"]["head"]
        assert [item["role"] for item in upload["attachments"]] == ["analysis_db", "analysis_codebook"]
        assert all(Path(item["path"]).is_absolute() for item in upload["attachments"])
        assert not (process / "execution_report.json").exists()

        missing_browser_target = subprocess.run(
            [sys.executable, str(CHECKER_PATH), "verify-ready",
             "--formal-dir", str(formal), "--process-dir", str(process),
             "--topic-id", "025", "--start-sync",
             "--database", "CHARLS", "--topic-name", "家庭支持"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        assert missing_browser_target.returncode != 0
        assert "--post-id and --base-url" in missing_browser_target.stderr
        assert not (process / "execution_report.json").exists()

        unchanged = {name: (formal / name).read_bytes() for name in files.values()}
        readiness_bytes = (process / checker.REPORT_NAME).read_bytes()
        prepared = json.loads(prepare_sync_command(formal, process).stdout)
        prepared_action = prepared["browser_action"]
        assert "preload_script" in prepared_action
        assert "run_script" not in prepared_action
        preparation = json.loads((process / "execution_report.json").read_text(encoding="utf-8"))
        assert preparation["stages"][0]["stage_id"] == "website_preparation"
        assert preparation["stages"][0]["status"] == "running"

        started = json.loads(sync_command(formal, process).stdout)
        assert "upload" not in started
        browser_action = started["browser_action"]
        assert browser_action["payload"]["sync_run_id"] == started["execution"]["run_id"]
        assert browser_action["payload"]["sync_attempt"] == started["execution"]["attempt"]
        assert "preload_script" not in browser_action
        assert "run_script" in browser_action
        assert browser_action["preload_sha256"] == prepared_action["preload_sha256"]
        assert browser_action["existing_tab_match"] == [
            "http://localhost:8000/nodes/post/221/",
            "http://localhost:8000/nodes/edit/221/",
        ]
        assert browser_action["payload"]["expected_title_parts"] == [
            "025", "charls", "家庭支持"
        ]
        assert browser_action["payload"]["identity_title_parts"] == ["025", "charls"]
        assert browser_action["payload"]["desired_title"] == (
            "025 CHARLS — 家庭支持（Family Support）"
        )
        assert browser_action["payload"]["note"] == upload["note"]
        assert browser_action["payload"]["body_check"] == upload["body_check"]
        assert browser_action["payload"]["dispatch_limit_ms"] == 60000
        assert [item["name"] for item in browser_action["payload"]["attachments"]] == [
            "analysis_db.xlsx", "analysis_codebook.xlsx"
        ]
        preload_script = prepared_action["preload_script"]
        assert 'chooser.setFiles([filePath])' in preload_script
        assert 'for (const attachment of payload.attachments)' in preload_script
        assert 'const titleDeadline = Date.now() + 5000' in preload_script
        assert 'titleValue.toLocaleLowerCase().includes(String(part).toLocaleLowerCase())' in preload_script
        assert 'await title.fill(payload.desired_title)' in preload_script
        assert 'button[title="删除"]' in preload_script
        assert 'body.length !== payload.body_check.length_utf16' in preload_script
        assert 'JSON.stringify(actualNames) !== JSON.stringify(expectedNames)' in preload_script
        assert 'getByRole("button", { name: "更新文章" })' in preload_script
        assert 'timings.open_edit_ms' in preload_script
        assert 'timings.identity_check_ms' in preload_script
        assert 'timings.title_update_ms' in preload_script
        assert 'timings.body_import_ms' in preload_script
        assert 'timings.attachments_ms' in preload_script
        assert 'timings.submit_and_return_ms' in preload_script
        assert 'dispatchLatencyMs > payload.dispatch_limit_ms' in preload_script
        assert 'dispatch_latency_ms: dispatchLatencyMs' in preload_script
        assert 'sync_elapsed_to_browser_return_ms' in preload_script
        assert 'quality_checks' in preload_script
        run_script = browser_action["run_script"]
        assert 'await syncDbCodeBookPost(tab, dbCodeBookSyncPayload)' in run_script
        assert len(run_script) < len(preload_script) // 2
        assert browser_action["payload"]["sync_started_at"] == started["execution"]["started_at"]
        assert "setInputFiles" not in preload_script
        created = checker.build_cua_sync_action(
            upload, "http://localhost:8000", "", "CHARLS", "025", "家庭支持",
            "025 CHARLS 家庭支持", create=True, directory_tag="medical",
        )
        assert created["payload"]["post_id"] == ""
        assert created["payload"]["post_url"] is None
        assert created["existing_tab_match"] == ["http://localhost:8000/nodes/edit/"]
        assert created["payload"]["directory_tag"] == "medical"
        assert created["preload_sha256"] == prepared_action["preload_sha256"]
        assert 'if (blank.title || blank.body || blank.attachments)' in preload_script
        assert 'name: /发布文章/' in preload_script
        assert 'state: "domcontentloaded"' in preload_script
        assert 'timeoutMs: 30000' in preload_script
        assert 'post_url: postUrl' in preload_script
        node = shutil.which("node")
        if node:
            category_code = preload_script.split("const categoryOptions =", 1)[1].split(
                'await tab.playwright.locator("#tags-input")', 1
            )[0]
            category_test = r'''
const assert = require("node:assert/strict");
async function selectDatabase(database, options) {
  const payload = { database };
  let selected;
  const tab = { playwright: {
    evaluate: async () => options,
    locator: () => ({ selectOption: async option => { selected = option.value; } })
  } };
  CATEGORY_CODE
  return selected;
}
(async () => {
  const options = [{label: "CHARLS", value: "1"}, {label: "KLoSA", value: "2"}];
  assert.equal(await selectDatabase("CHARLS", options), "1");
  assert.equal(await selectDatabase(" charls ", options), "1");
  assert.equal(await selectDatabase("klosa", options), "2");
  await assert.rejects(selectDatabase("ELSA", options));
  await assert.rejects(selectDatabase("charls", [...options, options[0]]));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''.replace("CATEGORY_CODE", "const categoryOptions =" + category_code)
            subprocess.run([node, "-e", category_test], check=True)
        else:
            print("SKIP category JavaScript runtime fixture: Node.js unavailable")
        expect_failure(
            lambda: checker.build_cua_sync_action(
                upload, "http://localhost:8000", "221", "CHARLS", "025", "家庭支持",
                "025 CHARLS 家庭支持", create=True, directory_tag="medical",
            ),
            "cannot be combined",
        )
        expect_failure(
            lambda: checker.build_cua_sync_action(
                upload, "http://localhost:8000", "", "CHARLS", "025", "家庭支持",
                "025 CHARLS 家庭支持", create=True,
            ),
            "requires --website-title and --directory-tag",
        )
        expect_failure(
            lambda: checker.build_cua_sync_action(
                upload, "localhost:8000", "221", "CHARLS", "025", "家庭支持"
            ),
            "absolute http or https URL",
        )
        expect_failure(
            lambda: checker.build_cua_sync_action(
                upload, "http://localhost:8000", "0", "CHARLS", "025", "家庭支持"
            ),
            "positive integer",
        )
        expect_failure(
            lambda: checker.build_cua_sync_action(
                upload, "http://localhost:8000", "221", "CHARLS", "025", "家庭支持",
                "025 CHARLS — Other Topic",
            ),
            "must contain the topic id, database and topic name",
        )
        report_path = process / "execution_report.json"
        execution = json.loads(report_path.read_text(encoding="utf-8"))
        assert execution["status"] == "running"
        assert execution["stages"][0]["stage_id"] == "website_preparation"
        assert execution["stages"][1]["stage_id"] == "website_sync"
        assert started["execution"]["started_at"] == execution["stages"][1]["started_at"]
        repeated = json.loads(sync_command(formal, process).stdout)
        assert repeated["execution"] == started["execution"]
        assert len(json.loads(report_path.read_text(encoding="utf-8"))["stages"]) == 2
        assert {name: (formal / name).read_bytes() for name in files.values()} == unchanged
        assert (process / checker.REPORT_NAME).read_bytes() == readiness_bytes

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
        report_bytes_before_failed_preflight = report_path.read_bytes()
        failed = sync_command(formal, process, ok=False)
        assert "audit is stale" in failed.stderr
        assert report_path.read_bytes() == report_bytes_before_failed_preflight

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
        original_reader = reader_path.read_bytes()
        (formal / files["analysis_db"]).write_bytes(b"changed data fixture")
        result = checker.initialize_audit(
            formal, process, "025", files, overwrite=True, preserve_reader=True
        )
        assert result["reader_review_preserved"]
        assert reader_path.read_bytes() == original_reader
        assert not (process / checker.REPORT_NAME).exists()
        complete_audit(checker, audit_path)
        checker.validate_audit(formal, process, "025")

        note_path = formal / files["note"]
        original_note = note_path.read_bytes()
        note_path.write_bytes(original_note + b"\nchanged reader text\n")
        expect_failure(
            lambda: checker.initialize_audit(
                formal, process, "025", files, overwrite=True, preserve_reader=True
            ),
            "final note changed",
        )
        note_path.write_bytes(original_note)
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
