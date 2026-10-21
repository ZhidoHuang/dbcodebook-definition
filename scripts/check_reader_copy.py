"""Check reader content at copy, rendering-input, and publication boundaries."""

from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from definition_display import resolve_display_policy
from reference_format import reference_items, render_references
from questionnaire_groups import period_keys, original_options, question_matches, question_identifiers, unverified_question_periods
from questionnaire_groups import validate_shared_option_rows
from questionnaire_groups import question_identity, validate_display_titles
from questionnaire_display import validate_display_sequence, display_route_destination
from questionnaire_display import (requires_questionnaire_display, display_question, display_answers, cross_period_options,
    shared_question_info, referenced_options, referenced_jump_options,
    rendered_when_matches, jump_descriptions, is_plain_paraphrase, validate_paraphrase_display)


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


def table_cells(line):
    """Split a Markdown row without splitting escaped pipes or inline code."""
    cells, cell, ticks = [], [], 0
    i = 0
    line = line.strip()
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line):
            cell.append(line[i:i + 2])
            i += 2
            continue
        if char == "`":
            ticks ^= 1
        if char == "|" and not ticks:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        i += 1
    cells.append("".join(cell).strip())
    if line.startswith("|"):
        cells.pop(0)
    if line.endswith("|") and not line.endswith("\\|"):
        cells.pop()
    return [value.replace(r"\|", "|") for value in cells]


def criteria_blocks(text):
    """Keep table cells structured; ordinary lines retain their existing format."""
    lines = text.splitlines()
    result, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        delimiters = table_cells(lines[i + 1]) if i + 1 < len(lines) else []
        if "|" in line and delimiters and all(re.fullmatch(r":?-{3,}:?", d) for d in delimiters):
            header = table_cells(line)
            if len(header) != len(delimiters):
                raise ValueError("Criteria 表格表头与分隔行列数不同")
            align = ["center" if d.startswith(":") and d.endswith(":") else
                     "right" if d.endswith(":") else "left" for d in delimiters]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                row = table_cells(lines[i])
                if len(row) != len(header):
                    raise ValueError("Criteria 表格数据行与表头列数不同")
                rows.append(row)
                i += 1
            result.append(dict(type="table", header=header, rows=rows, align=align))
        else:
            result.append(dict(type="text", text=line))
            i += 1
    return result


def criteria_comparable(text):
    blocks = criteria_blocks(text)
    for block in blocks:
        if block["type"] == "table":
            block.pop("align")  # Alignment is presentation, not source content.
            block["header"] = [normalized(c) for c in block["header"]]
            block["rows"] = [[normalized(c) for c in row] for row in block["rows"]]
        else:
            block["text"] = normalized(block["text"])
    # Preserve old whitespace tolerance for prose, but keep table boundaries.
    merged = []
    for block in blocks:
        if block["type"] == "text" and merged and merged[-1]["type"] == "text":
            merged[-1]["text"] += block["text"]
        else:
            merged.append(block)
    return merged


INSIGHT_MARKER = r"(?:[①②③④⑤⑥⑦⑧⑨⑩]|[0-9]+[、.)．](?=[ \t]|$))[ \t]*"


def insight_items(text):
    items = re.split(r"\r?\n[ \t]*\r?\n|\r?\n(?=[ \t]*" + INSIGHT_MARKER + ")", text)
    return [re.sub(r"^\s*" + INSIGHT_MARKER, "", item).strip()
            for item in items if item.strip()]


def insight_markup_content(markup, expected):
    """Check the generated list, rather than merely ignoring its numbering."""
    root = Document(markup).root if isinstance(markup, str) else markup
    bodies = list(root.find(lambda e: e.attrs.get("data-summary-insight-body") == "true"))
    if not bodies:
        return visible_markup(markup) if isinstance(markup, str) else ""
    items = list(bodies[0].find(lambda e: e.attrs.get("data-summary-insight-paragraph") == "true"))
    if len(items) != len(insight_items(expected)):
        raise ValueError("小book 条目数与文案分段不一致")
    content = []
    for i, item in enumerate(items, 1):
        numbers = list(item.find(lambda e: "summary-insight-number" in e.attrs.get("class", "").split()))
        texts = list(item.find(lambda e: "summary-insight-text" in e.attrs.get("class", "").split()))
        if len(numbers) != 1 or numbers[0].text() != f"{i}." or len(texts) != 1:
            raise ValueError("小book 必须由生成器逐条顺序编号，并与正文分列")
        if "display:flex" not in item.attrs.get("style", "").replace(" ", ""):
            raise ValueError("小book 缺少编号与正文分列的缩进结构")
        if normalized(item.text()) != normalized(numbers[0].text() + texts[0].text()):
            raise ValueError("小book 条目存在未核对的额外文字")
        content.append(texts[0].text())
    if normalized(bodies[0].text()) != normalized("".join(item.text() for item in items)):
        raise ValueError("小book 存在未归入条目的文字")
    return "\n\n".join(content)



def route_matches(destination, description, period=None, *, allow_topic_exit=False):
    # Ignore presentation whitespace symmetrically while retaining identifier
    # boundaries: DA002 must never match DA0020 or XDA002.
    target = normalized(destination)
    if not target:
        return False
    # Strip the same Markdown presentation as normalized(), but keep spaces
    # here so an English word before DN005 does not become an identifier prefix.
    description = re.sub(r"`([^`]+)`", r"\1", str(description))
    description = re.sub(r"\*\*(.*?)\*\*", r"\1", description)
    # This exception is enabled only after shared display validation has checked
    # the period-specific exit evidence. Do not accept arbitrary '结束' prose.
    if allow_topic_exit and re.fullmatch(r'\s*结束该主题[。.!！]?\s*', description.split('→')[-1]):
        return True
    pattern = r"(?<![A-Za-z0-9_])" + r"\s*".join(re.escape(c) for c in target) + r"(?![A-Za-z0-9_])"
    if period is not None:
        # A visibly scoped target may carry a different question number in another year.
        source_id = re.sub(r"^第\s*(\d+)\s*题$", r"\1", str(destination).strip())
        target_id = re.fullmatch(r"([A-Za-z0-9_][A-Za-z0-9_.-]*)(?:[（(][^）)]+[）)])?", source_id)
        scoped = re.search(r"([A-Za-z0-9_][A-Za-z0-9_.-]*\s*[（(](?:\d{4}|Wave\s*\d+)[^）)]*[）)](?:\s*[／/]\s*[A-Za-z0-9_][A-Za-z0-9_.-]*\s*[（(][^）)]+[）)])*)", description, re.I)
        if target_id and scoped:
            return question_matches(scoped[1], target_id[1], period)
    return re.search(pattern, description) is not None


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


def semantic_tree(text):
    """Explicit roles only; connectors are syntax, never inferred result names."""
    roles = {"result", "component", "relation", "meta"}
    pieces, plain = [], []
    def add(value, role=None):
        plain.append(value)
        if role:
            pieces.append(f'<span data-tree-role="{role}">{escape(value)}</span>')
        else:
            pieces.append(re.sub(r'([│├└─┐┘┬┤→←]+)', r'<span data-tree-role="connector">\1</span>', escape(value)))
    offset = 0
    for match in re.finditer(r'\[\[([a-z]+):((?:\[[^\[\]\n]*\]|[^\[\]\n])+)\]\]', text):
        add(text[offset:match.start()])
        if match[1] not in roles:
            raise ValueError('未知关系树角色：' + match[1])
        add(match[2], match[1])
        offset = match.end()
    add(text[offset:])
    if '[[' in ''.join(plain) or ']]' in ''.join(plain):
        raise ValueError('关系树角色标记不完整')
    block = {"type": "code_tree", "text": ''.join(plain)}
    if offset:
        block['role_html'] = ''.join(pieces)
    return block


def summary_blocks(text):
    """Parse prose and literal trees once; renderers must not reinterpret fences."""
    lines = str(text).splitlines()
    blocks, prose = [], []

    def flush():
        if prose:
            blocks.append({"type": "paragraph", "text": "\n".join(prose)})
            prose.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = re.fullmatch(r" {0,3}(`{3,}|~{3,})(?:(?:text|plaintext)(?:[ \t]+([^\r\n]+?))?)?[ \t]*", line)
        if fence:
            flush()
            marker, body = fence[1], []
            i += 1
            while i < len(lines) and not re.fullmatch(r" {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*", lines[i]):
                body.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError("摘要代码树缺少结束围栏")
            if not any(x.strip() for x in body):
                raise ValueError("摘要代码树不能为空")
            block = semantic_tree("\n".join(body))
            if fence[2]:
                block['label'] = fence[2].strip()
            blocks.append(block)
        elif re.match(r" {0,3}(?:`{3,}|~{3,})", line):
            raise ValueError("摘要代码树使用无语言或 text 围栏")
        elif line.startswith("    "):
            flush()
            body = []
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                body.append(lines[i][4:] if lines[i].startswith("    ") else "")
                i += 1
            while body and not body[-1]:
                body.pop()
            blocks.append(semantic_tree("\n".join(body)))
            continue
        elif not line.strip():
            flush()
        else:
            prose.append(line)
        i += 1
    flush()
    return blocks


def summary_prose(text):
    return "\n\n".join(b["text"] for b in summary_blocks(text) if b["type"] == "paragraph")


def rendered_summary_trees(markup):
    trees = []
    for node in Document(markup).root.find(lambda e: e.attrs.get("data-summary-tree") == "true"):
        if node.tag != "pre":
            raise ValueError("摘要代码树必须用 pre 保留换行和缩进")
        trees.append(node.text())
    return trees


def read_copy(path, expected_vars=None, record=None):
    text = Path(path).read_text(encoding="utf-8-sig")
    policy = resolve_display_policy(text, expected_vars, record)
    if expected_vars is None and policy["analysis_vars"]:
        expected_vars = policy["analysis_vars"]
    if re.search(r"<(?:div|span|section|style)\b", text, re.I):
        raise ValueError("文案.md 只能保存纯文案，不能含展示 HTML。")
    parts = sections(text, 2)
    required = ("摘要导读", "小book提示") if policy["compact_module"] else ("摘要导读", "Criteria", "小book提示")
    for key in required:
        if not normalized(parts.get(key, "")):
            raise ValueError(f"文案缺少内容：{key}")
    criteria = {}
    if policy["compact_module"] and "Criteria" in parts:
        raise ValueError("模块最终变量超过 30 个时，不编写 Criteria 栏目")
    for variable, body in sections(parts.get("Criteria", ""), 3).items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", variable):
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
    if not criteria and not policy["compact_module"]:
        raise ValueError("Criteria 没有按最终分析变量逐项填写")
    if not policy["compact_module"] and expected_vars is not None and list(criteria) != list(expected_vars):
        raise ValueError(f"Criteria 变量或顺序不一致：文案={list(criteria)}，定义={list(expected_vars)}")
    if not policy["analysis_vars"]:
        policy = resolve_display_policy(text, list(criteria), record)
    insight = parts["小book提示"]
    if normalized(insight) == NO_INSIGHT:
        insight = ""
    result = {"summary": parts["摘要导读"], "criteria": criteria,
              "criteria_intro": re.split(r"(?m)^### ", parts.get("Criteria", ""), maxsplit=1)[0].strip(),
              "insight": insight, "references": render_references(parts.get("参考资料说明", ""))}
    result["display_policy"] = policy
    result["definition_basis"] = parts.get("定义依据", "")
    result["criteria_blocks"] = {v: {f: criteria_blocks(t) for f, t in fields.items()}
                                 for v, fields in criteria.items()}
    result["summary_blocks"] = summary_blocks(result["summary"])
    if "问卷" in parts:
        result["questionnaire"] = read_questionnaire_copy(parts["问卷"])
    return result


def read_questionnaire_copy(text):
    top = sections(text, 3)
    # A module contains fourth-level periods, not fourth-level design/questions.
    nested = [bool(re.search(r"(?m)^##### 问卷设计(?:变化)?\s*$", body)) for body in top.values()]
    if any(nested):
        if not all(nested):
            raise ValueError("问卷不能混用题组内时期与全局时期结构")
        result = {}
        for module, body in top.items():
            if re.split(r"(?m)^#### ", body, maxsplit=1)[0].strip():
                raise ValueError("题组说明应写在对应时期的问卷设计中：" + module)
            module_key = re.sub(r"[^A-Za-z0-9\u3400-\u9fff]+", "_", module).strip("_")
            if not module_key:
                raise ValueError("问卷题组名称为空")
            lowered = re.sub(r"(?m)^(#{4,6})(?= )", lambda m: m[0][1:], body)
            for key, period in read_questionnaire_copy(lowered).items():
                combined = module_key + "__" + key
                if combined in result:
                    raise ValueError("问卷题组和时期标识重复：" + combined)
                period["module"] = module
                result[combined] = period
        return result
    periods = {}
    for label, body in sections(text, 3).items():
        # Explicit colon titles distinguish multiple legal modules in one Wave.
        key_pattern = r"[^A-Za-z0-9\u3400-\u9fff]+" if re.search(r"[:：]", label) else r"[^A-Za-z0-9]+"
        period = re.sub(key_pattern, "_", label).strip("_")
        if not period or period in periods:
            raise ValueError("问卷时期标识为空或重复：" + label)
        # Read the authored heading as a title, separately from its body.
        heading = re.match(r"\A(?:####[ \t]+|\*\*)?(问卷设计变化|问卷设计)(?:\*\*)?[ \t]*(?:\n|$)", body.strip())
        design_title = heading.group(1) if heading else "问卷设计"
        # Unheaded legacy copy keeps its former default; new copy supplies a heading.
        questionnaire_body = body.strip()[heading.end():].lstrip() if heading else body
        design = re.split(r"(?m)^#### ", questionnaire_body, maxsplit=1)[0].strip()
        if not normalized(design):
            raise ValueError("问卷缺少时期设计说明：" + label)
        questions = []
        question_blocks = []
        for title, content in sections(questionnaire_body, 4).items():
            grouped = sections(content, 5)
            if grouped or title.endswith(("上游问题", "原始问题")):
                if not grouped or re.split(r"(?m)^##### ", content, maxsplit=1)[0].strip():
                    raise ValueError("题目分组下须用五级标题逐题展示：" + title)
                question_blocks.extend((qid, body, title) for qid, body in grouped.items())
            else:
                question_blocks.append((title, content, ""))
        for question_id, content, group in question_blocks:
            question_identifiers(question_id)  # Validate explicit alias scopes before comparison.
            question = {"id": question_id, "text": "", "condition": "", "options": [], "instructions": []}
            flows = re.findall(r"(?ms)^```(?:text)?[ \t]*\n(.*?)\n```[ \t]*$", content)
            if flows:
                question["flows"] = flows
                content = re.sub(r"(?ms)^```(?:text)?[ \t]*\n.*?\n```[ \t]*$", "", content)
            if group:
                question["group"] = group
            text_lines = []
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("适用对象："):
                    if question["condition"]:
                        raise ValueError("重复的题目适用对象：" + question_id)
                    question["condition"] = line.removeprefix("适用对象：").strip()
                elif line.startswith(("各个时期的变量名：", "对应数据变量：", "原问卷变量名题号：")):
                    question.setdefault("notes", []).append(line)
                elif line.startswith("跳题说明："):
                    question["instructions"].append(line.removeprefix("跳题说明：").strip())
                elif line.startswith("共同跳题（"):
                    question["instructions"].append(line)
                elif (re.search(r"(?:选项|跳题规则)与\s*[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\s*相同。", re.sub(r"`([^`]+)`", r"\1", line))
                      or re.search(r"的选项设置相同，(?:(?:该范围内的后续题目|下列题目)不再逐一展开选项|后续题目仅列有跳转的选项)。", line)):
                    question["instructions"].append(line)
                elif line.startswith("- "):
                    option = re.split(r"\s*(?:→|->)\s*", line[2:], maxsplit=1)
                    question["options"].append({"text": option[0], "jump": "→ " + option[1] if len(option) > 1 else ""})
                else:
                    text_lines.append(line)
            question["text"] = "\n".join(text_lines)
            if not question["text"]:
                raise ValueError("问卷缺少完整题文：" + question_id)
            questions.append(question)
        summary_only = all(re.search(r"(?m)^" + marker + r"[：:][ \t]*\S", design)
                           for marker in ("题意概括", "未取得完整原题的原因"))
        if not questions and not summary_only:
            raise ValueError("问卷缺少题目：" + label)
        ids = [q["id"] for q in questions]
        if len(ids) != len(set(ids)):
            raise ValueError("本时期题号重复：" + label)
        for question in questions:
            referenced_jump_options(question["id"], [(q["id"], q["options"], "\n".join(q["instructions"])) for q in questions])
            referenced = referenced_options("\n".join(question["instructions"]), question["id"],
                [(q["id"], [o["text"] for o in q["options"]], "\n".join(q["instructions"])) for q in questions])
            if referenced and question["options"]:
                validate_shared_option_rows(referenced, question["options"])
            shared_text = design + "\n" + "\n".join(s for q in questions for s in q["instructions"] if s.startswith("共同跳题（"))
            shared_options, _ = shared_question_info(shared_text, question["id"], ids)
            if shared_options and question["options"]:
                raise ValueError("共同选项与单题选项重复：" + question["id"])
        periods[period] = {"label": label, "design_title": design_title, "design": design, "questions": questions}
    if not periods:
        raise ValueError("问卷没有时期内容")
    return periods


def questionnaire_text(period):
    parts = [period["label"], period.get("design_title", "问卷设计"), period["design"]]
    if period.get("module"):
        parts.insert(0, period["module"])
    previous_group = None
    for question in period["questions"]:
        group = question.get("group")
        if group and group != previous_group:
            parts.append(group)
        previous_group = group
        parts.extend([question["id"], question["text"]])
        parts.extend(question.get("notes", []))
        if question["condition"]:
            parts.append("（" + question["condition"] + "）")
        parts.extend(option["text"] + option["jump"] for option in question["options"])
        parts.extend(question["instructions"])
        parts.extend(question.get("flows", []))
    return "\n".join(parts)


def questionnaire_content(markup):
    root = Document(markup).root
    for module in root.find(lambda e: e.tag == "div" and bool(e.attrs.get("data-questionnaire-module"))):
        headings = list(module.find(lambda e: e.attrs.get("data-questionnaire-module-title") == "true"))
        if len(headings) != 1 or headings[0].text() != module.attrs["data-questionnaire-module"]:
            raise ValueError("问卷题组标题缺失或与分组不一致")
        for period in module.find(lambda e: bool(e.attrs.get("data-raw-source-period"))):
            if period.attrs.get("data-questionnaire-module") != module.attrs["data-questionnaire-module"]:
                raise ValueError("问卷时期放入了错误题组")
    periods = {}
    for element in root.find(lambda e: bool(e.attrs.get("data-raw-source-period"))):
        key = element.attrs["data-raw-source-period"]
        if key in periods:
            raise ValueError("成品有重复的问卷时期：" + key)
        prefix = element.attrs.get("data-questionnaire-module", "")
        periods[key] = (prefix + "\n" if prefix else "") + element.text()
    return periods


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
            tables = list(element.find(lambda e: e.attrs.get("data-criteria-table") == "true"))
            if tables:
                if len(tables) != 1 or normalized(element.text()) != normalized(tables[0].text()):
                    raise ValueError("Criteria 表格包含未归入单元格的文字")
                rows = []
                accounted_cells = []
                for row in tables[0].find(lambda e: e.tag == "tr"):
                    elements = [c for c in row.children if isinstance(c, Element) and c.tag in {"th", "td"}]
                    expected_tag = "th" if not rows else "td"
                    if not elements or any(c.tag != expected_tag for c in elements):
                        raise ValueError("Criteria 表格的表头或数据行结构不正确")
                    accounted_cells.extend(c.text() for c in elements)
                    cells = [c.text().replace("|", r"\|") for c in elements]
                    rows.append("| " + " | ".join(cells) + " |")
                if normalized(tables[0].text()) != normalized("".join(accounted_cells)):
                    raise ValueError("Criteria 表格包含未归入单元格的文字")
                if not rows:
                    raise ValueError("Criteria 表格缺少表头")
                count = len(table_cells(rows[0]))
                rows.insert(1, "| " + " | ".join(["---"] * count) + " |")
                fields[current] += "\n".join(rows) + "\n"
            else:
                fields[current] += element.text() + "\n"
            accounted.append(element.text())
    if normalized(root.text()) != normalized("".join(accounted)):
        raise ValueError("Criteria 存在未归入栏目或重复提取的可见文字")
    return fields


def compare_content(copy, actual, *, source=False):
    blocks = summary_blocks(copy["summary"])
    expected_trees = [b["text"] for b in blocks if b["type"] == "code_tree"]
    actual_trees = rendered_summary_trees(actual.get("summary", "")) if source else actual.get("summary_trees", [])
    # Raw copy comparisons are useful before rendering; publication and R source
    # comparisons always supply rendered trees and check their exact structure.
    if not source and "summary_blocks" in actual and "summary_trees" not in actual:
        actual_trees = [b["text"] for b in summary_blocks(actual["summary"]) if b["type"] == "code_tree"]
    if expected_trees != actual_trees:
        raise ValueError("summary 代码树的节点、顺序、换行或缩进与文案不一致")
    for field in ("summary", "insight", "references", "criteria_intro", "definition_basis"):
        value = actual.get(field, "")
        if source:
            value = visible_markup(value)
        expected = "\n\n".join(b["text"] for b in blocks) if field == "summary" else copy.get(field, "")
        if field == "references":
            # Compare material content and order, not generator-owned numbering.
            if [normalized(x) for x in reference_items(expected)] != [normalized(x) for x in reference_items(value)]:
                raise ValueError("references 内容或条目顺序与文案不一致")
            continue
        if field == "insight":
            value = insight_markup_content(actual.get(field, ""), expected)
            value = "\n\n".join(insight_items(value))
            expected = "\n\n".join(insight_items(expected))
        if field == "summary" and not source and "summary_blocks" in actual and "summary_trees" not in actual:
            value = "\n\n".join(b["text"] for b in summary_blocks(value))
        require_equal(expected, value, field)
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
            if criteria_comparable(text) != criteria_comparable(rendered[field]):
                raise ValueError(f"Criteria/{variable}/{field} 的正文或表格单元格与文案不一致")
    if "questionnaire" in copy:
        rendered = actual.get("questionnaire", {})
        if isinstance(rendered, str):
            rendered = questionnaire_content(rendered)
        if list(copy["questionnaire"]) != list(rendered):
            raise ValueError("问卷的时期或顺序与文案不一致")
        for period, value in copy["questionnaire"].items():
            actual_text = questionnaire_text(rendered[period]) if isinstance(rendered[period], dict) else rendered[period]
            require_equal(questionnaire_text(value), actual_text, "问卷/" + period)
        expected_flows = [flow for p in copy["questionnaire"].values() for q in p["questions"] for flow in q.get("flows", [])]
        if isinstance(actual.get("questionnaire"), str):
            actual_flows = [e.text() for e in Document(actual["questionnaire"]).root.find(lambda e: e.attrs.get("data-questionnaire-flow") == "true")]
            if expected_flows != actual_flows:
                raise ValueError("问卷流程图的内容、顺序或缩进与文案不一致")
        elif "questionnaire_flows" in actual and expected_flows != actual["questionnaire_flows"]:
            raise ValueError("问卷流程图的内容、顺序或缩进与文案不一致")
    policy = copy.get("display_policy", {})
    criteria_check = "criteria_omission" if policy.get("compact_module") else "criteria"
    return {"ok": True, "variables": policy.get("analysis_vars", list(copy["criteria"])), "checked": ["summary", criteria_check, "insight", "references"]}


def note_content(text, *, compact_module=False):
    text = re.sub(r"(?ms)^```.*?^```\s*$", "", text)
    parts = sections(text, 2)
    summary = parts.get("摘要导读", "")
    summary = re.split(r'<div\s+class="raw-source-structure"|<div\s+data-questionnaire-module=|<!-- summary-insight-card:start -->|<div\s+class="raw-source-link"', summary, maxsplit=1)[0]
    root = Document(text).root
    insight = list(root.find(lambda e: e.attrs.get("data-summary-insight-body") == "true"))
    if len(insight) > 1:
        raise ValueError("成品有重复的小book提示卡")
    tables = list(root.find(lambda e: e.tag == "table" and any(c.tag == "tr" and "".join(t.text() for t in c.children if isinstance(t, Element) and t.tag == "th") == "DefinitionCriteriadetail" for c in e.children if isinstance(c, Element))))
    if compact_module and (tables or "定义" in parts or "Criteria" in parts):
        raise ValueError("简化模块成品不生成 Definition / Criteria / detail 定义表及其栏目")
    if not compact_module and len(tables) != 1:
        raise ValueError("成品必须有一份 Definition / Criteria / detail 定义表")
    criteria = {}
    for row in tables[0].children if tables else []:
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
    basis = parts.get("定义依据", "").split("<!-- definition-basis:end -->", 1)[0].strip()
    # Generated detail HTML is not part of the reference prose.
    references = re.split(r"<style\b|<table\b", references, maxsplit=1, flags=re.I)[0]
    intros = list(root.find(lambda e: e.attrs.get("data-criteria-intro") == "true"))
    if len(intros) > 1:
        raise ValueError("成品有重复的Criteria共同说明")
    return {"summary": visible_markup(summary), "criteria": criteria, "definition_basis": visible_markup(basis),
            "criteria_intro": intros[0].text() if intros else "",
            "summary_trees": rendered_summary_trees(summary),
            "questionnaire_flows": [e.text() for e in root.find(lambda e: e.attrs.get("data-questionnaire-flow") == "true")],
            "insight": "\n\n".join(e.text() for e in insight[0].find(
                lambda e: "summary-insight-text" in e.attrs.get("class", "").split()))
                if insight and list(insight[0].find(lambda e: e.attrs.get("data-summary-insight-paragraph") == "true"))
                else insight[0].text() if insight else "", "references": visible_markup(references),
            "questionnaire": questionnaire_content(text)}


def codebook_variables(codebook_path, expected=None):
    from check_definition_output import read_xlsx_rows
    rows = read_xlsx_rows(Path(codebook_path))
    column = rows[0].index("Variable")
    actual = [str(row[column]) for row in rows[1:]]
    if expected is not None and list(expected) != actual:
        raise ValueError("analysis_vars 与实际分析字典不一致")
    return actual


def validate_note(copy_path, note_path, codebook_path=None, record=None, analysis_vars=None):
    expected = analysis_vars
    if codebook_path:
        actual = codebook_variables(codebook_path, expected)
        expected = actual
    copy = read_copy(copy_path, expected, record)
    text = Path(note_path).read_text(encoding="utf-8-sig")
    insight_markup_content(text, copy["insight"])
    result = compare_content(copy, note_content(text, compact_module=copy["display_policy"]["compact_module"]))
    errors = summary_markup_errors(copy["summary"])
    if errors:
        raise ValueError("；".join(errors))
    summary = sections(text, 2).get("摘要导读", "")
    opening = re.split(r'<div\s+class="raw-source-structure"|<div\s+data-questionnaire-module=|<!-- summary-insight-card:start -->|<div\s+class="raw-source-link"', summary, maxsplit=1)[0]
    validate_summary_marks(copy["summary"], opening)
    return result


def validate_summary_marks(summary, rendered):
    summary = summary_prose(summary)
    expected = [("count" if re.fullmatch(r"[0-9]+", value) else "concept", value)
                for value in re.findall(r"\*\*([^*\n]+)\*\*", summary)]
    actual = []
    for element in Document(rendered).root.find(lambda e: e.attrs.get("data-summary-concept") == "true" or e.attrs.get("data-summary-count") == "true"):
        kind = "count" if element.attrs.get("data-summary-count") == "true" else "concept"
        actual.append((kind, element.text()))
    if expected != actual:
        raise ValueError(f"摘要语义标记与文案不一致：expected={expected!r}, actual={actual!r}")


def questionnaire_copy_errors(copy, record):
    """Check all source/copy differences before R generation, without editing either."""
    # Use the publication check's normalization, not a looser early-stage rule.
    from check_definition_readability import normalized_evidence_text, normalized_period

    if record.get("schema_version", 0) < 6:
        return []
    # Keep authored headings/notes intact for rendering. Only the checking view
    # uses the same scoped identities formerly carried by long headings.
    from copy import deepcopy
    copy = deepcopy(copy)
    for block in copy.get("questionnaire", {}).values():
        for question in block["questions"]:
            question["display_id"] = question["id"]
            question["id"] = question_identity(question["id"], question.get("notes", []))
    evidence = record.get("questionnaire_evidence")
    if not isinstance(evidence, list):
        return ["questionnaire_evidence must be a list"]
    validate_display_titles(evidence)
    periods = {}
    for period in copy.get("questionnaire", {}).values():
        for key in period_keys(period["label"], [x.get("period", "") for x in record.get("questionnaire_coverage", [])]):
            periods.setdefault(key, []).append(period)
    errors = []
    displayed_evidence = [item for item in evidence if item.get("display_required", True) is not False]
    for block in copy.get("questionnaire", {}).values():
        errors.extend(unverified_question_periods(block["label"], [q["id"] for q in block["questions"]],
                                                 displayed_evidence, block.get("module", ""),
                                                 [x.get("period", "") for x in record.get("questionnaire_coverage", [])]))
    cross_periods = [(p["label"], [(q["id"], [o["text"] for o in q["options"]]) for q in p["questions"]], p["design"], p.get("module", ""))
                     for p in copy.get("questionnaire", {}).values()]
    for item in evidence:
        question_id = str(item.get("question_id", ""))
        try:
            if not requires_questionnaire_display(item):
                continue
            if is_plain_paraphrase(item):
                validate_paraphrase_display(item, list(copy.get("questionnaire", {}).values()), normalized_evidence_text, displayed_evidence)
                continue
            display_text, display_instructions = display_question(item, record)
            expected_options, expected_jumps = display_answers(item, record)
        except ValueError as error:
            errors.append(str(error))
            continue
        text = normalized_evidence_text(display_text)
        if not question_id or not text or not isinstance(item.get("periods"), list):
            errors.append(f"{question_id or '?'}: missing question id/text/periods")
            continue
        for period in item["periods"]:
            label = f"{period}/{question_id}"
            matches = [p for p in periods.get(normalized_period(period), [])
                       if any(question_matches(q["id"], question_id, period, item) for q in p["questions"])
                       and (not item.get("questionnaire_module") or p.get("module") == item["questionnaire_module"])]
            if len(matches) != 1:
                errors.append(f"{label}: expected one questionnaire period")
                continue
            questions = [q for q in matches[0]["questions"] if question_matches(q["id"], question_id, period, item)]
            if len(questions) != 1:
                errors.append(f"{label}: expected one question")
                continue
            question = questions[0]
            ordered_questions = matches[0]["questions"]
            question_index = ordered_questions.index(question)
            next_identifier = ordered_questions[question_index + 1]["id"] if question_index + 1 < len(ordered_questions) else None
            validate_display_sequence(item, next_identifier, period, displayed_evidence)
            if text not in normalized_evidence_text(question["text"]):
                errors.append(f"{label}: incomplete or different question text")
            if text in normalized_evidence_text(matches[0]["design"]):
                errors.append(f"{label}: question duplicated in design note")
            visible = normalized_evidence_text(question["text"] + " " + question["condition"] + " " + matches[0]["design"] + " " + " ".join(question["instructions"]))
            for instruction in display_instructions:
                if normalized_evidence_text(instruction) not in visible:
                    errors.append(f"{label}: missing display instruction")
            options = question["options"]
            inherited_jumps = referenced_jump_options(question["display_id"],
                [(q["display_id"], q["options"], "\n".join(q["instructions"])) for q in matches[0]["questions"]])
            shared_text = matches[0]["design"] + "\n" + "\n".join(s for q in matches[0]["questions"] for s in q["instructions"] if s.startswith("共同跳题（"))
            shared_options, shared_routes = shared_question_info(shared_text, question["display_id"])
            referenced = referenced_options("\n".join(question["instructions"]), question["display_id"],
                [(q["display_id"], [o["text"] for o in q["options"]], "\n".join(q["instructions"])) for q in matches[0]["questions"]])
            option_text = shared_options or original_options(referenced or [o["text"] for o in options], matches[0]["design"] + "\n" + question["text"], period)
            try:
                cross_options = cross_period_options(question["text"] + "\n" + "\n".join(question["instructions"]),
                                                     matches[0]["label"], question_id,
                                                     [p[:3] for p in cross_periods if p[3] == matches[0].get("module", "")])
            except ValueError as error:
                errors.append(f"{label}: {error}")
                continue
            if cross_options:
                if options or referenced or shared_options:
                    errors.append(f"{label}: cross-period options repeated or ambiguous")
                    continue
                option_text = cross_options
            if item.get("response_type") == "closed_options":
                expected = [normalized(f"{o['value']} {o['label']}") for o in expected_options]
                if [normalized(o) for o in option_text] != expected:
                    errors.append(f"{label}: option values/labels/order differ; expected={expected!r}; actual={[normalized(o['text']) for o in options]!r}")
            for jump in expected_jumps:
                # Legends may restore source codes to label-only rendered rows.
                rows = options if referenced else [{"text": raw, "jump": option["jump"]} for option, raw in zip(options, option_text)]
                descriptions = jump_descriptions(jump["when"], rows, question["instructions"])
                descriptions += [r["destination"] for r in shared_routes if rendered_when_matches(jump["when"], r["when"])]
                descriptions += jump_descriptions(jump["when"], inherited_jumps, [])
                destination = display_route_destination(jump["destination"], item, record, period)
                if not any(route_matches(destination, s, period,
                                         allow_topic_exit=jump.get('presentation') == 'topic_exit')
                           for s in descriptions):
                    errors.append(f"{label}: route differs: {jump['when']} -> {jump['destination']}")
    return errors


def summary_markup_errors(summary):
    summary = summary_prose(summary)
    marks = re.findall(r"\*\*([^*\n]+)\*\*", summary)
    errors = []
    if not any(not re.fullmatch(r"\d+(?:\.\d+)?", mark.strip()) for mark in marks):
        errors.append("摘要结果名称缺少语义标记：按文案模板用 **名称** 标记实际结果或共享维度；数量标记不能代替结果名称。")
    if summary.count("**") % 2:
        errors.append("摘要语义标记必须成对。")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", required=True)
    parser.add_argument("--record")
    parser.add_argument("--process-dir", help="Save the submitted complete draft before checking; requires an active copy stage")
    parser.add_argument("--source-json")
    parser.add_argument("--note")
    parser.add_argument("--analysis-codebook")
    parser.add_argument("--analysis-vars", help="Comma-separated actual final result names, in output order")
    parser.add_argument("--export")
    args = parser.parse_args()
    try:
        if args.process_dir:
            from writing_evidence import capture_before_check
            capture_before_check(args.process_dir, args.copy)
        expected = args.analysis_vars.split(",") if args.analysis_vars is not None else None
        record = None
        if args.record:
            record = json.loads(Path(args.record).read_text(encoding="utf-8-sig"))
        if args.analysis_codebook:
            expected = codebook_variables(args.analysis_codebook, expected)
        copy = read_copy(args.copy, expected, record)
        errors = questionnaire_copy_errors(copy, record) if record else []
        # Only verify declared markup; semantic completeness remains an author's judgment.
        errors.extend(summary_markup_errors(copy["summary"]))
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
            return 1
        result = {"ok": True, "variables": copy["display_policy"]["analysis_vars"]}
        if args.source_json:
            actual = json.loads(Path(args.source_json).read_text(encoding="utf-8-sig"))
            result = compare_content(copy, actual, source=True)
        if args.note:
            result = validate_note(args.copy, args.note, args.analysis_codebook, record, expected)
        if args.export:
            Path(args.export).write_text(json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8")
        if record is not None:
            result["questionnaire_check"] = {
                "scope": "record_to_copy" if record.get("schema_version", 0) >= 6 else "not_checked_legacy_record",
                "original_material_check": "not_performed_by_this_command",
            }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
