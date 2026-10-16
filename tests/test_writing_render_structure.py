"""Render real copy inputs and verify list items and table cell boundaries."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import (Document, criteria_blocks, criteria_comparable,
                               insight_items, read_copy, validate_note)


def rejects(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Invalid generated structure passed")


assert insight_items("第一项。\n同一条续行。\n\n第二项。") == ["第一项。\n同一条续行。", "第二项。"]
assert insight_items("① 第一项。\n② 第二项。") == ["第一项。", "第二项。"]
assert insight_items("1.5% 的记录。") == ["1.5% 的记录。"]
assert criteria_blocks("| a | b |\n| --- | :---: |\n| `x|y` | a\\|b |")[0]["rows"] == [["`x|y`", "a|b"]]
rejects(lambda: criteria_blocks("| a | b |\n| --- | --- |\n| only one |"))
assert criteria_comparable("| a | b |\n| --- | --- |\n| ab | c |") != criteria_comparable(
    "| a | b |\n| --- | --- |\n| a | bc |")

base = """# 示例 — 行动能力（Mobility）

## 摘要导读

本主题定义“**是否需要帮助**”，共 **1** 个变量。

## Criteria

### Mob_help

#### 定义

完成活动是否需要他人帮助。

#### 定义逻辑

① 保留当期回答，来源如下。

| 波次 | 数据变量 | 备注 |
| --- | :---: | ---: |
| Wave 1 | `w01C205` | 原值 [1] |
| Wave 2 | `w02C205` | A\\|B |

② 条件公式为 `x<y`；按已定条件赋值。

| 条件 | 结果 |
| --- | --- |
| `x|y` | [1] |

#### 分类

- [0] 否
- [1] 是

## 小book提示

{insight}
"""

insights = ["结果采用人—年长格式。\n同一条的续行。\n\n各期为追踪调查。",
            "1. 结果采用人—年长格式。\n同一条的续行。\n2. 各期为追踪调查。",
            "7. 结果采用人—年长格式。\n同一条的续行。\n9. 各期为追踪调查。",
            "① 结果采用人—年长格式。\n同一条的续行。\n② 各期为追踪调查。",
            "1.5% 是本条文字。"]

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    paths = []
    for i, insight in enumerate(insights):
        path = folder / f"copy{i}.md"
        path.write_text(base.replace("{insight}", insight), encoding="utf-8")
        paths.append(str(path))
        parsed = read_copy(path)
        tables = [b for b in parsed["criteria_blocks"]["Mob_help"]["定义逻辑"] if b["type"] == "table"]
        assert len(tables) == 2 and tables[0]["align"] == ["left", "center", "right"]
    (folder / "paths.json").write_text(json.dumps(paths), encoding="utf-8")
    script = folder / "render.R"
    script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root, "scripts/summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(root, "scripts/render_definition_bundle.R"), encoding="UTF-8")
paths <- jsonlite::read_json("paths.json")
for (path in paths) {
  copy <- read_definition_copy("Mob_help", path)
  for (variant in c("standard", "compact")) {
    insight <- paste(render_summary_insight_card(copy$summary_insight_items, "#A33842", variant), collapse="\\n")
    actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry, "#A33842"),
                   criteria=copy$criteria, insight=insight, references="")
    definition_copy_check(path, source=actual)
    definition <- c('<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',
      paste0('<tr><td>Mob_help</td><td>',copy$criteria[[1]],'</td><td>distribution</td></tr>'), '</table>')
    note <- paste0(path, ".", variant, ".note.md")
    lines <- compose_definition_note_lines(c("## 摘要导读", actual$summary, insight),
      character(), definition, character(), "extract", "print(1)", character())
    writeLines(lines, note, useBytes=TRUE)
    definition_copy_check(path, note=note)
  }
}
''', encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1", "DBCODEBOOK_DEFINITION_PYTHON": sys.executable,
           "DBCODEBOOK_DEFINITION_SKILL_ROOT": str(ROOT)}
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        env.pop(key, None)
    run = subprocess.run([os.environ["RSCRIPT"], "--vanilla", "--encoding=UTF-8", str(script)],
                         cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    for path in paths:
        for variant in ("standard", "compact"):
            note = Path(path + f".{variant}.note.md")
            rendered = note.read_text(encoding="utf-8")
            assert validate_note(path, note)["ok"]
            root = Document(rendered).root
            tables = list(root.find(lambda e: e.attrs.get("data-criteria-table") == "true"))
            assert len(tables) == 2
            assert len(list(tables[0].find(lambda e: e.tag == "td"))) == 6
            assert "<code>w01C205</code>" in rendered and "<code>x|y</code>" in rendered
            assert "<code>x&lt;y</code>" in rendered and "text-align:center" in rendered
            markers = list(root.find(lambda e: e.attrs.get("class") == "summary-insight-number"))
            assert [m.text() for m in markers] == [f"{i}." for i in range(1, len(insight_items(read_copy(path)["insight"])) + 1)]
            for changed in [rendered.replace("w02C205", "w09C205"),
                            re.sub(r'<span class="summary-insight-number"[^>]*>1\.</span>', "", rendered, count=1),
                            rendered.replace('>1.</span>', '>2.</span>', 1),
                            rendered.replace('>A|B</td>', '>AB</td>', 1),
                            rendered.replace('</tbody>', '<tr><td>多余内容</td></tr></tbody>', 1),
                            rendered.replace('<thead>', '<thead>表格外文字', 1),
                            rendered.replace('text-indent:0;display:flex', 'text-indent:0;display:block', 1)]:
                assert changed != rendered
                note.write_text(changed, encoding="utf-8")
                rejects(lambda: validate_note(path, note))
            note.write_text(rendered, encoding="utf-8")

print("WRITING_RENDER_STRUCTURE_PASS: actual R tables, cell boundaries, inline code, automatic numbering, wrapping, both variants and mutations")
