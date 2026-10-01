"""Catch source/copy mismatches together, before production or independent review."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import read_copy, questionnaire_copy_errors

record = {"schema_version": 6, "questionnaire_evidence": [
    {"question_id": "DA001", "question_text": "Question one?", "periods": ["2011"],
     "response_type": "closed_options", "options": [{"value": "1", "label": "Yes"}],
     "skip_logic": [{"when": "1 Yes", "destination": "DA002"}]},
    {"question_id": "DA002", "question_text": "Question two?", "periods": ["2011"],
     "response_type": "open_value", "options": [], "skip_logic": []}]}

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "copy.md"
    text = (ROOT / "templates/reader-copy.md").read_text(encoding="utf-8-sig")
    text += "\n## 原始问卷\n### 2011年\nPeriod design.\n#### DA001\nQuestion one?\n- 1 Yes → 跳至 DA002\n#### DA002\nQuestion two?\n"
    path.write_text(text, encoding="utf-8")
    content = read_copy(path)
    record["approved_analysis_vars"] = list(content["criteria"])
    assert questionnaire_copy_errors(content, record) == []
    broken = copy.deepcopy(content)
    questions = broken["questionnaire"]["2011"]["questions"]
    questions[0]["options"][0] = {"text": "1 Wrong label", "jump": "→ DA0020"}
    questions[1]["text"] = "Wrong question."
    errors = questionnaire_copy_errors(broken, record)
    assert len(errors) == 3, errors
    assert any("route differs" in e for e in errors)
    assert any("option values" in e for e in errors)
    assert any("question text" in e for e in errors)
    missing = copy.deepcopy(content)
    missing.pop("questionnaire")
    assert len(questionnaire_copy_errors(missing, record)) == 2
    assert questionnaire_copy_errors({}, {"schema_version": 6, "questionnaire_evidence": []}) == []
    assert questionnaire_copy_errors({}, {"schema_version": 5}) == []
    source = Path(temp) / "record.json"
    source.write_text(json.dumps(record), encoding="utf-8")
    command = [sys.executable, str(ROOT / "scripts/check_reader_copy.py"), "--copy", str(path), "--record", str(source)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["questionnaire_check"]["scope"] == "record_to_copy"
    assert receipt["questionnaire_check"]["original_material_check"] == "not_performed_by_this_command"
    # A route absent from the record cannot be verified by a record comparator.
    incomplete = copy.deepcopy(record)
    incomplete["questionnaire_evidence"][0]["skip_logic"] = []
    source.write_text(json.dumps(incomplete), encoding="utf-8")
    path.write_text(text.replace(" → 跳至 DA002", ""), encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0
    assert json.loads(result.stdout)["questionnaire_check"]["original_material_check"] == "not_performed_by_this_command"
    source.write_text(json.dumps(record), encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "route differs" in result.stdout
    path.write_text(text.replace("1 Yes → 跳至 DA002", "1 Wrong label → DA0020").replace("Question two?", "Wrong question."), encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(json.loads(result.stdout)["errors"]) == 3

print("COPY_EVIDENCE_PREFLIGHT_PASS: all differences, CLI failure, no-question and legacy paths")
