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
        "--status", "completed", "--summary", "模拟网站返回成功")
    run("finish", "--process-dir", temp_dir, "--status", "completed")
    finished = report_path.read_bytes()
    restarted = execution_report.begin_website_sync(root, "CHARLS", "036", "工作属性")
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
        assert "formal_r" in str(error)
    else:
        raise AssertionError("unfinished production stage unexpectedly accepted")
    assert report_path.read_bytes() == before
    run("stage-finish", "--process-dir", temp_dir, "--stage-id", "formal_r",
        "--status", "completed")
    original = json.loads(report_path.read_text(encoding="utf-8"))
    sync = execution_report.begin_website_sync(Path(temp_dir), "CHARLS", "036", "工作属性")
    current = json.loads(report_path.read_text(encoding="utf-8"))
    assert sync["run_id"] == original["run_id"]
    assert current["stages"][0] == original["stages"][0]
    assert current["stages"][1]["stage_id"] == "website_sync"

print("EXECUTION_REPORT_TEST_PASS")
