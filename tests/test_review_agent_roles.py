"""A reused agent keeps separately timed role records and their input guards."""
import copy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_report as er

report = {"status": "running", "started_at": "2000-01-01T00:00:00+00:00", "reviews": []}
def fake_log(path, role):
    turn = "exploration-turn" if role == "独立探索 A" else "implementation-turn"
    return {"agent_id": "reused-agent", "role": role, "created_at": "2020-01-01T00:00:00+00:00",
            "rounds": [{"turn_id": turn, "started_at": "2021-01-01T00:01:00+00:00",
                        "finished_at": "2021-01-01T00:02:00+00:00", "elapsed_seconds": 60,
                        "outcome": "completed"}]}
def args(role):
    return SimpleNamespace(process_dir=Path("unused"), log=Path("unused.jsonl"), role=role,
                           turn_id=None, inherit_completed=False, inherit_reason=None,
                           closed=False, close_unavailable="fixture host has no close tool")

with patch.object(er, "paths", return_value=(Path("unused.json"), Path("unused.md"))), \
     patch.object(er, "load", side_effect=lambda _: report), \
     patch.object(er, "save"), patch.object(er, "read_review_log", side_effect=fake_log):
    er.command_review_import(args("独立探索 A"))
    first = copy.deepcopy(report["reviews"][0])
    er.command_review_import(args("公开 R 复核"))
    assert len(report["reviews"]) == 2
    assert report["reviews"][0] == first
    assert {r["role"] for r in report["reviews"]} == {"独立探索 A", "公开 R 复核"}
    er.command_review_import(args("公开 R 复核"))
    assert len(report["reviews"]) == 2
    assert [r["rounds"][0]["turn_id"] for r in report["reviews"]] == ["exploration-turn", "implementation-turn"]

with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / "stable.txt"
    source.write_text("reviewed inputs", encoding="utf8")
    report["stage_reviews"] = {
        role: {"status": "pass", "mode": "independent", "agent_id": "reused-agent",
               "started_at": "2021-01-01T00:00:00+00:00", "inputs": er.input_hashes([source]),
               "evidence": "Actual completed role-specific fixture."}
        for role in ["独立探索 A", "公开 R 复核"]}
    for role in report["stage_reviews"]:
        assert er.validate_stage_review(report, role)["status"] == "pass"
    missing = copy.deepcopy(report)
    missing["reviews"] = [r for r in missing["reviews"] if r["role"] != "独立探索 A"]
    try: er.validate_stage_review(missing, "独立探索 A")
    except ValueError as error: assert "缺少本轮实际完成" in str(error)
    else: raise AssertionError("A different role must not satisfy exploration completion")
    source.write_text("changed unreviewed inputs", encoding="utf8")
    for role in report["stage_reviews"]:
        try: er.validate_stage_review(report, role)
        except ValueError as error: assert "输入已变化" in str(error)
        else: raise AssertionError("Role preservation must not bypass changed input guards")
print("REUSED_AGENT_ROLE_RECORDS_PASS")
