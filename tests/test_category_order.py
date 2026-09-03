from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_definition_output.py"


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_definition_output_for_test", CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load check_definition_output.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_case(checker, html: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="category_order_") as tmp:
        root = Path(tmp)
        (root / "topic_detail.html").write_text(html, encoding="utf-8")
        results: list[dict] = []
        checker.check_category_order(root, html, results)
        return bool(results and results[-1]["ok"])


def main() -> int:
    checker = load_checker()

    defined_only = (
        '<a href="#cat-defined">Defined variables</a>'
        '<summary>Defined variables</summary>'
    )
    assert run_case(checker, defined_only) is True

    source_then_defined = (
        '<a href="#cat-source">Source variables</a>'
        '<a href="#cat-defined">Defined variables</a>'
        '<summary>Source variables</summary>'
        '<summary>Defined variables</summary>'
    )
    assert run_case(checker, source_then_defined) is True

    source_only = (
        '<a href="#cat-source">Source variables</a>'
        '<summary>Source variables</summary>'
    )
    assert run_case(checker, source_only) is False

    print("category order fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
