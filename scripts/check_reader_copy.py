"""Check reader content at copy, rendering-input, and publication boundaries."""

from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re


NO_INSIGHT = "本主题没有需要单独提示的主题级边界"
REQUIRED_FIELDS = ("定义", "定义逻辑", "分类")
FIELDS = (*REQUIRED_FIELDS, "注意点")


class Element:
    def __init__(self, tag="root", attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def text(self):
        if self.tag in {"style", "script"}:
            return ""
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find(self, predicate):
        for child in self.children:
            if isinstance(child, Element):
                if predicate(child):
                    yield child
                yield from child.find(predicate)


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs)
        self.stack[-1].children.append(element)
        if tag not in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def visible_markup(text):
    # Markdown code in a mixed Markdown/HTML note must survive HTML parsing.
    text = re.sub(r"`([^`]+)`", lambda m: "<code>" + escape(m[1]) + "</code>", str(text))
    return Document(text).root.text()


def normalized(text):
    # Only presentation differences are ignored. Codes, names, values and
    # punctuation stay significant; this is not a semantic quality judgement.
    text = re.sub(r"(?m)^\s*[-*]\s+", "", str(text))
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    return re.sub(r"\s+", "", text)


def sections(text, level):
    matches = list(re.finditer(rf"(?m)^{'#' * level} (.+?)\s*$", text))
    result = {}
    for i, match in enumerate(matches):
        name = match[1].strip().strip("`")
        if name in result:
            raise ValueError(f"文案重复栏目：{name}")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[name] = text[match.end():end].strip()
    return result


def read_copy(path, expected_vars=None):
    text = Path(path).read_text(encoding="utf-8-sig")
    if re.search(r"<(?:div|span|section|style)\b", text, re.I):
        raise ValueError("文案.md 只能保存纯文案，不能含展示 HTML。")
    parts = sections(text, 2)
    for key in ("摘要导读", "Criteria", "小book提示", "参考资料说明"):
        if not normalized(parts.get(key, "")):
            raise ValueError(f"文案缺少内容：{key}")
    criteria = {}
    for variable, body in sections(parts["Criteria"], 3).items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", variable):
            raise ValueError(f"Criteria 应按实际分析变量逐项列出：{variable}")
        fields = sections(body, 4)
        for field in REQUIRED_FIELDS:
            if not normalized(fields.get(field, "")):
                raise ValueError(f"Criteria/{variable}/{field} 缺失或没有内容")
        if any(field not in FIELDS for field in fields):
            raise ValueError(f"Criteria/{variable} 栏目应为：{', '.join(FIELDS)}")
        if list(fields) != [field for field in FIELDS if field in fields]:
            raise ValueError(f"Criteria/{variable} 栏目顺序不符合正式模板")
        if "注意点" in fields and not normalized(fields["注意点"]):
            raise ValueError(f"Criteria/{variable}/注意点 为空；无内容时省略栏目")
        criteria[variable] = fields
    if not criteria:
        raise ValueError("Criteria 没有按最终分析变量逐项填写")
    if expected_vars is not None and list(criteria) != list(expected_vars):
        raise ValueError(f"Criteria 变量或顺序不一致：文案={list(criteria)}，定义={list(expected_vars)}")
    insight = parts["小book提示"]
    if normalized(insight) == NO_INSIGHT:
        insight = ""
    return {"summary": parts["摘要导读"], "criteria": criteria,
            "insight": insight, "references": parts["参考资料说明"]}


def require_equal(expected, actual, location):
    left, right = normalized(expected), normalized(actual)
    if left != right:
        pos = next((i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]), min(len(left), len(right)))
        raise ValueError(f"{location} 与文案不一致（字符 {pos}）：文案={left[max(0,pos-15):pos+65]!r}；成品={right[max(0,pos-15):pos+65]!r}")


def criteria_fields(markup):
    root = Document(markup).root if isinstance(markup, str) else markup
    fields = {}
    current = None
    accounted = []
    for element in root.find(lambda e: e.attrs.get("data-criteria-heading") == "true" or e.attrs.get("data-criteria-item") == "true" or e.attrs.get("data-criteria-context") == "true"):
        if element.attrs.get("data-criteria-heading") == "true":
            current = element.text().strip()
            if current in fields:
                raise ValueError(f"Criteria 重复栏目：{current}")
            fields[current] = ""
            accounted.append(element.text())
        elif current:
            fields[current] += element.text() + "\n"
            accounted.append(element.text())
    if normalized(root.text()) != normalized("".join(accounted)):
        raise ValueError("Criteria 存在未归入栏目或重复提取的可见文字")
    return fields


def compare_content(copy, actual, *, source=False):
    for field in ("summary", "insight", "references"):
        value = actual.get(field, "")
        if source:
            value = visible_markup(value)
        require_equal(copy[field], value, field)
    actual_criteria = actual.get("criteria", {})
    if list(copy["criteria"]) != list(actual_criteria):
        raise ValueError("生成内容的 Criteria 变量或顺序与文案不一致")
    for variable, fields in copy["criteria"].items():
        rendered = actual_criteria[variable]
        if isinstance(rendered, str):
            rendered = criteria_fields(rendered)
        if list(fields) != list(rendered):
            raise ValueError(f"Criteria/{variable} 栏目丢失或增加：应为{list(fields)}，实际{list(rendered)}")
        for field, text in fields.items():
            require_equal(text, rendered[field], f"Criteria/{variable}/{field}")
    return {"ok": True, "variables": list(copy["criteria"]), "checked": ["summary", "criteria", "insight", "references"]}


def note_content(text):
    text = re.sub(r"(?ms)^```.*?^```\s*$", "", text)
    parts = sections(text, 2)
    summary = parts.get("摘要导读", "")
    summary = re.split(r'<div\s+class="raw-source-structure"|<!-- summary-insight-card:start -->|<div\s+class="raw-source-link"', summary, maxsplit=1)[0]
    root = Document(text).root
    insight = list(root.find(lambda e: e.attrs.get("data-summary-insight-body") == "true"))
    if len(insight) > 1:
        raise ValueError("成品有重复的小book提示卡")
    tables = list(root.find(lambda e: e.tag == "table" and any(c.tag == "tr" and "".join(t.text() for t in c.children if isinstance(t, Element) and t.tag == "th") == "DefinitionCriteriadetail" for c in e.children if isinstance(c, Element))))
    if len(tables) != 1:
        raise ValueError("成品必须有一份 Definition / Criteria / detail 定义表")
    criteria = {}
    for row in tables[0].children:
        if not isinstance(row, Element) or row.tag != "tr":
            continue
        cells = [c for c in row.children if isinstance(c, Element) and c.tag == "td"]
        if not cells:
            continue
        if len(cells) != 3:
            raise ValueError("成品定义表的列数不正确")
        variable = cells[0].text().strip()
        if variable in criteria:
            raise ValueError(f"成品定义表重复变量：{variable}")
        criteria[variable] = criteria_fields(cells[1])
    references = parts.get("参考资料说明", "")
    # Generated detail HTML is not part of the reference prose.
    references = re.split(r"<style\b|<table\b", references, maxsplit=1, flags=re.I)[0]
    return {"summary": visible_markup(summary), "criteria": criteria,
            "insight": insight[0].text() if insight else "", "references": visible_markup(references)}


def validate_note(copy_path, note_path, codebook_path=None):
    expected = None
    if codebook_path:
        from check_definition_output import read_xlsx_rows
        rows = read_xlsx_rows(Path(codebook_path))
        column = rows[0].index("Variable")
        expected = [str(row[column]) for row in rows[1:]]
    copy = read_copy(copy_path, expected)
    return compare_content(copy, note_content(Path(note_path).read_text(encoding="utf-8-sig")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", required=True)
    parser.add_argument("--record")
    parser.add_argument("--source-json")
    parser.add_argument("--note")
    parser.add_argument("--analysis-codebook")
    parser.add_argument("--export")
    args = parser.parse_args()
    try:
        expected = None
        if args.record:
            expected = json.loads(Path(args.record).read_text(encoding="utf-8-sig"))["approved_analysis_vars"]
        copy = read_copy(args.copy, expected)
        result = {"ok": True, "variables": list(copy["criteria"])}
        if args.source_json:
            actual = json.loads(Path(args.source_json).read_text(encoding="utf-8-sig"))
            result = compare_content(copy, actual, source=True)
        if args.note:
            result = validate_note(args.copy, args.note, args.analysis_codebook)
        if args.export:
            Path(args.export).write_text(json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
