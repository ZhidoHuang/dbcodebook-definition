"""Checker boundary and adversarial fixtures for explicit compact modules."""
from pathlib import Path
import html
import importlib.util
import json
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from definition_display import resolve_display_policy
from test_definition_readability_gate import (complete_impact, load_checker as load_readability,
    initialize_fixture_audit, FIXTURE_CONTENT, render_note)


def load_output():
    spec = importlib.util.spec_from_file_location("compact_output", ROOT / "scripts/check_definition_output.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def surface(names):
    return ('<a href="#cat-defined">Defined variables</a>'
            '<summary>Defined variables</summary>'
            '<table data-defined-overview="true">' + ''.join(
                f'<tr><td><a href="#var-{html.escape(n, quote=True)}">{html.escape(n)}</a></td></tr>' for n in names)
            + '</table>' + ''.join(
                f'<span class="var-name" id="var-{html.escape(n, quote=True)}" data-defined-variable="{html.escape(n, quote=True)}">{html.escape(n)}</span>' for n in names))


def workbook(path, rows):
    def column(index):
        name = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="data" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        body = ''.join(f'<row r="{i}">' + ''.join(f'<c r="{column(j)}{i}" t="inlineStr"><is><t>{html.escape(str(v))}</t></is></c>' for j, v in enumerate(row, 1)) + '</row>' for i, row in enumerate(rows, 1))
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + body + '</sheetData></worksheet>')


def assert_failure(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def main():
    c = load_output()
    names = [f"V.{i}" for i in range(31)]
    for kind, count, compact in (("module", 30, False), ("module", 31, True), ("standard", 31, False)):
        copy = f"---\ntopic_kind: {kind}\n---\n"
        record = dict(topic_kind=kind, approved_analysis_vars=names[:count])
        assert resolve_display_policy(copy, record=record)["compact_module"] is compact
    assert not resolve_display_policy("legacy module with 100 results", names)["compact_module"]
    assert_failure(lambda: resolve_display_policy("---\ntopic_kind: module\n---\n"))
    assert_failure(lambda: resolve_display_policy("---\ntopic_kind: module\n---\n", names, dict(topic_kind="standard")))

    with tempfile.TemporaryDirectory() as tmp:
        formal = Path(tmp)
        detail = formal / "topic_detail.html"
        good = surface(names)

        def checks(note=good, detail_text=good):
            detail.write_text(detail_text, encoding="utf-8")
            results = []
            c.check_compact_surfaces(formal, note, names, results)
            c.check_category_order(formal, note, results, compact_module=True)
            return results

        assert all(r["ok"] for r in checks())
        # Dots and escaped attribute values are identifiers, not CSS selectors.
        escaped = ['V.a&b', 'V."quoted"']
        parser = c.DefinedSurfaceParser()
        parser.feed(surface(escaped))
        assert parser.variables == parser.overview_variables == escaped
        for broken in (surface(names[:-1]), surface(names + [names[0]]), surface(names + ['Extra']),
                       good.replace('href="#var-V.0"', 'href="#var-Other"'),
                       good + '<span class="var-name" id="var-raw">raw</span>',
                       good.replace('id="var-V.0"', 'id="var-Other"'),
                       good + '<summary>Source variables</summary>',
                       good + '<table><tr><th>Criteria</th></tr></table>'):
            assert any(not r["ok"] for r in checks(broken)), broken[:100]
            assert any(not r["ok"] for r in checks(detail_text=broken)), broken[:100]
        (formal / "topic_definition.html").write_text("stale", encoding="utf-8")
        assert any(not r["ok"] for r in checks())
        (formal / "topic_definition.html").unlink()

        copy = "---\ntopic_kind: module\n---\n"
        (formal / "文案.md").write_text(copy, encoding="utf-8")
        record = dict(topic_kind="module", approved_analysis_vars=names)
        note = ('## 摘要导读\n' + '这是对变量模块、适用人群、调查时期和结果用途的完整说明。' * 3
                + '\n<div class="raw-source-link">来源</div>\n## 定义的组分概览\n' + good)
        (formal / "note.md").write_text(note, encoding="utf-8")
        detail.write_text(good, encoding="utf-8")
        workbook(formal / "cb.xlsx", [["Variable"]] + [[n] for n in names])
        workbook(formal / "db.xlsx", [["SEQN", "YEAR"] + names])
        # Public R outline has its own tests; isolate this test to real workbook/display coverage.
        c.check_public_code_outline = lambda *args: None
        results = []
        c.check_summary_facts(formal, "db.xlsx", "cb.xlsx", results, "nhanes", record=record)
        assert all(r["ok"] for r in results), results
        assert not any(r["check"] == "definition table variables and order" for r in results)
        text_results = []
        c.check_required_user_text(formal, ["适用人群"], text_results, dict(compact_module=True))
        assert all(r["ok"] for r in text_results), text_results
        workbook(formal / "db.xlsx", [["SEQN", "YEAR"] + names[:-1]])
        results = []
        c.check_summary_facts(formal, "db.xlsx", "cb.xlsx", results, "nhanes", record=record)
        assert any(not r["ok"] and r["check"] == "definition variables in analysis_db" for r in results)
        for kind, subset in (("module", names[:30]), ("standard", names)):
            (formal / "文案.md").write_text(f"---\ntopic_kind: {kind}\n---\n", encoding="utf-8")
            workbook(formal / "cb.xlsx", [["Variable"]] + [[n] for n in subset])
            results = []
            c.check_summary_facts(formal, "db.xlsx", "cb.xlsx", results, "nhanes", record=dict(topic_kind=kind, approved_analysis_vars=subset))
            assert any(not r["ok"] and r["check"] == "definition table structure" for r in results)

    r = load_readability()
    with tempfile.TemporaryDirectory() as tmp:
        formal, process = Path(tmp) / "formal", Path(tmp) / "process"
        formal.mkdir()
        complete_impact(r, formal, process)
        original = (formal / "文案.md").read_text(encoding="utf-8")
        without_criteria = original[:original.index("## Criteria")] + original[original.index("## 小book提示"):]
        for kind, count, accepted in (("module", 30, False), ("module", 31, True), ("standard", 31, False)):
            (formal / "文案.md").write_text(f"---\ntopic_kind: {kind}\n---\n" + without_criteria, encoding="utf-8")
            (process / r.SOURCE_RECORD_NAME).write_text(json.dumps(dict(topic_kind=kind, approved_analysis_vars=names[:count])), encoding="utf-8")
            if accepted:
                r.validate_impact(formal, process, "025")
            else:
                try:
                    r.validate_impact(formal, process, "025")
                except ValueError:
                    pass
                else:
                    raise AssertionError("ordinary display must still require Criteria")

    # Use the same isolated artifact/result fixture as mechanical_delivery,
    # but actually bind compact copy, its source plan and 31-result workbook.
    from writing_evidence import scope_bindings
    with tempfile.TemporaryDirectory() as tmp:
        formal, process = Path(tmp) / "formal", Path(tmp) / "process"
        formal.mkdir()
        complete_impact(r, formal, process)
        copy_path = formal / "文案.md"
        original = copy_path.read_text(encoding="utf-8")
        compact_copy = ("---\ntopic_kind: module\n---\n"
                        + original[:original.index("## Criteria")]
                        + original[original.index("## 小book提示"):])
        copy_path.write_text(compact_copy, encoding="utf-8")
        r.write_json(process / r.SOURCE_RECORD_NAME, dict(schema_version=1,
            topic_kind="module", approved_analysis_vars=names))
        content = dict(FIXTURE_CONTENT, criteria={})
        note = render_note(content)
        note = note[:note.index("## 定义\n")] + "## 定义的组分概览\n" + surface(names) + "\n" + note[note.index("## 参考资料说明"):]
        files = dict(note="note.md", public_r="define.R", analysis_db="db.xlsx", analysis_codebook="cb.xlsx")
        (formal / files["note"]).write_text(note, encoding="utf-8")
        (formal / files["public_r"]).write_text("# isolated gate fixture\n", encoding="utf-8")
        workbook(formal / files["analysis_codebook"], [["Variable"]] + [[n] for n in names])
        workbook(formal / files["analysis_db"], [["SEQN", "YEAR"] + names, ["1", "2011"] + [0] * len(names)])
        initialize_fixture_audit(r, formal, process, "025", files)
        initialized = r.initialize_audit(formal, process, "025", files, overwrite=True)
        bindings = scope_bindings(formal, process, initialized["artifacts"])
        assert set(bindings) == {"title_summary", "definition_logic", "criteria", "insight_card", "references"}
        assert all(isinstance(digest, str) and len(digest) == 64 for digest in bindings.values())
        checked = r.validate_audit(formal, process, "025")
        assert checked["writing_quality"] == "NOT_ASSESSED" and checked["scope_count"] == 0
        assert r.verify_existing_readiness(formal, process, "025")["ok"]
        assert not list(formal.glob("*_definition.html"))
    print("COMPACT_MODULE_CHECKS_PASS: 30/31/standard boundaries, exact coverage, stale/source/duplicate rejection, real workbooks, scope_bindings and compact init/check/verify-ready")


if __name__ == "__main__":
    main()
