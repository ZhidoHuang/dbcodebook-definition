"""Exercise the large-module decision and copy/publication boundaries."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from definition_display import resolve_display_policy, result_specs, compare_result_values, confirmed_result_label
from check_reader_copy import read_copy, validate_note, compare_content


def rejects(action, reason):
    try:
        action()
    except ValueError as error:
        assert reason in str(error), str(error)
    else:
        raise AssertionError("Expected rejection: " + reason)


def main():
    from copy import deepcopy
    assert confirmed_result_label({'display_name':'血糖','unit':'mmol/L'}) == '血糖（mmol/L）'
    assert confirmed_result_label({'display_name':'患病状态','unit':''}) == '患病状态'
    assert confirmed_result_label({'display_name':'血糖（mmol/L）','unit':'mmol/L'}) == '血糖（mmol/L）'
    assert confirmed_result_label({'display_name':'患病状态','value_type':'categorical','unit':''}) == '患病状态'
    assert confirmed_result_label({'display_name':'患病状态','value_type':'categorical'}) is None
    assert confirmed_result_label({'display_name':'旧名称'}) is None
    assert confirmed_result_label({'unit':'mmol/L'}) is None
    rejects(lambda: confirmed_result_label({'display_name':'血糖','unit':' mmol/L'}), 'unit')
    from check_reader_copy import check_tree_result_order
    from check_definition_source_record import validate_logic_review
    from check_definition_output import check_summary_prose, _xlsx_row_values, ET, NS_MAIN
    plan = {"result_spec_version": 1, "approved_analysis_vars": ["JC_weight", "Demo_sex", "Sm_now"],
            "definition_plan": [
                {"analysis_var": "JC_weight", "prefix": "JC_", "value_type": "numeric", "unit": "kg"},
                {"analysis_var": "Demo_sex", "prefix": "Demo_", "value_type": "categorical", "allowed_values": ["Male", "Female"]},
                {"analysis_var": "Sm_now", "prefix": "Sm_", "value_type": "numeric", "unit": "", "allowed_values": [0, 1]}]}
    rows = [["JC_weight", "Demo_sex", "Sm_now"], [60, "Male", 1], [None, "Female", 0]]
    assert not compare_result_values(rows, plan)["errors"]
    assert not compare_result_values([rows[0], [None, None, None]], plan)["errors"]
    for replacement in (["60", "Male", 1], [60, 1, 1], [60, "Unknown", 1], [60, "Male", 2], [60, "NA", 1], [True, "Male", 1]):
        assert compare_result_values([rows[0], replacement], plan)["errors"], replacement
    assert not compare_result_values([rows[0], ["6e1", "Male", "1"]], plan, csv_input=True)["errors"]
    assert compare_result_values([rows[0], ["NaN", "Male", "1"]], plan, csv_input=True)["errors"]
    for field, value, message in (("prefix", "JY_", "confirmed prefix"), ("value_type", "guessed", "value_type")):
        bad = deepcopy(plan); bad["definition_plan"][0][field] = value
        rejects(lambda: result_specs(bad), message)
    bad = deepcopy(plan); bad["definition_plan"][1]["allowed_values"].append(None)
    rejects(lambda: result_specs(bad), "non-missing")
    bad = deepcopy(plan); del bad["definition_plan"][0]["unit"]
    rejects(lambda: result_specs(bad), "missing result facts")
    old = {"approved_analysis_vars": ["Old_age"], "definition_plan": [{"analysis_var": "Old_age"}]}
    legacy = compare_result_values([["Old_age"], [50]], old)
    assert legacy["checked"] == [] and "Old_age" in legacy["not_checked"]
    specs, _ = result_specs(plan)
    tree = "```tree\n身体测量\n- [[result:JC_weight|体重]] [[meta:kg]]\n```"
    checked = check_tree_result_order(tree, ["JC_weight"], {"JC_weight": "体重"}, require_explicit=True, result_spec=specs)
    assert checked["units_checked"] == ["JC_weight"]
    assert check_tree_result_order(tree.replace("meta:kg", "meta:0–100 kg"), ["JC_weight"],
            {"JC_weight": "体重"}, require_explicit=True, result_spec=specs)["units_checked"] == ["JC_weight"]
    rejects(lambda: check_tree_result_order(tree.replace("meta:kg", "meta:mmHg"), ["JC_weight"],
            {"JC_weight": "体重"}, require_explicit=True, result_spec=specs), "单位与方案不一致")
    for metadata in ("[[meta:0–100 kg]] [[period:Wave 2、4、6]]",
                     "[[period:Wave 2、4、6]] [[meta:0–100 kg]]"):
        with_period = tree.replace("[[meta:kg]]", metadata)
        for explicit in (False, True):
            assert check_tree_result_order(with_period, ["JC_weight"], {"JC_weight": "体重"},
                    require_explicit=explicit, result_spec=specs)["units_checked"] == ["JC_weight"]
            rejects(lambda: check_tree_result_order(with_period.replace("100 kg", "100 mmHg"),
                    ["JC_weight"], {"JC_weight": "体重"}, require_explicit=explicit,
                    result_spec=specs), "单位与方案不一致")
    rejects(lambda: check_tree_result_order(tree.replace("[[meta:kg]]", "[[period:kg]]"),
            ["JC_weight"], {"JC_weight": "体重"}, require_explicit=False, result_spec=specs), "单位与方案不一致")
    # Excel scientific notation is a number; a text or Boolean cell is not.
    row_xml = f'<row xmlns="{NS_MAIN[1:-1]}"><c r="A1"><v>1E-5</v></c><c r="B1" t="str"><v>12</v></c><c r="C1" t="b"><v>1</v></c></row>'
    assert _xlsx_row_values(ET.fromstring(row_xml), []) == [0.00001, "12", True]
    for summary, expected in (("本主题定义 **1** 个变量：①“**年龄**”。", True), ("", False)):
        checks = []
        check_summary_prose("## 摘要导读\n" + summary + "\n## 定义\n", checks)
        assert all(c["ok"] for c in checks) is expected, checks
    period_note = '<section class="raw-source-period" data-label="2011 年"><div data-summary-period-note="true"><div data-summary-period-note-title="true">问卷设计</div>询问上周睡眠。</div></section>'
    for period, expected in ((period_note, True), (period_note.replace("询问上周睡眠。", ""), False)):
        checks = []
        check_summary_prose("## 摘要导读\n本主题定义①**睡眠**。\n" + period + "\n## 定义\n", checks)
        assert all(c["ok"] for c in checks) is expected, checks
    minimal = {"schema_version": 7, "logic_review": {"result": "clear"}, "logic_issues": []}
    validate_logic_review(minimal)
    bad = deepcopy(minimal); bad["logic_review"]["naming_checked"] = False
    rejects(lambda: validate_logic_review(bad), "unfinished")
    bad = deepcopy(minimal); bad["logic_issues"] = [{"description": "来源矛盾", "impact": "影响分类", "reported_to_user_at": "2026-11-04", "decision": "待确认", "status": "reported_pending"}]
    rejects(lambda: validate_logic_review(bad), "unresolved")
    from check_definition_output import check_public_dictionary
    public = "# 1 环境 -----------\n# 2 读取数据 -----------\n# 3 定义 -----------\n" + (ROOT / "templates/public-r-dictionary.R").read_text(encoding="utf-8-sig")
    variants = [public, public.replace("变量字典", "分析字典").replace("正式输出", "输出结果")
                .replace("map <- data.frame", "map<-\ndata.frame").replace("codebook <- lapply", "codebook<- lapply")]
    for variant in variants:
        checks = []; check_public_dictionary(variant, checks)
        assert all(c["ok"] for c in checks), checks
    checks = []; check_public_dictionary(public.replace("map$original_vars", "wrong_source"), checks)
    assert any(not c["ok"] for c in checks), checks
    from definition_display import remove_source_navigation
    navigation = '<div class="raw-source-link">本主题对应3个原始变量，可从 dbCodeBook 目录 <span>Core</span> 查看。</div>'
    assert remove_source_navigation('a'+navigation+'b') == ('ab', 1)
    assert remove_source_navigation('没有导航') == ('没有导航', 0)
    rejects(lambda: remove_source_navigation(navigation[:-6]), '没有闭合')
    rejects(lambda: remove_source_navigation('<div class="raw-source-link">其他定义</div>'), '未识别')
    names = [f"Lab_v{i}" for i in range(31)]
    names[-1] = "Lab_v30.ng_ml"
    module = "---\ntopic_kind: module\n---\n"
    for text, variables, compact in ((module, names[:10], False), (module, names[:11], False), (module, names, False), ("", names, False)):
        policy = resolve_display_policy(text, variables)
        assert policy["compact_module"] is compact
        assert policy["analysis_vars"] == variables
    rejects(lambda: resolve_display_policy(module), "实际 analysis_vars")
    rejects(lambda: resolve_display_policy(module, names, {"approved_analysis_vars": names}), "topic_kind")
    record = {"topic_kind": "module", "approved_analysis_vars": names}
    assert not resolve_display_policy(module, record=record)["compact_module"]
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
    summary = "、".join(f"[[序号:{i}]]检测值{i}" for i in range(1, len(names) + 1))
    body = f"## 摘要导读\n\n本模块定义 **实验室检测值**：{summary}。\n\n## 小book提示\n\n本主题没有需要单独提示的主题级边界\n"
    note = '## 摘要导读\n\n本模块定义 <span data-summary-concept="true">实验室检测值</span>。\n\n## 材料\n'
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        path, output = folder / "文案.md", folder / "笔记.md"
        path.write_text(module + body, encoding="utf-8")
        output.write_text(note, encoding="utf-8")
        rejects(lambda: read_copy(path, names, record), "Criteria")
        from test_reader_copy import render_note
        fields = {"定义": "检测的发布数值。", "定义逻辑": "保留发布的检测数值。", "分类": "- [数值] 检测单位。"}
        criteria = {v: dict(fields) for v in names}
        blocks = "## Criteria\n\n" + "\n\n".join("### " + v + "\n\n" + "\n\n".join("#### " + k + "\n\n" + t for k,t in fields.items()) for v in names)
        path.write_text(module + body.replace("## 小book提示", blocks + "\n\n## 小book提示"), encoding="utf-8")
        copy = read_copy(path, names, record)
        assert list(copy["criteria"]) == names
        output.write_text(render_note(copy), encoding="utf-8")
        assert validate_note(path, output, record=record)["variables"] == names
        rejects(lambda: compare_content(copy, dict(copy, criteria={})), "Criteria")
        output.write_text(note, encoding="utf-8")
        rejects(lambda: validate_note(path, output, record=record), "定义表")
        output.write_text(render_note(copy), encoding="utf-8")
        exported = folder / "copy.json"
        run = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/check_reader_copy.py"),
            "--copy", str(path), "--analysis-vars", ",".join(names), "--export", str(exported)],
            capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert json.loads(exported.read_text(encoding="utf-8"))["display_policy"]["analysis_vars"] == names
        # Real copy/record/export path: category metadata is not a measurement unit.
        label_vars = ['Lab_glucose', 'Demo_group', 'Old_age', 'Old_group']
        label_plan = {'approved_analysis_vars': label_vars, 'definition_plan': [
            {'analysis_var':'Lab_glucose', 'display_name':'血糖', 'value_type':'numeric', 'unit':'mmol/L'},
            {'analysis_var':'Demo_group', 'display_name':'分组', 'value_type':'categorical', 'unit':'', 'allowed_values':['男','女']},
            {'analysis_var':'Old_age', 'display_name':'年龄', 'value_type':'numeric'},
            {'analysis_var':'Old_group', 'display_name':'旧分组', 'value_type':'categorical', 'allowed_values':['是','否']},
        ]}
        tree = '''```tree
结果
- [[result:Lab_glucose|血糖]] [[meta:mmol/L]]
- [[result:Demo_group|分组]] [[meta:男／女]]
- [[result:Old_age|年龄]] [[meta:岁]]
- [[result:Old_group|旧分组]] [[meta:是／否]]
```'''
        label_summary = '本主题定义①**血糖**、②**分组**、③**年龄**和④**旧分组**。\n\n' + tree
        label_criteria = '## Criteria\n\n' + '\n\n'.join(
            '### ' + v + '\n\n' + '\n\n'.join('#### ' + k + '\n\n' + t for k,t in fields.items())
            for v in label_vars)
        path.write_text('## 摘要导读\n\n' + label_summary + '\n\n' + label_criteria +
                        '\n\n## 小book提示\n\n本主题没有需要单独提示的主题级边界\n', encoding='utf-8')
        record_path = folder / 'result-plan.json'
        record_path.write_text(json.dumps(label_plan, ensure_ascii=False), encoding='utf-8')
        result = read_copy(path, label_vars, label_plan)
        expected_labels = {'Lab_glucose':'血糖（mmol/L）', 'Demo_group':'分组'}
        assert result['result_labels'] == expected_labels
        assert 'Old_age' in result['result_labels_not_checked']
        assert 'Old_group' in result['result_labels_not_checked']
        run = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'scripts/check_reader_copy.py'),
            '--copy', str(path), '--record', str(record_path), '--analysis-vars', ','.join(label_vars),
            '--export', str(exported)], capture_output=True, text=True, encoding='utf-8')
        assert run.returncode == 0, run.stdout + run.stderr
        exported_copy = json.loads(exported.read_text(encoding='utf-8'))
        assert exported_copy['result_labels'] == expected_labels
        assert 'Old_age' in exported_copy['result_labels_not_checked']
        assert 'Old_group' in exported_copy['result_labels_not_checked']
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
    # Real public CLI: local display changes only; no reports or version folders.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        note = root/'note.md'
        note.write_text(old, encoding='utf-8')
        raw = root/'raw_data.csv'
        raw.write_bytes(b'id,x\n1,7\n')
        command = [sys.executable, '-X', 'utf8', str(ROOT/'scripts/definition_display.py'),
                   'periods', '--input', str(note), '--database', 'SHARE']
        first = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        assert first.returncode == 0, first.stderr
        assert json.loads(first.stdout)['changed'] is True
        assert note.read_text(encoding='utf-8') == new
        signature = note.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        assert second.returncode == 0 and not json.loads(second.stdout)['changed']
        assert note.read_bytes() == signature
        assert set(p.name for p in root.iterdir()) == {'note.md', 'raw_data.csv'}
        assert raw.read_bytes() == b'id,x\n1,7\n'
        note.write_bytes(b'\xef\xbb\xbf' + ('prefix\r\n'+old+'\r\nsuffix').encode('utf-8'))
        preserved = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        assert preserved.returncode == 0, preserved.stderr
        assert note.read_bytes() == b'\xef\xbb\xbf' + ('prefix\r\n'+new+'\r\nsuffix').encode('utf-8')
        # Unsupported or malformed inputs fail before writing any content.
        note.write_text('no period table', encoding='utf-8')
        failed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        assert failed.returncode != 0 and note.read_text(encoding='utf-8') == 'no period table'
    print("DEFINITION_DISPLAY_PASS: module modes and complete period grids; existing counts unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
