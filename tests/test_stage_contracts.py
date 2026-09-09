"""Check stage handoffs with isolated positive and negative examples."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_definition_readability as review
from check_reader_copy import read_questionnaire_copy, questionnaire_text, compare_content


def rejects(action, message):
    try:
        action()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + message)


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        formal = root / "formal"
        process = root / "process"
        formal.mkdir()
        process.mkdir()
        (formal / "run.log").write_text("Completed", encoding="utf-8")
        command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/check_definition_output.py"),
                   "--formal-dir", str(formal)]
        partial = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        assert partial.returncode == 0, partial.stderr
        assert json.loads(partial.stdout)["status"] == "PARTIAL_CHECK_PASS"
        incomplete = subprocess.run(command + ["--complete"], capture_output=True, text=True, encoding="utf-8")
        assert incomplete.returncode != 0 and "--complete requires" in incomplete.stderr

        source = {"schema_version": 6, "questionnaire_evidence": [{
            "question_id": "Q001", "question_text": "Did you work?", "periods": ["2011"],
            "response_type": "closed_options", "options": [{"value": "1", "label": "Yes"}, {"value": "2", "label": "No"}],
            "skip_logic": [{"when": "1 Yes", "destination": "Q002"}],
            "rendered_in_copy": True, "copy_locator": "copy > 2011"}]}
        (process / review.SOURCE_RECORD_NAME).write_text(json.dumps(source), encoding="utf-8")
        template = ('<section data-raw-source-period="2011" data-label="2011">'
                    '<div data-summary-period-note="true"><div data-summary-period-note-title="true">问卷设计</div>Work survey.</div>'
                    '<span data-summary-questionnaire-line="true"><strong data-summary-question-id="true">Q001</strong>Did you work?'
                    '<span data-summary-question-detail="true"><span data-summary-question-option="true">{first}</span>'
                    '<span data-summary-question-instruction="true">Go to {target}</span></span>'
                    '<span data-summary-question-option="true">{second}</span></span></section>')
        note = formal / "note.md"
        def check(first="1 Yes", second="2 No", target="Q002"):
            note.write_text(template.format(first=first, second=second, target=target), encoding="utf-8")
            return review.validate_questionnaire_rendering(formal, process, note.name)
        assert check()["status"] == "QUESTIONNAIRE_RENDERING_PASS"
        rejects(lambda: check(first="1 No", second="2 Yes"), "option values/labels/order")
        rejects(lambda: check(target="Q999"), "route differs")
        rejects(lambda: check(target="Q0029"), "route differs")

        artifacts = {"note": {"path": note.name, "sha256": review.sha256_file(note)}}
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "完整结果检查缺失")
        result = {"ok": True, "scope": "partial", "status": "PARTIAL_CHECK_PASS", "checks": [{"ok": True}],
                  "artifacts": {note.name: artifacts["note"]["sha256"]},
                  "source_sha256": review.sha256_file(process / review.SOURCE_RECORD_NAME),
                  "checker_sha256": review.sha256_file(ROOT / "scripts/check_definition_output.py")}
        path = process / review.RESULT_CHECK_NAME
        path.write_text(json.dumps(result), encoding="utf-8")
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "不是完整")
        # This is a handoff fixture, not a claim that these files were generated.
        result.update(scope="complete", status="MACHINE_CHECK_PASS")
        path.write_text(json.dumps(result), encoding="utf-8")
        assert review.validate_result_check(formal, process, artifacts)["scope"] == "complete"
        note.write_text("Changed", encoding="utf-8")
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "已变化")

        questionnaire = read_questionnaire_copy((ROOT / "templates/questionnaire-copy.md").read_text(encoding="utf-8").split("## 原始问卷", 1)[1])
        content = {"summary": "summary", "criteria": {}, "insight": "", "references": "ref", "questionnaire": questionnaire}
        assert compare_content(content, copy.deepcopy(content))["ok"]
        changed = copy.deepcopy(content)
        changed["questionnaire"]["2011"]["questions"][0]["options"][0]["jump"] = "→ 跳至 Q999"
        rejects(lambda: compare_content(content, changed), "原始问卷/2011")
        assert "适用对象：" not in questionnaire_text(questionnaire["2011"])
    print("STAGE_CONTRACT_TESTS_PASS: partial scope, missing prerequisites, options, routes, current result evidence, questionnaire copy")


if __name__ == "__main__":
    main()
