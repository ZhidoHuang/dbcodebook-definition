"""Chinese display is checked independently from preserved source quotations."""
import copy
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors
from check_definition_readability import validate_questionnaire_rendering, SOURCE_RECORD_NAME
from test_reader_copy import rejects

question = "现在请说出您能够回忆起来的词语。"
instruction = "访员记录正确词数，最多等待2分钟。"
record = {"schema_version": 6, "questionnaire_display_policy": "chinese_v1", "questionnaire_evidence": [{
    "question_id": "Q01", "question_text": "Please recall the words. INTERVIEWER: Wait up to 2 minutes.",
    "periods": ["Wave 1", "Wave 2"], "response_type": "open_value", "options": [], "skip_logic": [],
    "rendered_in_copy": True, "copy_locator": "问卷 / Wave 1–2 / Q01",
    "display": {"question_text": question, "instructions": [instruction]},
}]}
text = f"### Wave 1–2\n本人认知测验。{instruction}\n\n#### Q01\n{question}\n"
content = {"questionnaire": read_questionnaire_copy(text)}
assert questionnaire_copy_errors(content, record) == []
original = copy.deepcopy(record)
assert questionnaire_copy_errors({"questionnaire": read_questionnaire_copy(text.replace(instruction, ""))}, record)
assert questionnaire_copy_errors({"questionnaire": read_questionnaire_copy(text.replace(question, "概括题意。"))}, record)
missing = copy.deepcopy(record)
missing["questionnaire_evidence"][0].pop("display")
assert questionnaire_copy_errors(content, missing)
english = copy.deepcopy(record)
english["questionnaire_evidence"][0]["display"]["question_text"] = "Please recall the words."
assert questionnaire_copy_errors(content, english)
with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    (folder / SOURCE_RECORD_NAME).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    markup = ('<section class="raw-source-period" data-raw-source-period="Wave 1–2" data-label="Wave 1–2">'
              '<div data-summary-period-note="true"><strong data-summary-period-note-title="true">问卷设计</strong>'
              f'本人认知测验。{instruction}</div><div data-summary-questionnaire-line="true">'
              f'<strong data-summary-question-id="true">Q01</strong>{question}</div></section>')
    note = folder / "note.md"
    note.write_text(markup, encoding="utf-8")
    assert validate_questionnaire_rendering(folder, folder, note.name)["rendered_question_periods"] == 2
    note.write_text(markup.replace(instruction, ""), encoding="utf-8")
    rejects(lambda: validate_questionnaire_rendering(folder, folder, note.name), "omits display instruction")
    note.write_text(markup.replace(question, "中文概括。"), encoding="utf-8")
    rejects(lambda: validate_questionnaire_rendering(folder, folder, note.name), "complete text")
assert record == original  # No comparator rewrites the original evidence.

# Evidence lists may be stored by variable rather than questionnaire order.
# Explicit next-question display metadata must match both copy and final HTML.
sequential = copy.deepcopy(record)
sequential['questionnaire_evidence'] = []
for identifier in ['Q01', 'Q03', 'Q02']:
    sequential['questionnaire_evidence'].append({
        'question_id': identifier, 'periods': ['Wave 1'], 'question_text': 'Original question',
        'response_type': 'open_value', 'options': [], 'skip_logic': [],
        'rendered_in_copy': True, 'copy_locator': '问卷 / Wave 1 / ' + identifier,
        'display': {'question_text': '请回答' + identifier + '的问题。', 'instructions': []}})
first = sequential['questionnaire_evidence'][0]
first['skip_logic'] = [{'when': '回答本题后', 'destination': 'Q02'}]
first['display'].update(next_question='Q02', skip_logic=[{
    'source_index': 0, 'when': '回答本题后', 'destination': '跳至 Q02', 'presentation': 'sequence'}])
sequence_copy = '### Wave 1\n问卷设计：按原问卷顺序回答。\n\n' + '\n\n'.join(
    '#### ' + identifier + '\n请回答' + identifier + '的问题。' for identifier in ['Q01', 'Q02', 'Q03'])
snapshot = copy.deepcopy(sequential)
assert not questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(sequence_copy)}, sequential)
reordered = sequence_copy.replace('#### Q02', '#### TEMP').replace('#### Q03', '#### Q02').replace('#### TEMP', '#### Q03')
rejects(lambda: questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(reordered)}, sequential), 'next displayed')
with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    (folder / SOURCE_RECORD_NAME).write_text(json.dumps(sequential, ensure_ascii=False), encoding='utf-8')
    bodies = ['<div data-summary-questionnaire-line="true"><strong data-summary-question-id="true">' + identifier
              + '</strong>请回答' + identifier + '的问题。</div>' for identifier in ['Q01', 'Q02', 'Q03']]
    markup = '<section class="raw-source-period" data-raw-source-period="Wave 1" data-label="Wave 1"><div data-summary-period-note="true"><strong data-summary-period-note-title="true">问卷设计</strong>按原问卷顺序回答。</div>' + ''.join(bodies) + '</section>'
    (folder / 'note.md').write_text(markup, encoding='utf-8')
    assert validate_questionnaire_rendering(folder, folder, 'note.md')['rendered_question_periods'] == 3
    (folder / 'note.md').write_text(markup.replace(''.join(bodies), bodies[0] + bodies[2] + bodies[1]), encoding='utf-8')
    rejects(lambda: validate_questionnaire_rendering(folder, folder, 'note.md'), 'next displayed')
assert sequential == snapshot
bad = copy.deepcopy(sequential)
bad['questionnaire_evidence'][0]['display']['skip_logic'][0]['destination'] = '跳至 Q03'
assert questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(sequence_copy)}, bad)

# Pure-letter identifiers must obey the same period, group and adjacency checks.
letter_record = json.loads(json.dumps(sequential).replace('Q01', 'HESKD').replace('Q02', 'HESKE').replace('Q03', 'HESKF'))
letter_copy = sequence_copy.replace('Q01', 'HESKD').replace('Q02', 'HESKE').replace('Q03', 'HESKF')
letter_snapshot = copy.deepcopy(letter_record)
assert not questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(letter_copy)}, letter_record)
for destination in ['跳至 HESKF', '跳至 HESKE_EXTRA', '跳至 HESKE 或 HESKF', '结束 HESKE']:
    wrong = copy.deepcopy(letter_record)
    wrong['questionnaire_evidence'][0]['display']['skip_logic'][0]['destination'] = destination
    assert questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(letter_copy)}, wrong)
for field, value in [('periods', ['Wave 2']), ('questionnaire_module', '另一题组')]:
    wrong = copy.deepcopy(letter_record)
    wrong['questionnaire_evidence'][2][field] = value
    assert questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(letter_copy)}, wrong)
letter_reordered = letter_copy.replace('#### HESKE', '#### TEMP').replace('#### HESKF', '#### HESKE').replace('#### TEMP', '#### HESKF')
rejects(lambda: questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(letter_reordered)}, letter_record), 'next displayed')
with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    (folder / SOURCE_RECORD_NAME).write_text(json.dumps(letter_record, ensure_ascii=False), encoding='utf-8')
    letter_markup = markup.replace('Q01', 'HESKD').replace('Q02', 'HESKE').replace('Q03', 'HESKF')
    (folder / 'note.md').write_text(letter_markup, encoding='utf-8')
    assert validate_questionnaire_rendering(folder, folder, 'note.md')['rendered_question_periods'] == 3
    (folder / 'note.md').write_text(letter_markup.replace('>HESKE<', '>TEMP<').replace('>HESKF<', '>HESKE<').replace('>TEMP<', '>HESKF<'), encoding='utf-8')
    rejects(lambda: validate_questionnaire_rendering(folder, folder, 'note.md'), 'next displayed')
assert letter_record == letter_snapshot
print("QUESTIONNAIRE_DISPLAY_PASS: Chinese display, instructions, grouped periods, source preservation")
