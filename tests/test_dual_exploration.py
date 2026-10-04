"""Synthetic role records test gating; they are not evidence of real agents."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from execution_report import input_hashes
from exploration_handoff import POLICY, ROLES, plan_hash, validate_exploration


def rejects(action, phrase):
    try:
        action()
    except ValueError as error:
        assert phrase in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + phrase)


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    request = root / "request.md"
    request.write_text("Explore the provided data and possible definitions.", encoding="utf-8")
    plan = root / "definition_search_record.json"
    payload = {"database": "test", "definition_plan": [{"meaning": "confirmed meaning"}],
               "questionnaire_evidence": [{"question_text": "Original?", "rendered_in_copy": False}],
               "questionnaire_path_closure": [{"all_observed_paths_mapped": None,
                   "structural_missing_explained": None, "branches": [{"route": ["Q1"],
                       "observed_count": None, "unexplained_count": None}]}]}
    plan.write_text(json.dumps(payload), encoding="utf-8")
    decision = root / "decision.md"
    decision.write_text("The proposals differ; official evidence supports the selected definition.", encoding="utf-8")
    report = {"exploration_policy": POLICY, "primary_agent_id": "primary",
              "exploration": {"inputs": input_hashes([request]), "branches": {}},
              "stage_reviews": {}, "reviews": []}
    for branch, role in ROLES.items():
        output = root / (branch + ".md")
        output.write_text("Distinct proposal " + branch, encoding="utf-8")
        report["stage_reviews"][role] = {"status": "pass", "mode": "independent", "agent_id": branch,
            "started_at": "2026-10-01T00:00:00+00:00", "finished_at": "2026-10-01T00:10:00+00:00",
            "inputs": input_hashes([request]), "evidence": "Completed independent investigation"}
        report["reviews"].append({"agent_id": branch, "role": role, "unfinished_turns": 0,
            "closed": True, "rounds": [{"outcome": "completed", "started_at": "2026-10-01T00:01:00+00:00"}]})
        report["exploration"]["branches"][branch] = {"agent_id": branch, "outputs": input_hashes([output]),
            "review_started_at": "2026-10-01T00:00:00+00:00", "review_finished_at": "2026-10-01T00:10:00+00:00"}
    report["exploration"]["merge"] = {"status": "ready", "unresolved": [], "record": str(plan.resolve()),
        "plan_hash": plan_hash(plan), "decision": input_hashes([decision])}
    assert validate_exploration(report, plan)
    assert validate_exploration({"review_policy": "execution_first_v1"}) is None
    assert validate_exploration({}) is None
    bad = copy.deepcopy(report); del bad["exploration"]["branches"]["b"]
    rejects(lambda: validate_exploration(bad), "缺少独立探索")
    bad = copy.deepcopy(report); bad["exploration"]["merge"]["unresolved"] = ["Unresolved classification"]
    rejects(lambda: validate_exploration(bad), "未解决")
    bad = copy.deepcopy(report); bad["stage_reviews"][ROLES["a"]]["mode"] = "isolated"
    bad["stage_reviews"][ROLES["a"]]["limitation"] = "fixture"
    rejects(lambda: validate_exploration(bad), "独立完成")
    bad = copy.deepcopy(report); bad["reviews"][0]["rounds"][0]["outcome"] = "aborted"
    rejects(lambda: validate_exploration(bad), "实际完成")
    bad = copy.deepcopy(report); bad["stage_reviews"][ROLES["a"]]["finished_at"] = "2026-10-01T00:11:00+00:00"
    rejects(lambda: validate_exploration(bad), "本轮代理记录不匹配")
    bad = copy.deepcopy(report); bad["primary_agent_id"] = "a"
    rejects(lambda: validate_exploration(bad), "独立于主线程")
    rejects(lambda: validate_exploration(report, request), "不是同一文件")
    request.write_text("Changed research scope", encoding="utf-8")
    rejects(lambda: validate_exploration(report), "共同输入已变化")
    request.write_text("Explore the provided data and possible definitions.", encoding="utf-8")
    (root / "a.md").write_text("Changed first output", encoding="utf-8")
    rejects(lambda: validate_exploration(report), "产出已变化")
    (root / "a.md").write_text("Distinct proposal a", encoding="utf-8")
    payload["questionnaire_evidence"][0].update(rendered_in_copy=True, copy_locator="copy/period")
    payload["questionnaire_display_policy"] = "chinese_v1"
    payload["questionnaire_evidence"][0]["display"] = {"question_text": "中文题文", "instructions": []}
    path = payload["questionnaire_path_closure"][0]
    path.update(all_observed_paths_mapped=True, structural_missing_explained=True)
    path["branches"][0].update(observed_count=10, unexplained_count=0)
    plan.write_text(json.dumps(payload), encoding="utf-8")
    assert validate_exploration(report, plan)
    payload["definition_plan"][0]["meaning"] = "different definition"
    plan.write_text(json.dumps(payload), encoding="utf-8")
    rejects(lambda: validate_exploration(report), "来源方案已变化")

    # CLI init requires exploration for new full runs; failures cannot mutate reports.
    script = ROOT / "scripts/execution_report.py"
    process = root / "process"
    def cli(*args, ok=True):
        result = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return result
    cli("init", "--process-dir", process, "--database", "test", "--topic-id", "001", "--topic-name", "fixture", "--task", "test")
    saved = process / "execution_report.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["exploration_policy"] == POLICY
    initial = saved.read_bytes()
    cli("exploration-check", "--process-dir", process, ok=False)
    assert saved.read_bytes() == initial
    cli("exploration-start", "--process-dir", process, "--input", request)
    initial = saved.read_bytes()
    cli("exploration-result", "--process-dir", process, "--branch", "a", "--agent-id", "no-log",
        "--output", root / "a.md", "--evidence", "test", ok=False)
    assert saved.read_bytes() == initial
    cli("exploration-start", "--process-dir", process, "--input", request)
    assert len(json.loads(saved.read_text(encoding="utf-8"))["exploration_history"]) == 1
    # Synthetic completed sessions stand in for the independently tested log importer.
    current = json.loads(saved.read_text(encoding="utf-8"))
    current["reviews"] = copy.deepcopy(report["reviews"])
    for agent in current["reviews"]:
        agent.update(created_during_run=True, turn_count=1, nickname="synthetic fixture",
                     running_seconds=1, between_rounds_seconds=0)
        agent["rounds"][0]["started_at"] = "2099-01-01T00:00:00+00:00"
    saved.write_text(json.dumps(current), encoding="utf-8")
    for branch in ROLES:
        cli("exploration-result", "--process-dir", process, "--branch", branch, "--agent-id", branch,
            "--output", root / (branch + ".md"), "--evidence", "Synthetic independent fixture completed")
    cli("exploration-merge", "--process-dir", process, "--record", plan,
        "--decision", decision, "--result", "blocked", "--unresolved", "Method choice pending")
    cli("exploration-check", "--process-dir", process, ok=False)
    initial = saved.read_bytes()
    cli("exploration-merge", "--process-dir", process, "--record", plan,
        "--decision", decision, "--result", "ready", "--unresolved", "Still pending", ok=False)
    assert saved.read_bytes() == initial
    cli("exploration-merge", "--process-dir", process, "--record", plan,
        "--decision", decision, "--result", "ready")
    cli("exploration-check", "--process-dir", process, "--record", plan)
    assert json.loads(saved.read_text(encoding="utf-8"))["exploration"]["merge_history"][0]["status"] == "blocked"
    # Updating a branch clears the ready verdict, preserving the earlier decision.
    cli("exploration-result", "--process-dir", process, "--branch", "a", "--agent-id", "a",
        "--output", root / "a.md", "--evidence", "Updated fixture result")
    cli("exploration-check", "--process-dir", process, ok=False)

print("DUAL_EXPLORATION_TESTS_PASS: independent completion, stale inputs/results/plan, dynamic observations, legacy, truthful CLI")
