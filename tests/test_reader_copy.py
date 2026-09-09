from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import compare_content, read_copy, validate_note, require_equal, criteria_fields


def rejects(action, reason):
    try:
        action()
    except ValueError as error:
        assert reason in str(error), str(error)
    else:
        raise AssertionError(f"Expected rejection: {reason}")


def render_note(content):
    rows = []
    for variable, fields in content["criteria"].items():
        body = "".join(
            f'<div data-criteria-heading="true">{name}</div>'
            + "".join(f'<div data-criteria-item="true">{line}</div>' for line in text.splitlines())
            for name, text in fields.items()
        )
        rows.append(f'<tr><td class="plain-cell">{variable}</td><td>{body}</td><td>distribution</td></tr>')
    insight = (f'<div data-summary-insight-body="true">{content["insight"]}</div>' if content["insight"] else "")
    return (f'## 摘要导读\n{content["summary"]}\n<div class="raw-source-structure">questionnaire</div>\n'
            f'{insight}\n## 定义\n<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>'
            + "".join(rows) + f'</table>\n## 参考资料说明\n{content["references"]}\n## 材料\n')


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        path = folder / "文案.md"
        original = (ROOT / "templates" / "reader-copy.md").read_text(encoding="utf-8")
        path.write_text(original, encoding="utf-8")
        content = read_copy(path, ["fall_status", "fall_count"])
        assert "注意点" not in content["criteria"]["fall_status"]
        assert not content["insight"]
        assert compare_content(content, copy.deepcopy(content))["ok"]
        note = folder / "note.md"
        note.write_text(render_note(content), encoding="utf-8")
        assert validate_note(path, note)["ok"]

        # Correct formatting differences pass, while actual content loss fails.
        styled = copy.deepcopy(content)
        styled["summary"] = styled["summary"].replace("**是否发生跌倒**", "<strong>是否发生跌倒</strong>")
        assert compare_content(content, styled, source=True)["ok"]
        rejects(lambda: require_equal("`x<a`", "`x<b`", "comparison"), "comparison")
        rejects(lambda: criteria_fields('<div data-criteria-heading="true">定义</div><div data-criteria-item="true">description</div><p>缺失全部记为零</p>'), "未归入栏目")
        for field in ("summary", "references"):
            bad = copy.deepcopy(content)
            bad[field] = ""
            rejects(lambda: compare_content(content, bad), field)
        bad = copy.deepcopy(content)
        bad["insight"] = "Extra summary invented in R."
        rejects(lambda: compare_content(content, bad), "insight")
        for field in ("定义", "定义逻辑", "分类"):
            bad = copy.deepcopy(content)
            del bad["criteria"]["fall_status"][field]
            note.write_text(render_note(bad), encoding="utf-8")
            rejects(lambda: validate_note(path, note), "栏目丢失")
        bad = copy.deepcopy(content)
        bad["criteria"]["fall_status"]["分类"] = "- [1] 否\n- [0] 是"
        rejects(lambda: compare_content(content, bad), "分类")
        rejects(lambda: read_copy(path, ["fall_count", "fall_status"]), "顺序")
        for field in ("定义", "定义逻辑", "分类"):
            path.write_text(original.replace(f"#### {field}\n", "", 1), encoding="utf-8")
            rejects(lambda: read_copy(path), field)
        path.write_text(original.replace("### fall_count", "#### 注意点\n\n此变量不能表示伤害严重程度。\n\n### fall_count"), encoding="utf-8")
        with_note = read_copy(path)
        assert "注意点" in with_note["criteria"]["fall_status"]
        bad = copy.deepcopy(with_note)
        del bad["criteria"]["fall_status"]["注意点"]
        rejects(lambda: compare_content(with_note, bad), "栏目丢失")

        path.write_text(original.replace("① 回答“是”记为[1]，回答“否”记为[0]。", "① 当`raw_a[1]<a`时保留缺失。"), encoding="utf-8")
        rscript = os.environ.get("RSCRIPT")
        if not rscript:
            raise RuntimeError("RSCRIPT is required for the real reader-loader forward test")
        script = folder / "forward.R"
        script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root, "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(root, "scripts", "render_definition_bundle.R"), encoding="UTF-8")
copy <- read_definition_copy(c("fall_status", "fall_count"))
stopifnot(grepl("<code>raw_a[1]&lt;a</code>", copy$criteria$fall_status, fixed=TRUE))
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry, "#A33842"),
               criteria=copy$criteria, insight="", references=tail(copy$reference_lines, 1))
definition_copy_check(source=actual)
bad <- actual
bad$criteria$fall_status <- criteria_block(criteria_heading("定义"), criteria_item("only one field"))
failed <- tryCatch({definition_copy_check(source=bad); FALSE}, error=function(e) TRUE)
stopifnot(failed)
failed <- tryCatch({render_definition_bundle(analysis_vars=c("fall_status", "fall_count"),
  criteria=bad$criteria, summary_entry=copy$summary_entry, summary_insight_items=NULL,
  reference_lines=copy$reference_lines); FALSE}, error=function(e) grepl("Criteria", conditionMessage(e)))
stopifnot(failed)
rows <- vapply(names(copy$criteria), function(v) paste0('<tr><td class="plain-cell">',v,
 '</td><td>',copy$criteria[[v]],'</td><td>distribution</td></tr>'), character(1))
text <- c("## 摘要导读", actual$summary,
 '<div class="raw-source-structure">questionnaire</div>', "## 定义",
 '<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>', rows, '</table>',
 copy$reference_lines, "## 材料")
writeLines(text, "note.md", useBytes=TRUE)
definition_copy_check(note="note.md")
cat("R_COPY_FORWARD_PASS\\n")
''', encoding="utf-8")
        env = {**os.environ, "DBCODEBOOK_DEFINITION_SKILL_ROOT": str(ROOT),
               "DBCODEBOOK_DEFINITION_PYTHON": sys.executable}
        for key in ("LANG", "LC_ALL", "LC_CTYPE"):
            env.pop(key, None)
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(script)], cwd=folder,
                             env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert "R_COPY_FORWARD_PASS" in run.stdout
        assert validate_note(path, note)["ok"]
        questionnaire_copy = (ROOT / "templates/questionnaire-copy.md").read_text(encoding="utf-8")
        path.write_text(original + "\n\n" + questionnaire_copy, encoding="utf-8")
        questionnaire_script = folder / "questionnaire.R"
        questionnaire_script.write_text('''
root <- Sys.getenv("DBCODEBOOK_DEFINITION_SKILL_ROOT")
source(file.path(root, "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(root, "scripts", "render_definition_bundle.R"), encoding="UTF-8")
copy <- read_definition_copy(c("fall_status", "fall_count"))
actual <- list(summary=render_summary_entry_paragraph(copy$summary_entry, "#A33842"),
  criteria=copy$criteria, insight="", references=tail(copy$reference_lines, 1),
  questionnaire=render_summary_selection_paragraph(copy$summary_selection, "#A33842"))
definition_copy_check(source=actual)
rows <- vapply(names(copy$criteria), function(v) paste0('<tr><td>',v,
 '</td><td>',copy$criteria[[v]],'</td><td>distribution</td></tr>'), character(1))
writeLines(c("## 摘要导读",actual$summary,actual$questionnaire,"## 定义",
 '<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>',rows,'</table>',
 copy$reference_lines,"## 材料"),"questionnaire_note.md",useBytes=TRUE)
definition_copy_check(note="questionnaire_note.md")
cat("QUESTIONNAIRE_COPY_FORWARD_PASS\\n")
''', encoding="utf-8")
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(questionnaire_script)],
                             cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert "QUESTIONNAIRE_COPY_FORWARD_PASS" in run.stdout
        generated = folder / "questionnaire_note.md"
        assert validate_note(path, generated)["ok"]
        generated.write_text(generated.read_text(encoding="utf-8").replace("跳至 Q002", "跳至 Q999"), encoding="utf-8")
        rejects(lambda: validate_note(path, generated), "原始问卷")
    print("READER_COPY_TESTS_PASS: copy, actual R inputs, rendered output, optional notes, missing fields, extra insight, order, values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
