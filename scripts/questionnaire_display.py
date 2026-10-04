"""Separate source quotations from reader-facing questionnaire text.

Checks compare registered display strings; they do not certify translation quality.
Legacy records without a display policy retain their original comparison behavior.
"""
import re


POLICY = "chinese_v1"


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
