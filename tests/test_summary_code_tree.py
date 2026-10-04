"""Exercise Markdown trees through the real loader, rendering and final-note check."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import summary_blocks, read_copy, compare_content, validate_note


def rejects(action, phrase):
    try:
        action()
    except ValueError as error:
        assert phrase in str(error), str(error)
    else:
        raise AssertionError(phrase)


tree = "total\n    ├── group_a\n    │   └── item_x < item_y\n    └── group_b"
rejects(lambda: summary_blocks("```text\nmissing close"), "结束围栏")
rejects(lambda: summary_blocks("```\n\n```"), "不能为空")
rejects(lambda: summary_blocks("```python\nx\n```"), "无语言或 text")
fenced = "```text\n" + tree + "\n```"
indented = "\n".join("    " + line for line in tree.splitlines())
assert summary_blocks(fenced) == summary_blocks(indented)

with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    original = (ROOT / "tests/fixtures/writing-inputs/reader-copy.md").read_text(encoding="utf-8")
    script = folder / "forward.R"
    script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root,"scripts","summary_fact_helpers.R"),encoding="UTF-8")
source(file.path(root,"scripts","render_definition_bundle.R"),encoding="UTF-8")
copy <- read_definition_copy(c("fall_status","fall_count"))
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry,"#A33842"),
 criteria=copy$criteria,insight="",references=tail(copy$reference_lines,1))
definition_copy_check(source=actual)
jsonlite::write_json(actual,"actual.json",auto_unbox=TRUE)
rows <- vapply(names(copy$criteria),function(v) paste0('<tr><td>',v,'</td><td>',
 copy$criteria[[v]],'</td><td>distribution</td></tr>'),character(1))
writeLines(c("## 摘要导读",actual$summary,"## 定义",
 '<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',rows,'</table>',
 copy$reference_lines,"## 材料"),"note.md",useBytes=TRUE)
definition_copy_check(note="note.md")
''', encoding="utf-8")
    env = {**os.environ, "DBCODEBOOK_DEFINITION_SKILL_ROOT": str(ROOT), "DBCODEBOOK_DEFINITION_PYTHON": sys.executable}
    for name in ("LANG", "LC_ALL", "LC_CTYPE"):
        env.pop(name, None)
    for block in (fenced, indented):
        path = folder / "文案.md"
        path.write_text(original.replace("## Criteria", block + "\n\n## Criteria"), encoding="utf-8")
        result = subprocess.run([os.environ["RSCRIPT"], "--vanilla", "--encoding=UTF-8", str(script)],
                                cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
        actual = json.loads((folder / "actual.json").read_text(encoding="utf-8"))
        content = read_copy(path)
        assert "white-space:pre;" in actual["summary"] and "font-family:monospace" in actual["summary"]
        assert "item_x &lt; item_y" in actual["summary"]
        for old, new in (("    ├", "├"), ("\n    └", "    └"), ("group_b", "group_c")):
            bad = copy.deepcopy(actual)
            bad["summary"] = bad["summary"].replace(old, new)
            rejects(lambda: compare_content(content, bad, source=True), "代码树")
        note = folder / "note.md"
        note.write_text(note.read_text(encoding="utf-8").replace("    ├", "├"), encoding="utf-8")
        rejects(lambda: validate_note(path, note), "代码树")
print("SUMMARY_CODE_TREE_PASS: real R, fenced/indented, escaping, missing node/newline/indent rejected")
