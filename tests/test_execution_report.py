import json
import copy
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_report


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "execution_report.py"


def expect_system_exit(action, contains: str) -> None:
    try:
        action()
    except SystemExit as error:
        assert contains in str(error), str(error)
    else:
        raise AssertionError(f"expected SystemExit containing {contains!r}")


full_report = {
    "workflow": "full_definition",
    "started_at": "2026-09-08T10:00:00+08:00",
    "stages": [
        {
            "stage_id": stage_id,
            "status": "completed",
            "started_at": f"2026-09-08T10:0{index}:00+08:00",
            "finished_at": f"2026-09-08T10:0{index + 1}:00+08:00",
        }
        for index, stage_id in enumerate(execution_report.FULL_DEFINITION_STAGES)
    ],
    "reviews": [
        {"role": role, "closed": True, "unfinished_turns": 0}
        for role in execution_report.FULL_DEFINITION_REVIEW_ROLES
    ],
}
full_end = execution_report.parse_time("2026-09-08T10:05:00+08:00")
execution_report.validate_full_definition_completion(full_report, full_end)
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "execution_report.json"
    for variant, expected in (({**full_report, "finished_at": execution_report.iso(full_end)}, 0),
                              ({**full_report, "finished_at": execution_report.iso(full_end), "stages": []}, 1),
                              (full_report, 1),
                              ({"workflow": "general"}, 1)):
        path.write_text(json.dumps(variant), encoding="utf-8")
        before = path.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "check", "--report", str(path)],
                                capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == expected, result.stderr
        assert path.read_bytes() == before
        assert list(Path(folder).iterdir()) == [path]
        if expected == 0:
            receipt = json.loads(result.stdout)
            assert receipt["scope"] == "registration_only"
            assert receipt["historical_quality_verified"] is False
split_report = copy.deepcopy(full_report)
production = next(s for s in split_report["stages"] if s["stage_id"] == "formal_r")
split_report["stages"].remove(production)
for index, stage_id in enumerate(("copy", "public_r", "generate")):
    split_report["stages"].append({**production, "stage_id": stage_id,
        "started_at": f"2026-09-08T10:03:{index * 20:02d}+08:00",
        "finished_at": (f"2026-09-08T10:03:{(index + 1) * 20:02d}+08:00"
                        if index < 2 else "2026-09-08T10:04:00+08:00")})
execution_report.validate_full_definition_completion(split_report, full_end)
split_report["stages"].pop()
expect_system_exit(lambda: execution_report.validate_full_definition_completion(split_report, full_end), "generate")
split_validation = copy.deepcopy(full_report)
validation = next(s for s in split_validation["stages"] if s["stage_id"] == "validation")
split_validation["stages"].remove(validation)
for stage_id in ("results", "review"):
    split_validation["stages"].append({**validation, "stage_id": stage_id})
execution_report.validate_full_definition_completion(split_validation, full_end)
split_validation["stages"].pop()
expect_system_exit(lambda: execution_report.validate_full_definition_completion(split_validation, full_end), "review")
skipped_stage = copy.deepcopy(full_report)
skipped_stage["stages"][2]["status"] = "skipped"
skipped_stage["stages"][2]["summary"] = ["来源未变化，不重复下载。"]
execution_report.validate_full_definition_completion(skipped_stage, full_end)
unexplained_skip = copy.deepcopy(skipped_stage)
unexplained_skip["stages"][2]["summary"] = []
expect_system_exit(
    lambda: execution_report.validate_full_definition_completion(
        unexplained_skip, full_end
    ),
    "未执行环节没有说明原因",
)
missing_stage = copy.deepcopy(full_report)
missing_stage["stages"] = [
    stage for stage in missing_stage["stages"] if stage["stage_id"] != "download"
]
expect_system_exit(
    lambda: execution_report.validate_full_definition_completion(
        missing_stage, full_end
    ),
    "download",
)
missing_review = copy.deepcopy(full_report)
missing_review["reviews"] = missing_review["reviews"][:-1]
expect_system_exit(
    lambda: execution_report.validate_full_definition_completion(
        missing_review, full_end
    ),
    "缺少已完成审核",
)
execution_report.validate_full_definition_completion(
    full_report, execution_report.parse_time("2026-09-08T10:08:00+08:00"))
assert full_report["timing_coverage"]["status"] == "incomplete"
assert full_report["timing_coverage"]["untracked_seconds"] == 180


def browser_result(process_dir: Path) -> Path:
    report = json.loads((process_dir / "execution_report.json").read_text(encoding="utf-8"))
    stage = execution_report.latest_stage(report, "website_sync")
    path = process_dir / "browser-result.json"
    path.write_text(json.dumps({
        "ok": True, "status": "ARTICLE_PAGE_RETURNED", "sync_run_id": report["run_id"],
        "sync_attempt": stage["attempt"], "sync_started_at": stage["started_at"],
        "preload_sha256": "0" * 64,
        "dispatch_latency_ms": 0, "browser_elapsed_ms": 0,
        "sync_elapsed_to_browser_return_ms": 0,
        "quality_checks": {key: True for key in ("edit_url_verified", "title_verified", "body_verified",
                                                "attachment_order_verified", "article_page_returned")},
    }), encoding="utf-8")
    return path


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if ok and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    if not ok and result.returncode == 0:
        raise AssertionError("command unexpectedly succeeded")
    return result


with tempfile.TemporaryDirectory() as temp_dir:
    run(
        "init",
        "--process-dir", temp_dir,
        "--database", "CHARLS",
        "--topic-id", "036",
        "--topic-name", "工作属性",
        "--task", "前向验收",
        "--workflow", "general",
    )
    run(
        "stage-start",
        "--process-dir", temp_dir,
        "--stage-id", "source",
        "--name", "来源核对",
        "--role", "主执行者",
        "--model", "test-model",
    )
    run(
        "issue",
        "--process-dir", temp_dir,
        "--stage-id", "source",
        "--kind", "bug",
        "--description", "发现旧别名",
        "--impact", "旧 R 无法读取新 raw",
        "--resolution", "重新编写 R",
        "--status", "resolved",
    )
    run(
        "issue-amend",
        "--process-dir", temp_dir,
        "--issue-number", "1",
        "--description", "发现并修正旧别名",
        "--note", "原问题描述不完整",
    )
    run(
        "stage-finish",
        "--process-dir", temp_dir,
        "--stage-id", "source",
        "--status", "completed_with_issues",
        "--summary", "核对最终来源",
        "--output", "raw_data.csv",
    )
    run(
        "finish",
        "--process-dir", temp_dir,
        "--status", "completed_with_issues",
        "--summary", "测试完成",
    )

    report_path = Path(temp_dir) / "execution_report.json"
    markdown_path = Path(temp_dir) / "执行报告.md"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert report["status"] == "completed_with_issues"
    assert report["stages"][0]["elapsed_seconds"] >= 0
    assert report["issues"][0]["status"] == "resolved"
    assert report["issues"][0]["description"] == "发现并修正旧别名"
    assert report["issues"][0]["amendments"][0]["previous"]["description"] == "发现旧别名"
    assert "来源核对" in markdown
    assert "发现并修正旧别名" in markdown
    assert "总耗时" in markdown

    duplicate = run(
        "stage-start",
        "--process-dir", temp_dir,
        "--stage-id", "late",
        "--name", "不应开始",
        "--role", "测试",
        ok=False,
    )
    assert "已经结束" in duplicate.stderr

    previous_id = report["run_id"]
    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "重新运行",
        "--workflow", "general")
    archived = Path(temp_dir) / "archived_runs" / previous_id / "execution_report.json"
    assert not archived.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["continued_from_run"] == previous_id
    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "覆盖",
        "--workflow", "general", ok=False)
    run("stage-start", "--process-dir", temp_dir, "--stage-id", "fix",
        "--name", "修复", "--role", "主执行者", "--mode", "rework")
    run("stage-start", "--process-dir", temp_dir, "--stage-id", "fix",
        "--name", "重复", "--role", "主执行者", ok=False)
    run("issue", "--process-dir", temp_dir, "--stage-id", "fix", "--kind", "wait",
        "--description", "等待输入", "--status", "open")
    run("stage-finish", "--process-dir", temp_dir, "--stage-id", "fix",
        "--status", "completed_with_issues")
    blocked = run("finish", "--process-dir", temp_dir,
                  "--status", "completed_with_issues", ok=False)
    assert "未解决" in blocked.stderr
    run("issue-amend", "--process-dir", temp_dir, "--issue-number", "1",
        "--status", "resolved", "--note", "等待结束")
    run("finish", "--process-dir", temp_dir, "--status", "completed", ok=False)
    run("finish", "--process-dir", temp_dir, "--status", "completed_with_issues",
        "--summary", "当前执行结果")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "返工" in markdown and "等待：1" in markdown
    assert "当前执行结果" in markdown

with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    execution_report.begin_website_preparation(root, "CHARLS", "036", "工作属性")
    started = execution_report.begin_website_sync(root, "CHARLS", "036", "工作属性")
    same = execution_report.begin_website_sync(root, "charls", "036", "工作属性")
    assert same == started
    report_path = root / "execution_report.json"
    before = report_path.read_bytes()
    try:
        execution_report.begin_website_sync(root, "ELSA", "036", "工作属性")
    except ValueError as error:
        assert "不一致" in str(error)
    else:
        raise AssertionError("wrong database unexpectedly accepted")
    assert report_path.read_bytes() == before
    run("stage-finish", "--process-dir", temp_dir, "--stage-id", "website_sync",
        "--status", "completed", ok=False)
    inline_result = browser_result(root).read_text(encoding="utf-8")
    run("website-finish", "--process-dir", temp_dir, "--result-json", inline_result)
    saved_result = root / "website_sync_result.json"
    assert json.loads(saved_result.read_text(encoding="utf-8")) == json.loads(inline_result)
    run("finish", "--process-dir", temp_dir, "--status", "completed")
    finished = report_path.read_bytes()
    restarted = execution_report.begin_website_preparation(root, "CHARLS", "036", "工作属性")
    assert restarted["run_id"] != started["run_id"]
    archive = root / "archived_runs" / started["run_id"] / "execution_report.json"
    assert not archive.exists()

with tempfile.TemporaryDirectory() as temp_dir:
    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "完整定义",
        "--workflow", "general")
    run("stage-start", "--process-dir", temp_dir, "--stage-id", "formal_r",
        "--name", "正在运行R", "--role", "主执行者")
    report_path = Path(temp_dir) / "execution_report.json"
    before = report_path.read_bytes()
    try:
        execution_report.begin_website_sync(Path(temp_dir), "CHARLS", "036", "工作属性")
    except ValueError as error:
        assert "其它实际工作环节" in str(error)
    else:
        raise AssertionError("unfinished production stage unexpectedly accepted")
    assert report_path.read_bytes() == before
    run("stage-finish", "--process-dir", temp_dir, "--stage-id", "formal_r",
        "--status", "completed")
    original = json.loads(report_path.read_text(encoding="utf-8"))
    execution_report.begin_website_preparation(Path(temp_dir), "CHARLS", "036", "工作属性")
    sync = execution_report.begin_website_sync(Path(temp_dir), "CHARLS", "036", "工作属性")
    current = json.loads(report_path.read_text(encoding="utf-8"))
    assert sync["run_id"] == original["run_id"]
    assert current["stages"][0] == original["stages"][0]
    assert current["stages"][1]["stage_id"] == "website_preparation"
    assert current["stages"][2]["stage_id"] == "website_sync"

with tempfile.TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    log = root / "review.jsonl"
    events = [
        {"type": "session_meta", "payload": {"id": "agent-1", "timestamp": "2025-12-31T23:59:59+00:00",
         "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent", "agent_nickname": "Reviewer"}}}}},
        {"type": "turn_context", "payload": {"model": "fixture-model", "effort": "high", "turn_id": "one"}},
        {"timestamp": "2026-01-01T00:00:00+00:00", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "copied-parent",
                     "started_at": 1767225540}},
        {"timestamp": "2026-01-01T00:00:00+00:00", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "one", "started_at": 1767225600}},
        {"timestamp": "2026-01-01T00:00:10+00:00", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "one"}},
        {"timestamp": "2026-01-01T00:01:10+00:00", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "two"}},
        {"timestamp": "2026-01-01T00:01:15+00:00", "type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "two"}},
    ]
    log.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    run("init", "--process-dir", temp_dir, "--database", "CHARLS", "--topic-id", "040",
        "--topic-name", "review", "--task", "review fixture", "--workflow", "general")
    # Synthetic task interval contains the synthetic review turns.
    report_path = root / "execution_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["started_at"] = "2026-01-01T00:00:00+00:00"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    for _ in range(2):
        imported = json.loads(run("review-import", "--process-dir", temp_dir,
                                  "--log", str(log), "--role", "logic").stdout)
        assert imported["registered_agents"] == 1
        assert imported["turn_count"] == 2
        assert imported["running_seconds"] == 15
        assert imported["between_rounds_seconds"] == 60
    evidence = execution_report.read_review_log(log, "logic")
    assert evidence["rounds"][0]["model"] == "fixture-model"
    assert evidence["rounds"][0]["effort"] == "high"
    assert evidence["rounds"][1]["model"] is None
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic",
        "--close-unavailable", "Host has no close tool", ok=False)
    assert "未登记关闭" in run("finish", "--process-dir", temp_dir,
                             "--status", "completed", ok=False).stderr
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic", "--closed")
    run("finish", "--process-dir", temp_dir, "--status", "completed")
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic", ok=False)
    markdown = (root / "执行报告.md").read_text(encoding="utf-8")
    assert "新建 0 个" in markdown and "15秒" in markdown and "1分0秒" in markdown
    run("init", "--process-dir", temp_dir, "--database", "CHARLS", "--topic-id", "040",
        "--topic-name", "review", "--task", "unfinished fixture", "--workflow", "general")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["started_at"] = "2026-01-01T00:00:00+00:00"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    log.write_text("\n".join(json.dumps(event) for event in events[:-1]) + "\n", encoding="utf-8")
    assert "未结束轮次" in run("review-import", "--process-dir", temp_dir,
                            "--log", str(log), "--role", "logic", "--closed", ok=False).stderr
    unfinished = execution_report.read_review_log(log, "logic")
    assert unfinished["unfinished_turns"] == 1 and unfinished["running_seconds"] == 10
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic",
        "--close-unavailable", "Host has no close tool", ok=False)
    log.write_text("\n".join(json.dumps(event) for event in events[:-2]) + "\n", encoding="utf-8")
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic",
        "--close-unavailable", "Host has no close tool")
    run("finish", "--process-dir", temp_dir, "--status", "completed")
    finished = json.loads((root / "execution_report.json").read_text(encoding="utf-8"))
    assert not finished["reviews"][0]["closed"]
    markdown = (root / "执行报告.md").read_text(encoding="utf-8")
    assert "审核已完成；宿主无关闭工具" in markdown and "fixture-model / high" in markdown
    log.write_text('{"type":"session_meta","payload":{"source":"cli","id":"parent"}}\n', encoding="utf-8")
    try:
        execution_report.read_review_log(log, "logic")
    except ValueError:
        pass
    else:
        raise AssertionError("parent log accepted as a reviewer")

with tempfile.TemporaryDirectory() as temp_dir:
    from datetime import timedelta

    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "042", "--topic-name", "fixture", "--task", "timing",
        "--workflow", "general")
    path = Path(temp_dir) / "execution_report.json"
    initial = json.loads(path.read_text(encoding="utf-8"))
    earlier = execution_report.parse_time(initial["started_at"]) - timedelta(seconds=50)
    log = Path(temp_dir) / "task.jsonl"
    def write_start(value):
        log.write_text(json.dumps({"timestamp": value, "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "measured"}}) + "\n", encoding="utf-8")
    write_start(earlier.isoformat())
    run("start-amend", "--process-dir", temp_dir, "--log", str(log), "--turn-id", "measured")
    amended = json.loads(path.read_text(encoding="utf-8"))
    assert amended["start_amendments"][0]["previous_started_at"] == initial["started_at"]
    before = path.read_bytes()
    for value in (initial["started_at"], "2026-01-01T00:00:00"):
        write_start(value)
        run("start-amend", "--process-dir", temp_dir, "--log", str(log), "--turn-id", "measured", ok=False)
        assert path.read_bytes() == before
    run("start-amend", "--process-dir", temp_dir, "--log", str(log), "--turn-id", "missing", ok=False)
    run("start-amend", "--process-dir", temp_dir, "--started-at", earlier.isoformat(),
        "--evidence", "estimated midnight", ok=False)
    assert path.read_bytes() == before
    run("stage-start", "--process-dir", temp_dir, "--stage-id", "website",
        "--name", "website", "--role", "writer")
    run("issue", "--process-dir", temp_dir, "--stage-id", "website", "--kind", "abnormal",
        "--description", "click failed", "--status", "mitigated", ok=False)
    run("issue", "--process-dir", temp_dir, "--stage-id", "website", "--kind", "abnormal",
        "--description", "click failed", "--status", "mitigated",
        "--resolution", "Keyboard activation returned the article; click cause unknown.")
    run("stage-finish", "--process-dir", temp_dir, "--stage-id", "website",
        "--status", "completed_with_issues")
    run("finish", "--process-dir", temp_dir, "--status", "completed", ok=False)
    result = json.loads(run("finish", "--process-dir", temp_dir,
                            "--status", "completed_with_issues").stdout)
    assert result["elapsed_seconds"] >= 50
    markdown = (Path(temp_dir) / "执行报告.md").read_text(encoding="utf-8")
    assert "未解决：1" in markdown and "根因待修复 1" in markdown
    assert "task.jsonl" in markdown and "turn_id=measured" in markdown
    assert "发现问题并解决" not in markdown

with tempfile.TemporaryDirectory() as temp_dir:
    from unittest.mock import patch
    from datetime import datetime, timezone

    home = Path(temp_dir)
    thread = "019f0737-c39b-7ab3-b38c-a79dfefc7df7"
    log_dir = home / "sessions" / "2026" / "09" / "07"
    log_dir.mkdir(parents=True)
    log = log_dir / f"rollout-fixture-{thread}.jsonl"
    context = lambda model, minute: json.dumps({
        "type": "turn_context", "timestamp": f"2026-09-07T00:{minute}:00Z",
        "payload": {"model": model, "effort": "high", "turn_id": minute},
    })
    log.write_text(context("first-model", "00") + "\n" +
                   json.dumps({"type": "response_item", "payload": "长记录" * 100000}) + "\n" +
                   context("second-model", "01") + '\n{"incomplete":', encoding="utf-8")
    with patch.dict(os.environ, {"CODEX_HOME": str(home), "CODEX_THREAD_ID": thread}):
        first = execution_report.stage_model("", "2026-09-07T00:00:30+00:00")
        second = execution_report.stage_model("", "2026-09-07T00:01:30+00:00")
        assert first["model"] == "first-model" and second["model"] == "second-model"
        assert second["model_evidence"]["turn_id"] == "01"
        assert second["model_source"] == "session_log"
        assert execution_report.stage_model("declared", "2026-09-07T00:02:00Z")["model"] == "declared"
    with patch.dict(os.environ, {"CODEX_THREAD_ID": "unavailable"}):
        unknown = execution_report.stage_model("", "2026-09-07T00:02:00Z")
        assert unknown == {"model": "", "model_source": "unavailable"}

    process = home / "process"
    t0 = datetime(2026, 9, 7, tzinfo=timezone.utc)
    with patch.object(execution_report, "now", return_value=t0):
        prep = execution_report.begin_website_preparation(process, "CHARLS", "043", "fixture")
        assert execution_report.begin_website_preparation(process, "CHARLS", "043", "fixture") == prep
    with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=300)):
        execution_report.begin_website_sync(process, "CHARLS", "043", "fixture")
    path = browser_result(process)
    good = json.loads(path.read_text(encoding="utf-8"))
    good.update(dispatch_latency_ms=759, browser_elapsed_ms=1791,
                sync_elapsed_to_browser_return_ms=2550)
    report_path = process / "execution_report.json"
    before = report_path.read_bytes()
    bad_cases = [[], dict(good, sync_run_id="another-run"), dict(good, sync_attempt=100),
                 dict(good, ok=False), dict(good, quality_checks={}),
                 dict(good, quality_checks=None), dict(good, preload_sha256=None),
                 dict(good, browser_elapsed_ms=float("nan")),
                 dict(good, sync_elapsed_to_browser_return_ms=10)]
    for invalid in bad_cases:
        path.write_text(json.dumps(invalid), encoding="utf-8")
        run("website-finish", "--process-dir", str(process), "--result", str(path), ok=False)
        assert report_path.read_bytes() == before
    path.write_text(json.dumps(good), encoding="utf-8")
    with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=456)):
        execution_report.command_website_finish(execution_report.argparse.Namespace(
            process_dir=str(process), result=path))
        execution_report.command_finish(execution_report.argparse.Namespace(
            process_dir=str(process), status="completed", summary=[]))
    final = json.loads(report_path.read_text(encoding="utf-8"))
    assert [s["elapsed_seconds"] for s in final["stages"]] == [300, 2.55, 153.45]
    returned = execution_report.latest_stage(final, "website_sync")
    assert returned["status"] == "completed" and returned["browser_result"] == good
    assert returned["finished_at"] == (t0 + timedelta(seconds=302.55)).isoformat(timespec="milliseconds")
    assert "456.000" in (process / "执行报告.md").read_text(encoding="utf-8")
    run("website-finish", "--process-dir", str(process), "--result", str(path), ok=False)

    late_process=home / "late-return"
    with patch.object(execution_report,"now",return_value=t0):
        execution_report.begin_website_preparation(late_process,"CHARLS","043","fixture")
    with patch.object(execution_report,"now",return_value=t0+timedelta(seconds=300)):
        execution_report.begin_website_sync(late_process,"CHARLS","043","fixture")
    late_path=browser_result(late_process)
    late=json.loads(late_path.read_text(encoding="utf-8"))
    late.update(late_navigation_observed=True,read_only=True,original_operation_state="failed",
                recovered_original_result=False,observed_at=(t0+timedelta(seconds=400)).timestamp())
    late_report=late_process / "execution_report.json"
    before_late=late_report.read_bytes()
    for invalid in [dict(late,read_only=False),dict(late,original_operation_state="running"),
                    dict(late,observed_at=float("nan")),dict(late,observed_at=(t0+timedelta(seconds=999)).timestamp())]:
        late_path.write_text(json.dumps(invalid),encoding="utf-8")
        with patch.object(execution_report,"now",return_value=t0+timedelta(seconds=456)):
            expect_system_exit(lambda:execution_report.command_website_finish(
                execution_report.argparse.Namespace(process_dir=str(late_process),result=late_path)),"延迟返回")
        assert late_report.read_bytes()==before_late
    late_path.write_text(json.dumps(late),encoding="utf-8")
    with patch.object(execution_report,"now",return_value=t0+timedelta(seconds=456)):
        execution_report.command_website_finish(execution_report.argparse.Namespace(process_dir=str(late_process),result=late_path))
    late_stage=execution_report.latest_stage(json.loads(late_report.read_text(encoding="utf-8")),"website_sync")
    assert late_stage["status"]=="completed_with_issues" and late_stage["elapsed_seconds"]==100

with tempfile.TemporaryDirectory() as temp_dir:
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    t0 = datetime(2026, 9, 7, tzinfo=timezone.utc)
    for original_status in ("SUBMISSION_UNCERTAIN", "SYNC_FAILED"):
        process = Path(temp_dir) / original_status
        with patch.object(execution_report, "now", return_value=t0):
            execution_report.begin_website_preparation(process, "CHARLS", "043", "fixture")
        with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=10)):
            execution_report.begin_website_sync(process, "CHARLS", "043", "fixture")
            execution_report.command_issue(execution_report.argparse.Namespace(
                process_dir=str(process), stage_id="website_sync", kind="abnormal",
                description="提交返回超时", impact="保存结果待核对", resolution="原因为返回超时",
                status="mitigated"))
        report_path = process / "execution_report.json"
        markdown_path = process / "执行报告.md"
        current = json.loads(report_path.read_text(encoding="utf-8"))
        stage = execution_report.latest_stage(current, "website_sync")
        original_path = process / "original-failure.json"
        original = {
            "ok": False, "status": original_status, "sync_run_id": current["run_id"],
            "sync_attempt": stage["attempt"], "sync_started_at": stage["started_at"],
            "browser_elapsed_ms": 30000,
            "observation": {"receipt_id": "a" * 32, "tab_id": "fixture-tab"},
        }
        path = process / "saved-confirmation.json"
        good = {
            "ok": True, "status": "ARTICLE_SAVED_CONFIRMED", "sync_run_id": current["run_id"],
            "sync_attempt": stage["attempt"], "sync_started_at": stage["started_at"],
            "preload_sha256": "0" * 64, "original_result_path": str(original_path.resolve()),
            "original_browser_elapsed_ms": original["browser_elapsed_ms"],
            "confirmation_started_at": (t0 + timedelta(seconds=60)).isoformat(),
            "confirmation_finished_at": (t0 + timedelta(seconds=120)).isoformat(),
            "saved_content_verified": True, "saved_attachment_hashes_verified": True, "read_only": True,
            "observation": copy.deepcopy(original["observation"]),
            "attachment_signatures": [{"name": "fixture.R", "sha256": "A" * 64}],
            "quality_checks": {key: True for key in (
                "edit_url_verified", "title_verified", "body_verified",
                "attachment_order_verified", "article_page_returned")},
        }
        original_path.write_text(json.dumps(original), encoding="utf-8")
        original_bytes = original_path.read_bytes()
        before_report, before_markdown = report_path.read_bytes(), markdown_path.read_bytes()
        standard_path = process / "website_sync_result.json"
        args = execution_report.argparse.Namespace(process_dir=str(process), result=path)

        def rejected(result, expected, failed=original):
            path.write_text(json.dumps(result), encoding="utf-8")
            original_path.write_text(json.dumps(failed), encoding="utf-8")
            source_before, failure_before = path.read_bytes(), original_path.read_bytes()
            with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=130)):
                expect_system_exit(lambda: execution_report.command_website_finish(args), expected)
            assert report_path.read_bytes() == before_report
            assert markdown_path.read_bytes() == before_markdown
            assert path.read_bytes() == source_before and original_path.read_bytes() == failure_before
            assert not standard_path.exists()

        if original_status == "SUBMISSION_UNCERTAIN":
            for invalid in (
                dict(good, sync_run_id="another-run"), dict(good, sync_attempt=100),
                dict(good, sync_started_at=t0.isoformat()),
            ):
                rejected(invalid, "不属于本次")
            for invalid in (
                dict(good, saved_attachment_hashes_verified=None),
                dict(good, saved_content_verified=False), dict(good, read_only=False),
            ):
                rejected(invalid, "正文、附件哈希或只读")
            for invalid in (dict(good, attachment_signatures=None),
                            dict(good, attachment_signatures=[{"name": "fixture.R", "sha256": "short"}])):
                rejected(invalid, "附件哈希记录")
            rejected(dict(good, quality_checks={**good["quality_checks"], "body_verified": False}), "完整的同步成功证据")
            rejected(dict(good, preload_sha256="invalid"), "哈希记录")
            for invalid in (
                dict(good, observation={}),
                dict(good, observation={"receipt_id": "b" * 32, "tab_id": "fixture-tab"}),
                dict(good, observation={"receipt_id": "a" * 32, "tab_id": "other-tab"}),
            ):
                rejected(invalid, "receipt_id/tab_id")
            rejected(dict(good, original_browser_elapsed_ms=29999), "original_browser_elapsed_ms")
            rejected(dict(good, browser_elapsed_ms=120000), "不能声明原同步直接返回")
            for invalid in (
                dict(good, confirmation_started_at="2026-09-07T00:01:00"),
                dict(good, confirmation_finished_at="2026-09-07T00:02:00"),
                dict(good, confirmation_started_at=(t0 + timedelta(seconds=5)).isoformat()),
                dict(good, confirmation_finished_at=(t0 + timedelta(seconds=59)).isoformat()),
                dict(good, confirmation_finished_at=(t0 + timedelta(seconds=131)).isoformat()),
                dict(good, confirmation_started_at="invalid"),
            ):
                rejected(invalid, "只读确认时间")
            for invalid_original in (
                dict(original, status="ARTICLE_PAGE_RETURNED"),
                dict(original, sync_run_id="another-run"), dict(original, sync_attempt=100),
                dict(original, sync_started_at=t0.isoformat()),
            ):
                rejected(good, "原始结果不是本次提交", invalid_original)
            rejected(good, "程序哈希不一致", dict(original, preload_sha256="1" * 64))
            rejected(dict(good, original_result_path=str(process / "missing.json")), "原始失败结果文件不存在")
            rejected(dict(good, original_result_path=str(path.resolve())), "不能覆盖或冒充")
            path.write_text(json.dumps(good), encoding="utf-8")
            original_path.write_bytes(original_bytes)
            with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=130)):
                expect_system_exit(lambda: execution_report.command_website_finish(
                    execution_report.argparse.Namespace(process_dir=str(process), result_json=json.dumps(good))),
                    "真实确认结果文件")
            assert report_path.read_bytes() == before_report and original_path.read_bytes() == original_bytes
            standard_path.write_bytes(original_bytes)
            path.write_text(json.dumps(dict(good, original_result_path=str(standard_path.resolve()))), encoding="utf-8")
            with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=130)):
                expect_system_exit(lambda: execution_report.command_website_finish(args), "不能覆盖或冒充")
            assert standard_path.read_bytes() == original_bytes and report_path.read_bytes() == before_report
            standard_path.unlink()

        path.write_text(json.dumps(good), encoding="utf-8")
        original_path.write_bytes(original_bytes)
        confirmation_bytes = path.read_bytes()
        with patch.object(execution_report, "now", return_value=t0 + timedelta(seconds=130)):
            imported = execution_report.command_website_finish(args)
            execution_report.command_finish(execution_report.argparse.Namespace(
                process_dir=str(process), status="completed_with_issues", summary=[]))
        final = json.loads(report_path.read_text(encoding="utf-8"))
        saved = execution_report.latest_stage(final, "website_sync")
        assert saved["status"] == "completed_with_issues" and saved["browser_result"] == good
        assert saved["elapsed_seconds"] == imported["submission_seconds"] == 110
        assert "只读确认" in saved["summary"][0] and "直接返回回执" in saved["summary"][0]
        assert [s["elapsed_seconds"] for s in final["stages"]] == [10, 110, 10]
        assert final["issues"] == current["issues"]
        assert json.loads(standard_path.read_text(encoding="utf-8")) == good
        assert original_path.read_bytes() == original_bytes and path.read_bytes() == confirmation_bytes
        assert saved["finished_at"] == execution_report.latest_stage(final, "website_closure")["started_at"]
        assert not any(key in saved["browser_result"] for key in (
            "dispatch_latency_ms", "browser_elapsed_ms", "sync_elapsed_to_browser_return_ms"))

with tempfile.TemporaryDirectory() as temp_dir:
    from unittest.mock import patch
    root = Path(temp_dir)
    report = {"status": "completed", "started_at": "2026-09-09T10:00:25Z", "finished_at": "2026-09-09T10:02:00Z"}
    log = root / "task.jsonl"
    log.write_text('\n'.join(json.dumps(event) for event in [
        {"type": "event_msg", "timestamp": "2026-09-09T10:00:00Z", "payload": {"type": "task_started", "turn_id": "selected"}},
        {"type": "event_msg", "timestamp": "2026-09-09T10:02:50Z", "payload": {"type": "task_complete", "turn_id": "selected"}},
    ]), encoding="utf-8")
    args = execution_report.argparse.Namespace(process_dir=temp_dir, log=log, turn_id="selected")
    with patch.object(execution_report, "load", return_value=report), patch.object(execution_report, "save"):
        timing = execution_report.command_turn_timing(args)
        assert timing["elapsed_seconds"] == 170 and timing["before_report_seconds"] == 25 and timing["after_report_seconds"] == 50
        args.turn_id = "wrong"
        expect_system_exit(lambda: execution_report.command_turn_timing(args), "不包含报告")
        args.turn_id = "selected"
        report["status"] = "running"
        expect_system_exit(lambda: execution_report.command_turn_timing(args), "轮次结束后")

print("EXECUTION_REPORT_TEST_PASS")


# Current-run replacement retains reusable evidence without a report archive.
with tempfile.TemporaryDirectory() as temporary:
    from argparse import Namespace
    root = Path(temporary)
    source = root / "source.txt"
    source.write_text("stable", encoding="utf-8")
    options = Namespace(process_dir=str(root), database="test", topic_id="001",
                        topic_name="fixture", task="current materials", workflow="general")
    execution_report.command_init(options)
    path, md = execution_report.paths(str(root))
    prior = execution_report.load(path)
    prior.update(status="completed", stage_reviews={"fixture": {
        "status": "pass", "mode": "isolated", "limitation": "fixture only",
        "inputs": execution_report.input_hashes([source]), "evidence": "checked fixture"}})
    execution_report.save(path, md, prior)
    execution_report.command_init(options)
    current = execution_report.load(path)
    execution_report.validate_stage_review(current, "fixture")
    assert not (root / "archived_runs").exists()
    source.write_text("changed", encoding="utf-8")
    try:
        execution_report.validate_stage_review(current, "fixture")
    except ValueError as error:
        assert "变化" in str(error)
    else:
        raise AssertionError("stale carried evidence was accepted")
    current["status"] = "completed"
    execution_report.save(path, md, current)
    options.archive_previous = True
    execution_report.command_init(options)
    assert (root / "archived_runs" / current["run_id"] / "execution_report.json").is_file()
