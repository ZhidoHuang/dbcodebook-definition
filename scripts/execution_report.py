#!/usr/bin/env python3
"""Record truthful stage timing and issues for a definition-topic run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from writing_evidence import capture_copy, skill_version
from source_record_binding import research_record, SOURCE_SCOPE
from exploration_handoff import POLICY as EXPLORATION_POLICY, validate_exploration, add_commands


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
WORKFLOWS = {
    "general": "一般任务",
    "full_definition": "完整定义流程",
    "website_only": "仅网站同步",
}
FULL_DEFINITION_STAGES = {
    "locate": "任务定位与既有材料检查",
    "sources": "来源探索与权威材料核对",
    "download": "最终来源选择与下载",
    "formal_r": "正式 R 编写、运行与成果生成",
    "validation": "机器验证与成品交接",
}
FULL_DEFINITION_REVIEW_ROLES = {
    "定义逻辑复核",
    "公开 R 复核",
    "普通读者复核",
}
MAX_UNTRACKED_SECONDS = 60
REVIEW_POLICY = "execution_first_v1"
COMBINED_REVIEW_ROLE = "公开 R 复核"


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


def validate_full_definition_completion(
    report: dict[str, Any], finished_at: datetime
) -> None:
    if report.get("workflow", "general") != "full_definition":
        return
    latest = {stage["stage_id"]: stage for stage in report.get("stages", [])}
    required_stages = dict(FULL_DEFINITION_STAGES)
    # The three production steps may be timed separately; do not require a
    # fabricated aggregate stage just to satisfy a different stage name.
    if "formal_r" not in latest and any(key in latest for key in ("copy", "public_r", "generate")):
        required_stages.pop("formal_r")
        required_stages.update(copy="文案定稿", public_r="正式 R 编写与复核", generate="成果生成")
    if "validation" not in latest and any(key in latest for key in ("results", "review")):
        required_stages.pop("validation")
        required_stages.update(results="结果验证", review="成品交接")
    terminal_statuses = {"completed", "completed_with_issues", "skipped"}
    missing = [
        f"{stage_id}（{label}）"
        for stage_id, label in required_stages.items()
        if stage_id not in latest
        or latest[stage_id].get("status") not in terminal_statuses
    ]
    if missing:
        raise SystemExit("完整定义流程缺少已收口环节：" + "、".join(missing))
    unexplained_skips = [
        f"{stage_id}（{label}）"
        for stage_id, label in required_stages.items()
        if latest[stage_id].get("status") == "skipped"
        and not latest[stage_id].get("summary")
    ]
    if unexplained_skips:
        raise SystemExit(
            "完整定义流程的未执行环节没有说明原因：" + "、".join(unexplained_skips)
        )

    validate_exploration(report)

    closed_roles = {
        review.get("role")
        for review in report.get("reviews", [])
        if review_lifecycle_complete(review)
    }
    for role, review in report.get("stage_reviews", {}).items():
        if (review.get("mode") == "isolated" or review.get("reused_from")) and review.get("status") == "pass":
            validate_stage_review(report, role)
            closed_roles.add(role)
    required_roles = FULL_DEFINITION_REVIEW_ROLES
    if report.get("review_policy") == REVIEW_POLICY:
        required_roles = {COMBINED_REVIEW_ROLE}
        validate_stage_review(report, COMBINED_REVIEW_ROLE)
    missing_roles = sorted(required_roles - closed_roles)
    if missing_roles:
        raise SystemExit("完整定义流程缺少已完成审核：" + "、".join(missing_roles))

    run_start = parse_time(report["started_at"])
    run_end = finished_at
    intervals: list[tuple[datetime, datetime]] = []
    for stage in report.get("stages", []):
        start_text = stage.get("started_at")
        if not start_text:
            continue
        start = max(parse_time(start_text), run_start)
        end_text = stage.get("finished_at")
        end = parse_time(end_text) if end_text else run_end
        end = min(end, run_end)
        if end > start:
            intervals.append((start, end))
    intervals.sort(key=lambda item: item[0])
    covered_seconds = 0.0
    merged_start: datetime | None = None
    merged_end: datetime | None = None
    for start, end in intervals:
        if merged_start is None:
            merged_start, merged_end = start, end
        elif start <= merged_end:
            merged_end = max(merged_end, end)
        else:
            covered_seconds += (merged_end - merged_start).total_seconds()
            merged_start, merged_end = start, end
    if merged_start is not None and merged_end is not None:
        covered_seconds += (merged_end - merged_start).total_seconds()
    total_seconds = max(0.0, (run_end - run_start).total_seconds())
    untracked_seconds = max(0.0, total_seconds - covered_seconds)
    report["timing_coverage"] = {
        "covered_seconds": round(covered_seconds, 3),
        "untracked_seconds": round(untracked_seconds, 3),
        "status": "incomplete" if untracked_seconds > MAX_UNTRACKED_SECONDS else "complete",
        "note": "未归属区间不推定为工作或等待，不补造阶段；不代替成果质量结论。",
    }


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


def review_lifecycle_complete(review):
    if review.get("unfinished_turns"):
        return False
    if review.get("closed"):
        return True
    rounds = review.get("rounds", [])
    return bool(review.get("close_unavailable") and rounds and rounds[-1].get("outcome") == "completed")


def read_review_log(log_path: Path, role: str) -> dict[str, Any]:
    """Read one explicitly selected agent log, never the whole session archive."""
    meta = None
    models = []
    contexts = {}
    turns = {}
    with log_path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get("payload", {})
            if event.get("type") == "session_meta" and meta is None:
                meta = payload
            elif event.get("type") == "turn_context":
                contexts[payload.get("turn_id")] = {"model": payload.get("model"), "effort": payload.get("effort")}
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
    if not spawn and meta.get("forked_from_id"):
        # Session logs contain timestamps and parent identity; CLI console JSONL does not.
        spawn = {"parent_thread_id": meta["forked_from_id"], "agent_nickname": meta["id"]}
    if not spawn:
        raise ValueError("selected log has no verifiable reviewer parent; use the reviewer session log, not CLI console output")
    rounds = sorted(turns.values(), key=lambda item: parse_time(item["started_at"]))
    prior_end = None
    for item in rounds:
        item.update(contexts.get(item["turn_id"], {"model": None, "effort": None}))
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
    all_rounds = review["rounds"]
    selected_ids = getattr(args, "turn_id", None)
    start = parse_time(report["started_at"])
    end = now()
    rounds = [item for item in all_rounds if start <= parse_time(item["started_at"]) <= end]
    if selected_ids:
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("重复的复核轮次")
        rounds = [item for item in rounds if item["turn_id"] in selected_ids]
        if {item["turn_id"] for item in rounds} != set(selected_ids):
            raise ValueError("指定复核轮次不存在或不属于本次报告时间范围")
    if not rounds:
        raise ValueError("本次任务没有复核轮次；历史结论请沿用，不重新导入为本次工作")
    if all_rounds[-1].get("finished_at") is None and all_rounds[-1] not in rounds:
        raise ValueError("代理仍有未结束轮次，不能通过筛选隐藏")
    for index, item in enumerate(rounds):
        item["gap_before_seconds"] = (elapsed_seconds(rounds[index - 1]["finished_at"], item["started_at"])
                                     if index and rounds[index - 1]["finished_at"] else 0)
    review.update(rounds=rounds, turn_count=len(rounds),
                  running_seconds=round(sum(item["elapsed_seconds"] or 0 for item in rounds), 3),
                  between_rounds_seconds=round(sum(item["gap_before_seconds"] for item in rounds), 3),
                  unfinished_turns=sum(item["finished_at"] is None for item in rounds),
                  excluded_turn_count=len(all_rounds) - len(rounds),
                  timing_scope={"started_at": report["started_at"], "through": iso(end),
                                "turn_ids": [item["turn_id"] for item in rounds]})
    if args.closed and review["unfinished_turns"]:
        raise SystemExit("审核日志仍有未结束轮次，不能登记为已关闭。")
    limitation = getattr(args, "close_unavailable", None)
    if limitation and (not limitation.strip() or review["unfinished_turns"] or review["rounds"][-1].get("outcome") != "completed"):
        raise SystemExit("缺少关闭工具的例外只适用于日志确认已完成的审核，并须说明工具限制。")
    reviews = report.setdefault("reviews", [])
    prior = next((item for item in reviews if item["agent_id"] == review["agent_id"]), None)
    same_rounds = prior and [r["turn_id"] for r in prior.get("rounds", [])] == [r["turn_id"] for r in rounds]
    review["closed"] = bool(args.closed or (same_rounds and prior.get("closed")))
    review["close_unavailable"] = limitation or ((prior or {}).get("close_unavailable") if same_rounds else None)
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


def input_hashes(paths, r_scope="full", source_scope="legacy"):
    result = {}
    for value in paths:
        path = Path(value).resolve(strict=True)
        if not path.is_file():
            raise ValueError("审核输入必须是文件：" + str(path))
        content = path.read_bytes()
        if r_scope == "public" and path.suffix.lower() == ".r":
            source = content.decode("utf-8-sig")
            matches = list(re.finditer(r"(?m)^# 输出\s*$", source))
            if len(matches) != 1:
                raise ValueError("公开 R 范围绑定要求唯一的 # 输出 分界")
            content = source[:matches[0].start()].encode("utf-8")
        if path.name == "definition_search_record.json":
            plan = json.loads(content.decode("utf-8-sig"))
            # Recording the review verdict does not change its source-plan input.
            plan.pop("logic_review", None)
            if source_scope == SOURCE_SCOPE:
                plan = research_record(plan)
            elif source_scope != "legacy":
                raise ValueError("Unknown source binding scope")
            content = json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")
        result[str(path)] = hashlib.sha256(content).hexdigest()
    if not result:
        raise ValueError("审核不能没有输入")
    return result


def validate_stage_review(report, role, required_inputs=None):
    review = report.get("stage_reviews", {}).get(role)
    if not review or review.get("status") != "pass" or not review.get("evidence", "").strip():
        raise ValueError("本环节审核尚未通过：" + role)
    if input_hashes(review["inputs"], review.get("r_scope", "full"), review.get("source_scope", "legacy")) != review["inputs"]:
        raise ValueError("审核输入已变化，须复核受影响部分：" + role)
    if required_inputs:
        expected = input_hashes(required_inputs, review.get("r_scope", "full"), review.get("source_scope", "legacy"))
        bound = {Path(path): digest for path, digest in review["inputs"].items()}
        if any(bound.get(Path(path)) != digest for path, digest in expected.items()):
            raise ValueError("实际运行输入未绑定到本次审核：" + role)
    if review.get("mode") == "isolated":
        if report.get("review_policy") == REVIEW_POLICY and role == COMBINED_REVIEW_ROLE:
            raise ValueError("定义逻辑与 R 实现需要独立复核，隔离自查不能替代")
        if not review.get("limitation", "").strip():
            raise ValueError("隔离自查缺少环境限制说明")
    else:
        agent = review.get("prior_agent_record") or next((item for item in report.get("reviews", []) if item["agent_id"] == review.get("agent_id")), None)
        latest = max(agent.get("rounds", []), key=lambda item: parse_time(item["started_at"]), default={}) if agent else {}
        if (not agent or agent["role"] != role or agent["unfinished_turns"]
                or latest.get("outcome") != "completed"
                or parse_time(latest["started_at"]) < parse_time(review["started_at"])):
            raise ValueError("缺少本轮实际完成的只读审核记录：" + role)
    return review


def command_review_stage(args):
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    if args.command == "review-check":
        if args.role == COMBINED_REVIEW_ROLE:
            validate_exploration(report)
        if args.role not in report.get("stage_reviews", {}):
            candidates = sorted(report_path.parent.glob("archived_runs/*/execution_report.json"),
                                key=lambda path: path.stat().st_mtime, reverse=True)
            for path in candidates:
                previous = load(path)
                if (report.get("review_policy") == REVIEW_POLICY
                        and args.role == COMBINED_REVIEW_ROLE
                        and previous.get("review_policy") != REVIEW_POLICY):
                    continue
                if args.role not in previous.get("stage_reviews", {}):
                    continue
                prior = validate_stage_review(previous, args.role, getattr(args, "input", None))
                agent = prior.get("prior_agent_record") or next((item for item in previous.get("reviews", [])
                    if item["agent_id"] == prior.get("agent_id")), None)
                report.setdefault("stage_reviews", {})[args.role] = {
                    **prior, "reused_from": str(path), "prior_agent_record": agent}
                if report["status"] == "running" and not getattr(args, "read_only", False):
                    save(report_path, markdown_path, report)
                break
        review = validate_stage_review(report, args.role, getattr(args, "input", None))
        return {"ok": True, "role": args.role, "mode": review["mode"], "input_count": len(review["inputs"])}
    if report["status"] != "running":
        raise ValueError("审核交接须在正在执行的报告中登记")
    reviews = report.setdefault("stage_reviews", {})
    if args.command == "review-start":
        scope = getattr(args, "r_scope", "full")
        inputs = input_hashes(args.input, scope, SOURCE_SCOPE)
        previous = reviews.get(args.role)
        if previous:
            report.setdefault("stage_review_history", {}).setdefault(args.role, []).append(dict(previous))
        reviews[args.role] = {"status": "pending", "started_at": iso(), "inputs": inputs, "r_scope": scope, "source_scope": SOURCE_SCOPE}
        if previous and any(not f["resolved"] for f in previous.get("findings", [])):
            reviews[args.role]["findings"] = [dict(f) for f in previous["findings"] if not f["resolved"]]
    else:
        prior = reviews.get(args.role)
        if not prior or input_hashes(prior["inputs"], prior.get("r_scope", "full"), prior.get("source_scope", "legacy")) != prior["inputs"]:
            raise ValueError("先绑定稳定输入；审核期间发生变化则重新发起受影响复核")
        if not args.evidence.strip():
            raise ValueError("必须保留审核者的具体发现与结论")
        updated = {**prior, "status": args.result, "evidence": args.evidence,
                   "agent_id": args.agent_id, "limitation": args.isolated_reason,
                   "mode": "isolated" if args.isolated_reason else "independent", "finished_at": iso()}
        findings_file = getattr(args, "findings_file", None)
        if findings_file:
            findings = json.loads(findings_file.read_text(encoding="utf-8-sig"))
            if not isinstance(findings, list):
                raise ValueError("findings-file must contain a JSON list")
            for finding in findings:
                if not isinstance(finding, dict) or any(not isinstance(finding.get(k), str) or not finding[k].strip()
                        for k in ("category", "location", "problem", "evidence")):
                    raise ValueError("Each finding requires category, location, problem and evidence")
                if any(type(finding.get(k)) is not bool for k in ("changed_artifact", "resolved")):
                    raise ValueError("changed_artifact and resolved must be booleans")
            if args.result == "pass" and any(not f["resolved"] for f in findings):
                raise ValueError("Unresolved review findings cannot pass")
            updated["findings"] = findings
        if args.result == "pass" and any(not f["resolved"] for f in updated.get("findings", [])):
            raise ValueError("Unresolved review findings cannot pass")
        if prior.get("status") != "pending":
            report.setdefault("stage_review_history", {}).setdefault(args.role, []).append(dict(prior))
        reviews[args.role] = updated
        if args.result == "pass":
            validate_stage_review(report, args.role)
    save(report_path, markdown_path, report)
    return {"ok": True, "role": args.role, "status": reviews[args.role]["status"]}


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
        f"- 流程：{WORKFLOWS.get(report.get('workflow', 'general'), report.get('workflow', 'general'))}",
        f"- 状态：{RUN_STATUS[report['status']]}",
        f"- 开始：{report['started_at']}",
        f"- 结束：{finished_at or '尚未结束'}",
        f"- 报告计时区间：{duration_text(total)}（{total:.3f} 秒；截至报告收口，不含之后的回复时间）",
        f"- Bug：{bug_count} 个；异常：{abnormal_count} 个；等待：{wait_count} 个；未解决：{open_count + pending_count} 个（仍阻断交付 {open_count} 个，已恢复但根因待修复 {pending_count} 个）",
        "",
        "## 环节耗时",
        "",
        "| 环节 | 性质 | 执行者 | 模型 | 状态 | 耗时 | 完成内容 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]

    exploration = report.get("exploration")
    if exploration:
        merge = exploration.get("merge", {})
        lines[12:12] = ["## 双路探索", "", f"- 已登记分支：{', '.join(exploration.get('branches', {})) or '无'}",
            f"- 主线程合并：{merge.get('status', '未完成')}",
            f"- 未决事项：{'; '.join(merge.get('unresolved', [])) or '见合并依据'}",
            f"- 合并依据：{', '.join(merge.get('decision', {})) or '未提供'}", ""]

    timing = report.get("timing_coverage")
    if timing:
        lines.insert(8, f"- 未归属阶段时间：{duration_text(timing['untracked_seconds'])}；计时覆盖：{timing['status']}。不推定其为工作或等待，不影响成果完成状态。")
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
                    model=(stage.get("model") or "未核实") + " / " + (stage.get("model_evidence", {}).get("effort") or "未核实"),
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
            "", "| 角色 | 名称 | 实际模型 / 推理档位 | 轮次 | 已结束轮次运行时间 | 轮次间隔 | 收口 |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ])
        for review in reviews:
            models = list(dict.fromkeys(f"{r.get('model') or '未核实'} / {r.get('effort') or '未核实'}" for r in review.get("rounds", [])))
            lifecycle = '已关闭' if review['closed'] else ('审核已完成；宿主无关闭工具' if review_lifecycle_complete(review) else '未登记关闭')
            lines.append(f"| {review['role']} | {review['nickname']} | {'; '.join(models)} | {review['turn_count']} | "
                         f"{duration_text(review['running_seconds'])} | "
                         f"{duration_text(review['between_rounds_seconds'])} | "
                         f"{lifecycle} |")
            if review.get("close_unavailable"):
                lines.append(f"关闭限制（{review['nickname']}）：{review['close_unavailable']}")
    if report.get("execution_metrics"):
        metrics = report["execution_metrics"]
        lines.extend(["", "## 执行用量（指定日志范围）", "",
                      "请求数仅指有用量事件的请求；缓存输入包含在总输入内。不换算价格或额度，缺失值显示未提供。",
                      "| 会话 | 有用量请求 | 输入 | 缓存输入 | 输出 | 最大请求输入 | 工具调用 | 相同调用重复 | 最大工具输出字符 |",
                      "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for item in metrics["logs"]:
            tokens = item["tokens"] or {}
            values = [item["session_id"] or item["log"], item["requests_with_usage"],
                      tokens.get("input_tokens"), tokens.get("cached_input_tokens"), tokens.get("output_tokens"),
                      item["largest_request_input_tokens"], item["tool_calls"],
                      item["repeated_identical_tool_calls"], item["max_tool_output_chars"]]
            lines.append("| " + " | ".join("未提供" if v is None else str(v) for v in values) + " |")
        lines.append(f"已登记返工段：{metrics['rework_segments']}。相同调用不等于无效调用；任意 shell 的重复读文件次数、错误重跑原因无法可靠自动推断，未伪造统计。")
    if report.get("summary"):
        lines.extend(["", "## 执行结果", "", *report["summary"]])
    if report.get("turn_timing"):
        timing = report["turn_timing"]
        lines.extend(["", "## 任务轮次实耗", "",
                      f"原始任务日志：{timing['started_at']} 至 {timing['finished_at']}，共 {duration_text(timing['elapsed_seconds'])}（{timing['elapsed_seconds']:.3f} 秒）。",
                      f"报告初始化前 {timing['before_report_seconds']:.3f} 秒；报告收口后 {timing['after_report_seconds']:.3f} 秒。两者不是某个业务步骤的纯操作时间。"])
    if report.get("stage_reviews"):
        lines.extend(["", "## 环节审核交接", ""])
        for role, review in report["stage_reviews"].items():
            mode = "隔离自查（非独立复核）" if review.get("mode") == "isolated" else "只读角色复核"
            lines.append(f"- {role}：{review['status']}；{mode}；输入 {len(review['inputs'])} 份。")
            findings = review.get("findings")
            if findings is not None:
                lines.append(f"  当前结论发现 {len(findings)} 条；改变成果 {sum(f['changed_artifact'] for f in findings)} 条；当前未解决 {sum(not f['resolved'] for f in findings)} 条。")
                for finding in findings:
                    lines.append(f"  - {finding['category']} / {finding['location']}：{finding['problem']}；依据：{finding['evidence']}")
            else:
                lines.append("  发现数量未结构化登记，不等于零发现。")
            if review.get("limitation"):
                lines.append("  环境限制：" + review["limitation"])
            if review.get("reused_from"):
                lines.append("  沿用当前输入未变的既有结论，不计本轮新增审核耗时：" + review["reused_from"])
            if review.get("evidence"):
                lines.append("  实际结论：" + review["evidence"])
            history = report.get("stage_review_history", {}).get(role, [])
            if history:
                rounds = [*history, review]
                structured = [r for r in rounds if "findings" in r]
                occurrences = sum(len(r["findings"]) for r in structured)
                changed = sum(any(f["changed_artifact"] for f in r["findings"]) for r in structured)
                lines.append(f"  保留 {len(rounds)} 次绑定/结论记录；累计结构化发现 {occurrences} 条次（同一问题跨轮可重复），其中 {changed} 次记录包含成果修改。")
                lines.append("  未结构化登记的记录不推定零发现；修改记录数不等于独立审核会话轮次。")
                for i, prior in enumerate(history, 1):
                    lines.append(f"  - 历史 {i}：{prior['status']}；{prior.get('evidence', '未完成结论')}；输入版本保存在 JSON。")
                    for finding in prior.get("findings", []):
                        lines.append(f"    - {finding['location']}：{finding['problem']}；已解决={finding['resolved']}")
            else:
                lines.append("  未保存此前结构化轮次，不以当前结论反推整个过程零发现。")
    if report.get("first_copy"):
        first = report["first_copy"]
        lines.extend(["", "## 首次完整文案", ""])
        if first["status"] == "captured":
            lines.extend([f"- 首稿：{first['snapshot_path']}", f"- SHA256：{first['sha256']}",
                          f"- Skill 内容版本：{first['skill_version']}",
                          "- 首份已记录完整文案的快照；是否早于检查以实际记录为准，不是语义合格证明。"])
        else:
            lines.append(first["reason"])
        lines.append(f"- 已登记文案交接 {len(report.get('copy_history', []))} 次；后续版本不覆盖首次记录。")
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
        "review_policy": REVIEW_POLICY,
        "exploration_policy": EXPLORATION_POLICY if getattr(args, "workflow", "full_definition") == "full_definition" else None,
        "run_id": str(uuid.uuid4()),
        "database": args.database,
        "topic_id": args.topic_id,
        "topic_name": args.topic_name,
        "task": args.task,
        "workflow": getattr(args, "workflow", "full_definition"),
        "status": "running",
        "started_at": iso(),
        "finished_at": None,
        "updated_at": None,
        "summary": [],
        "stages": [],
        "issues": [],
    }
    version = skill_version()
    report["skill_version_at_start"] = version["id"]
    report["skill_versions"] = {version["id"]: version["files"]}
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
    value = None
    with args.log.open(encoding="utf-8-sig") as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get("payload", {})
            if (event.get("type") == "event_msg" and payload.get("type") == "task_started"
                    and payload.get("turn_id") == args.turn_id):
                value = parse_time(event["timestamp"])
                break
    if value is None:
        raise SystemExit("日志中没有该轮次的开始事件；保留现有计时，不估算。")
    if value.tzinfo is None or value > parse_time(report["started_at"]):
        raise SystemExit("起始时间必须带时区，且只能依据记录补回更早的实际开始时间。")
    evidence = f"{args.log.resolve()} / turn_id={args.turn_id} / task_started"
    report.setdefault("start_amendments", []).append({
        "amended_at": iso(), "previous_started_at": report["started_at"],
        "started_at": iso(value), "evidence": evidence,
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
    if args.stage_id == "copy" and (args.status in ("completed", "completed_with_issues") or getattr(args, "copy", None)):
        capture_copy(report, report_path.parent, stage, getattr(args, "copy", None))
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


def command_turn_timing(args):
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    if report["status"] == "running":
        raise SystemExit("任务轮次结束后才导入完整耗时，不估算尚未完成的时间。")
    start = end = None
    with args.log.open(encoding="utf-8-sig") as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get("payload", {})
            if event.get("type") != "event_msg" or payload.get("turn_id") != args.turn_id:
                continue
            if payload.get("type") == "task_started":
                start = event["timestamp"]
            elif payload.get("type") in {"task_complete", "turn_aborted"}:
                end = event["timestamp"]
    if not start or not end or not (parse_time(start) <= parse_time(report["started_at"]) <= parse_time(report["finished_at"]) <= parse_time(end)):
        raise SystemExit("该完整任务轮次不包含报告计时区间，不能混用两次任务的耗时。")
    report["turn_timing"] = {"log": str(args.log.resolve()), "turn_id": args.turn_id,
        "started_at": start, "finished_at": end, "elapsed_seconds": elapsed_seconds(start, end),
        "before_report_seconds": elapsed_seconds(start, report["started_at"]),
        "after_report_seconds": elapsed_seconds(report["finished_at"], end)}
    save(report_path, markdown_path, report)
    return {"ok": True, **report["turn_timing"]}


def command_finish(args: argparse.Namespace) -> dict[str, Any]:
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    running = [stage["stage_id"] for stage in report["stages"] if stage["status"] == "running"]
    if running and running != ["website_closure"]:
        raise SystemExit("仍有执行中的环节：" + ", ".join(running))
    if args.status in ("completed", "completed_with_issues"):
        if any(not review_lifecycle_complete(review) for review in report.get("reviews", [])):
            raise SystemExit("仍有审核会话未登记关闭；先关闭不再需要的会话并更新记录。")
        if any(issue["status"] == "open" for issue in report["issues"]):
            raise SystemExit("仍有未解决的问题；不能标记完成。")
        latest = {stage["stage_id"]: stage for stage in report["stages"]}
        if any(stage["status"] == "failed" for stage in latest.values()):
            raise SystemExit("仍有失败环节未完成重试；不能标记完成。")
        if args.status == "completed" and report["issues"]:
            raise SystemExit("存在问题记录；请使用 completed_with_issues。")
        validate_full_definition_completion(report, now())
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
            workflow="website_only",
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
    try:
        result_json = getattr(args, "result_json", None)
        if result_json is not None:
            result = json.loads(result_json)
        else:
            result = json.loads(args.result.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"无法读取浏览器同步结果：{error}") from error
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
    result_path = report_path.parent / "website_sync_result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stage.update(status="completed", finished_at=finished.isoformat(timespec="milliseconds"),
                 elapsed_seconds=round(total / 1000, 3),
                 summary=["正文和附件已提交，返回文章页。"], outputs=[str(result_path.resolve())],
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


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    report = load(args.report)
    if report.get("workflow") != "full_definition":
        raise SystemExit("Only full_definition registration is supported by check.")
    if not report.get("finished_at"):
        raise SystemExit("Report has no finished_at; historical completion cannot be checked.")
    validate_full_definition_completion(report, parse_time(report["finished_at"]))
    return {"ok": True, "scope": "registration_only", "read_only": True,
            "report": str(args.report), "historical_quality_verified": False}


def command_metrics(args):
    from execution_metrics import summarize_log
    report_path, markdown_path = paths(args.process_dir)
    report = load(report_path)
    selected = list(dict.fromkeys(str(p.resolve()) for p in args.log))
    end = report.get("finished_at") or iso()
    report["execution_metrics"] = {
        "started_at": report["started_at"], "finished_at": end,
        "logs": [summarize_log(p, report["started_at"], end) for p in selected],
        "rework_segments": sum(s.get("mode") == "rework" for s in report.get("stages", [])),
    }
    ids = [x["session_id"] for x in report["execution_metrics"]["logs"] if x["session_id"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Multiple logs for one session may overlap; select one complete log per session")
    save(report_path, markdown_path, report)
    return {"ok": True, **report["execution_metrics"]}


def command_find_log(args):
    from execution_metrics import find_logs
    return {"ok": True, "logs": find_logs(args.sessions_root, args.agent_id, args.parent_id)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    metrics = subparsers.add_parser("metrics-import", help="Import scoped log metrics without estimating missing telemetry")
    metrics.add_argument("--process-dir", required=True)
    metrics.add_argument("--log", type=Path, action="append", required=True)
    metrics.set_defaults(func=command_metrics)
    finder = subparsers.add_parser("find-log", help="Find exact agent log and verify its metadata")
    finder.add_argument("--agent-id", required=True)
    finder.add_argument("--parent-id")
    finder.add_argument("--sessions-root", type=Path, required=True)
    finder.set_defaults(func=command_find_log)
    check = subparsers.add_parser("check", help="Check finished registration without writing files")
    check.add_argument("--report", required=True, type=Path)
    check.set_defaults(func=command_check)

    preparation = subparsers.add_parser("website-prepare")
    preparation.add_argument("--process-dir", required=True)
    preparation.add_argument("--database", required=True)
    preparation.add_argument("--topic-id", required=True)
    preparation.add_argument("--topic-name", required=True)
    preparation.set_defaults(func=command_website_prepare)

    website_finish = subparsers.add_parser("website-finish")
    website_finish.add_argument("--process-dir", required=True)
    website_result = website_finish.add_mutually_exclusive_group(required=True)
    website_result.add_argument("--result", type=Path)
    website_result.add_argument("--result-json")
    website_finish.set_defaults(func=command_website_finish)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--process-dir", required=True)
    init_parser.add_argument("--database", required=True)
    init_parser.add_argument("--topic-id", required=True)
    init_parser.add_argument("--topic-name", required=True)
    init_parser.add_argument("--task", required=True)
    init_parser.add_argument(
        "--workflow", choices=tuple(WORKFLOWS), default="full_definition"
    )
    init_parser.set_defaults(func=command_init)

    start_amend = subparsers.add_parser("start-amend")
    start_amend.add_argument("--process-dir", required=True)
    start_amend.add_argument("--log", required=True, type=Path)
    start_amend.add_argument("--turn-id", required=True)
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
    stage_finish.add_argument("--copy", type=Path, help="Current complete 文案.md at copy handoff; --output 文案.md also captures it")
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
    review_parser.add_argument("--turn-id", action="append", help="Exact task turns when an agent served multiple tasks; repeat as needed.")
    review_parser.add_argument("--closed", action="store_true",
                               help="Use only after the agent close tool succeeded.")
    review_parser.add_argument("--close-unavailable", help="Actual host/tool limitation; requires a completed final review turn.")
    review_parser.set_defaults(func=command_review_import)
    turn_timing = subparsers.add_parser("turn-timing")
    turn_timing.add_argument("--process-dir", required=True)
    turn_timing.add_argument("--log", required=True, type=Path)
    turn_timing.add_argument("--turn-id", required=True)
    turn_timing.set_defaults(func=command_turn_timing)
    for name in ("review-start", "review-result", "review-check"):
        stage_review = subparsers.add_parser(name)
        stage_review.add_argument("--process-dir", required=True)
        stage_review.add_argument("--role", required=True)
        if name == "review-check":
            stage_review.add_argument("--input", action="append", help="Require this actual execution input to be bound to the review; repeat for each input")
            stage_review.add_argument("--read-only", action="store_true", help="Inspect current or reusable review without modifying the report")
        if name == "review-start":
            stage_review.add_argument("--input", action="append", required=True)
            stage_review.add_argument("--r-scope", choices=("full", "public"), default="full", help="Bind business code before # 输出; backend generation remains subject to output tests.")
        if name == "review-result":
            stage_review.add_argument("--findings-file", type=Path, help="Optional actual findings JSON; [] explicitly records zero findings")
            stage_review.add_argument("--evidence", required=True)
            stage_review.add_argument("--result", choices=("pass", "blocked"), required=True)
            stage_review.add_argument("--agent-id")
            stage_review.add_argument("--isolated-reason")
        stage_review.set_defaults(func=command_review_stage)

    review_template = subparsers.add_parser("review-template", help="Create the findings JSON structure without registering a conclusion")
    review_template.add_argument("--out", required=True, type=Path)
    review_template.set_defaults(func=command_review_template)
    add_commands(subparsers)
    return parser


def command_review_template(args):
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    draft = [{"category": "", "location": "", "problem": "", "evidence": "",
              "changed_artifact": False, "resolved": False}]
    with path.open("x", encoding="utf-8") as handle:
        json.dump(draft, handle, ensure_ascii=False, indent=2)
    return {"ok": True, "status": "FINDINGS_TEMPLATE_CREATED", "path": str(path),
            "instruction": "Fill actual findings; use [] only after a review found none. This template is not a review result."}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
