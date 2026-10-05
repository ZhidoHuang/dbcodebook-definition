"""Explicit period coverage and shared option-code legends for questionnaire display."""
import re


def option_reference(text):
    matches = re.findall(r"选项与\s*([A-Za-z][A-Za-z0-9_]*)\s*相同。", text)
    if len(matches) > 1:
        raise ValueError("一道题不能引用多套选项")
    return matches[0] if matches else None


def referenced_options(text, question_id, entries):
    """Read one scoped statement below the question that displays the options.

    Entries contain id, option labels and optional visible instructions.
    Historical per-question references remain readable. Routes are not shared.
    """
    pattern = r"([A-Za-z][A-Za-z0-9_]*(?:\s*、\s*[A-Za-z][A-Za-z0-9_]*)*)\s*的选项与\s*([A-Za-z][A-Za-z0-9_]*)\s*相同。"
    ids = [entry[0] for entry in entries]
    targets = []
    covered = set()
    for entry in entries:
        visible = entry[2] if len(entry) > 2 else ""
        def expand_range(match):
            first, last = match.groups()
            start = re.fullmatch(r"([A-Za-z_]+)(\d+)", first)
            end = re.fullmatch(r"([A-Za-z_]+)(\d+)", last)
            if (not start or not end or start[1] != end[1] or len(start[2]) != len(end[2])
                    or not 0 < int(end[2]) - int(start[2]) <= 1000 or first != entry[0]):
                raise ValueError("连续选项范围须从本题开始，使用同一题号前缀和顺序：" + match[0])
            scope = [start[1] + str(i).zfill(len(start[2])) for i in range(int(start[2]) + 1, int(end[2]) + 1)]
            return "、".join(scope) + " 的选项与 " + first + " 相同。"
        visible = re.sub(r"([A-Za-z][A-Za-z0-9_]*)\s*[–—-]\s*([A-Za-z][A-Za-z0-9_]*)\s*的选项设置相同，(?:该范围内的后续题目|下列题目)不再逐一展开选项。", expand_range, visible)
        for match in re.finditer(pattern, visible):
            scope, source = match.groups()
            scope = [x.strip() for x in scope.split("、")]
            if source != entry[0] or not entry[1]:
                raise ValueError("共同选项说明须放在完整展示选项的题目下：" + source)
            if len(scope) != len(set(scope)) or covered.intersection(scope):
                raise ValueError("共同选项说明重复覆盖题目")
            if any(q not in ids or ids.index(q) <= ids.index(source) for q in scope):
                raise ValueError("共同选项说明须列出本时期后续题号：" + match[0])
            covered.update(scope)
            if question_id in scope:
                targets.append(source)
    target = option_reference(re.sub(pattern, "", text))
    if target:
        targets.append(target)
    if len(targets) > 1:
        raise ValueError("一道题不能引用多套选项")
    target = targets[0] if targets else None
    if not target:
        return []
    for entry in entries:
        identifier, options = entry[:2]
        if identifier == question_id:
            break
        if identifier == target:
            if not options:
                raise ValueError("引用题须完整展示选项：" + target)
            return options
    raise ValueError("选项须引用本时期前面已展示的题目：" + target)


def period_key(value):
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value)).casefold().replace("年", "").replace("期", "")


def referenced_jump_options(question_id, entries):
    """Share option-attached jumps only with explicitly named questions.

    entries: (id, option dictionaries, visible instructions). Reuse scope
    validation; ordinary option references never imply shared jumps.
    """
    scoped = []
    for identifier, options, instructions in entries:
        declarations = "\n".join(match.group(0).replace("的跳题规则与", "的选项与")
            for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*(?:\s*、\s*[A-Za-z][A-Za-z0-9_]*)*\s*的跳题规则与\s*[A-Za-z][A-Za-z0-9_]*\s*相同。", instructions))
        if declarations and not any(option.get("jump") for option in options):
            raise ValueError("引用题须在选项后完整展示跳题规则：" + identifier)
        scoped.append((identifier, options, declarations))
    return referenced_options("", question_id, scoped)


def period_keys(label):
    """Expand declared ranges; evidence checks must separately verify every period."""
    # Module titles are reader-facing labels, not additional period evidence.
    label = re.split(r"[:：]", label, maxsplit=1)[0]
    result = []
    for part in re.split(r"[；;、]", label):
        part = part.strip()
        match = re.fullmatch(r"Wave\s*(\d+)\s*[–—-]\s*(?:Wave\s*)?(\d+)", part, re.I)
        if match:
            start, end = map(int, match.groups())
            if not 0 < start <= end <= 100:
                raise ValueError("Invalid questionnaire Wave range: " + part)
            result.extend("wave" + str(i) for i in range(start, end + 1))
        elif re.fullmatch(r"\d{4}\s*年?\s*[–—-]\s*\d{4}\s*年?", part):
            start, end = map(int, re.findall(r"\d{4}", part))
            if not 1000 <= start <= end <= 9999:
                raise ValueError("Invalid questionnaire year range: " + part)
            result.extend(str(i) for i in range(start, end + 1))
        elif part:
            result.append(period_key(part))
    if len(result) != len(set(result)):
        raise ValueError("Duplicate questionnaire period: " + label)
    return result


def question_identifiers(title, period=None):
    """Resolve visible question aliases only inside their explicitly declared scope."""
    title = re.split(r"[:：]", str(title), maxsplit=1)[0].strip()
    if not re.search(r"[（(].*\d{4}.*[）)]", title):
        return [re.sub(r"\s|`", "", title)]
    result, covered = [], set()
    for part in re.split(r"[／/]", title):
        match = re.fullmatch(r"\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*[（(]([^）)]+)[）)]\s*", part)
        if not match:
            raise ValueError("Invalid scoped questionnaire question id: " + title)
        identifier, scope = match.groups()
        keys = period_keys(scope)
        if any(not re.fullmatch(r"\d{4}", key) for key in keys) or not keys:
            raise ValueError("Question id scope must name explicit years: " + title)
        if covered.intersection(keys):
            raise ValueError("Overlapping questionnaire question id scopes: " + title)
        covered.update(keys)
        if period is None or period_key(period) in keys:
            result.append(identifier)
    return result


def question_matches(title, identifier, period):
    # Q is a conventional displayed prefix for numeric questionnaire IDs.
    canonical = lambda value: re.sub(r"^Q(?=\d+(?:-\d+)*$)", "", str(value))
    return canonical(identifier) in [canonical(value) for value in question_identifiers(title, period)]


def unverified_question_periods(label, identifiers, evidence, module=""):
    """A declared continuous year block cannot add periods absent from source evidence."""
    if not re.search(r"\d{4}\s*年?\s*[–—-]\s*\d{4}", label):
        return []
    errors = []
    declared = set(period_keys(label))
    for title in identifiers:
        alias_scopes = re.findall(r"[（(]([^）)]*\d{4}[^）)]*)[）)]", re.split(r"[:：]", title, maxsplit=1)[0])
        if any(not set(period_keys(scope)) <= declared for scope in alias_scopes):
            errors.append(f"{title}: question id scope extends outside its questionnaire period")
    for period in period_keys(label):
        for title in identifiers:
            if not any(period_key(period) in {period_key(p) for p in item.get("periods", [])}
                       and question_matches(title, item.get("question_id", ""), period)
                       and (not item.get("questionnaire_module") or item["questionnaire_module"] == module)
                       for item in evidence):
                errors.append(f"{period}/{title}: declared questionnaire period has no matching source evidence")
    return errors


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
        if "=" not in body:
            codes = [entry.strip() for entry in body.split("、")]
            if len(codes) != len(actual) or any(not re.fullmatch(r"[^\s；;=、]+", code) for code in codes):
                raise ValueError("Original option code list must match the displayed option order/count")
            pairs = list(zip(codes, [s.strip() for s in actual]))
        else:
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
    # A label may end with 。 before the option separator; that punctuation
    # belongs to the label, not to the whole declaration.
    pattern = r"共同(选项|跳题)（([^）]+)）：(.+?)。(?![；;])"
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
