"""Resolve presentation from explicit topic kind and the actual result list."""

from __future__ import annotations

import re
import html
import json
import math
from pathlib import Path
from html.parser import HTMLParser


def remove_source_navigation(text):
    """Remove only the legacy generated source-navigation container."""
    class NavigationBlocks(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack, self.spans = [], []
            self.lines = [0] + [m.end() for m in re.finditer('\n', text)]

        def position(self):
            line, column = self.getpos()
            return self.lines[line - 1] + column

        def handle_starttag(self, tag, attrs):
            if tag in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
                return
            self.stack.append((tag, self.position(), 'raw-source-link' in dict(attrs).get('class', '').split()))

        def handle_endtag(self, tag):
            index = next((i for i in range(len(self.stack)-1, -1, -1) if self.stack[i][0] == tag), None)
            if index is None:
                return
            _, start, target = self.stack[index]
            del self.stack[index:]
            if target:
                end = text.index('>', self.position()) + 1
                fragment = text[start:end]
                if not re.search(r'dbCodeBook|dbcodebook|原始变量', fragment) or not re.search(r'目录|检索|进入查看|查看变量', fragment):
                    raise ValueError('未识别的来源导航内容')
                self.spans.append((start, end))

    parser = NavigationBlocks()
    parser.feed(text)
    if any(target for _, _, target in parser.stack):
        raise ValueError('来源导航容器没有闭合')
    spans = sorted(parser.spans)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError('来源导航容器重叠')
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    return text, len(spans)


def display_periods(database, observed=(), language=None, dataset_id=None):
    """Display catalogue plus genuine extra periods; never change data scope."""
    catalog = json.loads((Path(__file__).resolve().parents[1] / 'references/display-periods.json').read_text(encoding='utf-8'))
    periods = catalog[database.upper()]
    if database.upper() == 'NHIS':
        from nhis_export_contract import require_dataset
        periods = periods[require_dataset(dataset_id)]
        return list(dict.fromkeys(periods + list(observed)))
    if database.upper() == 'KLOSA' and language == 'en':
        periods = periods[:9]
    values = list(dict.fromkeys(periods + list(observed)))
    return sorted(values, key=lambda x: tuple(map(int, re.findall(r'\d+', x))))


def expand_period_tables(text, periods):
    """Reflow existing cells and add empty cells, preserving all existing values."""
    details = []
    def small(match):
        cells = re.findall(r"<td\b[^>]*class=['\"]dbcb-var-cycle-cell['\"][^>]*>.*?</td>", match[2], re.S)
        existing = {}
        for cell in cells:
            label = re.search(r"class=['\"]dbcb-var-cycle-label['\"][^>]*>(.*?)</span>", cell, re.S)
            if not label or html.unescape(label[1]) in existing:
                raise ValueError('周期格标签缺失或重复')
            existing[html.unescape(label[1])] = cell
        if not existing or set(existing) - set(periods):
            raise ValueError('展示范围不能删除已有周期')
        new = []
        for period in periods:
            label = html.escape(period, quote=True)
            new.append(existing.get(period) or (
                "<td class='dbcb-var-cycle-cell' style='background-color:#f7f6f4;' "
                f"title='{label}: 无数据'><span class='dbcb-var-cycle-label'>{label}</span>"
                "<span class='dbcb-var-cycle-count'></span></td>"))
        columns = math.ceil(len(periods) / (2 if len(periods) > 6 else 1))
        start = re.sub(r'min-width:max\(100%,\s*\d+px\)', f'min-width:max(100%, {columns * 42}px)', match[1])
        rows = ''.join('<tr>' + ''.join(new[i:i+columns]) + '</tr>' for i in range(0, len(new), columns))
        details.append({'kind': 'variable', 'before': list(existing), 'after': periods})
        return start + rows + match[3]
    text = re.sub(r"(<table\b[^>]*class=['\"]dbcb-var-cycle-table['\"][^>]*>)(.*?)(</table>)", small, text, flags=re.S)
    def overview(match):
        rows = re.findall(r'<tr\b[^>]*>.*?</tr>', match[2], re.S)
        if not rows:
            raise ValueError('组分周期表没有表头')
        headers = re.findall(r'<th\b[^>]*>(.*?)</th>', rows[0], re.S)
        if headers[:3] != ['Variable', 'original_vars', 'easylabel']:
            raise ValueError('未知组分表结构，不猜测列位置')
        old = [html.unescape(x) for x in headers[3:]]
        if not old or len(set(old)) != len(old) or set(old) - set(periods):
            raise ValueError('组分周期表不能删除已有周期')
        newrows = ['<tr>' + ''.join('<th>' + html.escape(h) + '</th>' for h in headers[:3] + periods) + '</tr>']
        for row in rows[1:]:
            if 'colspan=' in row:
                newrows.append(re.sub(r'colspan="\d+"', f'colspan="{3+len(periods)}"', row))
                continue
            cells = re.findall(r'<td\b[^>]*>.*?</td>', row, re.S)
            if len(cells) != len(headers):
                raise ValueError('组分周期表列数不一致')
            lookup = dict(zip(old, cells[3:]))
            newrows.append('<tr>' + ''.join(cells[:3]) + ''.join(lookup.get(p,
                '<td class="year-cell" style="background-color:#f4f2f0;color:#000;text-align:center;"></td>') for p in periods) + '</tr>')
        details.append({'kind': 'overview', 'before': old, 'after': periods})
        return match[1] + ''.join(newrows) + match[3]
    text = re.sub(r'(<table\b[^>]*class="heatmap-table"[^>]*>)(.*?)(</table>)', overview, text, flags=re.S)
    return text, details


def topic_kind(value="standard"):
    if value not in ("standard", "module", "questionnaire_module"):
        raise ValueError("topic_kind must be standard, module or questionnaire_module")
    return value


def copy_topic_kind(text):
    text = text.lstrip("\ufeff")
    if not re.match(r"\A---[ \t]*\r?\n", text):
        return "standard"
    front = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not front:
        raise ValueError("文案 frontmatter 缺少结束 ---")
    values = re.findall(r"(?m)^topic_kind\s*:\s*(.*?)\s*$", front[1])
    if len(values) > 1:
        raise ValueError("文案 topic_kind 重复")
    value = values[0] if values else "standard"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return topic_kind(value)


def _variables(value):
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError("analysis_vars must be a list of actual result names")
    names = list(value)
    if len(names) != len(set(names)):
        raise ValueError("analysis_vars contains duplicates")
    return names


def resolve_display_policy(text, analysis_vars=None, record=None):
    kind = copy_topic_kind(text)
    approved = None
    if record is not None:
        record_kind = topic_kind(record.get("topic_kind", "standard"))
        if ("module" if kind == "questionnaire_module" else kind) != record_kind:
            raise ValueError("文案 topic_kind 与来源方案的模块/普通定义身份不对应")
        if "approved_analysis_vars" in record:
            approved = _variables(record["approved_analysis_vars"])
    names = _variables(analysis_vars) if analysis_vars is not None else approved
    if approved is not None and names != approved:
        raise ValueError("实际 analysis_vars 与 approved_analysis_vars 的变量或顺序不一致")
    if kind in ("module", "questionnaire_module") and not names:
        raise ValueError("module 展示判断需要实际 analysis_vars，不能从标题或文案猜测数量")
    return {"topic_kind": kind, "analysis_vars": names or [],
            "compact_module": kind == "module" and len(names) > 10}
