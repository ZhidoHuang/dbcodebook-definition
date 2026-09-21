"""Execution-first flow reduces roles without treating missing reviews as passes."""
import copy
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_report as report
import check_definition_readability as readability


def rejects(action, message):
    try:
        action()
    except (ValueError, SystemExit) as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(message)


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "definition.R"
    source.write_text("stable definition", encoding="utf-8")
    role = report.COMBINED_REVIEW_ROLE
    review = {"status": "pass", "mode": "independent", "agent_id": "reviewer",
              "started_at": "2026-09-22T10:00:00+08:00",
              "inputs": report.input_hashes([source]),
              "evidence": "Definition boundaries and implementation checked together."}
    run = {"workflow": "full_definition", "review_policy": report.REVIEW_POLICY,
           "started_at": "2026-09-22T10:00:00+08:00",
           "stages": [{"stage_id": stage, "status": "completed",
                       "started_at": "2026-09-22T10:00:00+08:00",
                       "finished_at": "2026-09-22T10:05:00+08:00"}
                      for stage in report.FULL_DEFINITION_STAGES],
           "stage_reviews": {role: review},
           "reviews": [{"role": role, "agent_id": "reviewer", "closed": True,
                        "unfinished_turns": 0, "rounds": [{"outcome": "completed",
                        "started_at": "2026-09-22T10:01:00+08:00"}]}]}
    end = report.parse_time("2026-09-22T10:05:00+08:00")
    report.validate_full_definition_completion(run, end)
    missing = copy.deepcopy(run)
    missing["stage_reviews"] = {}
    rejects(lambda: report.validate_full_definition_completion(missing, end), "尚未通过")
    isolated = copy.deepcopy(run)
    isolated["stage_reviews"][role].update(mode="isolated", limitation="No agent available")
    rejects(lambda: report.validate_full_definition_completion(isolated, end), "隔离自查不能替代")
    interrupted = copy.deepcopy(run)
    interrupted["reviews"][0]["rounds"][0]["outcome"] = "aborted"
    rejects(lambda: report.validate_full_definition_completion(interrupted, end), "实际完成")
    source.write_text("changed definition", encoding="utf-8")
    rejects(lambda: report.validate_full_definition_completion(run, end), "输入已变化")

    audit = {"review_policy": readability.REVIEW_POLICY}
    assert readability.publication_reader_review(audit, root, root, "001", {}, "author")["status"] == "NOT_REQUESTED"
    with patch.object(readability, "validate_reader_review", side_effect=ValueError("reader incomplete")):
        rejects(lambda: readability.publication_reader_review({}, root, root, "001", {}, "author"), "reader incomplete")
        audit["reader_review_required"] = True
        rejects(lambda: readability.publication_reader_review(audit, root, root, "001", {}, "author"), "reader incomplete")
        audit["reader_review_required"] = False
        (root / readability.READER_REVIEW_NAME).write_text("{}", encoding="utf-8")
        rejects(lambda: readability.publication_reader_review(audit, root, root, "001", {}, "author"), "reader incomplete")

print("EXECUTION_FIRST_REVIEW_PASS: one independent role, no fake self-review, optional reader remains binding once started")
