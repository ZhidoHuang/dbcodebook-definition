"""Build reference-list presentation from one material per nonempty line."""

import re


def reference_items(text):
    items = []
    for line in str(text).splitlines():
        line = re.sub(r"^\s*>\s?", "", line).strip()
        line = re.sub(r"^(?:\d+[.)]|\[\d+\]|[-*])\s+", "", line)
        if line:
            items.append(line)
    return items


def render_references(text):
    return "\n".join(f"> {i}. {item}" for i, item in enumerate(reference_items(text), 1))
