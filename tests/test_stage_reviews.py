import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from execution_report import input_hashes, validate_stage_review


def rejects(action, phrase):
    try:
        action()
    except ValueError as error:
        assert phrase in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + phrase)


with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / "definition_search_record.json"
    plan = {"approved_analysis_vars": ["result"], "logic_review": {"result": "pending"}}
    path.write_text(json.dumps(plan), encoding="utf-8")
    review = {"status": "pass", "mode": "independent", "agent_id": "agent-1",
              "started_at": "2026-09-09T01:00:00+00:00", "inputs": input_hashes([path]),
              "evidence": "The source plan and the result scope agree; no open findings."}
    report = {"stage_reviews": {"logic": review}, "reviews": [{
        "agent_id": "agent-1", "role": "logic", "unfinished_turns": 0,
        "rounds": [{"outcome": "completed", "started_at": "2026-09-09T01:01:00+00:00"}]}]}
    assert validate_stage_review(report, "logic")["mode"] == "independent"
    missing = copy.deepcopy(report)
    missing["reviews"] = []
    rejects(lambda: validate_stage_review(missing, "logic"), "缺少本轮实际完成")
    stale = copy.deepcopy(report)
    stale["reviews"][0]["rounds"][0]["started_at"] = "2026-09-08T01:01:00+00:00"
    rejects(lambda: validate_stage_review(stale, "logic"), "缺少本轮实际完成")
    aborted = copy.deepcopy(report)
    aborted["reviews"][0]["rounds"][0]["outcome"] = "aborted"
    rejects(lambda: validate_stage_review(aborted, "logic"), "缺少本轮实际完成")
    later_aborted = copy.deepcopy(report)
    later_aborted["reviews"][0]["rounds"].append({"outcome": "aborted", "started_at": "2026-09-09T02:01:00+00:00"})
    rejects(lambda: validate_stage_review(later_aborted, "logic"), "缺少本轮实际完成")
    isolated = copy.deepcopy(missing)
    isolated["stage_reviews"]["logic"].update(mode="isolated", limitation="No independent agent is available in this test.")
    assert validate_stage_review(isolated, "logic")["mode"] == "isolated"
    plan["logic_review"]["result"] = "clear"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_stage_review(report, "logic")["status"] == "pass"
    plan["approved_analysis_vars"].append("unreviewed")
    path.write_text(json.dumps(plan), encoding="utf-8")
    rejects(lambda: validate_stage_review(report, "logic"), "输入已变化")

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "input.txt"
    source.write_text("stable plan", encoding="utf-8")
    process = root / "process"
    script = Path(__file__).resolve().parents[1] / "scripts/execution_report.py"

    def cli(*args, ok=True):
        result = subprocess.run([sys.executable, "-X", "utf8", str(script), *map(str, args)],
                                capture_output=True, text=True, encoding="utf-8")
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return result

    def init():
        cli("init", "--process-dir", process, "--database", "test", "--topic-id", "test",
            "--topic-name", "isolated fixture", "--task", "Review reuse test", "--workflow", "general")

    init()
    cli("review-start", "--process-dir", process, "--role", "logic", "--input", source)
    cli("review-check", "--process-dir", process, "--role", "logic", ok=False)
    cli("review-result", "--process-dir", process, "--role", "logic", "--result", "pass",
        "--evidence", "The plan was checked against this fixture.", "--agent-id", "missing", ok=False)
    cli("review-result", "--process-dir", process, "--role", "logic", "--result", "pass",
        "--evidence", "The plan was checked against this fixture.",
        "--isolated-reason", "This subprocess test has no independent agent.")
    cli("review-check", "--process-dir", process, "--role", "logic")
    other = root / "other.txt"
    other.write_bytes(source.read_bytes())
    cli("review-check", "--process-dir", process, "--role", "logic", "--input", source)
    mismatch = cli("review-check", "--process-dir", process, "--role", "logic", "--input", other, ok=False)
    assert "实际运行输入未绑定" in mismatch.stderr
    cli("finish", "--process-dir", process, "--status", "completed", "--summary", "Fixture review finished.")
    init()
    original_report = (process / "execution_report.json").read_bytes()
    cli("review-check", "--process-dir", process, "--role", "logic", "--input", other, ok=False)
    assert (process / "execution_report.json").read_bytes() == original_report
    cli("review-check", "--process-dir", process, "--role", "logic", "--read-only")
    assert (process / "execution_report.json").read_bytes() == original_report
    cli("review-check", "--process-dir", process, "--role", "logic", "--input", source, "--read-only")
    assert (process / "execution_report.json").read_bytes() == original_report
    cli("review-check", "--process-dir", process, "--role", "logic")
    saved = json.loads((process / "execution_report.json").read_text(encoding="utf-8"))
    assert Path(saved["stage_reviews"]["logic"]["reused_from"]).is_file()
    source.write_text("changed plan", encoding="utf-8")
    cli("review-check", "--process-dir", process, "--role", "logic", ok=False)
    source.write_text("stable plan", encoding="utf-8")
    cli("review-start", "--process-dir", process, "--role", "logic", "--input", source)
    cli("review-check", "--process-dir", process, "--role", "logic", ok=False)
    cli("review-result", "--process-dir", process, "--role", "logic", "--result", "blocked",
        "--evidence", "Current review found an unresolved branch.",
        "--isolated-reason", "This subprocess test has no independent agent.")
    cli("review-check", "--process-dir", process, "--role", "logic", ok=False)

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    r = root / "A.R"
    source = root / "definition_search_record.json"
    codebook = root / "raw_codebook.csv"
    r.write_text("x <- 1\n# 输出\nprint(x)\n", encoding="utf-8")
    source.write_text('{"approved_analysis_vars": ["x"]}', encoding="utf-8")
    codebook.write_text("name\nx\n", encoding="utf-8")
    inputs = [r, source, codebook]
    report = {"stage_reviews": {"fixture": {
        "status": "pass", "evidence": "Synthetic fixture only", "mode": "isolated",
        "limitation": "unit test", "r_scope": "public", "inputs": input_hashes(inputs, "public")}}}
    validate_stage_review(report, "fixture", inputs)
    for original in inputs:
        other = root / ("other_" + original.name)
        other.write_bytes(original.read_bytes())
        rejects(lambda: validate_stage_review(report, "fixture", [other]), "实际运行输入未绑定")
    r.write_text("x <- 1\n# 输出\nprint(summary(x))\n", encoding="utf-8")
    validate_stage_review(report, "fixture", inputs)
    r.write_text("x <- 2\n# 输出\nprint(x)\n", encoding="utf-8")
    rejects(lambda: validate_stage_review(report, "fixture", inputs), "输入已变化")

print("STAGE_REVIEW_TESTS_PASS: actual/latest review, execution input binding, public scope, CLI handoff, archived reuse, pending/blocked cannot reuse")
