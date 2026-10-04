"""Bind two independent exploration results and the primary agent's decision.

These checks establish traceable completion, not research correctness or semantic
independence. The primary agent must compare the actual evidence and conclusions.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

POLICY = "dual_exploration_v1"
ROLES = {"a": "独立探索 A", "b": "独立探索 B"}


def plan_hash(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    # Execution observations and copy locations are added after the source plan.
    for key in ("status", "logic_review", "exploration_log", "searched_at", "questionnaire_display_policy"):
        data.pop(key, None)
    for item in data.get("questionnaire_evidence", []):
        for key in ("rendered_in_copy", "copy_locator", "display"):
            item.pop(key, None)
    for item in data.get("questionnaire_path_closure", []):
        for key in ("observed_count", "unexplained_count", "closed", "all_observed_paths_mapped", "structural_missing_explained"):
            item.pop(key, None)
        for branch in item.get("branches", []):
            for key in ("observed_count", "unexplained_count"):
                branch.pop(key, None)
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_branches(report):
    from execution_report import input_hashes, validate_stage_review, review_lifecycle_complete
    exploration = report.get("exploration", {})
    if not exploration:
        raise ValueError("双路探索尚未登记")
    if input_hashes(exploration["inputs"]) != exploration["inputs"]:
        raise ValueError("探索共同输入已变化")
    ids = []
    outputs = set()
    for branch, role in ROLES.items():
        item = exploration.get("branches", {}).get(branch)
        if not item:
            raise ValueError("缺少独立探索结果：" + branch)
        review = validate_stage_review(report, role)
        if item.get("agent_id") != review.get("agent_id") or item.get("review_started_at") != review.get("started_at") or item.get("review_finished_at") != review.get("finished_at"):
            raise ValueError("探索产出与本轮代理记录不匹配")
        if review.get("mode") != "independent" or review["inputs"] != exploration["inputs"]:
            raise ValueError("探索必须独立完成并使用相同输入")
        if not review.get("agent_id") or review.get("agent_id") == report.get("primary_agent_id"):
            raise ValueError("探索代理身份必须独立于主线程")
        agent = next((a for a in report.get("reviews", []) if a.get("agent_id") == review["agent_id"]), {})
        if not review_lifecycle_complete(agent):
            raise ValueError("探索代理尚未完成或未登记关闭限制")
        if input_hashes(item["outputs"]) != item["outputs"]:
            raise ValueError("独立探索产出已变化")
        if outputs.intersection(item["outputs"]) or set(item["outputs"]).intersection(exploration["inputs"]):
            raise ValueError("两路产出必须分开，不能覆盖共同输入")
        outputs.update(item["outputs"])
        ids.append(review["agent_id"])
    if len(set(ids)) != 2:
        raise ValueError("必须是两个不同的探索代理")
    return exploration


def validate_exploration(report, record=None):
    from execution_report import input_hashes
    if report.get("exploration_policy") != POLICY:
        return None  # Historical and execution-only reports keep their contract.
    exploration = validate_branches(report)
    merge = exploration.get("merge", {})
    if merge.get("status") != "ready" or merge.get("unresolved"):
        raise ValueError("探索尚未合并或仍有未解决问题")
    if input_hashes(merge["decision"]) != merge["decision"]:
        raise ValueError("主线程合并依据已变化")
    if record and str(Path(record).resolve()) != merge["record"]:
        raise ValueError("合并方案与当前来源记录不是同一文件")
    if plan_hash(merge["record"]) != merge["plan_hash"]:
        raise ValueError("来源方案已变化，须更新受影响探索与合并结论")
    return merge


def command_exploration(args):
    import os
    from execution_report import paths, load, save, input_hashes, iso, validate_stage_review
    report_path, markdown = paths(args.process_dir)
    report = load(report_path)
    if args.command == "exploration-check":
        result = validate_exploration(report, args.record)
        return {"ok": True, "applicable": result is not None}
    if report["status"] != "running":
        raise ValueError("探索交接须在执行中的报告登记")
    if args.command == "exploration-start":
        inputs = input_hashes(args.input)
        if report.get("exploration"):
            report.setdefault("exploration_history", []).append(deepcopy(report["exploration"]))
        report["exploration_policy"] = POLICY
        report["primary_agent_id"] = os.environ.get("CODEX_THREAD_ID", "")
        report["exploration"] = {"started_at": iso(), "inputs": inputs, "branches": {}}
        for role in ROLES.values():
            reviews = report.setdefault("stage_reviews", {})
            if role in reviews:
                report.setdefault("stage_review_history", {}).setdefault(role, []).append(deepcopy(reviews[role]))
            reviews[role] = {"status": "pending", "started_at": iso(), "inputs": inputs, "r_scope": "full"}
    elif args.command == "exploration-result":
        exploration = report.get("exploration")
        if not exploration or input_hashes(exploration["inputs"]) != exploration["inputs"]:
            raise ValueError("先登记稳定的探索共同输入")
        output = Path(args.output).resolve(strict=True)
        if not output.read_text(encoding="utf-8-sig").strip() or not args.evidence.strip():
            raise ValueError("探索产出和交付说明不能为空")
        if str(output) in exploration["inputs"] or any(str(output) in b["outputs"] for k, b in exploration["branches"].items() if k != args.branch):
            raise ValueError("探索产出不能覆盖共同输入或另一分支")
        role = ROLES[args.branch]
        prior = report["stage_reviews"][role]
        updated = {**prior, "status": "pass", "mode": "independent", "agent_id": args.agent_id,
                   "evidence": args.evidence, "finished_at": iso()}
        report["stage_reviews"][role] = updated
        validate_stage_review(report, role)
        if args.branch in exploration["branches"]:
            exploration.setdefault("result_history", []).append(deepcopy(exploration["branches"][args.branch]))
        exploration["branches"][args.branch] = {"outputs": input_hashes([output]), "agent_id": args.agent_id, "review_started_at": updated["started_at"], "review_finished_at": updated["finished_at"]}
        if exploration.get("merge"):
            exploration.setdefault("merge_history", []).append(exploration.pop("merge"))
    else:
        exploration = validate_branches(report)
        decision = Path(args.decision).resolve(strict=True)
        if not decision.read_text(encoding="utf-8-sig").strip():
            raise ValueError("须保存主线程实际比较和判断依据")
        if args.result == "ready" and args.unresolved:
            raise ValueError("未解决问题不能标记ready")
        record = Path(args.record).resolve(strict=True)
        if exploration.get("merge"):
            exploration.setdefault("merge_history", []).append(deepcopy(exploration["merge"]))
        exploration["merge"] = {"status": args.result, "unresolved": args.unresolved or [],
            "decision": input_hashes([decision]), "record": str(record), "plan_hash": plan_hash(record), "merged_at": iso()}
        if args.result == "ready":
            validate_exploration(report, record)
    save(report_path, markdown, report)
    return {"ok": True, "command": args.command}


def add_commands(subparsers):
    for command in ("exploration-start", "exploration-result", "exploration-merge", "exploration-check"):
        parser = subparsers.add_parser(command)
        parser.add_argument("--process-dir", required=True)
        if command == "exploration-start":
            parser.add_argument("--input", action="append", required=True)
        elif command == "exploration-result":
            parser.add_argument("--branch", choices=tuple(ROLES), required=True)
            parser.add_argument("--agent-id", required=True)
            parser.add_argument("--output", required=True)
            parser.add_argument("--evidence", required=True)
        elif command == "exploration-merge":
            parser.add_argument("--record", required=True)
            parser.add_argument("--decision", required=True)
            parser.add_argument("--result", choices=("ready", "blocked"), required=True)
            parser.add_argument("--unresolved", action="append")
        else:
            parser.add_argument("--record")
        parser.set_defaults(func=command_exploration)
