"""Exercise the CURRENT examples through copy checks and actual R rendering."""
from pathlib import Path
import json
import html
import os
import re
import subprocess
import sys
import tempfile
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_reader_copy import read_copy, read_questionnaire_copy, questionnaire_copy_errors, validate_note
from check_definition_readability import validate_questionnaire_rendering

text = (ROOT / 'templates/reader-copy.md').read_text(encoding='utf-8')

def block(label):
    start = text.index('**' + label + '**')
    return re.search(r'```markdown\n(.*?)\n```', text[start:], re.S)[1]

questionnaire = block('分期问卷的展示格式')
intro = block('前置跳题补零的写法')
criteria = block('计算公式与计算条件的写法')
summary = '## 摘要导读\n\n本主题定义“**困难项目数**”。\n\n'
document = summary + questionnaire + '\n\n' + intro + '\n\n' + criteria + '\n\n## 小book提示\n\n本主题没有需要单独提示的主题级边界\n'
q = read_questionnaire_copy(questionnaire)
groups = list(q.values())
assert [len(g['questions']) for g in groups] == [15, 4]
assert all('共同跳题（' not in g['design'] for g in groups)
assert groups[0]['questions'][1]['options'][0]['jump'] == '→ 跳至 DB004。'
assert not any(question['condition'] for question in groups[0]['questions'])
assert groups[0]['questions'][0]['options'][0]['jump'] == '→ 跳至 DB004。'
assert [x['id'] for x in groups[0]['questions'][:9]] == [f'DB{i:03d}' for i in range(1,10)]
assert [g['design_title'] for g in groups] == ['问卷设计', '问卷设计变化']
# Expected evidence is independently transcribed from official PDF pages.
# Do not reconstruct this record from the template or parser output.
record = json.loads((ROOT / 'tests/fixtures/charls_questionnaire_example_evidence.json').read_text(encoding='utf-8'))
assert not questionnaire_copy_errors({'questionnaire': q}, record)

# One shared introduction in each period satisfies its applicable questions.
# It remains an instruction in evidence, rather than part of every question.
shared_intro = '请按本期实际情况回答以下问题。'
shared_record = deepcopy(record)
shared_copy = deepcopy(q)
for period in shared_copy.values():
    period['design'] += '\n' + shared_intro
for item in shared_record['questionnaire_evidence']:
    item['display'] = {'question_text': item['question_text'], 'instructions': [shared_intro]}
assert not questionnaire_copy_errors({'questionnaire': shared_copy}, shared_record)
assert questionnaire_copy_errors({'questionnaire': q}, shared_record)

# Dropping a question from the template must not also drop it from expectations.
missing_help = deepcopy(q)
list(missing_help.values())[1]['questions'].pop(1)
assert questionnaire_copy_errors({'questionnaire': missing_help}, record)

# A later shared option must keep its own code, not inherit the first option's.
nonfirst = deepcopy(q)
list(nonfirst.values())[0]['questions'][1]['options'][0]['text'] = '4 无法完成'
nonfirst_record = deepcopy(record)
nonfirst_record['questionnaire_evidence'][1]['skip_logic'][0]['when'] = '4 无法完成'
assert not questionnaire_copy_errors({'questionnaire': nonfirst}, nonfirst_record)
assert questionnaire_copy_errors({'questionnaire': nonfirst}, record)

def rejected(action):
    try:
        result = action()
    except (ValueError, SystemExit):
        return
    assert result, 'Changed input unexpectedly passed'

mutations = [
    ('1 没有困难', '1 不确定'),
    ('DB001–DB009 的活动中都没有困难', 'DB009 没有困难'),
    ('跳至 DB016', '跳至 DB099'),
    ('穿衣服的时候是否有人帮助', '穿衣服的时候是否需要帮助'),
    ('- 2 没有', '- 2 不确定'),

    ('→ 跳至 DB004。', '→ 跳至 DB005。'),
    ('DB001–DB015 的选项设置', 'DB001–DB016 的选项设置'),
    ('DB001–DB015 的选项设置', 'DB001–DB014 的选项设置'),
    ('DB001–DB015 的选项设置', 'DB002–DB015 的选项设置'),
    ('2011 年', '2012 年'),
]
for old, new in mutations:
    changed = questionnaire.replace('`', '').replace(old, new, 1)
    rejected(lambda: questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(changed)}, record))

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    path = folder / '文案.md'
    path.write_text(document, encoding='utf-8')
    parsed = read_copy(path)
    assert parsed['criteria_intro'] == ''
    assert '② 2011' in parsed['criteria']['ADL_eating']['定义逻辑']
    assert parsed['references'] == ''
    (folder / 'definition_search_record.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    script = folder / 'render.R'
    script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root, "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(root, "scripts", "render_definition_bundle.R"), encoding="UTF-8")
copy <- read_definition_copy(c("ADL_eating", "ADL_count"))
stopifnot(length(copy$reference_lines) == 0)
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry, "#A33842"),
 criteria=copy$criteria, criteria_intro=paste(render_criteria_intro(copy$criteria_intro), collapse=""),
 insight="", references="", questionnaire=render_summary_selection_paragraph(copy$summary_selection, "#A33842"))
definition_copy_check(source=actual)
row <- vapply(names(copy$criteria), function(v) paste0('<tr><td>',v,'</td><td>',copy$criteria[[v]],'</td><td>distribution</td></tr>'), character(1))
definition <- definition_html_with_intro(c('<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',row,'</table>'), copy$criteria_intro)
writeLines(definition, "definition.html", useBytes=TRUE)
lines <- compose_definition_note_lines(c("## 摘要导读", actual$summary,actual$questionnaire),
 character(), definition, copy$reference_lines, "extract", "print(1)", character())
writeLines(lines,"note.md",useBytes=TRUE)
definition_copy_check(note="note.md")
''', encoding='utf-8')
    env = {**os.environ, 'PYTHONUTF8': '1', 'DBCODEBOOK_DEFINITION_PYTHON': sys.executable,
           'DBCODEBOOK_DEFINITION_SKILL_ROOT': str(ROOT)}
    for key in ('LANG', 'LC_ALL', 'LC_CTYPE'):
        env.pop(key, None)
    run = subprocess.run([os.environ['RSCRIPT'], '--vanilla', '--encoding=UTF-8', str(script)],
                         cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
    note = folder / 'note.md'
    rendered = note.read_text(encoding='utf-8')
    assert '## 参考资料说明' not in rendered
    assert rendered.count('data-criteria-intro="true"') == 0
    assert (folder / 'definition.html').read_text(encoding='utf-8').count('data-criteria-intro="true"') == 0
    assert rendered.count('data-summary-question-option="true"') == 17  # 2011: four shared answers + one jump; 2020: 4 + 2 + 4 + 2
    assert '→ 跳至 DB004。' in rendered
    assert '跳至 <code>DB004</code>' not in rendered
    assert '共同跳题（' not in rendered
    assert '的跳题规则与' not in rendered
    assert validate_note(path, note)['ok']
    assert validate_questionnaire_rendering(folder, folder, 'note.md')['rendered_question_periods'] == 19
    for old, new in mutations[:-1]:
        def markup(value):
            escaped = html.escape(value.removeprefix('- '), quote=False)
            if '选项' in old:
                return re.sub(r'DB\d{3}', lambda m: '<code>' + m[0] + '</code>', escaped)
            return escaped
        changed = rendered.replace(markup(old), markup(new), 1)
        assert changed != rendered, 'Mutation did not reach rendered text: ' + old
        note.write_text(changed, encoding='utf-8')
        try:
            validate_questionnaire_rendering(folder, folder, 'note.md')
        except (ValueError, SystemExit):
            pass
        else:
            raise AssertionError('Rendered mutation passed: ' + old)
    note.write_text(rendered.replace('两道步行题只要有困难回答，就不补零。', ''), encoding='utf-8')
    try:
        validate_note(path, note)
    except ValueError:
        pass
    else:
        raise AssertionError('Lost variable-specific imputation condition passed')

print('CURRENT_WRITING_CONTRACT_PASS: actual examples, scoped options/routes, common criteria, optional references, R rendering, negative mutations')
