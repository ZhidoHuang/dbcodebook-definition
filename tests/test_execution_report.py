import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_report


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "execution_report.py"


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
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "重新运行")
    archived = Path(temp_dir) / "archived_runs" / previous_id / "execution_report.json"
    assert json.loads(archived.read_text(encoding="utf-8")) == report
    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "覆盖", ok=False)
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
    assert archive.read_bytes() == finished

with tempfile.TemporaryDirectory() as temp_dir:
    run("init", "--process-dir", temp_dir, "--database", "CHARLS",
        "--topic-id", "036", "--topic-name", "工作属性", "--task", "完整定义")
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
        {"type": "session_meta", "payload": {"id": "agent-1", "timestamp": "2026-01-01T00:00:00+00:00",
         "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent", "agent_nickname": "Reviewer"}}}}},
        {"type": "turn_context", "payload": {"model": "fixture-model"}},
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
        "--topic-name", "review", "--task", "review fixture")
    for _ in range(2):
        imported = json.loads(run("review-import", "--process-dir", temp_dir,
                                  "--log", str(log), "--role", "logic").stdout)
        assert imported["registered_agents"] == 1
        assert imported["turn_count"] == 2
        assert imported["running_seconds"] == 15
        assert imported["between_rounds_seconds"] == 60
    assert "未登记关闭" in run("finish", "--process-dir", temp_dir,
                             "--status", "completed", ok=False).stderr
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic", "--closed")
    run("finish", "--process-dir", temp_dir, "--status", "completed")
    run("review-import", "--process-dir", temp_dir, "--log", str(log), "--role", "logic", ok=False)
    markdown = (root / "执行报告.md").read_text(encoding="utf-8")
    assert "新建 0 个" in markdown and "15秒" in markdown and "1分0秒" in markdown
    run("init", "--process-dir", temp_dir, "--database", "CHARLS", "--topic-id", "040",
        "--topic-name", "review", "--task", "unfinished fixture")
    log.write_text("\n".join(json.dumps(event) for event in events[:-1]) + "\n", encoding="utf-8")
    assert "未结束轮次" in run("review-import", "--process-dir", temp_dir,
                            "--log", str(log), "--role", "logic", "--closed", ok=False).stderr
    unfinished = execution_report.read_review_log(log, "logic")
    assert unfinished["unfinished_turns"] == 1 and unfinished["running_seconds"] == 10
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
        "--topic-id", "042", "--topic-name", "fixture", "--task", "timing")
    path = Path(temp_dir) / "execution_report.json"
    initial = json.loads(path.read_text(encoding="utf-8"))
    earlier = execution_report.parse_time(initial["started_at"]) - timedelta(seconds=50)
    run("start-amend", "--process-dir", temp_dir, "--started-at", earlier.isoformat(),
        "--evidence", "fixture first tool timestamp")
    amended = json.loads(path.read_text(encoding="utf-8"))
    assert amended["start_amendments"][0]["previous_started_at"] == initial["started_at"]
    before = path.read_bytes()
    for value in (initial["started_at"], "2026-01-01T00:00:00"):
        run("start-amend", "--process-dir", temp_dir, "--started-at", value,
            "--evidence", "invalid correction", ok=False)
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
    assert "fixture first tool timestamp" in markdown
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
    assert "456.000" in (process / "执行报告.md").read_text(encoding="utf-8")
    run("website-finish", "--process-dir", str(process), "--result", str(path), ok=False)

print("EXECUTION_REPORT_TEST_PASS")
