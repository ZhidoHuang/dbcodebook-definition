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
    if exploration.get("from_report"):
        source = Path(exploration["from_report"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != exploration.get("from_report_hash"):
            raise ValueError("沿用的原探索报告已变化")
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
        agent = review.get("prior_agent_record") or next((a for a in report.get("reviews", []) if a.get("agent_id") == review["agent_id"]), {})
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
    from execution_report import paths, load, save, input_hashes, iso, parse_time, validate_stage_review
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
    elif args.command == "exploration-reuse":
        source_path = Path(args.from_report).resolve(strict=True)
        if source_path == report_path.resolve():
            raise ValueError("沿用须明确指定另一份原探索报告")
        source_bytes = source_path.read_bytes()
        previous = json.loads(source_bytes.decode("utf-8-sig"))
        if previous.get("exploration_policy") != POLICY:
            raise ValueError("原报告未登记双路探索策略")
        if any(previous.get(key) != report.get(key) for key in ("database", "topic_id")):
            raise ValueError("原探索报告与当前数据库或主题不同")
        original = validate_branches(previous)
        inputs = input_hashes(args.input)
        if inputs != original["inputs"]:
            raise ValueError("声明的共同输入与原探索不一致")
        primary = os.environ.get("CODEX_THREAD_ID", "").strip()
        if not primary or primary in {item["agent_id"] for item in original["branches"].values()}:
            raise ValueError("沿用须有独立于历史分支的当前主线程身份")
        current = report.get("exploration")
        if current:
            # Only an empty failed/pending registration may be replaced. Real
            # investigation or an existing decision needs an explicit new round.
            if current.get("branches") or current.get("merge") or current.get("inputs") != inputs:
                raise ValueError("当前探索与沿用冲突，不能替换已有结果、合并或不同输入")
            for role in ROLES.values():
                pending = report.get("stage_reviews", {}).get(role, {})
                if pending.get("status") != "pending" or pending.get("inputs") != inputs:
                    raise ValueError("只能替换同输入的空pending探索登记")
                for agent in report.get("reviews", []):
                    if agent.get("role") == role and (agent.get("unfinished_turns") or any(
                            parse_time(turn["started_at"]) >= parse_time(pending["started_at"])
                            for turn in agent.get("rounds", []))):
                        raise ValueError("当前探索已有实际代理轮次，不能用历史探索替换")
            if not (args.replace_reason or "").strip():
                raise ValueError("替换失败pending登记须提供--replace-reason")
            report.setdefault("exploration_history", []).append(deepcopy(current))
        reused_at = iso()
        report["exploration_policy"] = POLICY
        report["primary_agent_id"] = primary
        report["exploration"] = {
            "started_at": original["started_at"], "inputs": deepcopy(inputs),
            "branches": deepcopy(original["branches"]), "from_report": str(source_path),
            "from_report_hash": hashlib.sha256(source_bytes).hexdigest(), "reused_at": reused_at,
        }
        if current:
            report["exploration"]["replacement_reason"] = args.replace_reason.strip()
        for role in ROLES.values():
            reviews = report.setdefault("stage_reviews", {})
            if role in reviews:
                report.setdefault("stage_review_history", {}).setdefault(role, []).append(deepcopy(reviews[role]))
            prior = previous["stage_reviews"][role]
            agent = prior.get("prior_agent_record") or next(
                item for item in previous.get("reviews", []) if item.get("agent_id") == prior["agent_id"])
            reviews[role] = {**deepcopy(prior), "reused_from": str(source_path),
                             "prior_agent_record": deepcopy(agent)}
        validate_branches(report)
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
    for command in ("exploration-start", "exploration-reuse", "exploration-result", "exploration-merge", "exploration-check"):
        parser = subparsers.add_parser(command)
        parser.add_argument("--process-dir", required=True)
        if command == "exploration-start":
            parser.add_argument("--input", action="append", required=True)
        elif command == "exploration-reuse":
            parser.add_argument("--from-report", required=True)
            parser.add_argument("--input", action="append", required=True)
            parser.add_argument("--replace-reason")
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
