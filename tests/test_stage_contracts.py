"""Check stage handoffs with isolated positive and negative examples."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_definition_readability as review
from check_reader_copy import read_questionnaire_copy, questionnaire_text, compare_content
from result_check_binding import make_binding


def rejects(action, message):
    try:
        action()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + message)


def check_program_binding(root, formal, process, artifacts, result):
    # Mutate only temporary copies, then use the actual delivery gate.
    scripts = root / "skill" / "scripts"
    scripts.mkdir(parents=True)
    for key in result["checker_binding"]["logic"]:
        relative = Path("scripts") / key.split(":")[0] if ":" in key else Path(key)
        destination = scripts.parent / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    assert make_binding(scripts) == result["checker_binding"]
    receipt = process / review.RESULT_CHECK_NAME
    with patch.object(review, "__file__", str(scripts / "check_definition_readability.py")):
        check = lambda: review.validate_result_check(formal, process, artifacts)
        main = scripts / "check_definition_output.py"
        main.write_text(main.read_text(encoding="utf-8-sig") + "\n# comment only\n\n", encoding="utf-8")
        assert check()["scope"] == "complete"
        helper = scripts / "definition_display.py"
        original = helper.read_text(encoding="utf-8-sig")
        helper.write_text(original.replace("original_bytes = path.read_bytes()", "original_bytes = b'uncalled'"), encoding="utf-8")
        assert check()["scope"] == "complete", "Unused period-rewrite body invalidated the result"
        helper.write_text(original.replace('def resolve_display_policy(text, analysis_vars=None, record=None):',
            'def resolve_display_policy(text, analysis_vars=None, record=None):\n    raise ValueError("changed rule")'), encoding="utf-8")
        rejects(check, "definition_display.py:resolve_display_policy")
        helper.write_text(original.replace('def _variables(value):',
            'def _variables(value):\n    raise ValueError("changed nested helper")'), encoding="utf-8")
        rejects(check, "definition_display.py:_variables")
        helper.write_text(original, encoding="utf-8")
        deeper = scripts / "check_reader_copy.py"
        original_deeper = deeper.read_text(encoding="utf-8-sig")
        deeper.write_text(original_deeper.replace(
            'NO_INSIGHT = "本主题没有需要单独提示的主题级边界"', 'NO_INSIGHT = "changed constant"'), encoding="utf-8")
        rejects(check, "check_reader_copy.py:@module")
        deeper.write_text(original_deeper, encoding="utf-8")
        extra = scripts / "new_helper.py"
        extra.write_text("def check():\n    return False\n", encoding="utf-8")
        helper.write_text(original.replace('def resolve_display_policy(text, analysis_vars=None, record=None):',
            'def resolve_display_policy(text, analysis_vars=None, record=None):\n    from new_helper import check\n    check()'), encoding="utf-8")
        added = make_binding(scripts)
        assert "new_helper.py:check" in added["logic"]
        rejects(check, "结果检查逻辑已变化")
        helper.write_text(original, encoding="utf-8")
        routing = scripts.parent / "references/database-routing.json"
        routing_original = routing.read_text(encoding="utf-8-sig")
        routing.write_text(json.dumps(json.loads(routing_original), ensure_ascii=False, indent=4), encoding="utf-8")
        assert check()["scope"] == "complete"
        routing.write_text("{}", encoding="utf-8")
        rejects(check, "references/database-routing.json")
        routing.write_text(routing_original, encoding="utf-8")
        helper.unlink()
        rejects(check, "结果检查逻辑已变化")
        helper.write_text(original, encoding="utf-8")
        legacy = dict(result)
        legacy.pop("checker_binding")
        receipt.write_text(json.dumps(legacy), encoding="utf-8")
        rejects(check, "缺少程序依赖记录")
        receipt.write_text(json.dumps(result), encoding="utf-8")
        assert check()["scope"] == "complete"


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
                  "checker_sha256": review.sha256_file(ROOT / "scripts/check_definition_output.py"),
                  "checker_binding": make_binding()}
        path = process / review.RESULT_CHECK_NAME
        path.write_text(json.dumps(result), encoding="utf-8")
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "不是完整")
        # This is a handoff fixture, not a claim that these files were generated.
        result.update(scope="complete", status="MACHINE_CHECK_PASS")
        path.write_text(json.dumps(result), encoding="utf-8")
        assert review.validate_result_check(formal, process, artifacts)["scope"] == "complete"
        check_program_binding(root, formal, process, artifacts, result)
        source_path = process / review.SOURCE_RECORD_NAME
        original_source = source_path.read_bytes()
        source_path.write_bytes(original_source + b"\n")
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "来源方案已变化")
        source_path.write_bytes(original_source)
        note.write_text("Changed", encoding="utf-8")
        rejects(lambda: review.validate_result_check(formal, process, artifacts), "已变化")

        questionnaire = read_questionnaire_copy((ROOT / "tests/fixtures/writing-inputs/questionnaire-copy.md").read_text(encoding="utf-8").split("## 问卷", 1)[1])
        content = {"summary": "summary", "criteria": {}, "insight": "", "references": "ref", "questionnaire": questionnaire}
        assert compare_content(content, copy.deepcopy(content))["ok"]
        changed = copy.deepcopy(content)
        changed["questionnaire"]["2011"]["questions"][0]["options"][0]["jump"] = "→ 跳至 Q999"
        rejects(lambda: compare_content(content, changed), "问卷/2011")
        assert "适用对象：" not in questionnaire_text(questionnaire["2011"])
    print("STAGE_CONTRACT_TESTS_PASS: partial scope, missing prerequisites, options, routes, current result evidence, questionnaire copy")


if __name__ == "__main__":
    main()
