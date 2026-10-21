"""Check labeled semantic trees through the actual Python and R renderers."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_reader_copy import semantic_tree, summary_blocks, rendered_summary_trees, read_copy

# Parser-level roles, escaping and legacy compatibility remain separate from
# the writing fixtures below; all accepted trees share one real R render.
role_source = '[[component:条目]] [[meta:（1992 年）]]\n└─ [[relation:值 <4]] → [[result:结果]]'
role_block = semantic_tree(role_source)
named = summary_blocks('```text CES-D-11\n' + role_source + '\n```')[0]
assert named['label'] == 'CES-D-11'
assert named['text'] == role_block['text']
role_block['label'] = 'CES-D-11'
assert role_block['text'] == '条目 （1992 年）\n└─ 值 <4 → 结果'
assert '&lt;4' in role_block['role_html']
for role in ('component', 'meta', 'relation', 'result', 'connector'):
    assert f'data-tree-role="{role}"' in role_block['role_html']
assert 'role_html' not in semantic_tree('普通旧树\n└─ 结果')
period = semantic_tree('主题 [[meta:[1993-2022年]]]')
assert period['text'] == '主题 [1993-2022年]'
assert '<span data-tree-role="meta">[1993-2022年]</span>' in period['role_html']
for bad in ('[[bad:结果]]', '[[result:未闭合', '[[result:跨\n行]]'):
    try:
        semantic_tree(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)

fixtures = ROOT / 'tests/fixtures/tree-writing'
trees = []
for name, count in [('hrs-cesd.md', 2), ('continuous-score.md', 1)]:
    source = (fixtures / name).read_text(encoding='utf-8')
    blocks = [b for b in summary_blocks(source) if b['type'] == 'code_tree']
    assert len(blocks) == count
    for block in blocks:
        assert block.get('label') and block.get('role_html')
        assert '\n\n' not in block['text']
        assert not re.search(r'\{[^}]+\}|\[\[', block['text'])
    trees.extend(blocks)
assert trees[0]['text'].count('（0/1）') == 9  # eight items plus classification
assert trees[1]['text'].count('0–3 分') == 11
assert trees[1]['role_html'].count('data-tree-role="component"') == 11
assert sum(t['role_html'].count('data-tree-role="result"') for t in trees[:2]) == 13
assert trees[2]['role_html'].count('data-tree-role="result"') == 14
assert trees[2]['role_html'].count('data-tree-role="component"') == 5
assert '听力分＋（远视力分＋近视力分）÷2' in trees[2]['text']
assert trees[2]['text'].count('取平均，再标准化') == 2
assert '总分不再标准化' in trees[2]['text']
# Exercise the shared-item template itself through the same renderer, with only
# the two totals marked as delivered results and all six items as components.
template = (ROOT / 'templates/reader-copy.md').read_text(encoding='utf-8')
shared_tree = re.search(r'```text 两种总分\n.*?\n```', template, re.S)[0]
shared = [b for b in summary_blocks(shared_tree) if b['type'] == 'code_tree'][0]
assert shared['role_html'].count('data-tree-role="result"') == 2
assert shared['role_html'].count('data-tree-role="component"') == 6
trees.append(shared)
trees.append(role_block)
for bad in ['```text 例\n[[unknown:名字]]\n```', '```text 例\n[[meta:未闭合\n```']:
    try:
        summary_blocks(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Malformed roles were accepted')
assert summary_blocks('```text\n旧树\n└─ 结果\n```')[0]['text'] == '旧树\n└─ 结果'
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
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
    copy_path = path / 'copy.md'
    copy_path.write_text(copy_text, encoding='utf-8')
    current = read_copy(copy_path)
    assert current.get('questionnaire'), 'The questionnaire section must be read'
    (path/'trees.json').write_text(json.dumps({'paragraphs': trees}, ensure_ascii=False), encoding='utf-8')
    (path/'render.R').write_text('''source(file.path(Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT"), "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
entry <- jsonlite::fromJSON("trees.json", simplifyVector=FALSE)
writeLines(render_summary_entry_paragraph(entry, "#123456"), "trees.html", useBytes=TRUE)
empty <- render_summary_note_section(entry, NULL, "#123456")
stopifnot(!any(empty == "## 问卷"))
selection <- list(lines=list(summary_questionnaire_line("Q1", "问题", options=list(summary_questionnaire_option("1 是")))))
shown <- render_summary_note_section(entry, selection, "#123456", definition_basis="依据")
stopifnot(sum(shown == "## 问卷") == 1L, sum(shown == "## 定义依据") == 1L)
''', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k not in ('LANG', 'LC_ALL', 'LC_CTYPE')}
    env['DBCODEBOOK_DEFINITION_SKILL_ROOT'] = str(ROOT)
    run = subprocess.run([os.environ['RSCRIPT'], '--vanilla', '--encoding=UTF-8', str(path/'render.R')], cwd=path, env=env, capture_output=True)
    assert run.returncode == 0, run.stderr.decode('utf-8', errors='replace')
    rendered = (path/'trees.html').read_text(encoding='utf-8')
    assert rendered_summary_trees(rendered) == [t['text'] for t in trees]
    for tree in trees:
        assert f'data-tree-label="{tree["label"]}"' in rendered
    assert 'data-tree-role="result"' in rendered
    assert '&lt;4' in rendered
    assert '[[result:' not in rendered
print('TREE_CONTRACT_PASS: trial trees and shared-item template, all roles, escaping, legacy/malformed input, questionnaire headings, meta, formula order, literal text, labels, actual R')
