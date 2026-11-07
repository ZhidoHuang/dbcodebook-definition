"""Both public-R checks detect annotated, grouped and misleading recode markers."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_definition_output import check_public_code_outline

runner = (ROOT / "scripts/run_r_definition.ps1").read_text(encoding="utf-8")
marker_block = runner[runner.index('$publicLines = $publicSource -split'):runner.index('\nif ($publicIssues.Count -gt 0)', runner.index('$publicLines = $publicSource -split'))]
cases = [
    ("# 先用 recode.chr(data$x) 查看标签，随后按方案核对。\ntable(data$x)\n", False),
    ('# recode.chr(data$raw): label\ndata$raw <- case_when(\n  data$raw == "Yes" ~ 1,\n  TRUE ~ NA_real_\n)\n', False),
    ('# recode.chr(data$raw)\ndata$raw <- case_when(\n  # category\n  data$raw == 1 ~ 2\n)\n', False),
    ('# recode.num(data$raw)\ndata$raw <- ifelse(data$raw > 0, 1, 0)\n', False),
    ('# recode.chr(data$raw): label\ndata$result <- case_when(data$raw == "Yes" ~ 1)\n', True),
    ('# recode.chr(data$a) recode.chr(data$b): labels\ndata$a <- case_when(data$a == "x" ~ 1)\ndata$b <- case_when(data$b == "x" ~ 1)\n', True),
    ('# recode.num(data$raw)\ndata$raw <- 1\ndata$other <- data$raw\n', True),
    ('# recode.num(data$raw)\ndata$raw <- "data$raw" # data$raw\n', True),
    ('# recode.num(data$raw)\n', True),
    ('# shared mapping\ndata$a <- mapping[data$a]\ndata$b <- mapping[data$b]\n', False),
]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    ps = root / "test.ps1"
    ps.write_text('$publicSource = [IO.File]::ReadAllText($args[0])\n$publicIssues = [System.Collections.Generic.List[string]]::new()\n' + marker_block + '\n@($publicIssues) | ConvertTo-Json -Compress\n', encoding='utf-8')
    for code, should_fail in cases:
        script = root / 'define.R'
        script.write_text(code + '# 输出\n', encoding='utf-8')
        result = subprocess.run(['pwsh', '-NoProfile', '-File', str(ps), str(script)], capture_output=True, text=True, encoding='utf-8', check=True)
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        assert bool(issues) == should_fail, (code, issues, result.stderr)
        results = []
        check_public_code_outline(root, '### 2-代码材料\n\n```r\n' + code + '```', results, 'ELSA', script)
        found = any('recode.' in str(r) or 'recode markers' in str(r) for r in results)
        assert found == should_fail, (code, results)
print('RECODE_MARKERS_PASS')
