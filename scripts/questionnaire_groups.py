"""Explicit period coverage and shared option-code legends for questionnaire display."""
import re


def option_reference(text):
    text = re.sub(r"`([^`]+)`", r"\1", text)
    matches = re.findall(r"选项与\s*([A-Za-z][A-Za-z0-9_]*)\s*相同。", text)
    if len(matches) > 1:
        raise ValueError("一道题不能引用多套选项")
    return matches[0] if matches else None


def referenced_options(text, question_id, entries):
    """Read one scoped statement below the question that displays the options.

    Entries contain id, option labels and optional visible instructions.
    Historical per-question references remain readable. Routes are not shared.
    """
    # Compare visible identifiers; keep authored inline code in the output.
    text = re.sub(r"`([^`]+)`", r"\1", text)
    pattern = r"([A-Za-z][A-Za-z0-9_]*(?:\s*、\s*[A-Za-z][A-Za-z0-9_]*)*)\s*的选项与\s*([A-Za-z][A-Za-z0-9_]*)\s*相同。"
    ids = [entry[0] for entry in entries]
    targets = []
    covered = set()
    for entry in entries:
        visible = entry[2] if len(entry) > 2 else ""
        visible = re.sub(r"`([^`]+)`", r"\1", visible)
        def expand_range(match):
            first, last = match.groups()
            start = re.fullmatch(r"([A-Za-z_]+)(\d+)", first)
            end = re.fullmatch(r"([A-Za-z_]+)(\d+)", last)
            if (not start or not end or start[1] != end[1] or len(start[2]) != len(end[2])
                    or not 0 < int(end[2]) - int(start[2]) <= 1000 or first != entry[0]):
                raise ValueError("连续选项范围须从本题开始，使用同一题号前缀和顺序：" + match[0])
            scope = [start[1] + str(i).zfill(len(start[2])) for i in range(int(start[2]) + 1, int(end[2]) + 1)]
            return "、".join(scope) + " 的选项与 " + first + " 相同。"
        visible = re.sub(r"([A-Za-z][A-Za-z0-9_]*)\s*[–—-]\s*([A-Za-z][A-Za-z0-9_]*)\s*的选项设置相同，(?:(?:该范围内的后续题目|下列题目)不再逐一展开选项|后续题目仅列有跳转的选项)。", expand_range, visible)
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


def validate_shared_option_rows(referenced, rows):
    """Additional rows must be distinct shared answers with their own jumps."""
    normalize = lambda text: re.sub(r"[\s`]+", "", str(text))
    allowed = {normalize(text) for text in referenced}
    seen = set()
    for row in rows:
        key = normalize(row["text"])
        if key not in allowed or key in seen or not row.get("jump", "").strip():
            raise ValueError("引用选项与单题选项重复或不一致：仅可补列带跳转的共用选项")
        seen.add(key)


def period_key(value):
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(value)).casefold().replace("年", "").replace("期", "")


def referenced_jump_options(question_id, entries):
    """Share option-attached jumps only with explicitly named questions.

    entries: (id, option dictionaries, visible instructions). Reuse scope
    validation; ordinary option references never imply shared jumps.
    """
    scoped = []
    for identifier, options, instructions in entries:
        instructions = re.sub(r"`([^`]+)`", r"\1", instructions)
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
    if not re.search(r"[（(][^）)]*(?:\d{4}|Wave\s*\d+)[^）)]*[）)]", title, re.I):
        return [re.sub(r"\s|`", "", title)]
    result, covered = [], set()
    for part in re.split(r"[／/]", title):
        match = re.fullmatch(r"\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*[（(]([^）)]+)[）)]\s*", part)
        if not match:
            raise ValueError("Invalid scoped questionnaire question id: " + title)
        identifier, scope = match.groups()
        keys = period_keys(scope)
        if not keys or not (all(re.fullmatch(r"\d{4}", key) for key in keys)
                            or all(re.fullmatch(r"wave[1-9]\d*", key) for key in keys)):
            raise ValueError("Question id scope must name explicit years or Waves: " + title)
        if covered.intersection(keys):
            raise ValueError("Overlapping questionnaire question id scopes: " + title)
        covered.update(keys)
        if period is None or period_key(period) in keys:
            result.append(identifier)
    return result


def question_identity(title, notes):
    """Resolve a visible period mapping for checking, without changing its display."""
    text = "\n".join(notes) if isinstance(notes, list) else str(notes)
    mappings = re.findall(r"原问卷变量名题号：([^。\n]+)", text)
    if not mappings:
        return title
    if len(mappings) != 1:
        raise ValueError("Duplicate questionnaire identifier note")
    parts = []
    for entry in re.split(r"[；;]", mappings[0].replace("`", "")):
        match = re.fullmatch(r"\s*(.+?)\s+([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*", entry)
        if not match:
            raise ValueError("Questionnaire identifier note needs a period and original identifier")
        scope, identifier = match.groups()
        parts.append(f"{identifier}（{scope}）")
    resolved = "／".join(parts)
    identifiers = question_identifiers(resolved)
    if question_identifiers(title) != [title.strip()] or title.strip() not in identifiers:
        raise ValueError("Question title must be one of the original identifiers in its note")
    return resolved


def validate_display_titles(evidence):
    """Check internal merged-title links without publishing original ID mappings."""
    by_id = {}
    for item in evidence:
        by_id.setdefault(item.get("evidence_id"), []).append(item)
    for item in evidence:
        display = item.get("display", {})
        title, source_id = display.get("question_title"), display.get("question_title_source")
        if title is None and source_id is None:
            continue
        anchors = by_id.get(source_id, [])
        if not isinstance(title, str) or not title.strip() or len(anchors) != 1:
            raise ValueError("Merged question title requires one verified source evidence_id")
        anchor = anchors[0]
        if title not in [anchor.get("question_id"), anchor.get("question_variable")]:
            raise ValueError("Merged question title must retain its first-period original identifier")
        if anchor.get("questionnaire_module", "") != item.get("questionnaire_module", ""):
            raise ValueError("Merged question title cannot cross questionnaire groups")
        if not anchor.get("display_required", True) or not anchor.get("periods") or not item.get("periods"):
            raise ValueError("Merged question title source must be displayed with verified periods")
        order = lambda p: int(re.search(r"\d+", period_key(p))[0])
        if min(map(order, anchor["periods"])) > min(map(order, item["periods"])):
            raise ValueError("Merged question title source cannot be a later period")
        stem = lambda q: re.sub(r"\s+", "", q.get("display", {}).get("question_text", q.get("question_text", "")))
        if not stem(anchor) or stem(anchor) != stem(item):
            raise ValueError("Merged question title requires the same displayed question text")


def question_matches(title, identifier, period, evidence=None):
    """Match source IDs or explicitly evidenced variable names within a period."""
    canonical = lambda value: re.sub(r"^Q(?=\d+(?:-\d+)*$)", "", str(value))
    variable = ""
    if evidence is not None and evidence.get("question_variable") is not None:
        variable = evidence["question_variable"]
        if not isinstance(variable, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", variable):
            raise ValueError("question_variable must be a verified original variable name")
        if not str(evidence.get("locator", "")).strip():
            raise ValueError("question_variable requires its evidence locator")
        if period_key(period) not in {period_key(p) for p in evidence.get("periods", [])}:
            return False
    # Numeric-only originals may show their separately verified variable in parentheses.
    annotated = re.fullmatch(r"(?:第\s*)?(\d+(?:-\d+)*)(?:\s*题)?\s*[（(]变量\s*`?([A-Za-z_][A-Za-z0-9_.]*)`?[）)]", str(title).strip())
    if annotated:
        return bool(variable and annotated[2] == variable and canonical(annotated[1]) == canonical(identifier))
    identifiers = question_identifiers(title, period)
    if evidence is not None:
        display = evidence.get("display", {})
        if display.get("question_title_source"):
            return (display.get("question_title") in identifiers
                    and period_key(period) in {period_key(p) for p in evidence.get("periods", [])})
    return any(canonical(value) == canonical(identifier) or (variable and value == variable)
               for value in identifiers)


def unverified_question_periods(label, identifiers, evidence, module="", survey_periods=None):
    """Validate ranges against recorded survey periods, then each question's evidence."""
    has_wave_alias = any(re.search(r"[（(][^）)]*Wave\s*\d+", str(title), re.I)
                         for title in identifiers)
    if not re.search(r"\d{4}\s*年?\s*[–—-]\s*\d{4}", label) and not has_wave_alias:
        return []
    errors = []
    declared = set(period_keys(label))
    checked = set(declared)
    known = {period_key(p) for p in (survey_periods or [])}
    for match in re.finditer(r"(\d{4})\s*年?\s*[–—-]\s*(\d{4})", label):
        start, end = map(int, match.groups())
        years = sorted(int(p) for p in known if re.fullmatch(r"\d{4}", p) and start <= int(p) <= end)
        if years and years[0] == start and years[-1] == end:
            gaps = {b-a for a,b in zip(years, years[1:])}
            if len(gaps) <= 1:
                checked.difference_update(str(y) for y in range(start, end+1))
                checked.update(map(str, years))
            else:
                errors.append(f"{match[0]}: irregular survey periods must be listed explicitly")
    for title in identifiers:
        alias_scopes = re.findall(r"[（(]([^）)]*(?:\d{4}|Wave\s*\d+)[^）)]*)[）)]", re.split(r"[:：]", title, maxsplit=1)[0], re.I)
        if any(not set(period_keys(scope)) <= declared for scope in alias_scopes):
            errors.append(f"{title}: question id scope extends outside its questionnaire period")
    for period in sorted(checked):
        for title in identifiers:
            if not any(period_key(period) in {period_key(p) for p in item.get("periods", [])}
                       and question_matches(title, item.get("question_id", ""), period, item)
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
    # A group can state its changed periods once and use a remainder clause.
    for scope, body in re.findall(r"((?:Wave\s*\d|\d{4})[^。\n；]*?)\s*的选项编码为\s*([^。\n]+)", design, re.I):
        clauses = re.split(r"[；;]\s*其余时期(?:的选项编码)?为\s*", body)
        legends.append((scope.strip(), clauses[0].replace("、", "；")))
        if len(clauses) == 2:
            legends.append(("其余时期", clauses[1].replace("、", "；")))
        elif len(clauses) > 2:
            raise ValueError("Duplicate remainder option legend")
    matches, defaults = [], []
    for scope, body in legends:
        if scope != "其余时期" and period_key(period) not in period_keys(scope):
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
            (defaults if scope == "其余时期" else matches).append([code + " " + label for code, label in pairs])
    if len(defaults) > 1:
        raise ValueError("Overlapping remainder option legends: " + str(period))
    matches = matches or defaults
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
