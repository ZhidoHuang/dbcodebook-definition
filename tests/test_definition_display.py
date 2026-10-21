"""Exercise the large-module decision and copy/publication boundaries."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from definition_display import resolve_display_policy
from check_reader_copy import read_copy, validate_note, compare_content


def rejects(action, reason):
    try:
        action()
    except ValueError as error:
        assert reason in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + reason)


def main():
    names = [f"Lab_v{i}" for i in range(31)]
    names[-1] = "Lab_v30.ng_ml"
    module = "---\ntopic_kind: module\n---\n"
    for text, variables, compact in ((module, names[:30], False), (module, names, True), ("", names, False)):
        policy = resolve_display_policy(text, variables)
        assert policy["compact_module"] is compact
        assert policy["analysis_vars"] == variables
    rejects(lambda: resolve_display_policy(module), "实际 analysis_vars")
    rejects(lambda: resolve_display_policy(module, names, {"approved_analysis_vars": names}), "topic_kind")
    record = {"topic_kind": "module", "approved_analysis_vars": names}
    assert resolve_display_policy(module, record=record)["compact_module"]
    rejects(lambda: resolve_display_policy(module, names[::-1], record), "顺序")
    rejects(lambda: resolve_display_policy(module, names + names[:1]), "duplicates")
    rejects(lambda: resolve_display_policy("---\ntopic_kind: compact\n---\n", names), "topic_kind")
    rejects(lambda: resolve_display_policy("---\ntopic_kind: module\n"), "结束")
    rejects(lambda: resolve_display_policy("---\ntopic_kind: module\ntopic_kind: standard\n---\n", names), "重复")
    assert not resolve_display_policy("# Module with 100 results", names)["compact_module"]
    body = "## 摘要导读\n\n本模块定义 **实验室检测值**。\n\n## 小book提示\n\n本主题没有需要单独提示的主题级边界\n"
    note = '## 摘要导读\n\n本模块定义 <span data-summary-concept="true">实验室检测值</span>。\n\n## 材料\n'
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        path, output = folder / "文案.md", folder / "笔记.md"
        path.write_text(module + body, encoding="utf-8")
        output.write_text(note, encoding="utf-8")
        copy = read_copy(path, names, record)
        assert copy["criteria"] == {} and copy["criteria_intro"] == ""
        assert validate_note(path, output, record=record)["variables"] == names
        rendered = dict(copy, criteria=[])
        assert compare_content(copy, rendered)["variables"] == names
        rejects(lambda: compare_content(copy, dict(copy, criteria={"extra": {}})), "Criteria")
        output.write_text(note + "\n## 定义\n", encoding="utf-8")
        rejects(lambda: validate_note(path, output, record=record), "不生成")
        output.write_text(note + "\n<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr></table>\n", encoding="utf-8")
        rejects(lambda: validate_note(path, output, record=record), "不生成")
        path.write_text(module + body + "\n## Criteria\n", encoding="utf-8")
        rejects(lambda: read_copy(path, names, record), "不编写 Criteria")
        path.write_text(module + body, encoding="utf-8")
        rejects(lambda: read_copy(path, names[:30]), "Criteria")
        path.write_text(body, encoding="utf-8")
        rejects(lambda: read_copy(path, names), "Criteria")
        path.write_text(module + body, encoding="utf-8")
        exported = folder / "copy.json"
        run = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/check_reader_copy.py"),
            "--copy", str(path), "--analysis-vars", ",".join(names), "--export", str(exported)],
            capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert json.loads(exported.read_text(encoding="utf-8"))["display_policy"]["analysis_vars"] == names
    print("DEFINITION_DISPLAY_PASS: module30/full, module31/compact, standard31/full; portable copy, exact result list, no Criteria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
