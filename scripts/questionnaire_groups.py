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
