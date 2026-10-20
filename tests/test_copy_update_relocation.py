"""Relocation must not bypass the newest review or the pre-edit baseline.

Synthetic lifecycle fixtures only; these are not topic acceptance records.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execution_report as er
import update_reader_copy as update
from exploration_handoff import POLICY

assert update.same_topic({"database": "KLoSA", "topic_id": "001"},
                         {"database": "klosa", "topic_id": "001"})
assert not update.same_topic({"database": "HRS", "topic_id": "001"},
                             {"database": "klosa", "topic_id": "001"})


def reject(function, text):
    try:
        function()
    except (ValueError, SystemExit) as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + text)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    formal, process = root / "formal", root / "process"
    formal.mkdir()
    process.mkdir()
    source = process / "definition_search_record.json"
    update.write(source, {"definition_plan": {"formula": "x"}})
    (formal / "define.R").write_text("x <- 1\n", encoding="utf-8")
    (formal / "raw_codebook.csv").write_text("name\nx\n", encoding="utf-8")
    (formal / "文案.md").write_text("baseline", encoding="utf-8")
    mapping = root / "mapping.json"
    update.write(mapping, {"schema_version": 1, "roots": [
        {"old": str(root / "old-formal"), "new": str(formal)},
        {"old": str(root / "old-process"), "new": str(process)},
    ]})
    result = {"ok": True, "scope": "complete", "source_sha256": update.digest(source),
              "artifacts": {p.name: update.digest(p) for p in formal.iterdir()}}
    update.write(process / "result_check.json", result)
    current = {"database": "TEST", "topic_id": "001", "status": "completed",
               "stage_reviews": {er.COMBINED_REVIEW_ROLE: {
                   "status": "failed", "evidence": "SYNTHETIC failed review", "inputs": {
                       str(root / "old-formal/define.R"): er.input_hashes([formal / "define.R"])[str((formal / "define.R").resolve())]}}}}
    update.write(process / er.REPORT_NAME, current)
    older = process / "archived_runs/older/execution_report.json"
    older.parent.mkdir(parents=True)
    update.write(older, {"stage_reviews": {er.COMBINED_REVIEW_ROLE: {
        "status": "pass", "evidence": "SYNTHETIC older pass"}}})
    from report_relocation import ReportRelocation
    relocation = ReportRelocation(mapping, formal, process)
    reject(lambda: update.find_review(process, [formal / "define.R"], relocation),
           "本环节审核尚未通过")
    assert not (process / "copy_updates").exists()

    # A wrong-topic review must not acquire the current topic's identity.
    other = deepcopy(current)
    other["topic_id"] = "002"
    update.write(older, other)
    current.pop("stage_reviews")
    update.write(process / er.REPORT_NAME, current)
    reject(lambda: update.find_review(process, [formal / "define.R"], relocation),
           "与当前主题不同")

    # Content changed before prepare cannot be 'fixed' by supplying a path map.
    options = SimpleNamespace(formal_dir=formal, process_dir=process, path_map=mapping,
                              reason="Synthetic relocation test only; no new acceptance")
    (formal / "文案.md").write_text("edited before prepare", encoding="utf-8")
    reject(lambda: update.prepare(options), "修改前成果已变化")
    (formal / "文案.md").write_text("baseline", encoding="utf-8")

    # Select the newest registered exploration first; blocked is not a hint
    # to fall back to an older accepted report or start new research.
    request = process / "request.txt"
    request.write_text("SYNTHETIC common input", encoding="utf-8")
    current.update(exploration_policy=POLICY, exploration={
        "inputs": {str(root / "old-process/request.txt"):
                   er.input_hashes([request])[str(request.resolve())]},
        "branches": {}, "merge": {"status": "blocked", "unresolved": ["missing evidence"]}})
    update.write(process / er.REPORT_NAME, current)
    reject(lambda: update.prepare(options), "缺少独立探索结果")
    assert not (process / "copy_updates").exists()
    assert update.read(process / er.REPORT_NAME) == current

print("COPY_UPDATE_RELOCATION_PASS: latest failure retained, topic identity and baseline preserved")
