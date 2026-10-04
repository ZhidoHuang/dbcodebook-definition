"""Legacy questionnaire input fixtures remain accepted by the parser."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import read_questionnaire_copy, questionnaire_text

rule = (ROOT / "tests/fixtures/writing-inputs/questionnaire-copy.md").read_text(encoding="utf-8")
example = next(block for block in re.findall(r"```markdown\n(.*?)\n```", rule, re.S)
               if "#### FA001" in block)
period = read_questionnaire_copy("### 2011年\n\n本期设计说明。\n\n" + example)["2011"]
question = period["questions"][0]
assert question["id"] == "FA001"
assert question["condition"] == "[符合原问卷进入条件的受访者回答本题]"
assert question["options"] == [{"text": "1 是", "jump": "→ 结束该主题"}, {"text": "2 否", "jump": ""}]
assert "（[符合原问卷进入条件的受访者回答本题]）" in questionnaire_text(period)
template = (ROOT / "tests/fixtures/writing-inputs/questionnaire-copy.md").read_text(encoding="utf-8")
period = read_questionnaire_copy(template)["2011"]
assert [q["id"] for q in period["questions"]] == ["Q001", "Q002"]
assert period["questions"][0]["options"][0]["jump"] == "→ 跳至 Q002"
assert period["questions"][1]["condition"]
print("QUESTIONNAIRE_INPUT_EXAMPLES_PASS: template examples parse with original question, conditions and jumps intact")
