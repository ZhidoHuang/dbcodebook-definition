"""First copies and judgments survive later edits without manufacturing passes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from writing_evidence import digest, skill_version, copy_execution_conclusions, scope_bindings, carry_copy_scopes
import writing_evidence


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    process = root / "process"
    formal = root / "formal"
    formal.mkdir()
    document = formal / "文案.md"
    original = (ROOT / "tests/fixtures/writing-inputs/reader-copy.md").read_bytes()
    document.write_bytes(original)
    script = ROOT / "scripts/execution_report.py"

    def cli(*args, ok=True):
        result = subprocess.run([sys.executable, "-X", "utf8", str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
        assert (result.returncode == 0) == ok, result.stdout + result.stderr
        return result

    def report():
        return json.loads((process / "execution_report.json").read_text(encoding="utf-8"))

    def handoff():
        cli("stage-start", "--process-dir", process, "--stage-id", "copy", "--name", "文案", "--role", "test")
        cli("stage-finish", "--process-dir", process, "--stage-id", "copy", "--status", "completed", "--copy", document,
            "--summary", "已核对两个结果的含义与关系；这份测试不提供真实语义验收。")

    cli("init", "--process-dir", process, "--database", "test", "--topic-id", "fixture", "--topic-name", "fixture", "--task", "evidence test", "--workflow", "general")
    handoff()
    first = report()["current_copy"]
    assert not (process / "copy_versions").exists()
    assert first["sha256"] == digest(original)
    assert copy_execution_conclusions(process, document)["semantic_pass_inferred"] is False
    document.write_bytes(original + b"\n")
    assert copy_execution_conclusions(process, document)["status"] == "stale"
    handoff()
    assert report()["current_copy"]["sha256"] != first["sha256"]
    assert "copy_history" not in report() and "first_copy" not in report()
    assert not (process / "copy_versions").exists()
    assert copy_execution_conclusions(process, document)["status"] == "available"

    source = root / "input.txt"
    source.write_text("stable", encoding="utf-8")
    findings = root / "findings.json"
    finding = dict(category="meaning", location="opening", problem="missing relationship", evidence="fixture evidence",
                   changed_artifact=True, resolved=False)
    findings.write_text(json.dumps([finding]), encoding="utf-8")
    cli("review-start", "--process-dir", process, "--role", "fixture", "--input", source)
    cli("review-result", "--process-dir", process, "--role", "fixture", "--result", "blocked", "--evidence", "A relationship is missing",
        "--findings-file", findings, "--isolated-reason", "Local interface test")
    cli("review-result", "--process-dir", process, "--role", "fixture", "--result", "pass", "--evidence", "Unresolved findings must survive",
        "--isolated-reason", "Local interface test", ok=False)
    source.write_text("corrected", encoding="utf-8")
    cli("review-start", "--process-dir", process, "--role", "fixture", "--input", source)
    cli("review-result", "--process-dir", process, "--role", "fixture", "--result", "pass", "--evidence", "Restart alone does not resolve findings",
        "--isolated-reason", "Local interface test", ok=False)
    findings.write_text("[]", encoding="utf-8")
    cli("review-result", "--process-dir", process, "--role", "fixture", "--result", "pass", "--evidence", "No remaining fixture issues",
        "--findings-file", findings, "--isolated-reason", "Local interface test")
    saved = report()
    assert saved["stage_review_history"]["fixture"][0]["findings"][0] == finding
    assert saved["stage_reviews"]["fixture"]["findings"] == []
    rendered = (process / "执行报告.md").read_text(encoding="utf-8")
    assert "累计结构化发现 1 条次" in rendered and "当前未解决 0 条" in rendered

    (process / "definition_search_record.json").write_text("{}", encoding="utf-8")
    artifacts = {name: {"sha256": name} for name in ("public_r", "analysis_db", "analysis_codebook", "note")}
    bindings = scope_bindings(formal, process, artifacts)
    names = list(bindings)
    prior = {"status": "FULL_TEXT_READABILITY_PASS", "copy_scope_bindings": bindings, "scopes": [
        {"name": n, "result": "pass", "evidence": "An actual prior judgment for " + n, "findings": []} for n in names]}
    def payload():
        return {"copy_scope_bindings": scope_bindings(formal, process, artifacts), "scopes": [
            {"name": n, "result": "pending", "evidence": ""} for n in [*names, "full_note_flow"]]}
    current = payload()
    assert set(carry_copy_scopes(prior, current)) == set(names)
    assert current["scopes"][-1]["result"] == "pending"
    (formal / "note.md").write_text("# Original title\n", encoding="utf-8")
    artifacts["note"]["path"] = "note.md"
    title_prior = copy.deepcopy(prior)
    title_prior["copy_scope_bindings"] = scope_bindings(formal, process, artifacts)
    (formal / "note.md").write_text("# Different title\n", encoding="utf-8")
    title_carried = carry_copy_scopes(title_prior, payload())
    assert "title_summary" not in title_carried and "criteria" in title_carried
    artifacts["note"].pop("path")
    document.write_bytes(original.replace("两个变量".encode(), "两项结果".encode()))
    current = payload()
    carried = carry_copy_scopes(prior, current)
    assert "title_summary" not in carried and "insight_card" not in carried and "criteria" in carried
    (process / "definition_search_record.json").write_text('{"changed":true}', encoding="utf-8")
    assert carry_copy_scopes(prior, payload()) == []
    old = copy.deepcopy(prior)
    old.pop("copy_scope_bindings")
    assert carry_copy_scopes(old, payload()) == []

    # Only the current handoff is recorded; no first-draft claim is made.
    cli("finish", "--process-dir", process, "--status", "completed")
    cli("init", "--process-dir", process, "--database", "test", "--topic-id", "fixture", "--topic-name", "fixture", "--task", "missing first", "--workflow", "general")
    cli("stage-start", "--process-dir", process, "--stage-id", "copy", "--name", "文案", "--role", "test")
    cli("stage-finish", "--process-dir", process, "--stage-id", "copy", "--status", "completed")
    handoff()
    assert report()["current_copy"]["status"] == "captured"
    assert "first_copy" not in report()

    fake_skill = root / "skill"
    fake_skill.mkdir()
    (fake_skill / "SKILL.md").write_text("v1", encoding="utf-8")
    v1 = skill_version(fake_skill)
    (fake_skill / "SKILL.md").write_text("v2", encoding="utf-8")
    assert v1["id"] != skill_version(fake_skill)["id"]

    # Moving rules must not allow an old judgment to survive changed guidance.
    # Mutate only temporary rule copies; production guidance stays untouched.
    rule_paths = (
        "references/rules/stages/03-copy.md", "templates/reader-copy.md",
        "references/rules/copy/core.md", "references/rules/copy/questionnaire.md",
        "references/rules/copy/tree.md", "references/rules/copy/basis.md",
    )
    for name in rule_paths:
        target = fake_skill / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    original_root = writing_evidence.ROOT
    try:
        writing_evidence.ROOT = fake_skill
        baseline = copy.deepcopy(prior)
        baseline["copy_scope_bindings"] = scope_bindings(formal, process, artifacts)
        assert set(carry_copy_scopes(baseline, payload())) == set(names)
        for name in rule_paths:
            target = fake_skill / name
            before = target.read_bytes()
            target.write_bytes(before + b"\nChanged guidance for the isolated regression.\n")
            assert carry_copy_scopes(baseline, payload()) == [], name
            target.write_bytes(before)
            assert set(carry_copy_scopes(baseline, payload())) == set(names), name
    finally:
        writing_evidence.ROOT = original_root
print("WRITING_EVIDENCE_PASS: current file binding, no version copies, round history, scoped reuse, content versions")
