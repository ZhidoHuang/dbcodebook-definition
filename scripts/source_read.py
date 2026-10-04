"""Prepare bounded, read-only CHARLS directory/search/detail UI actions."""
import json
from pathlib import Path


def browser_code(action, url, database):
    if database != "charls":
        raise ValueError("source-read is currently verified for CHARLS only")
    kind = action.get("kind")
    if kind not in {"directory", "search", "detail"}:
        raise ValueError("kind must be directory, search or detail")
    if kind == "directory":
        path = action.get("path", [])
        if not isinstance(path, list) or len(path) > 6 or any(not isinstance(x, str) or not x.strip() or any(c in x for c in "[]") for x in path):
            raise ValueError("path must contain up to six nonempty directory names")
    elif kind == "search":
        if not isinstance(action.get("query"), str) or len(action["query"].strip()) < 2:
            raise ValueError("query must contain at least two characters")
    else:
        for key in ("variable", "file"):
            if not isinstance(action.get(key), str) or not action[key].strip() or any(c in action[key] for c in "[]"):
                raise ValueError(f"detail requires an unambiguous {key}")
        periods = action.get("periods")
        if not isinstance(periods, list) or not 1 <= len(periods) <= 6 or any(not isinstance(x, str) or not x.strip() for x in periods) or len(set(periods)) != len(periods):
            raise ValueError("detail requires one to six distinct period strings")
    helper = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return "async page => await (" + helper + ")(page," + json.dumps({**action, "url": url}, ensure_ascii=False) + ")"
