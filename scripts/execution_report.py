#!/usr/bin/env python3
"""Record truthful stage timing and issues for a definition-topic run."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
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
    "completed_with_issues": "完成，期间发现问题",
    "failed": "异常停止",
    "skipped": "未执行",
}

ISSUE_STATUS = {
    "open": "未解决",
    "resolved": "已解决",
    "mitigated": "本次交付已恢复，根因待修复",
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


def current_session_log() -> Path | None:
    """Resolve only this task's filename; never search other tasks' contents."""
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    try:
        uuid.UUID(thread_id)
    except ValueError:
        return None
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    matches = list((home / "sessions").glob(f"*/*/*/*-{thread_id}.jsonl"))
    return matches[0] if len(matches) == 1 else None


def reverse_lines(path: Path):
    """Read the tail first, so a long-lived task does not require a full replay."""
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        remainder = b""
        while position:
            size = min(position, 65536)
            position -= size
            stream.seek(position)
            lines = (stream.read(size) + remainder).split(b"\n")
            remainder = lines[0]
            yield from reversed(lines[1:])
        if remainder:
            yield remainder


def stage_model(declared: str, started_at: str) -> dict[str, Any]:
    if declared:
        return {"model": declared, "model_source": "explicit"}
    try:
        log = current_session_log()
        if log:
            for line in reverse_lines(log):
                if b'"turn_context"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if event.get("type") != "turn_context":
                    continue
                timestamp = event.get("timestamp")
                if not timestamp or parse_time(timestamp) > parse_time(started_at):
                    continue
                payload = event.get("payload", {})
                if payload.get("model"):
                    return {"model": payload["model"], "model_source": "session_log",
                            "model_evidence": {"log": str(log), "timestamp": timestamp,
                                               "turn_id": payload.get("turn_id"),
                                               "effort": payload.get("effort")}}
                break
    except (OSError, ValueError, TypeError):
        pass
    return {"model": "", "model_source": "unavailable"}


def read_review_log(log_path: Path, role: str) -> dict[str, Any]:
    """Read one explicitly selected agent log, never the whole session archive."""
    meta = None
    models = []
    turns = {}
    with log_path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get("payload", {})
            if event.get("type") == "session_meta" and meta is None:
                meta = payload
            elif event.get("type") == "turn_context":
                model = payload.get("model")
                if model and model not in models:
                    models.append(model)
            elif event.get("type") == "event_msg":
                turn_id = payload.get("turn_id")
                if not turn_id:
                    continue
                if payload.get("type") == "task_started":
                    started_epoch = payload.get("started_at")
                    if (
                        meta
                        and isinstance(started_epoch, (int, float))
                        and started_epoch < int(parse_time(meta["timestamp"]).timestamp())
                    ):
                        continue
                    turns.setdefault(turn_id, {"turn_id": turn_id,
                                              "started_at": event["timestamp"], "finished_at": None})
                elif payload.get("type") in {"task_complete", "turn_aborted"} and turn_id in turns:
                    turns[turn_id]["finished_at"] = event["timestamp"]
                    turns[turn_id]["outcome"] = (
                        "completed" if payload.get("type") == "task_complete" else "aborted"
                    )
    if not meta or not turns:
        raise ValueError("selected log has no agent identity or review turns")
    source = meta.get("source", {})
    spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    if not spawn:
        raise ValueError("selected log is not a subagent log")
    rounds = sorted(turns.values(), key=lambda item: parse_time(item["started_at"]))
    prior_end = None
    for item in rounds:
        item["elapsed_seconds"] = (elapsed_seconds(item["started_at"], item["finished_at"])
                                   if item["finished_at"] else None)
        item["gap_before_seconds"] = (elapsed_seconds(prior_end, item["started_at"])
                                      if prior_end else 0)
        prior_end = item["finished_at"]
    return {
        "agent_id": meta["id"], "nickname": spawn.get("agent_nickname") or meta["id"],
        "parent_thread_id": spawn["parent_thread_id"], "role": role,
        "created_at": meta["timestamp"], "models": models, "log_path": str(log_path.resolve()),
        "turn_count": len(rounds), "rounds": rounds,
        "running_seconds": round(sum(item["elapsed_seconds"] or 0 for item in rounds), 3),
        "between_rounds_seconds": round(sum(item["gap_before_seconds"] for item in rounds), 3),
        "unfinished_turns": sum(item["finished_at"] is None for item in rounds),
    }


def command_review_import(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    if report["status"] != "running":
        raise SystemExit("任务报告已经结束；历史审核复盘应登记到当前复盘报告。")
    review = read_review_log(args.log, args.role)
    if args.closed and review["unfinished_turns"]:
        raise SystemExit("审核日志仍有未结束轮次，不能登记为已关闭。")
    reviews = report.setdefault("reviews", [])
    prior = next((item for item in reviews if item["agent_id"] == review["agent_id"]), None)
    review["closed"] = bool(args.closed or (prior and prior.get("closed")))
    if review["unfinished_turns"]:
        review["closed"] = False
    review["created_during_run"] = parse_time(review["created_at"]) >= parse_time(report["started_at"])
    if prior:
        reviews[reviews.index(prior)] = review
    else:
        reviews.append(review)
    save(report_path, markdown_path, report)
    return {"ok": True, "agent_id": review["agent_id"], "registered_agents": len(reviews),
            "turn_count": review["turn_count"], "running_seconds": review["running_seconds"],
            "between_rounds_seconds": review["between_rounds_seconds"], "closed": review["closed"]}


def render_markdown(report: dict[str, Any]) -> str:
    finished_at = report.get("finished_at")
    total = elapsed_seconds(report["started_at"], finished_at)
    stages = report.get("stages", [])
    issues = report.get("issues", [])
    bug_count = sum(issue["kind"] == "bug" for issue in issues)
    abnormal_count = sum(issue["kind"] == "abnormal" for issue in issues)
    wait_count = sum(issue["kind"] == "wait" for issue in issues)
    open_count = sum(issue["status"] == "open" for issue in issues)
    pending_count = sum(issue["status"] == "mitigated" for issue in issues)

    lines = [
        f"# {report['database']} {report['topic_id']} {report['topic_name']}：执行报告",
        "",
        f"- 任务：{report['task']}",
        f"- 状态：{RUN_STATUS[report['status']]}",
        f"- 开始：{report['started_at']}",
        f"- 结束：{finished_at or '尚未结束'}",
        f"- 总耗时：{duration_text(total)}（{total:.3f} 秒）",
        f"- Bug：{bug_count} 个；异常：{abnormal_count} 个；等待：{wait_count} 个；未解决：{open_count + pending_count} 个（仍阻断交付 {open_count} 个，已恢复但根因待修复 {pending_count} 个）",
        "",
        "## 环节耗时",
        "",
        "| 环节 | 性质 | 执行者 | 模型 | 状态 | 耗时 | 完成内容 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]

    for correction in report.get("start_amendments", []):
        lines.insert(8, f"- 起始时间更正：{correction['previous_started_at']} → {correction['started_at']}；依据：{correction['evidence']}")
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
                    model=stage.get("model") or "未核实",
                    status=STAGE_STATUS[stage["status"]],
                    duration=duration_text(duration),
                    summary=summary.replace("|", "\\|"),
                )
            )

    preparations = [s for s in stages if s["stage_id"] == "website_preparation"]
    if preparations:
        website_stages = [s for s in stages if s["stage_id"] in
                          {"website_preparation", "website_sync", "website_closure"}]
        end = website_stages[-1].get("finished_at")
        seconds = elapsed_seconds(preparations[0]["started_at"], end)
        lines.extend(["", f"网站全过程：{duration_text(seconds)}（{seconds:.3f} 秒，含准备、提交、排错及收口；执行中则计至当前）。"])
    if any(s.get("model_source") == "session_log" for s in stages):
        lines.extend(["", "模型取自各环节开始时的本任务日志；具体证据和推理档位保存在 JSON 中。"])

    reviews = report.get("reviews", [])
    if reviews:
        lines.extend([
            "", "## 子智能体审核", "",
            f"已登记 {len(reviews)} 个独立会话，其中本次报告期间新建 {sum(r['created_during_run'] for r in reviews)} 个；"
            f"共处理 {sum(r['turn_count'] for r in reviews)} 轮；未登记关闭 {sum(not r['closed'] for r in reviews)} 个。",
            "运行时间来自子智能体日志，不是纯模型推理时间；轮次间隔包括主笔处理、讨论及其它工作，不能全部称为审核等待或主笔修改。历史复盘不计入本次任务总耗时。",
            "", "| 角色 | 名称 | 轮次 | 已结束轮次运行时间 | 轮次间隔 | 收口 |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ])
        for review in reviews:
            lines.append(f"| {review['role']} | {review['nickname']} | {review['turn_count']} | "
                         f"{duration_text(review['running_seconds'])} | "
                         f"{duration_text(review['between_rounds_seconds'])} | "
                         f"{'已关闭' if review['closed'] else '未登记关闭'} |")
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
    started_at = now().isoformat(timespec="milliseconds")
    report["stages"].append({
        "stage_id": args.stage_id,
        "attempt": attempts,
        "name": args.name,
        "role": args.role,
        **stage_model(args.model, started_at),
        "mode": args.mode,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "elapsed_seconds": None,
        "summary": [],
        "outputs": [],
    })
    save(report_path, markdown_path, report)
    return {"ok": True, "stage_id": args.stage_id, "attempt": attempts}


def command_start_amend(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    value = parse_time(args.started_at)
    if value.tzinfo is None or value > parse_time(report["started_at"]):
        raise SystemExit("起始时间必须带时区，且只能依据记录补回更早的实际开始时间。")
    if not args.evidence.strip():
        raise SystemExit("必须提供原始计时依据，不能估算。")
    report.setdefault("start_amendments", []).append({
        "amended_at": iso(), "previous_started_at": report["started_at"],
        "started_at": iso(value), "evidence": args.evidence,
    })
    report["started_at"] = iso(value)
    for review in report.get("reviews", []):
        review["created_during_run"] = parse_time(review["created_at"]) >= value
    save(report_path, markdown_path, report)
    return {"ok": True, "started_at": report["started_at"],
            "elapsed_seconds": elapsed_seconds(report["started_at"], report.get("finished_at"))}


def command_stage_finish(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    stage = latest_stage(report, args.stage_id)
    if stage["status"] != "running":
        raise SystemExit(f"环节不是执行中状态：{args.stage_id}")
    if args.stage_id == "website_sync" and args.status in ("completed", "completed_with_issues"):
        raise SystemExit("网站提交成功请用 website-finish --result 导入浏览器原始结果，不能用补写报告的时间代替提交时间。")
    stage["finished_at"] = now().isoformat(timespec="milliseconds")
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
    if args.status == "mitigated" and not args.resolution.strip():
        raise SystemExit("交付恢复必须说明验证结果和仍未修复的根因。")
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
    if (args.status or issue["status"]) == "mitigated" and not (
        args.resolution if args.resolution is not None else issue.get("resolution", "")
    ).strip():
        raise SystemExit("交付恢复必须说明验证结果和仍未修复的根因。")
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
    if running and running != ["website_closure"]:
        raise SystemExit("仍有执行中的环节：" + ", ".join(running))
    if args.status in ("completed", "completed_with_issues"):
        if any(not review.get("closed") for review in report.get("reviews", [])):
            raise SystemExit("仍有审核会话未登记关闭；先关闭不再需要的会话并更新记录。")
        if any(issue["status"] == "open" for issue in report["issues"]):
            raise SystemExit("仍有未解决的问题；不能标记完成。")
        latest = {stage["stage_id"]: stage for stage in report["stages"]}
        if any(stage["status"] == "failed" for stage in latest.values()):
            raise SystemExit("仍有失败环节未完成重试；不能标记完成。")
        if args.status == "completed" and report["issues"]:
            raise SystemExit("存在问题记录；请使用 completed_with_issues。")
    report["status"] = args.status
    report["finished_at"] = now().isoformat(timespec="milliseconds")
    if running == ["website_closure"]:
        closure = latest_stage(report, "website_closure")
        closure.update(status="completed", finished_at=report["finished_at"],
                       elapsed_seconds=elapsed_seconds(closure["started_at"], report["finished_at"]),
                       summary=["保存同步结果并完成本轮记录。"])
    report["summary"] = args.summary or []
    save(report_path, markdown_path, report)
    return {"ok": True, "status": args.status, "elapsed_seconds": elapsed_seconds(report["started_at"], report["finished_at"])}


def begin_website_preparation(process_dir: Path, database: str, topic_id: str, topic_name: str) -> dict[str, Any]:
    """Start the end-to-end clock before local or browser preparation."""
    report_path, _ = paths(str(process_dir))
    if report_path.exists():
        report = load(report_path)
        if report["database"].casefold() != database.casefold() or report["topic_id"] != topic_id:
            raise ValueError("执行报告与本次数据库或主题不一致；未改动报告。")
        other_running = [s["stage_id"] for s in report["stages"]
                         if s["status"] == "running" and s["stage_id"] != "website_preparation"]
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
              if s["stage_id"] == "website_preparation" and s["status"] == "running"]
    if not active:
        command_stage_start(argparse.Namespace(
            process_dir=str(process_dir), stage_id="website_preparation", name="网站准备",
            role="主执行者", model="", mode="work",
        ))
        report = load(report_path)
    stage = latest_stage(report, "website_preparation")
    return {"report": str(report_path), "run_id": report["run_id"],
            "stage_id": stage["stage_id"], "started_at": stage["started_at"]}


def begin_website_sync(process_dir: Path, database: str, topic_id: str, topic_name: str) -> dict[str, Any]:
    report_path, _ = paths(str(process_dir))
    report = load(report_path)
    if report["database"].casefold() != database.casefold() or report["topic_id"] != topic_id:
        raise ValueError("执行报告与本次数据库或主题不一致；未改动报告。")
    running = [s for s in report["stages"] if s["status"] == "running"]
    if report["status"] != "running" or len(running) != 1 or running[0]["stage_id"] not in {
        "website_preparation", "website_sync"
    }:
        raise ValueError("先运行 website-prepare 记录准备过程，并结束其它实际工作环节。")
    if running[0]["stage_id"] == "website_preparation":
        command_stage_finish(argparse.Namespace(
            process_dir=str(process_dir), stage_id="website_preparation", status="completed",
            summary=["本地检查、登录核对和 helper 预载完成。"], output=[],
        ))
        command_stage_start(argparse.Namespace(
            process_dir=str(process_dir), stage_id="website_sync", name="网站提交",
            role="主执行者", model="", mode="work",
        ))
    elif not any(s["stage_id"] == "website_preparation" and s["status"] == "completed"
                 for s in report["stages"]):
        raise ValueError("缺少准备计时；不能用手工创建的提交环节跳过 website-prepare。")
    stage = latest_stage(load(report_path), "website_sync")
    return {"report": str(report_path), "run_id": report["run_id"], "attempt": stage["attempt"],
            "stage_id": stage["stage_id"], "started_at": stage["started_at"]}


def command_website_prepare(args: argparse.Namespace) -> dict[str, Any]:
    return begin_website_preparation(Path(args.process_dir), args.database, args.topic_id, args.topic_name)


def command_website_finish(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    stage = latest_stage(report, "website_sync")
    result = json.loads(args.result.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise SystemExit("浏览器结果必须是原始 JSON 对象。")
    if (report["status"] != "running" or stage["status"] != "running" or
        result.get("sync_run_id") != report["run_id"] or
        result.get("sync_attempt") != stage["attempt"] or
        result.get("sync_started_at") != stage["started_at"]):
        raise SystemExit("同步结果不属于本次仍在执行的提交；未改动报告。")
    checks = ("edit_url_verified", "title_verified", "body_verified",
              "attachment_order_verified", "article_page_returned")
    quality = result.get("quality_checks")
    if (result.get("ok") is not True or result.get("status") != "ARTICLE_PAGE_RETURNED" or
        not isinstance(quality, dict) or any(quality.get(key) is not True for key in checks)):
        raise SystemExit("浏览器没有返回完整的同步成功证据；请记录实际失败。")
    if not re.fullmatch(r"[0-9a-f]{64}", str(result.get("preload_sha256", ""))):
        raise SystemExit("缺少固定提交程序的哈希记录。")
    values = [result.get(key) for key in ("dispatch_latency_ms", "browser_elapsed_ms",
                                          "sync_elapsed_to_browser_return_ms")]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        raise SystemExit("浏览器耗时缺失或无效。")
    dispatch, browser, total = values
    if abs(dispatch + browser - total) > 1:
        raise SystemExit("浏览器计时相互矛盾。")
    finished = parse_time(stage["started_at"]) + timedelta(milliseconds=total)
    if finished > now() + timedelta(seconds=1):
        raise SystemExit("浏览器完成时间在未来；检查原始结果。")
    stage.update(status="completed", finished_at=finished.isoformat(timespec="milliseconds"),
                 elapsed_seconds=round(total / 1000, 3),
                 summary=["正文和附件已提交，返回文章页。"], outputs=[str(args.result.resolve())],
                 browser_result=result)
    report["stages"].append({
        "stage_id": "website_closure", "attempt": stage["attempt"], "name": "网站收口",
        "role": stage["role"], "model": stage["model"], "model_source": stage.get("model_source"),
        "mode": "work", "status": "running", "started_at": stage["finished_at"],
        "finished_at": None, "elapsed_seconds": None, "summary": [], "outputs": [],
    })
    save(report_path, markdown_path, report)
    return {"ok": True, "submission_seconds": stage["elapsed_seconds"],
            "next_action": "保存其余记录后执行 finish；提交返回之后的时间单列为网站收口。"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preparation = subparsers.add_parser("website-prepare")
    preparation.add_argument("--process-dir", required=True)
    preparation.add_argument("--database", required=True)
    preparation.add_argument("--topic-id", required=True)
    preparation.add_argument("--topic-name", required=True)
    preparation.set_defaults(func=command_website_prepare)

    website_finish = subparsers.add_parser("website-finish")
    website_finish.add_argument("--process-dir", required=True)
    website_finish.add_argument("--result", required=True, type=Path)
    website_finish.set_defaults(func=command_website_finish)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--process-dir", required=True)
    init_parser.add_argument("--database", required=True)
    init_parser.add_argument("--topic-id", required=True)
    init_parser.add_argument("--topic-name", required=True)
    init_parser.add_argument("--task", required=True)
    init_parser.set_defaults(func=command_init)

    start_amend = subparsers.add_parser("start-amend")
    start_amend.add_argument("--process-dir", required=True)
    start_amend.add_argument("--started-at", required=True)
    start_amend.add_argument("--evidence", required=True)
    start_amend.set_defaults(func=command_start_amend)

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
    issue_parser.add_argument("--status", required=True, choices=tuple(ISSUE_STATUS))
    issue_parser.set_defaults(func=command_issue)

    amend_parser = subparsers.add_parser("issue-amend")
    amend_parser.add_argument("--process-dir", required=True)
    amend_parser.add_argument("--issue-number", required=True, type=int)
    amend_parser.add_argument("--description")
    amend_parser.add_argument("--impact")
    amend_parser.add_argument("--resolution")
    amend_parser.add_argument("--status", choices=tuple(ISSUE_STATUS))
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

    review_parser = subparsers.add_parser("review-import")
    review_parser.add_argument("--process-dir", required=True)
    review_parser.add_argument("--log", required=True, type=Path)
    review_parser.add_argument("--role", required=True)
    review_parser.add_argument("--closed", action="store_true",
                               help="Use only after the agent close tool succeeded.")
    review_parser.set_defaults(func=command_review_import)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
