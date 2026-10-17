"""MHAS dotted identifiers retain shared options and distinct option routes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_reader_copy import read_questionnaire_copy
from questionnaire_groups import referenced_options, validate_shared_option_rows

text = """### 日常生活活动

#### 2001、2003 年

##### 问卷设计

本人回答。

##### H.1

步行有困难吗？

- 1 是
- 2 否

H.2、H.3 的选项与 H.1 相同。

##### H.2

跑步有困难吗？

- 2 否 → 跳至 H.4。

##### H.3

站立有困难吗？
"""
block = next(iter(read_questionnaire_copy(text).values()))
qs = block["questions"]
entries = [(q["id"], [o["text"] for o in q["options"]], "\n".join(q["instructions"])) for q in qs]
assert referenced_options("", "H.3", entries) == ["1 是", "2 否"]
validate_shared_option_rows(referenced_options("", "H.2", entries), qs[1]["options"])
assert qs[2]["options"] == []
try:
    validate_shared_option_rows(["1 是", "2 否"], [{"text":"6 不能做", "jump":"H.4"}])
except ValueError:
    pass
else:
    raise AssertionError("unlisted option was accepted")
print("MHAS dotted shared options and route distinction PASS")
