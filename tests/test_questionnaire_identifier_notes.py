"""Short headings with visible period mappings keep evidence checks intact."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors, Document
from check_definition_readability import validate_questionnaire_rendering
from questionnaire_groups import original_options
from test_questionnaire_year_aliases import check

TEXT = '''## 问卷
### 活动
#### Wave 1–4
##### 问卷设计
两题依次询问活动情况。
Wave 3–4 的选项编码为 01=是、02=否；其余时期为 1=是、2=否。
##### C103
是否参加过活动？
原问卷变量名题号：Wave 1–2 C103；Wave 3–4 C203。
- 是
- 否
##### C104
是否参加过另一种活动？
原问卷变量名题号：Wave 1–2 C104；Wave 3–4 C204。
- 是
- 否
'''
RECORD = {'schema_version': 6, 'questionnaire_display_policy': 'chinese_v1',
          'questionnaire_evidence': []}
for wave in range(1, 5):
    for index, stem in enumerate(('是否参加过活动？', '是否参加过另一种活动？')):
        identifier = ('C10' if wave <= 2 else 'C20') + str(3 + index)
        codes = ['1', '2'] if wave <= 2 else ['01', '02']
        RECORD['questionnaire_evidence'].append({
            'question_id': identifier, 'periods': [f'Wave {wave}'],
            'question_text': stem, 'response_type': 'closed_options',
            'options': [{'value': code, 'label': label} for code, label in zip(codes, ['是', '否'])],
            'skip_logic': [], 'rendered_in_copy': True,
            'copy_locator': f'文案.md > 活动 > Wave {wave} > {identifier}',
            'display': {'question_text': stem, 'instructions': []}})

check(TEXT, RECORD)
parsed = read_questionnaire_copy(TEXT)
assert [q['id'] for q in next(iter(parsed.values()))['questions']] == ['C103', 'C104']
assert not questionnaire_copy_errors({'questionnaire': parsed}, RECORD)
# Checking must not replace the author's short headings in the shared object.
assert [q['id'] for q in next(iter(parsed.values()))['questions']] == ['C103', 'C104']
for old, new in [
    ('Wave 3–4 C203', 'Wave 3–4 C299'),
    ('Wave 3–4 C203', 'Wave 2–4 C203'),
    ('Wave 3–4 C203', 'Wave 3–5 C203'),
    ('Wave 3–4 C203', 'Wave 3 C203'),
    ('##### C103', '##### C999'),
    ('原问卷变量名题号：Wave 1–2 C103；Wave 3–4 C203。', ''),
    ('01=是、02=否', '01=是、03=否'),
    ('其余时期为 1=是、2=否', '其余时期为 2=是、1=否'),
]:
    check(TEXT.replace(old, new), RECORD, good=False)

# Normal sequence uses the target's identifier for that period.
sequence = copy.deepcopy(RECORD)
for item in sequence['questionnaire_evidence'][::2]:
    destination = 'C104' if int(item['periods'][0].split()[-1]) <= 2 else 'C204'
    item['skip_logic'] = [{'when': item['options'][0]['value'] + ' 是', 'destination': destination}]
    item['display']['skip_logic'] = [{'source_index': 0, 'when': item['options'][0]['value'] + ' 是',
        'destination': '跳至 ' + destination, 'presentation': 'sequence'}]
    item['display']['next_question'] = destination
check(TEXT, sequence)
shared = TEXT.replace('- 是\n- 否\n##### C104', '- 是\n- 否\nC103–C104 的选项设置相同，后续题目仅列有跳转的选项。\n##### C104')
shared = shared.rsplit('- 是\n- 否\n', 1)[0]
check(shared, RECORD)

# New reader copy shows only data variables; original IDs stay in evidence.
TEXT = TEXT.replace('原问卷变量名题号：Wave 1–2 C103；Wave 3–4 C203。',
    '各个时期的变量名：Wave 1–4，变量名有规律，使用 `w01`～`w04C103`。')
TEXT = TEXT.replace('原问卷变量名题号：Wave 1–2 C104；Wave 3–4 C204。',
    '各个时期的变量名：Wave 1–4，变量名有规律，使用 `w01`～`w04C104`。')
for index, item in enumerate(RECORD['questionnaire_evidence']):
    item['evidence_id'] = 'e' + str(index)
    item['display']['question_title'] = 'C10' + str(3 + index % 2)
    item['display']['question_title_source'] = 'e' + str(index % 2)
check(TEXT, RECORD)
for mutate in [
    lambda q: q['display'].update(question_title_source='absent'),
    lambda q: q['display'].update(question_title='C999'),
    lambda q: q.update(questionnaire_module='wrong group'),
    lambda q: q['display'].update(question_text='另一道题'),
    lambda q: q['options'][0].update(value='7'),
]:
    bad = copy.deepcopy(RECORD)
    mutate(bad['questionnaire_evidence'][-2])
    check(TEXT, bad, good=False)
check(TEXT.replace('##### C103', '##### C999'), RECORD, good=False)
bad = copy.deepcopy(RECORD)
bad['questionnaire_evidence'][0]['display']['question_title_source'] = 'e2'
check(TEXT, bad, good=False)

modern_sequence = copy.deepcopy(RECORD)
for item in modern_sequence['questionnaire_evidence'][::2]:
    wave = int(item['periods'][0].split()[-1])
    destination = 'C104' if wave <= 2 else 'C204'
    item['skip_logic'] = [{'when': item['options'][0]['value'] + ' 是', 'destination': destination}]
    item['display']['skip_logic'] = [{'source_index': 0, 'when': item['options'][0]['value'] + ' 是',
        'destination': '跳至 ' + destination, 'presentation': 'sequence'}]
    item['display']['next_question'] = destination
check(TEXT, modern_sequence)
check(TEXT.replace('##### C104', '##### C999'), modern_sequence, good=False)

# Read the current public template, rather than copying its syntax into a test.
template = (ROOT / 'templates/reader-copy.md').read_text(encoding='utf-8')
sample = re.search(r'```markdown\n(.*?)\n```', template[template.index('**多期相同问卷的展示格式**'):], re.S)[1]
group = next(iter(read_questionnaire_copy(sample).values()))
for wave in range(1, 12):
    assert original_options(['Yes', 'No'], group['design'], f'Wave {wave}') == (
        ['1 Yes', '2 No'] if wave <= 5 else ['01 Yes', '02 No'])

with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    doc = '# TEST — 活动（Activity）\n\n## 摘要导读\n\n本主题定义“**活动**”，共 **1** 个变量。\n\n' + TEXT
    doc += '\n## Criteria\n### X\n#### 定义\n活动。\n#### 定义逻辑\n保留回答。\n#### 分类\n- [0] 否\n- [1] 是\n'
    doc += '\n## 小book提示\n\n本主题没有需要单独提示的主题级边界\n'
    (folder / '文案.md').write_text(doc, encoding='utf-8')
    (folder / 'definition_search_record.json').write_text(json.dumps(RECORD, ensure_ascii=False), encoding='utf-8')
    script = folder / 'render.R'
    script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root, "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(root, "scripts", "render_definition_bundle.R"), encoding="UTF-8")
copy <- read_definition_copy("X")
writeLines(render_summary_selection_paragraph(copy$summary_selection, "#A33842"), "note.md", useBytes=TRUE)
''', encoding='utf-8')
    env = {**os.environ, 'PYTHONUTF8': '1', 'DBCODEBOOK_DEFINITION_PYTHON': sys.executable,
           'DBCODEBOOK_DEFINITION_SKILL_ROOT': str(ROOT)}
    for key in ('LANG', 'LC_ALL', 'LC_CTYPE'):
        env.pop(key, None)
    result = subprocess.run([os.environ['RSCRIPT'], '--vanilla', '--encoding=UTF-8', str(script)],
                            cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    rendered = (folder / 'note.md').read_text(encoding='utf-8')
    headings = list(Document(rendered).root.find(lambda e: e.attrs.get('data-summary-question-id') == 'true'))
    assert [h.text() for h in headings] == ['C103', 'C104']
    assert rendered.index('是否参加过活动？') < rendered.index('各个时期的变量名：') < rendered.index('data-summary-question-option')
    assert validate_questionnaire_rendering(folder, folder, 'note.md')['rendered_question_periods'] == 8
    (folder / 'note.md').write_text(rendered.replace('>C103</', '>C999</'), encoding='utf-8')
    try:
        validate_questionnaire_rendering(folder, folder, 'note.md')
    except (SystemExit, ValueError):
        pass
    else:
        raise AssertionError('Rendered identifier-note corruption accepted')
print('QUESTIONNAIRE_IDENTIFIER_NOTES_PASS: short headings, remainder coding, period evidence and actual R rendering')
