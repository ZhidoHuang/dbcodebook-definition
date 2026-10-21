"""Resolve presentation from explicit topic kind and the actual result list."""

from __future__ import annotations

import re


def topic_kind(value="standard"):
    if value not in ("standard", "module"):
        raise ValueError("topic_kind must be standard or module")
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
        if kind != topic_kind(record.get("topic_kind", "standard")):
            raise ValueError("文案 topic_kind 与来源方案不一致")
        if "approved_analysis_vars" in record:
            approved = _variables(record["approved_analysis_vars"])
    names = _variables(analysis_vars) if analysis_vars is not None else approved
    if approved is not None and names != approved:
        raise ValueError("实际 analysis_vars 与 approved_analysis_vars 的变量或顺序不一致")
    if kind == "module" and not names:
        raise ValueError("module 展示判断需要实际 analysis_vars，不能从标题或文案猜测数量")
    return {"topic_kind": kind, "analysis_vars": names or [],
            "compact_module": kind == "module" and len(names) > 30}
