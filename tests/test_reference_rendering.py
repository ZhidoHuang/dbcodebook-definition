"""Reference presentation is generated; source content and order stay intact."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import render_references
from check_reader_copy import read_copy, compare_content


def main():
    materials = ['[材料 A](https://example.org/a)：第 2 页支持计分。',
                 '材料 B（2024），第 5 页；保留 [0/1] 和正文数字 3.。']
    expected = '\n'.join(f'> {i}. {x}' for i, x in enumerate(materials, 1))
    assert render_references('') == ''
    assert render_references(materials[0]) == '> 1. ' + materials[0]
    for text in ('\n\n'.join(materials), expected,
                 f'> [1] {materials[0]}\n\n> [2] {materials[1]}',
                 f'- {materials[0]}\n- {materials[1]}'):
        assert render_references(text) == expected
    assert render_references(expected) == expected
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        original = (ROOT / 'tests/fixtures/writing-inputs/reader-copy.md').read_text(encoding='utf-8')
        path = folder / '文案.md'
        path.write_text(original.split('## 参考资料说明')[0] + '## 参考资料说明\n\n'
                        + f'> [1] {materials[0]}\n\n> [2] {materials[1]}\n', encoding='utf-8')
        content = read_copy(path)
        assert content['references'] == expected
        for bad in (materials[0], '\n'.join(reversed(materials)), expected.replace('第 2 页', '第 9 页')):
            try:
                compare_content(content, {**content, 'references': bad})
            except ValueError as error:
                assert 'references' in str(error)
            else:
                raise AssertionError('Reference content loss/change accepted')
        script = folder / 'render.R'
        script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root,"scripts","summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts","render_definition_bundle.R"),encoding="UTF-8")
copy <- read_definition_copy(c("fall_status","fall_count"))
writeLines(copy$reference_lines,"references.md",useBytes=TRUE)
''', encoding='utf-8')
        env = {**os.environ, 'DBCODEBOOK_DEFINITION_SKILL_ROOT': str(ROOT),
               'DBCODEBOOK_DEFINITION_PYTHON': sys.executable}
        for key in ('LANG', 'LC_ALL', 'LC_CTYPE'):
            env.pop(key, None)
        run = subprocess.run([os.environ['RSCRIPT'], '--vanilla', '--encoding=UTF-8', str(script)],
                             cwd=folder, env=env, capture_output=True)
        assert run.returncode == 0, run.stdout + run.stderr
        assert (folder/'references.md').read_text(encoding='utf-8') == '## 参考资料说明\n\n' + expected + '\n'
    print('REFERENCE_RENDERING_PASS')


if __name__ == '__main__':
    main()
