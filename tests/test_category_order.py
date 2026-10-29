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


def run_case(checker, html: str, note: str | None = None) -> bool:
    with tempfile.TemporaryDirectory(prefix="category_order_") as tmp:
        root = Path(tmp)
        (root / "topic_detail.html").write_text(html, encoding="utf-8")
        results: list[dict] = []
        checker.check_category_order(root, html if note is None else note, results)
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
    # Raw sources are no longer displayed, even alongside defined results.
    assert run_case(checker, source_then_defined) is False

    source_only = (
        '<a href="#cat-source">Source variables</a>'
        '<summary>Source variables</summary>'
    )
    assert run_case(checker, source_only) is False

    def marked_groups(groups, detail_groups=None):
        def tag(kind, group, role):
            return (f'<{kind} data-component-group="{group}" '
                    f'data-variable-role="{role}">{group}</{kind}>')
        return (
            ''.join(tag('a', group, role) for group, role in groups)
            + ''.join(tag('summary', group, role)
                      for group, role in (groups if detail_groups is None else detail_groups))
        )

    module = marked_groups([('Diabetes Module', 'defined')])
    assert run_case(checker, module) is True
    groups = [('Frailty Index·Components', 'component'), ('Frailty Index', 'defined')]
    components_and_result = marked_groups(groups)
    assert run_case(checker, components_and_result) is True
    wrong_order = marked_groups(groups, list(reversed(groups)))
    assert run_case(checker, wrong_order, components_and_result) is False
    assert run_case(checker, components_and_result, wrong_order) is False
    assert run_case(checker, marked_groups([('Diabetes Module', 'source')])) is False

    print("category order fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
