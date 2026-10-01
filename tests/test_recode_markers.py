"""New output variables must not carry an in-place recode marker."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_definition_output import check_public_code_outline

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    script = root / "define.R"
    for kind in ("chr", "num"):
        for target, marker, expected_error in [("raw", True, False), ("result", True, True), ("result", False, False)]:
            code = (f"# recode.{kind}(data$raw)\n" if marker else "")
            code += f'data${target} <- case_when(\n  data$raw == "Yes" ~ 1,\n  TRUE ~ NA_real_\n)\n'
            script.write_text(code + "# 输出\n", encoding="utf-8")
            results = []
            check_public_code_outline(root, "### 2-代码材料\n\n```r\n" + code + "```", results, "ELSA", script)
            found = "marker target differs from assignment" in str(results)
            assert found == expected_error, results
print("RECODE_MARKERS_PASS")
