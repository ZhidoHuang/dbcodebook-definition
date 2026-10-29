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
    from definition_display import remove_source_navigation
    navigation = '<div class="raw-source-link">本主题对应3个原始变量，可从 dbCodeBook 目录 <span>Core</span> 查看。</div>'
    assert remove_source_navigation('a'+navigation+'b') == ('ab', 1)
    assert remove_source_navigation('没有导航') == ('没有导航', 0)
    rejects(lambda: remove_source_navigation(navigation[:-6]), '没有闭合')
    rejects(lambda: remove_source_navigation('<div class="raw-source-link">其他定义</div>'), '未识别')
    names = [f"Lab_v{i}" for i in range(31)]
    names[-1] = "Lab_v30.ng_ml"
    module = "---\ntopic_kind: module\n---\n"
    for text, variables, compact in ((module, names[:10], False), (module, names[:11], True), (module, names, True), ("", names, False)):
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
    # Questionnaire and mixed modules keep Criteria, even beyond the threshold.
    ordinary_module = "---\ntopic_kind: questionnaire_module\n---\n"
    assert not resolve_display_policy(ordinary_module, [f"RH_{i}" for i in range(41)])["compact_module"]
    assert not resolve_display_policy(ordinary_module, names, record)["compact_module"]
    rejects(lambda: resolve_display_policy(ordinary_module, names, {"topic_kind": "standard"}), "topic_kind")
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
        rejects(lambda: read_copy(path, names[:10]), "Criteria")
        path.write_text(body, encoding="utf-8")
        rejects(lambda: read_copy(path, names), "Criteria")
        path.write_text(module + body, encoding="utf-8")
        exported = folder / "copy.json"
        run = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/check_reader_copy.py"),
            "--copy", str(path), "--analysis-vars", ",".join(names), "--export", str(exported)],
            capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert json.loads(exported.read_text(encoding="utf-8"))["display_policy"]["analysis_vars"] == names
    from definition_display import display_periods, expand_period_tables
    periods = display_periods('SHARE', ['Wave 6'])
    cell = "<td class='dbcb-var-cycle-cell' style='background-color:purple;' title='Wave 6: 14,899'><span class='dbcb-var-cycle-label'>Wave 6</span><span class='dbcb-var-cycle-count'>14,899</span></td>"
    old = "before<table class='dbcb-var-cycle-table' style='min-width:max(100%, 42px);'><tr>" + cell + "</tr></table>after"
    new, evidence = expand_period_tables(old, periods)
    assert cell in new and new.count('14,899') == old.count('14,899')
    assert new.count("class='dbcb-var-cycle-label'") == 8 and new.count('<tr>') == 2
    assert '168px' in new and new.startswith('before') and new.endswith('after')
    assert expand_period_tables(new, periods)[0] == new
    rejects(lambda: expand_period_tables(old, ['Wave 1']), '不能删除')
    assert '2016' in display_periods('MHAS', ['2016'])
    assert '2003' in display_periods('HRS', ['2003'])
    assert len(display_periods('KNHANES', ['2021'])) == 21
    overview = '<table class="heatmap-table"><tr><th>Variable</th><th>original_vars</th><th>easylabel</th><th>2009</th></tr><tr><td colspan="4">Group</td></tr><tr><td>x</td><td>raw</td><td>label</td><td class="year-cell">7</td></tr></table>'
    expanded, _ = expand_period_tables(overview, ['1989','2009'])
    assert 'colspan="5"' in expanded and '<td class="year-cell">7</td>' in expanded
    assert expanded.count('class="year-cell"') == 2
    print("DEFINITION_DISPLAY_PASS: module modes and complete period grids; existing counts unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
