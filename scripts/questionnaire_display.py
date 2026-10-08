"""Separate source quotations from reader-facing questionnaire text.

Checks compare registered display strings; they do not certify translation quality.
Legacy records without a display policy retain their original comparison behavior.
"""
import re
from questionnaire_groups import (period_keys, original_options,
    shared_question_info as _shared_question_info, referenced_options as _referenced_options,
    referenced_jump_options as _referenced_jump_options)


POLICY = "chinese_v1"


def requires_questionnaire_display(item):
    """Research evidence stays registered even when it adds no reader-facing value."""
    required = item.get("display_required", True)
    if not isinstance(required, bool):
        raise ValueError("display_required must be true or false")
    if not required:
        reason = item.get("display_omission_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("display_omission_reason is required when display_required is false")
        if item.get("rendered_in_copy") is not False:
            raise ValueError("omitted questionnaire evidence must have rendered_in_copy=false")
    return required


def is_plain_paraphrase(item):
    mode = item.get("question_text_mode", "verified_quote")
    if mode not in ("verified_quote", "plain_paraphrase"):
        raise ValueError("question_text_mode must be verified_quote or plain_paraphrase")
    return mode == "plain_paraphrase"


def validate_paraphrase(item):
    """The exception changes available wording, not the required factual evidence."""
    if item.get("question_text_complete") is not False:
        raise ValueError("plain_paraphrase requires question_text_complete=false")
    for field in ("question_text", "paraphrase_reason", "applicable_population", "recall_period"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("plain_paraphrase requires " + field)
    for field in ("question_text", "paraphrase_reason"):
        if not re.search(r"[\u3400-\u9fff]", item[field]):
            raise ValueError(field + " must contain Chinese text")
    if not isinstance(item.get("question_id", ""), str):
        raise ValueError("question_id must be text; leave unknown identifiers empty")


def validate_paraphrase_display(item, blocks, normalize, evidence=None):
    """Blocks carry label/module/design, shared by copy and rendered-note checks."""
    validate_paraphrase(item)
    periods = item.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ValueError("plain_paraphrase requires periods")
    supported = set()
    for other in evidence or [item]:
        if (other.get("question_text_mode") == "plain_paraphrase"
                and other.get("source_group") == item.get("source_group")
                and other.get("questionnaire_module") == item.get("questionnaire_module")
                and normalize(other.get("question_text", "")) == normalize(item["question_text"])
                and normalize(other.get("paraphrase_reason", "")) == normalize(item["paraphrase_reason"])):
            for period in other.get("periods", []):
                supported.update(period_keys(str(period)))
    for period in periods:
        keys = set(period_keys(str(period)))
        matches = [block for block in blocks
                   if keys.intersection(period_keys(block["label"]))
                   and (not item.get("questionnaire_module") or block.get("module") == item["questionnaire_module"])
                   and normalize(item["question_text"]) in normalize(block["design"])
                   and normalize(item["paraphrase_reason"]) in normalize(block["design"])]
        if len(matches) != 1:
            raise ValueError(f"{period}: expected one design with verified paraphrase and reason")
        if not set(period_keys(matches[0]["label"])).issubset(supported):
            raise ValueError(f"{period}: paraphrase includes unverified periods")
        if matches[0].get("design_count", 1) != 1 or matches[0].get("design_title") not in ("问卷设计", "问卷设计变化"):
            raise ValueError(f"{period}: expected exactly one questionnaire design note")
        design = matches[0]["design"]
        if not re.search(r"题意概括\s*[:：]", design) or not re.search(r"未取得完整原题的原因\s*[:：]", design):
            raise ValueError(f"{period}: paraphrase and reason must be explicitly labelled")


def display_question(item, record):
    policy = record.get("questionnaire_display_policy")
    if policy not in (None, POLICY):
        raise ValueError(f"unknown questionnaire_display_policy: {policy}")
    display = item.get("display")
    if display is None and policy is None:
        return str(item.get("question_text", "")), []
    if not isinstance(display, dict):
        raise ValueError(f"{item.get('question_id', '?')}: display is required")
    text = display.get("question_text")
    instructions = display.get("instructions", [])
    if not isinstance(text, str) or not re.search(r"[\u3400-\u9fff]", text):
        raise ValueError("display.question_text must contain the Chinese question")
    if not isinstance(instructions, list) or any(
        not isinstance(line, str) or not re.search(r"[\u3400-\u9fff]", line)
        for line in instructions
    ):
        raise ValueError("display.instructions must be a list of Chinese instructions")
    return text, instructions


def _chinese(text, field):
    if not isinstance(text, str) or not re.search(r"[\u3400-\u9fff]", text):
        raise ValueError(f"{field} must contain Chinese text")


def _condition_ids(text):
    # DN005_OtherCountry and DN005 denote the same question, DN0050 does not.
    return {identifier for identifier in re.findall(r"(?<![A-Za-z0-9_])([A-Z]+\d+)(?=_|[^A-Za-z0-9_]|$)", str(text))
            if not re.fullmatch(r"W\d+", identifier)}


def _destination_ids(text):
    # MN identifiers denote program flags, not destination questions.
    return {identifier for identifier in _condition_ids(text) if not re.fullmatch(r"MN\d+", identifier)}


def _question_alias(identifier):
    match = re.fullmatch(r"([A-Z]+\d+)(?:_[A-Za-z0-9_]+)?", str(identifier))
    return match[1] if match else str(identifier)


def _alias_declarations(text):
    # Change reference identifiers only, never quoted questions or CAPI routes.
    alias_ids = lambda value: re.sub(r"(?<![A-Za-z0-9_])[A-Z]+\d+_[A-Za-z0-9_]+(?![A-Za-z0-9_])", lambda m: _question_alias(m[0]), value)
    text = re.sub(r"[^。\n]*(?:选项|跳题规则)[^。\n]*相同。", lambda m: alias_ids(m[0]), text)
    return re.sub(r"(共同(?:选项|跳题)（)([^）]+)(）)",
                  lambda m: m[1] + alias_ids(m[2]) + m[3], text)


def _alias_entries(entries):
    identifiers = [_question_alias(entry[0]) for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("ambiguous questionnaire short question ids")
    return [(identifiers[i], entry[1], _alias_declarations(entry[2]) if len(entry) > 2 else "")
            for i, entry in enumerate(entries)]


def referenced_options(text, question_id, entries):
    return _referenced_options(_alias_declarations(text), _question_alias(question_id), _alias_entries(entries))


def referenced_jump_options(question_id, entries):
    return _referenced_jump_options(_question_alias(question_id), _alias_entries(entries))


def shared_question_info(design, question_id=None, question_ids=None):
    aliases = None if question_ids is None else [_question_alias(q) for q in question_ids]
    if aliases is not None and len(aliases) != len(set(aliases)):
        raise ValueError("ambiguous questionnaire short question ids")
    return _shared_question_info(_alias_declarations(design),
                                 None if question_id is None else _question_alias(question_id), aliases)


def _trigger_codes(text):
    return re.findall(r"(?<![A-Za-z0-9_])(?:a)?(-?\d+)(?![A-Za-z0-9_])", str(text))


def display_answers(item, record):
    """Optional translated answers: preserve source codes and branch identity.

    Older chinese_v1 records keep their original answers when a new field is
    absent. Once present, a field must be complete; never silently fall back.
    Source quotations and CAPI text are read without mutation.
    """
    policy = record.get("questionnaire_display_policy")
    if policy not in (None, POLICY):
        raise ValueError(f"unknown questionnaire_display_policy: {policy}")
    display = item.get("display") or {}
    source_options = item.get("options", [])
    source_jumps = item.get("skip_logic", [])
    options, jumps = source_options, source_jumps
    if "options" in display:
        options = display["options"]
        if not isinstance(options, list) or len(options) != len(source_options):
            raise ValueError("display.options must preserve all source options")
        for i, (translated, source) in enumerate(zip(options, source_options)):
            if not isinstance(translated, dict) or str(translated.get("value")) != str(source["value"]):
                raise ValueError(f"display.options[{i}] changes source code/order")
            _chinese(translated.get("label"), f"display.options[{i}].label")
    if "skip_logic" in display:
        jumps = display["skip_logic"]
        if not isinstance(jumps, list) or len(jumps) != len(source_jumps):
            raise ValueError("display.skip_logic must preserve all source branches")
        indices = [j.get("source_index") if isinstance(j, dict) else None for j in jumps]
        if any(type(i) is not int for i in indices) or sorted(indices) != list(range(len(source_jumps))):
            raise ValueError("display.skip_logic source_index must cover each source branch once")
        for jump in jumps:
            i = jump["source_index"]
            source = source_jumps[i]
            _chinese(jump.get("when"), f"display.skip_logic[{i}].when")
            _chinese(jump.get("destination"), f"display.skip_logic[{i}].destination")
            if _destination_ids(source["destination"]) != _destination_ids(jump["destination"]):
                raise ValueError(f"display.skip_logic[{i}] changes destination question id")
            if _trigger_codes(source["when"]) != _trigger_codes(jump["when"]):
                raise ValueError(f"display.skip_logic[{i}] changes trigger codes")
            own_id = _question_alias(item.get("question_id", ""))
            if _condition_ids(source["when"]) - {own_id} != _condition_ids(jump["when"]) - {own_id}:
                raise ValueError(f"display.skip_logic[{i}] changes trigger question/flag id")
    return options, jumps


def rendered_when_matches(when, text):
    """Conjunction fragments must coexist locally; do not infer semantics."""
    normalize = lambda value: re.sub(r"[\s`“”‘’]+", "", str(value))
    fragments = [normalize(part) for part in str(when).split("，且")]
    return all(fragments) and all(part in normalize(text) for part in fragments)


def jump_descriptions(when, options, instructions):
    """A whole option row or one same-question instruction is the unit."""
    result = [option["jump"] for option in options
              if rendered_when_matches(when, option["text"] + " " + option["jump"])]
    result.extend(line for line in instructions
                  if not line.strip().startswith("共同跳题（") and rendered_when_matches(when, line))
    return result


def cross_period_options(text, current_label, question_id, periods):
    """Resolve explicit same-question references to earlier period blocks only.

    periods contains (label, [(id, rendered option strings)], design). Only
    options are returned: this operation NEVER inherits option-attached jumps.
    """
    pattern = (r"([A-Za-z][A-Za-z0-9_]*)\s*的[^。\n]*?选项与\s*"
               r"(Wave\s*\d+[^。\n]*?)\s*的\s*([A-Za-z][A-Za-z0-9_]*)\s*相同。")
    matches = list(re.finditer(pattern, text))
    if not matches:
        # A recognizable unsupported Wave reference must not fall through.
        if re.search(r"选项与\s*Wave\b", text):
            raise ValueError("invalid cross-period option reference")
        return []
    if len(matches) != 1:
        raise ValueError("ambiguous cross-period option references")
    referring, scope, target = matches[0].groups()
    alias = _question_alias(question_id)
    if _question_alias(referring) != alias or _question_alias(target) != alias:
        raise ValueError("cross-period reference must name the same question")
    requested = period_keys(scope)
    current_indices = [i for i, (label, _, _) in enumerate(periods) if label == current_label]
    if len(current_indices) != 1:
        raise ValueError("ambiguous current questionnaire period")
    previous = periods[:current_indices[0]]
    candidates = []
    for key in requested:
        covered = [(label, entries, design) for label, entries, design in previous
                   if key in period_keys(label) and any(_question_alias(identifier) == alias for identifier, _ in entries)]
        if len(covered) != 1:
            raise ValueError("cross-period reference requires one earlier period: " + key)
        label, entries, design = covered[0]
        targets = [(identifier, options) for identifier, options in entries if _question_alias(identifier) == alias]
        if len(targets) != 1:
            raise ValueError("cross-period reference requires one earlier question: " + target)
        target_id, target_options = targets[0]
        common, _ = shared_question_info(design, target_id, [identifier for identifier, _ in entries])
        options = common or original_options(target_options, design, key)
        if not options:
            raise ValueError("cross-period target must display complete options")
        candidates.append(options)
    normalize = lambda values: [re.sub(r"\s+", "", v) for v in values]
    if not candidates or any(normalize(c) != normalize(candidates[0]) for c in candidates[1:]):
        raise ValueError("cross-period option contents differ")
    return candidates[0]
