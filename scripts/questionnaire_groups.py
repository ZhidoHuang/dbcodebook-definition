"""Explicit period coverage and shared option-code legends for questionnaire display."""
import re


def period_key(value):
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value)).casefold().replace("年", "").replace("期", "")


def period_keys(label):
    """Expand explicit Wave ranges or period lists; never infer intervening survey years."""
    result = []
    for part in re.split(r"[；;、]", label):
        part = part.strip()
        match = re.fullmatch(r"Wave\s*(\d+)\s*[–—-]\s*(?:Wave\s*)?(\d+)", part, re.I)
        if match:
            start, end = map(int, match.groups())
            if not 0 < start <= end <= 100:
                raise ValueError("Invalid questionnaire Wave range: " + part)
            result.extend("wave" + str(i) for i in range(start, end + 1))
        elif part:
            result.append(period_key(part))
    if len(result) != len(set(result)):
        raise ValueError("Duplicate questionnaire period: " + label)
    return result


def original_options(actual, design, period):
    """Resolve label-only options through an explicit, visible original-code legend.

    Without a legend, preserve the historical exact comparison. A legend applies
    only when its entire ordered label list matches the question's options.
    """
    legends = re.findall(r"原问卷选项编码（([^）]+)）：([^。\n]+)", design)
    matches = []
    for scope, body in legends:
        if period_key(period) not in period_keys(scope):
            continue
        pairs = []
        for entry in re.split(r"[；;]", body):
            pair = entry.strip().split("=", 1)
            if len(pair) != 2 or not all(p.strip() for p in pair):
                raise ValueError("Invalid original option legend: " + entry)
            pairs.append(tuple(p.strip() for p in pair))
        if [label for _, label in pairs] == [s.strip() for s in actual]:
            matches.append([code + " " + label for code, label in pairs])
    if len(matches) > 1:
        raise ValueError("Overlapping original option legends: " + str(period))
    return matches[0] if matches else actual


def shared_question_info(design, question_id=None, question_ids=None):
    """Read explicitly scoped common options/routes; never infer scope from prose.

    The same visible syntax survives Markdown and rendered HTML text extraction.
    Each declaration ends with 。; its question IDs are an explicit list.
    """
    options, routes = [], []
    pattern = r"共同(选项|跳题)（([^）]+)）：([^。]+)。"
    for match in re.finditer(pattern, design):
        kind, scope, body = match.groups()
        ids = [x.strip().strip('`') for x in re.split(r'[、,，；;]', scope)]
        if not ids or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', x) for x in ids) or len(ids) != len(set(ids)):
            raise ValueError('共同说明须逐项列出题号：' + scope)
        if question_ids is not None and not set(ids) <= set(question_ids):
            raise ValueError('共同说明包含本期未展示的题号：' + scope)
        if kind == '选项':
            pairs = [x.strip().split('=', 1) for x in re.split(r'[；;]', body)]
            if any(len(x) != 2 or not all(v.strip() for v in x) for x in pairs):
                raise ValueError('共同选项须写成编码=标签：' + body)
            if question_id in ids:
                if options:
                    raise ValueError('共同选项重复覆盖题目：' + question_id)
                options = [a.strip() + ' ' + b.strip() for a, b in pairs]
        else:
            route = re.split(r'\s*(?:→|->)\s*', body, maxsplit=1)
            if len(route) != 2 or not all(x.strip() for x in route):
                raise ValueError('共同跳题须写明完整条件和去向：' + body)
            if question_id in ids:
                routes.append({'when': route[0].strip(), 'destination': route[1].strip()})
    # Recognizable declarations must not silently fall back to ordinary prose.
    if len(re.findall(r'共同(?:选项|跳题)（', design)) != len(list(re.finditer(pattern, design))):
        raise ValueError('共同说明格式不完整，须用句号结束')
    return options, routes
