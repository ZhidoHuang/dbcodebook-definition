"""Exercise module-scoped periods and definition basis through the real R renderer."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_reader_copy import read_copy, compare_content, validate_note, read_questionnaire_copy, questionnaire_copy_errors
from check_definition_readability import validate_questionnaire_rendering, SOURCE_RECORD_NAME


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        path = folder / '文案.md'
        text = '''# 示例
## 摘要导读
本主题定义“**综合结果**”，由两个方面组成，共 **1** 个变量。
## 定义依据
根据[方法资料](https://example.org/method)，比较两种构造。

| 方案 | 组成 |
| --- | --- |
| 甲 | 握力、视力 |
| 乙 | 握力 |

本次采用甲。
## 原始问卷
### 握力
#### Wave 1–2
##### 问卷设计
测量握力，记录公斤数。
##### 测量问题
###### Q1
握力是多少公斤？
```text
准备测量
└─ 已完成 → 记录公斤数
```
### 视力
#### Wave 1
##### 问卷设计
询问视力。
##### Q1
视力怎样？
- 1 好
- 2 差
#### Wave 2
##### 问卷设计变化
改问矫正后视力。
##### Q1
矫正后视力怎样？
- 1 好
- 2 差
## Criteria
### result
#### 定义
综合结果。
#### 定义逻辑
按已定方法计算。
#### 分类
- 数值。
## 小book提示
本主题没有需要单独提示的主题级边界
'''
        path.write_text(text, encoding='utf-8')
        parsed = read_copy(path)
        assert list(parsed['questionnaire']) == ['握力__Wave_1_2', '视力__Wave_1', '视力__Wave_2']
        assert parsed['questionnaire']['握力__Wave_1_2']['questions'][0]['group'] == '测量问题'
        assert 'group' not in parsed['questionnaire']['视力__Wave_1']['questions'][0]
        assert len(parsed['summary_blocks']) == 1
        record = {'schema_version': 6, 'questionnaire_evidence': [{
            'question_id': 'Q1', 'question_text': '握力是多少公斤？',
            'periods': ['Wave 1', 'Wave 2'], 'response_type': 'open_value', 'options': [], 'skip_logic': [],
            'rendered_in_copy': True, 'copy_locator': '原始问卷/握力/Q1', 'questionnaire_module': '握力'}]}
        assert questionnaire_copy_errors(parsed, record) == []
        ambiguous = copy.deepcopy(record)
        ambiguous['questionnaire_evidence'][0].pop('questionnaire_module')
        assert questionnaire_copy_errors(parsed, ambiguous)
        bad = copy.deepcopy(parsed)
        bad['definition_basis'] = ''
        try:
            compare_content(parsed, bad)
        except ValueError as e:
            assert 'definition_basis' in str(e)
        else:
            raise AssertionError('Dropped basis accepted')
        script = folder / 'render.R'
        script.write_text('''root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root,"scripts","summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts","render_definition_bundle.R"),encoding="UTF-8")
copy <- read_definition_copy("result")
q <- render_summary_selection_paragraph(copy$summary_selection,"#A33842")
definition_copy_check(source=list(summary=render_summary_entry_paragraph(copy$summary_entry,"#A33842"),
 criteria=copy$criteria,insight="",references="",definition_basis=copy$definition_basis,questionnaire=q))
summary <- render_summary_note_section(copy$summary_entry,copy$summary_selection,"#A33842",definition_basis=copy$definition_basis)
writeLines(c(summary,"## 定义",'<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',
 paste0('<tr><td>result</td><td>',copy$criteria$result,'</td><td>分布</td></tr>'),'</table>'),"note.md",useBytes=TRUE)
definition_copy_check(note="note.md")
''', encoding='utf-8')
        env = dict(os.environ, DBCODEBOOK_DEFINITION_SKILL_ROOT=str(ROOT), DBCODEBOOK_DEFINITION_PYTHON=sys.executable)
        for key in ('LANG', 'LC_ALL', 'LC_CTYPE'):
            env.pop(key, None)
        rscript = os.environ.get('RSCRIPT', 'Rscript')
        run = subprocess.run([rscript, '--vanilla', '--encoding=UTF-8', str(script)], cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8')
        assert run.returncode == 0, run.stdout + run.stderr
        note = folder / 'note.md'
        assert validate_note(path, note)['ok']
        (folder / SOURCE_RECORD_NAME).write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
        assert validate_questionnaire_rendering(folder, folder, note.name)['rendered_question_periods'] == 2
        (folder / SOURCE_RECORD_NAME).write_text(json.dumps(ambiguous,ensure_ascii=False),encoding='utf-8')
        try:
            validate_questionnaire_rendering(folder, folder, note.name)
        except ValueError:
            pass
        else:
            raise AssertionError('Ambiguous repeated question ID accepted')
        output = note.read_text(encoding='utf-8')
        assert output.count('data-display="period-tabs"') == 2
        assert output.count('data-questionnaire-module-title="true"') == 2
        assert '<pre data-questionnaire-flow="true"' in output
        assert '| 甲 | 握力、视力 |' in output
        assert output.index('## 定义依据') < output.index('data-questionnaire-module=')
        note.write_text(output.replace('└─ 已完成', '  └─ 已完成'), encoding='utf-8')
        try:
            validate_note(path, note)
        except ValueError as e:
            assert '流程图' in str(e)
        else:
            raise AssertionError('Changed flowchart indentation accepted')
        note.write_text(output.replace('矫正后视力怎样？', '视力怎样？'), encoding='utf-8')
        try:
            validate_note(path, note)
        except ValueError as e:
            assert '原始问卷' in str(e)
        else:
            raise AssertionError('Wrong module-period text accepted')
    print('COMPLEX_READER_COPY_PASS')


if __name__ == '__main__':
    main()
