import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from check_reader_copy import semantic_tree, summary_blocks, rendered_summary_trees, read_copy

source = '[[component:条目]] [[meta:（1992 年）]]\n└─ [[relation:值 <4]] → [[result:结果]]'
block = semantic_tree(source)
named = summary_blocks('```text CES-D-11\n' + source + '\n```')[0]
assert named['label'] == 'CES-D-11'
assert named['text'] == block['text']
block['label'] = 'CES-D-11'
assert block['text'] == '条目 （1992 年）\n└─ 值 <4 → 结果'
assert '&lt;4' in block['role_html']
for role in ('component', 'meta', 'relation', 'result', 'connector'):
    assert f'data-tree-role="{role}"' in block['role_html']
assert 'role_html' not in semantic_tree('普通旧树\n└─ 结果')
period = semantic_tree('主题 [[meta:[1993-2022年]]]')
assert period['text'] == '主题 [1993-2022年]'
assert '<span data-tree-role="meta">[1993-2022年]</span>' in period['role_html']
for bad in ('[[bad:结果]]', '[[result:未闭合', '[[result:跨\n行]]'):
    try: semantic_tree(bad)
    except ValueError: pass
    else: raise AssertionError(bad)
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    copy_text = '''# 测试
## 摘要导读
本主题定义一个结果。
## 问卷
### 2011 年
询问当前情况。
#### Q1
是否困难？
- 1 是
- 2 否
## Criteria
### result
#### 定义
是否困难。
#### 定义逻辑
按回答取值。
#### 分类
- [1] 是
- [0] 否
## 小book提示
本主题没有需要单独提示的主题级边界
'''
    copy_path = p/'copy.md'
    copy_path.write_text(copy_text, encoding='utf-8')
    current = read_copy(copy_path)
    assert current.get('questionnaire'), 'The questionnaire section must be read'
    (p/'tree.json').write_text(json.dumps({'paragraphs':[block]},ensure_ascii=False),encoding='utf-8')
    (p/'test.R').write_text('''
source(file.path(Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT"), "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
entry <- jsonlite::fromJSON("tree.json", simplifyVector=FALSE)
writeLines(render_summary_entry_paragraph(entry, "#123456"), "tree.html", useBytes=TRUE)
empty <- render_summary_note_section(entry, NULL, "#123456")
stopifnot(!any(empty == "## 问卷"))
selection <- list(lines=list(summary_questionnaire_line("Q1", "问题", options=list(summary_questionnaire_option("1 是")))))
shown <- render_summary_note_section(entry, selection, "#123456", definition_basis="依据")
stopifnot(sum(shown == "## 问卷") == 1L, sum(shown == "## 定义依据") == 1L)
''',encoding='utf-8')
    env={k:v for k,v in os.environ.items() if k not in ('LANG','LC_ALL','LC_CTYPE')}
    run=subprocess.run([os.environ['RSCRIPT'],str(p/'test.R')],cwd=p,env={**env,'DBCODEBOOK_DEFINITION_SKILL_ROOT':str(ROOT)},capture_output=True)
    assert run.returncode == 0, run.stderr.decode('utf-8', errors='replace')
    output=(p/'tree.html').read_text(encoding='utf-8')
    assert rendered_summary_trees(output)==[block['text']]
    assert 'data-tree-role="result"' in output
    assert 'data-tree-label="CES-D-11"' in output
    assert '[[result:' not in output
print('TREE_ROLES_PASS: explicit roles, escaping, legacy text, malformed input, actual R output')
