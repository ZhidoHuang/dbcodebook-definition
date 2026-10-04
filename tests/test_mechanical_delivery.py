"""New delivery needs no author verdict; stale or failed evidence still blocks it."""
import json
from pathlib import Path
import tempfile
from test_definition_readability_gate import (
    load_checker, complete_impact, initialize_fixture_audit, write_codebook,
    FIXTURE_CONTENT, render_note, expect_failure,
)

c = load_checker()
with tempfile.TemporaryDirectory() as temp:
    formal = Path(temp) / "formal"
    process = Path(temp) / "process"
    formal.mkdir()
    files = dict(note="note.md", public_r="define.R", analysis_db="db.xlsx", analysis_codebook="cb.xlsx")
    for role, name in files.items():
        (formal / name).write_text(render_note(FIXTURE_CONTENT) if role == "note" else role, encoding="utf-8")
    write_codebook(formal / files["analysis_codebook"])
    complete_impact(c, formal, process)
    # Exercise the new scope contract, with actual facts and no review claims.
    path = process / c.IMPACT_NAME
    impact = json.loads(path.read_text(encoding="utf-8"))
    impact.update(schema_version=3, status=c.IMPACT_SCOPE_STATUS)
    for key in ("surfaces", "reviewer", "reviewed_at"):
        impact.pop(key)
    for group in impact["question_groups"]:
        group.pop("result")
        group["question_mode"] = "verified_translation"
    c.write_json(path, impact)
    assert c.validate_impact(formal, process, "025")["question_group_count"] == 1
    initialize_fixture_audit(c, formal, process, "025", files)
    c.initialize_audit(formal, process, "025", files, overwrite=True)
    audit_path = process / c.AUDIT_NAME
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["schema_version"] == 7
    assert not {"scopes", "reviewer", "review_scope", "copy_scope_bindings"} & audit.keys()
    assert not (process / "author_review_input.md").exists()
    ready = c.validate_audit(formal, process, "025")
    assert ready["writing_quality"] == "NOT_ASSESSED" and ready["scope_count"] == 0
    assert c.verify_existing_readiness(formal, process, "025")["ok"]
    # Changing a file invalidates both direct and saved readiness.
    r = formal / files["public_r"]
    original = r.read_bytes()
    r.write_text("changed", encoding="utf-8")
    expect_failure(lambda: c.validate_audit(formal, process, "025"), "stale")
    expect_failure(lambda: c.verify_existing_readiness(formal, process, "025"), "stale")
    r.write_bytes(original)
    result_path = process / c.RESULT_CHECK_NAME
    result = json.loads(result_path.read_text(encoding="utf-8"))
    broken = dict(result, ok=False)
    c.write_json(result_path, broken)
    expect_failure(lambda: c.validate_audit(formal, process, "025"), "结果")
    c.write_json(result_path, result)
    # Reinitializing cannot erase a known blocker.
    audit["unresolved_issues"] = ["Known source issue"]
    c.write_json(audit_path, audit)
    c.initialize_audit(formal, process, "025", files, overwrite=True)
    expect_failure(lambda: c.validate_audit(formal, process, "025"), "unresolved_issues")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["unresolved_issues"] == ["Known source issue"]
    audit["unresolved_issues"] = []
    c.write_json(audit_path, audit)
    # Optional independent review is still binding after it has been requested.
    c.initialize_reader_review(formal, process, "025", files["note"])
    expect_failure(lambda: c.validate_audit(formal, process, "025"), "reader review status")
    # New impact initialization neither generates PASS tasks nor erases issues.
    impact["unresolved_issues"] = ["Unresolved definition"]
    c.write_json(path, impact)
    c.initialize_impact(process, "025", overwrite=True)
    initialized = json.loads(path.read_text(encoding="utf-8"))
    assert not {"surfaces", "reviewer", "reviewed_at"} & initialized.keys()
    assert initialized["unresolved_issues"] == ["Unresolved definition"]
    assert audit_path.exists()

print("MECHANICAL_DELIVERY_PASS: no author verdict, stale/failed evidence and unresolved/requested reviews still block")
