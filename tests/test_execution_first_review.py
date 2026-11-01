"""Execution-first flow reduces roles without treating missing reviews as passes."""
import copy
import json
import os
import subprocess
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
    # Synthetic fixture: a real response can be bound without host telemetry.
    delivered = root / "reviewer-response.md"
    delivered.write_text("Checked the supplied definition; no unresolved findings.", encoding="utf-8")
    no_log = copy.deepcopy(run)
    no_log.update(primary_agent_id="primary", reviews=[], stages=[])
    no_log["stage_reviews"][role]["review_output"] = {"path": str(delivered), "sha256": report.input_hashes([delivered])[str(delivered)]}
    report.validate_full_definition_completion(no_log, end)
    assert no_log["stage_recording"]["status"] == "incomplete"
    self_review = copy.deepcopy(no_log)
    self_review["stage_reviews"][role]["agent_id"] = "primary"
    rejects(lambda: report.validate_full_definition_completion(self_review, end), "独立于主线程")
    unresolved = copy.deepcopy(no_log)
    unresolved["stage_reviews"][role]["findings"] = [{"resolved": False}]
    rejects(lambda: report.validate_full_definition_completion(unresolved, end), "Unresolved")
    delivered.write_text("changed response", encoding="utf-8")
    rejects(lambda: report.validate_full_definition_completion(no_log, end), "结论缺失或已变化")
    reused_agent = copy.deepcopy(run)
    reused_agent["reviews"][0]["closed"] = False
    reused_agent["reviews"][0]["rounds"][0].update(started_at="2026-09-22T09:00:00+08:00", finished_at="2026-09-22T10:04:00+08:00")
    report.validate_full_definition_completion(reused_agent, end)
    reused_agent["reviews"][0]["rounds"][0]["finished_at"] = "2026-09-22T09:30:00+08:00"
    rejects(lambda: report.validate_full_definition_completion(reused_agent, end), "实际完成")
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

# Actual CLI wiring with synthetic reviewer output; no real review is claimed.
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / 'definition.R'
    source.write_text('confirmed calculation', encoding='utf-8')
    output = root / 'review.md'
    output.write_text('Reviewed the supplied calculation. No unresolved findings.', encoding='utf-8')
    def cli(*args, ok=True):
        result = subprocess.run([sys.executable, str(Path(report.__file__)), *map(str, args)],
                                capture_output=True, encoding='utf-8',
                                env={**os.environ, 'CODEX_THREAD_ID': 'primary', 'PYTHONUTF8': '1'})
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return result
    cli('init', '--process-dir', root, '--database', 'fixture', '--topic-id', '001',
        '--topic-name', 'test', '--task', 'test', '--workflow', 'general')
    cli('review-start', '--process-dir', root, '--role', role, '--input', source)
    cli('review-result', '--process-dir', root, '--role', role, '--agent-id', 'reviewer',
        '--evidence', 'Synthetic original reviewer response', '--output', output, '--result', 'pass')
    cli('review-check', '--process-dir', root, '--role', role, '--input', source, '--read-only')
    saved = json.loads((root / 'execution_report.json').read_text(encoding='utf-8'))
    assert not saved.get('reviews') and saved['stage_reviews'][role]['review_output']
    assert '此交付不提供模型、轮次或耗时' in (root / '执行报告.md').read_text(encoding='utf-8')
    source.write_text('changed calculation', encoding='utf-8')
    cli('review-check', '--process-dir', root, '--role', role, '--read-only', ok=False)
    source.write_text('confirmed calculation', encoding='utf-8')
    # A truncated optional log must not override the actual bound final response.
    saved['reviews'] = [{'role': role, 'agent_id': 'reviewer', 'nickname': 'fixture',
                         'closed': False, 'unfinished_turns': 1, 'rounds': [],
                         'created_during_run': False, 'turn_count': 1,
                         'running_seconds': None, 'between_rounds_seconds': None}]
    (root / 'execution_report.json').write_text(json.dumps(saved), encoding='utf-8')
    cli('finish', '--process-dir', root, '--status', 'completed')
print('REVIEW_OUTPUT_CLI_PASS: original response binding without telemetry; changed inputs rejected')
