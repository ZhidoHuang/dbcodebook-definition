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
    "rendered_in_copy": True, "copy_locator": "原始问卷 / Wave 1–2 / Q01",
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
print("QUESTIONNAIRE_DISPLAY_PASS: Chinese display, instructions, grouped periods, source preservation")
