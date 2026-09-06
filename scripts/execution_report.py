#!/usr/bin/env python3
"""Record truthful stage timing and issues for a definition-topic run."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_NAME = "execution_report.json"
MARKDOWN_NAME = "执行报告.md"

RUN_STATUS = {
    "running": "执行中",
    "completed": "正常完成",
    "completed_with_issues": "完成，期间发现问题",
    "failed": "异常停止",
    "stopped": "主动停止",
}

STAGE_STATUS = {
    "running": "执行中",
    "completed": "正常完成",
    "completed_with_issues": "发现问题并解决",
    "failed": "异常停止",
    "skipped": "未执行",
}

ISSUE_STATUS = {
    "open": "未解决",
    "resolved": "已解决",
}

STAGE_MODE = {"work": "工作", "wait": "等待", "rework": "返工"}


def duration_text(seconds: float) -> str:
    whole = int(seconds)
    hours, remaining = divmod(whole, 3600)
    minutes, secs = divmod(remaining, 60)
    parts = ([f"{hours}小时"] if hours else [])
    parts += ([f"{minutes}分"] if minutes or hours else [])
    parts.append(f"{secs}秒")
    return "".join(parts)


def now() -> datetime:
    return datetime.now().astimezone()


def iso(value: datetime | None = None) -> str:
    return (value or now()).isoformat(timespec="seconds")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def elapsed_seconds(started_at: str, finished_at: str | None = None) -> float:
    end = parse_time(finished_at) if finished_at else now()
    return round(max(0.0, (end - parse_time(started_at)).total_seconds()), 3)


def paths(process_dir: str) -> tuple[Path, Path]:
    root = Path(process_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / REPORT_NAME, root / MARKDOWN_NAME


def load(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        raise SystemExit(f"执行报告不存在：{report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def save(report_path: Path, markdown_path: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = iso()
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def latest_stage(report: dict[str, Any], stage_id: str) -> dict[str, Any]:
    matches = [stage for stage in report["stages"] if stage["stage_id"] == stage_id]
    if not matches:
        raise SystemExit(f"找不到环节：{stage_id}")
    return matches[-1]


def render_markdown(report: dict[str, Any]) -> str:
    finished_at = report.get("finished_at")
    total = elapsed_seconds(report["started_at"], finished_at)
    stages = report.get("stages", [])
    issues = report.get("issues", [])
    bug_count = sum(issue["kind"] == "bug" for issue in issues)
    abnormal_count = sum(issue["kind"] == "abnormal" for issue in issues)
    wait_count = sum(issue["kind"] == "wait" for issue in issues)
    open_count = sum(issue["status"] == "open" for issue in issues)

    lines = [
        f"# {report['database']} {report['topic_id']} {report['topic_name']}：执行报告",
        "",
        f"- 任务：{report['task']}",
        f"- 状态：{RUN_STATUS[report['status']]}",
        f"- 开始：{report['started_at']}",
        f"- 结束：{finished_at or '尚未结束'}",
        f"- 总耗时：{duration_text(total)}（{total:.3f} 秒）",
        f"- Bug：{bug_count} 个；异常：{abnormal_count} 个；等待：{wait_count} 个；未解决：{open_count} 个",
        "",
        "## 环节耗时",
        "",
        "| 环节 | 性质 | 执行者 | 模型 | 状态 | 耗时 | 完成内容 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]

    if not stages:
        lines.append("| 尚未开始 | - | - | - | 未执行 | - | - |")
    else:
        for stage in stages:
            duration = stage.get("elapsed_seconds")
            if duration is None:
                duration = elapsed_seconds(stage["started_at"])
            summary = "；".join(stage.get("summary", [])) or "-"
            lines.append(
                "| {name} | {mode} | {role} | {model} | {status} | {duration} | {summary} |".format(
                    name=stage["name"],
                    mode=STAGE_MODE.get(stage.get("mode"), "未分类"),
                    role=stage["role"],
                    model=stage.get("model") or "未指定",
                    status=STAGE_STATUS[stage["status"]],
                    duration=duration_text(duration),
                    summary=summary.replace("|", "\\|"),
                )
            )

    if report.get("summary"):
        lines.extend(["", "## 执行结果", "", *report["summary"]])
    lines.extend(["", "## Bug 与异常", ""])
    if not issues:
        lines.append("本次尚未记录 Bug 或异常。")
    else:
        lines.extend([
            "| 类型 | 所在环节 | 问题 | 影响 | 处理 | 状态 |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        kind_labels = {"bug": "Bug", "abnormal": "异常", "wait": "等待"}
        for issue in issues:
            lines.append(
                "| {kind} | {stage} | {description} | {impact} | {resolution} | {status} |".format(
                    kind=kind_labels[issue["kind"]],
                    stage=issue["stage_id"],
                    description=issue["description"].replace("|", "\\|"),
                    impact=(issue.get("impact") or "-").replace("|", "\\|"),
                    resolution=(issue.get("resolution") or "-").replace("|", "\\|"),
                    status=ISSUE_STATUS[issue["status"]],
                )
            )

    lines.extend([
        "",
        "## 说明",
        "",
        "总耗时按任务开始到当前或结束的墙钟时间计算。各环节可能并行，不能把环节耗时简单相加作为总耗时。性质为工作、等待或返工；旧记录未分类时不反推其耗时构成。未计时的历史操作只能在说明中披露，不以补记动作的几秒钟代替。",
        "",
    ])
    return "\n".join(lines)


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    if report_path.exists():
        previous = load(report_path)
        if previous.get("status") == "running":
            raise SystemExit("已有执行中的报告；请继续该报告，不能静默覆盖。")
        archive = report_path.parent / "archived_runs" / previous["run_id"]
        archive.mkdir(parents=True, exist_ok=True)
        for existing in (report_path, markdown_path):
            if existing.exists():
                (archive / existing.name).write_bytes(existing.read_bytes())
    report = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "database": args.database,
        "topic_id": args.topic_id,
        "topic_name": args.topic_name,
        "task": args.task,
        "status": "running",
        "started_at": iso(),
        "finished_at": None,
        "updated_at": None,
        "summary": [],
        "stages": [],
        "issues": [],
    }
    save(report_path, markdown_path, report)
    return {"ok": True, "run_id": report["run_id"]}


def command_stage_start(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    if report["status"] != "running":
        raise SystemExit("任务报告已经结束，不能再开始新环节。")
    if any(s["stage_id"] == args.stage_id and s["status"] == "running" for s in report["stages"]):
        raise SystemExit("该环节仍在执行；请先结束它再记录下一次尝试。")
    attempts = sum(stage["stage_id"] == args.stage_id for stage in report["stages"]) + 1
    report["stages"].append({
        "stage_id": args.stage_id,
        "attempt": attempts,
        "name": args.name,
        "role": args.role,
        "model": args.model,
        "mode": args.mode,
        "status": "running",
        "started_at": iso(),
        "finished_at": None,
        "elapsed_seconds": None,
        "summary": [],
        "outputs": [],
    })
    save(report_path, markdown_path, report)
    return {"ok": True, "stage_id": args.stage_id, "attempt": attempts}


def command_stage_finish(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    stage = latest_stage(report, args.stage_id)
    if stage["status"] != "running":
        raise SystemExit(f"环节不是执行中状态：{args.stage_id}")
    stage["finished_at"] = iso()
    stage["elapsed_seconds"] = elapsed_seconds(stage["started_at"], stage["finished_at"])
    stage["status"] = args.status
    stage["summary"] = args.summary or []
    stage["outputs"] = args.output or []
    save(report_path, markdown_path, report)
    return {"ok": True, "stage_id": args.stage_id, "elapsed_seconds": stage["elapsed_seconds"]}


def command_issue(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    latest_stage(report, args.stage_id)
    report["issues"].append({
        "recorded_at": iso(),
        "stage_id": args.stage_id,
        "kind": args.kind,
        "description": args.description,
        "impact": args.impact,
        "resolution": args.resolution,
        "status": args.status,
    })
    save(report_path, markdown_path, report)
    return {"ok": True, "issue_count": len(report["issues"])}


def command_issue_amend(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    index = args.issue_number - 1
    if index < 0 or index >= len(report["issues"]):
        raise SystemExit(f"问题编号超出范围：{args.issue_number}")
    issue = report["issues"][index]
    previous = {
        key: issue.get(key)
        for key in ("description", "impact", "resolution", "status")
    }
    issue.setdefault("amendments", []).append({
        "amended_at": iso(),
        "note": args.note,
        "previous": previous,
    })
    for field in ("description", "impact", "resolution", "status"):
        value = getattr(args, field)
        if value is not None:
            issue[field] = value
    save(report_path, markdown_path, report)
    return {"ok": True, "issue_number": args.issue_number}


def command_finish(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    running = [stage["stage_id"] for stage in report["stages"] if stage["status"] == "running"]
    if running:
        raise SystemExit("仍有执行中的环节：" + ", ".join(running))
    if args.status in ("completed", "completed_with_issues"):
        if any(issue["status"] == "open" for issue in report["issues"]):
            raise SystemExit("仍有未解决的问题；不能标记完成。")
        latest = {stage["stage_id"]: stage for stage in report["stages"]}
        if any(stage["status"] == "failed" for stage in latest.values()):
            raise SystemExit("仍有失败环节未完成重试；不能标记完成。")
        if args.status == "completed" and report["issues"]:
            raise SystemExit("存在问题记录；请使用 completed_with_issues。")
    report["status"] = args.status
    report["finished_at"] = iso()
    report["summary"] = args.summary or []
    save(report_path, markdown_path, report)
    return {"ok": True, "status": args.status, "elapsed_seconds": elapsed_seconds(report["started_at"], report["finished_at"])}


def begin_website_sync(process_dir: Path, database: str, topic_id: str, topic_name: str) -> dict[str, Any]:
    """Start timing after preflight, preserving an active sync's start."""
    report_path, _ = paths(str(process_dir))
    if report_path.exists():
        report = load(report_path)
        if report["database"].casefold() != database.casefold() or report["topic_id"] != topic_id:
            raise ValueError("执行报告与本次数据库或主题不一致；未改动报告。")
        other_running = [s["stage_id"] for s in report["stages"]
                         if s["status"] == "running" and s["stage_id"] != "website_sync"]
        if other_running:
            raise ValueError("先结束实际仍在执行的环节：" + ", ".join(other_running))
    else:
        report = None
    if report is None or report["status"] != "running":
        command_init(argparse.Namespace(
            process_dir=str(process_dir), database=database, topic_id=topic_id,
            topic_name=topic_name, task="同步已经审核的正式笔记及本轮变化的附件",
        ))
        report = load(report_path)
    active = [s for s in report["stages"]
              if s["stage_id"] == "website_sync" and s["status"] == "running"]
    if not active:
        command_stage_start(argparse.Namespace(
            process_dir=str(process_dir), stage_id="website_sync", name="网站同步",
            role="主执行者", model="", mode="work",
        ))
        report = load(report_path)
    stage = latest_stage(report, "website_sync")
    return {"report": str(report_path), "run_id": report["run_id"],
            "stage_id": stage["stage_id"], "started_at": stage["started_at"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--process-dir", required=True)
    init_parser.add_argument("--database", required=True)
    init_parser.add_argument("--topic-id", required=True)
    init_parser.add_argument("--topic-name", required=True)
    init_parser.add_argument("--task", required=True)
    init_parser.set_defaults(func=command_init)

    stage_start = subparsers.add_parser("stage-start")
    stage_start.add_argument("--process-dir", required=True)
    stage_start.add_argument("--stage-id", required=True)
    stage_start.add_argument("--name", required=True)
    stage_start.add_argument("--role", required=True)
    stage_start.add_argument("--model", default="")
    stage_start.add_argument("--mode", choices=tuple(STAGE_MODE), default="work")
    stage_start.set_defaults(func=command_stage_start)

    stage_finish = subparsers.add_parser("stage-finish")
    stage_finish.add_argument("--process-dir", required=True)
    stage_finish.add_argument("--stage-id", required=True)
    stage_finish.add_argument(
        "--status",
        required=True,
        choices=("completed", "completed_with_issues", "failed", "skipped"),
    )
    stage_finish.add_argument("--summary", action="append")
    stage_finish.add_argument("--output", action="append")
    stage_finish.set_defaults(func=command_stage_finish)

    issue_parser = subparsers.add_parser("issue")
    issue_parser.add_argument("--process-dir", required=True)
    issue_parser.add_argument("--stage-id", required=True)
    issue_parser.add_argument("--kind", required=True, choices=("bug", "abnormal", "wait"))
    issue_parser.add_argument("--description", required=True)
    issue_parser.add_argument("--impact", default="")
    issue_parser.add_argument("--resolution", default="")
    issue_parser.add_argument("--status", required=True, choices=("open", "resolved"))
    issue_parser.set_defaults(func=command_issue)

    amend_parser = subparsers.add_parser("issue-amend")
    amend_parser.add_argument("--process-dir", required=True)
    amend_parser.add_argument("--issue-number", required=True, type=int)
    amend_parser.add_argument("--description")
    amend_parser.add_argument("--impact")
    amend_parser.add_argument("--resolution")
    amend_parser.add_argument("--status", choices=("open", "resolved"))
    amend_parser.add_argument("--note", required=True)
    amend_parser.set_defaults(func=command_issue_amend)

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--process-dir", required=True)
    finish_parser.add_argument(
        "--status",
        required=True,
        choices=("completed", "completed_with_issues", "failed", "stopped"),
    )
    finish_parser.add_argument("--summary", action="append")
    finish_parser.set_defaults(func=command_finish)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
