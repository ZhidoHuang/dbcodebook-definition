from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_reader_copy import compare_content, read_copy, validate_note, require_equal, criteria_fields, read_questionnaire_copy, sections


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
    summary = re.sub(r'\*\*(.*?)\*\*', r'<span data-summary-concept="true">\1</span>', content["summary"])
    return (f'## 摘要导读\n{summary}\n<div class="raw-source-structure">questionnaire</div>\n'
            f'{insight}\n## 定义\n<table><tr><th>Definition</th><th>Criteria</th><th>detail</th></tr>'
            + "".join(rows) + f'</table>\n## 参考资料说明\n{content["references"]}\n## 材料\n')


def main():
    from check_reader_copy import format_category_label, format_copy_categories
    assert format_category_label("  less   than 1 ") == "Less than 1"
    assert format_category_label("with COPD") == "With COPD"
    assert format_category_label("  McDonald ") == "McDonald"
    fields = {"A": {"分类": "- [less than 1]：少于一次\n- [About usual]：照常"}}
    tree_source = "[[result:A|类别]] [[meta:（少于一次／照常）]]"
    assert format_copy_categories(fields, tree_source) == tree_source
    assert "[Less than 1]" in fields["A"]["分类"]
    binary = "[[result:A|类别]] [[meta:（0/1）]]"
    assert format_copy_categories(fields, binary) == binary
    rejects(lambda: format_copy_categories({"A": {"分类": "- [one]\n- [One]"}}, ""), "重名")
    rscript_categories = os.environ.get("RSCRIPT")
    if rscript_categories:
        template = (ROOT / "templates" / "public-r-dictionary.R").read_text(encoding="utf-8")
        function = template[template.index("format_category_values <-"):template.index("for (variable in analysis_vars)")]
        probe = function + '''
stopifnot(identical(format_category_values(c(" less   than 1 ", "with COPD", NA_character_)),
                    c("Less than 1", "With COPD", NA_character_)))
x <- ordered(c("low", NA), levels=c("low", "high"))
y <- format_category_values(x)
stopifnot(is.ordered(y), identical(levels(y), c("Low", "High")), is.na(y[2]))
stopifnot(inherits(try(format_category_values(c("one", "One")), silent=TRUE), "try-error"))
stopifnot(identical(format_category_values(c(NA_character_)), NA_character_))
'''
        run = subprocess.run([rscript_categories, "--vanilla", "-"], input=probe, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
    fenced = "## 摘要导读\n```text 示例\n## 同名\n## 同名\n```\n## 材料\n```r\n## 同名\n## 同名\n```\n"
    parsed = sections(fenced, 2)
    assert list(parsed) == ["摘要导读", "材料"] and "## 同名" in parsed["摘要导读"]
    assert sections(fenced.replace("```", "~~~~"), 2) == {k:v.replace("```","~~~~") for k,v in parsed.items()}
    rejects(lambda: sections("## 正文\na\n## 正文\nb", 2), "文案重复栏目")
    base_questionnaire = "### 2011 年\n\n询问当前健康。\n\n#### DA001\n\n您的健康怎么样？\n\n- 1 好\n"
    expected = read_questionnaire_copy(base_questionnaire)
    mapping_note = "各个时期的变量名：2004 年 `JD111`；2006 年 `KD111`。"
    noted = read_questionnaire_copy(base_questionnaire + "\n" + mapping_note + "\n")["2011"]["questions"][0]
    assert noted["text"] == "您的健康怎么样？"
    assert noted["notes"] == [mapping_note]
    assert noted["instructions"] == []
    assert noted["options"] == expected["2011"]["questions"][0]["options"]
    for heading in ("**问卷设计**", "问卷设计", "#### 问卷设计"):
        assert read_questionnaire_copy(base_questionnaire.replace("询问当前健康。", heading + "\n\n询问当前健康。")) == expected
    changed = read_questionnaire_copy(base_questionnaire.replace("询问当前健康。", "#### 问卷设计变化\n\n询问当前健康。"))["2011"]
    assert changed["design_title"] == "问卷设计变化"
    assert changed["design"] == "询问当前健康。"
    assert [q["id"] for q in changed["questions"]] == ["DA001"]
    assert read_questionnaire_copy(base_questionnaire.replace("询问当前健康。", "问卷设计发生变化。"))["2011"]["design"] == "问卷设计发生变化。"
    rejects(lambda: read_questionnaire_copy(base_questionnaire.replace("询问当前健康。", "**问卷设计**")), "缺少时期设计说明")
    grouped = base_questionnaire.replace("#### DA001", "#### ADL上游问题\n\n##### DA001") + "\n#### ADL原始问题\n\n##### DA002\n\n第二道题。\n\n选项与 DA001 相同。\n"
    parsed = read_questionnaire_copy(grouped)["2011"]
    assert [q["group"] for q in parsed["questions"]] == ["ADL上游问题", "ADL原始问题"]
    assert parsed["questions"][1]["options"] == []
    modules = grouped.replace("ADL上游问题", "身体活动").replace("ADL原始问题", "日常生活活动")
    assert [q["group"] for q in read_questionnaire_copy(modules)["2011"]["questions"]] == ["身体活动", "日常生活活动"]
    rejects(lambda: read_questionnaire_copy(grouped.replace("选项与 DA001", "选项与 DA999")), "前面已展示")
    rejects(lambda: read_questionnaire_copy(grouped.replace("选项与 DA001", "选项与 DA002")), "前面已展示")
    rejects(lambda: read_questionnaire_copy(grouped + "\n- 1 好\n"), "引用选项与单题选项重复")
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        path = folder / "文案.md"
        original = (ROOT / "tests/fixtures/writing-inputs" / "reader-copy.md").read_text(encoding="utf-8")
        path.write_text(original, encoding="utf-8")
        content = read_copy(path, ["fall_status", "fall_count"])
        assert "注意点" not in content["criteria"]["fall_status"]
        assert not content["insight"]
        assert compare_content(content, copy.deepcopy(content))["ok"]
        note = folder / "note.md"
        note.write_text(render_note(content), encoding="utf-8")
        assert validate_note(path, note)["ok"]

        # Unit suffixes and legacy result names can contain dots. Preserve them exactly; keep
        # rejecting prose headings, renamed results and changed result order.
        dotted = original.replace("fall_status", "Lab_value_ng.ml")
        path.write_text(dotted, encoding="utf-8")
        dotted_content = read_copy(path, ["Lab_value_ng.ml", "fall_count"])
        assert list(dotted_content["criteria"]) == ["Lab_value_ng.ml", "fall_count"]
        note.write_text(render_note(dotted_content), encoding="utf-8")
        assert validate_note(path, note)["ok"]
        rejects(lambda: read_copy(path, ["Lab_value_ng_ml", "fall_count"]), "变量或顺序不一致")
        rejects(lambda: read_copy(path, ["fall_count", "Lab_value_ng.ml"]), "变量或顺序不一致")
        path.write_text(dotted.replace("### Lab_value_ng.ml", "### `Lab_value_ng.ml`"), encoding="utf-8")
        assert list(read_copy(path)["criteria"]) == ["Lab_value_ng.ml", "fall_count"]
        # Current names retain unit scales, conventional case and time suffixes.
        for name in ("JY_HDL_mg.dl", "JY_WBC_1e9.l", "JY_RBC_1e12.l",
                     "JY_HbA1c_p", "ZS_TyG_BMI", "Sleep_aid_2w", "Sleep_onset_freq"):
            path.write_text(original.replace("fall_status", name), encoding="utf-8")
            named = read_copy(path, [name, "fall_count"])
            assert list(named["criteria"]) == [name, "fall_count"]
            note.write_text(render_note(named), encoding="utf-8")
            assert validate_note(path, note)["ok"]
            rejects(lambda: read_copy(path, [name + "_changed", "fall_count"]), "变量或顺序不一致")
        for invalid in ("1value", "value label", "value-name", "value/units"):
            path.write_text(original.replace("### fall_status", "### " + invalid), encoding="utf-8")
            rejects(lambda: read_copy(path), "Criteria 应按实际分析变量逐项列出")
        path.write_text(original, encoding="utf-8")

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
stopifnot(is.null(copy$summary_selection))
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
text <- c("## 摘要导读", actual$summary, "## 定义",
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
        # Exercise the same dotted name through the real Python -> R loader,
        # source comparison and rendered-note comparison, without renaming it.
        path.write_text(path.read_text(encoding="utf-8").replace("fall_status", "Lab_value_ng.ml"), encoding="utf-8")
        script.write_text(script.read_text(encoding="utf-8").replace("fall_status", "Lab_value_ng.ml"), encoding="utf-8")
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(script)], cwd=folder,
                             env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert "R_COPY_FORWARD_PASS" in run.stdout
        assert validate_note(path, note)["ok"]
        assert "Lab_value_ng.ml" in note.read_text(encoding="utf-8")
        questionnaire_copy = (ROOT / "tests/fixtures/writing-inputs/questionnaire-copy.md").read_text(encoding="utf-8")
        # Exercise the accepted heading through the actual R loader and renderer.
        questionnaire_copy = questionnaire_copy.replace("### 2011年\n", "### 2011年\n\n#### 问卷设计变化\n", 1)
        questionnaire_copy += "\n\n" + mapping_note + "\n"
        assert "#### 问卷设计变化" in questionnaire_copy
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
        rendered = generated.read_text(encoding="utf-8")
        mapping_markup = mapping_note.replace('`JD111`', '<code>JD111</code>').replace('`KD111`', '<code>KD111</code>')
        assert re.search(r'<span[^>]*data-summary-question-detail-role="instruction"[^>]*font-size:0\.72em;[^>]*>' + re.escape(mapping_markup) + r"</span>", rendered)
        assert "#### 问卷设计变化" not in rendered
        assert rendered.count("问卷设计变化") == 1
        note_at = rendered.index(mapping_markup)
        # Note is inside its question, before that question's options.
        question_at = rendered.rfind('data-summary-selection-line="true"', 0, note_at)
        assert rendered.find('data-summary-question-option="true"', question_at) > note_at
        generated.write_text(rendered.replace("问卷设计变化", "问卷设计"), encoding="utf-8")
        rejects(lambda: validate_note(path, generated), "问卷")
        generated.write_text(rendered, encoding="utf-8")
        generated.write_text(generated.read_text(encoding="utf-8").replace("跳至 Q002", "跳至 Q999"), encoding="utf-8")
        rejects(lambda: validate_note(path, generated), "问卷")
        # Real template -> Python parser -> R renderer -> copy fidelity check.
        template = (ROOT / "templates/reader-copy.md").read_text(encoding="utf-8")
        adl = template.split("**分期问卷的展示格式**", 1)[1].split("```markdown", 1)[1].split("```", 1)[0]
        path.write_text(original + "\n\n" + adl, encoding="utf-8")
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(questionnaire_script)],
                             cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        rendered = generated.read_text(encoding="utf-8")
        assert validate_note(path, generated)["ok"]
        assert rendered.count("ADL上游问题") == 1 and rendered.count("ADL原始问题") == 1
        assert rendered.count('data-summary-question-option="true"') == 17
        assert "选项与 <code>DB001</code> 相同。" not in rendered
        assert rendered.count("<code>DB001</code>–<code>DB015</code> 的选项设置相同，后续题目仅列有跳转的选项。") == 1
        # A dropped group title must not escape the same full-text check.
        generated.write_text(rendered.replace("ADL上游问题", ""), encoding="utf-8")
        rejects(lambda: validate_note(path, generated), "问卷")
        # Module names are authored headings, not special parser keywords.
        path.write_text((original + "\n\n" + adl).replace("ADL上游问题", "身体活动").replace("ADL原始问题", "日常生活活动"), encoding="utf-8")
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(questionnaire_script)],
                             cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert validate_note(path, generated)["ok"]
        rendered_modules = generated.read_text(encoding="utf-8")
        assert rendered_modules.count("身体活动</") == 1
        numeric_questions = ('## 问卷\n\n### 核实项目\n\n#### 2011 年\n\n##### 问卷设计\n\n两题分别作答。\n\n'
            '##### 12\n\n第一项回答？\n\n- 0 否\n- 1 是\n\n14 的选项与 12 相同。\n\n'
            '##### 14\n\n第二项回答？\n')
        path.write_text(original + "\n\n" + numeric_questions, encoding="utf-8")
        run = subprocess.run([rscript, "--vanilla", "--encoding=UTF-8", str(questionnaire_script)],
                             cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert validate_note(path, generated)["ok"]
        numeric_markup = generated.read_text(encoding="utf-8")
        assert numeric_markup.count('data-summary-question-option="true"') == 2
        assert "14 的选项与 12 相同。" in numeric_markup
    print("READER_COPY_TESTS_PASS: copy, actual R inputs, rendered output, optional notes, missing fields, extra insight, order, values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
