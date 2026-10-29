"""Exercise Markdown trees through the real loader, rendering and final-note check."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import summary_blocks, read_copy, compare_content, validate_note, check_tree_result_order


def rejects(action, phrase):
    try:
        action()
    except ValueError as error:
        assert phrase in str(error), str(error)
    else:
        raise AssertionError(phrase)


tree = "total\n    ├── group_a\n    │   └── item_x < item_y\n    └── group_b"
rejects(lambda: summary_blocks("```text\nmissing close"), "结束围栏")
rejects(lambda: summary_blocks("```\n\n```"), "不能为空")
rejects(lambda: summary_blocks("```python\nx\n```"), "无语言或 text")
fenced = "```text\n" + tree + "\n```"
indented = "\n".join("    " + line for line in tree.splitlines())
assert summary_blocks(fenced) == summary_blocks(indented)

# Composite-root presentation can precede its ingredients; repeated references
# do not add outputs. Chinese labels are matched exactly, never guessed.
named_tree = "```text 得分\n[[result:总分]]\n├─ [[result:分项甲]]\n└─ [[result:分项乙]]\n[[relation:再次使用]] [[result:分项甲]]\n```"
names = ['Score_total', 'Score_a', 'Score_b']
labels = dict(zip(names, ['总分', '分项甲', '分项乙']))
assert check_tree_result_order(named_tree, names, labels)['references'] == 1
rejects(lambda: check_tree_result_order(named_tree, names[::-1], labels), '顺序不一致')
rejects(lambda: check_tree_result_order(named_tree.replace('分项乙', '未登记名称'), names, labels), '已确认显示名')
rejects(lambda: check_tree_result_order(named_tree, names, {**labels, 'Score_b': '分项甲'}), '重复')
rejects(lambda: check_tree_result_order(named_tree.replace('[[result:分项乙]]', '[[component:分项乙]]'), names, labels), '顺序不一致')
assert check_tree_result_order('只有一个直接结果，无需树。', ['A'], {'A': '年龄'})['scope'] == 'no_tree'

# Unit meta can distinguish same-named results without changing visible labels.
unit_tree = '```text 检验\n├─ [[result:葡萄糖]] [[meta:（mmol/L）]]\n└─ [[result:葡萄糖]] [[meta:（mg/dL）]]\n```'
unit_labels = {'glucose_si': '葡萄糖（mmol/L）', 'glucose_mass': '葡萄糖（mg/dL）'}
assert check_tree_result_order(unit_tree, list(unit_labels), unit_labels)['variables'] == list(unit_labels)
rejects(lambda: check_tree_result_order(unit_tree.replace('mmol/L', 'mol/L'), list(unit_labels), unit_labels), '已确认显示名')
rejects(lambda: check_tree_result_order(unit_tree, list(unit_labels)[::-1], unit_labels), '顺序不一致')
rejects(lambda: check_tree_result_order(unit_tree.replace(']] [[meta:', ']]\n[[meta:'), list(unit_labels), unit_labels), '已确认显示名')
rejects(lambda: check_tree_result_order(unit_tree, list(unit_labels), {'glucose_si': '葡萄糖', 'glucose_mass': '葡萄糖（mmol/L）'}), '不唯一')

# Identity is explicit even when dictionary labels are English or duplicated.
bound_tree = '```text 检验\n├─ [[result:JY_glucose_mmol.l|葡萄糖]] [[meta:（mmol/L）]]\n└─ [[result:JY_glucose_mg.dl|葡萄糖]] [[meta:（mg/dL）]]\n```'
bound_names = ['JY_glucose_mmol.l', 'JY_glucose_mg.dl']
duplicate_labels = dict.fromkeys(bound_names, 'Glucose')
assert check_tree_result_order(bound_tree, bound_names, duplicate_labels)['scope'] == 'explicit_results'
assert 'JY_glucose' not in summary_blocks(bound_tree)[0]['text']
assert 'data-tree-variable="JY_glucose_mmol.l"' in summary_blocks(bound_tree)[0]['role_html']
rejects(lambda: check_tree_result_order(bound_tree, bound_names[::-1], duplicate_labels), '顺序不一致')
rejects(lambda: check_tree_result_order(bound_tree.replace('JY_glucose_mmol.l|', 'wrong|'), bound_names, duplicate_labels), '身份未登记')
rejects(lambda: check_tree_result_order(bound_tree.replace('JY_glucose_mmol.l|', ''), bound_names, duplicate_labels), '身份未登记')
rejects(lambda: check_tree_result_order(bound_tree.replace('JY_glucose_mmol.l|', 'JY_glucose_mg.dl|'), bound_names, duplicate_labels), '顺序不一致')
rejects(lambda: summary_blocks(bound_tree.replace('JY_glucose_mmol.l|葡萄糖', 'bad name|葡萄糖')), '有效变量名')
rejects(lambda: summary_blocks(bound_tree.replace('JY_glucose_mmol.l|葡萄糖', 'JY_glucose_mmol.l| ')), '非空显示名')

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    original = (ROOT / "tests/fixtures/writing-inputs/reader-copy.md").read_text(encoding="utf-8")
    script = folder / "forward.R"
    script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root,"scripts","summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts","render_definition_bundle.R"),encoding="UTF-8")
copy <- read_definition_copy(c("fall_status","fall_count"))
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry,"#A33842"),
 criteria=copy$criteria,insight="",references=tail(copy$reference_lines,1))
definition_copy_check(source=actual)
jsonlite::write_json(actual,"actual.json",auto_unbox=TRUE)
rows <- vapply(names(copy$criteria),function(v) paste0('<tr><td>',v,'</td><td>',
 copy$criteria[[v]],'</td><td>distribution</td></tr>'),character(1))
writeLines(c("## 摘要导读",actual$summary,"## 定义",
 '<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',rows,'</table>',
 copy$reference_lines,"## 材料"),"note.md",useBytes=TRUE)
definition_copy_check(note="note.md")
''', encoding="utf-8")
    env = {**os.environ, "DBCODEBOOK_DEFINITION_SKILL_ROOT": str(ROOT), "DBCODEBOOK_DEFINITION_PYTHON": sys.executable}
    for name in ("LANG", "LC_ALL", "LC_CTYPE"):
        env.pop(name, None)
    explicit = '```text 跌倒\n├─ [[result:fall_status|是否跌倒]]\n└─ [[result:fall_count|跌倒次数]]\n```'
    for block in (fenced, indented, explicit):
        path = folder / "文案.md"
        path.write_text(original.replace("## Criteria", block + "\n\n## Criteria"), encoding="utf-8")
        result = subprocess.run([os.environ["RSCRIPT"], "--vanilla", "--encoding=UTF-8", str(script)],
                                cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
        actual = json.loads((folder / "actual.json").read_text(encoding="utf-8"))
        content = read_copy(path)
        assert "white-space:pre;" in actual["summary"] and "font-family:monospace" in actual["summary"]
        if block == explicit:
            assert 'data-tree-variable="fall_status"' in actual['summary']
            assert 'fall_status|' not in actual['summary']
            assert validate_note(path, folder / 'note.md')['ok']
            bad = copy.deepcopy(actual)
            bad['summary'] = bad['summary'].replace('data-tree-variable="fall_status"', 'data-tree-variable="fall_count"')
            rejects(lambda: compare_content(content, bad, source=True), '变量身份对应')
            note = folder / 'note.md'
            note.write_text(note.read_text(encoding='utf-8').replace('data-tree-variable="fall_status"', 'data-tree-variable="fall_count"'), encoding='utf-8')
            rejects(lambda: validate_note(path, note), '变量身份对应')
            continue
        assert "item_x &lt; item_y" in actual["summary"]
        for old, new in (("    ├", "├"), ("\n    └", "    └"), ("group_b", "group_c")):
            bad = copy.deepcopy(actual)
            bad["summary"] = bad["summary"].replace(old, new)
            rejects(lambda: compare_content(content, bad, source=True), "代码树")
        note = folder / "note.md"
        note.write_text(note.read_text(encoding="utf-8").replace("    ├", "├"), encoding="utf-8")
        rejects(lambda: validate_note(path, note), "代码树")
print("SUMMARY_CODE_TREE_PASS: real R, fenced/indented, escaping, missing node/newline/indent rejected")
