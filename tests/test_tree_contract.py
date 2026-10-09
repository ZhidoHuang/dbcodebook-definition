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
from check_reader_copy import summary_blocks, rendered_summary_trees

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
    (path/'trees.json').write_text(json.dumps({'paragraphs': trees}, ensure_ascii=False), encoding='utf-8')
    (path/'render.R').write_text('''source(file.path(Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT"), "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
entry <- jsonlite::fromJSON("trees.json", simplifyVector=FALSE)
writeLines(render_summary_entry_paragraph(entry, "#123456"), "trees.html", useBytes=TRUE)
''', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k not in ('LANG', 'LC_ALL', 'LC_CTYPE')}
    env['DBCODEBOOK_DEFINITION_SKILL_ROOT'] = str(ROOT)
    run = subprocess.run([os.environ['RSCRIPT'], '--vanilla', '--encoding=UTF-8', str(path/'render.R')], cwd=path, env=env, capture_output=True)
    assert run.returncode == 0, run.stderr.decode('utf-8', errors='replace')
    rendered = (path/'trees.html').read_text(encoding='utf-8')
    assert rendered_summary_trees(rendered) == [t['text'] for t in trees]
    for tree in trees:
        assert f'data-tree-label="{tree["label"]}"' in rendered
print('TREE_CONTRACT_PASS: three trial trees, variable roles, meta, formula order, literal text, labels, actual R')
