import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_definition_output import check_public_dictionary

prefix = """# ----------- 1 检查并安装包 -----------
# ----------- 2 读取数据 -----------
# ----------- 3 定义变量 -----------
"""
template = (ROOT / "templates/public-r-dictionary.R").read_text(encoding="utf-8")
valid = prefix + template
checks = []
check_public_dictionary(valid, checks)
assert checks and all(check["ok"] for check in checks), checks

for bad in (
    valid.replace("变量字典", "其他标题"),
    valid.replace("正式输出", "其他输出"),
    valid.replace('map <- add_mapping(map, "defined_value",', 'map <- add_mapping(map, "wrong",'),
    valid.replace("map <- data.frame", "map <- list"),
):
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "definition.R"
        source.write_text(bad + '\n# 输出\nstop("must not execute")\n', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts/check_definition_output.py"),
             "--public-r-script", str(source)],
            capture_output=True, encoding="utf-8",
        )
        assert result.returncode == 1, result.stderr
        assert not json.loads(result.stdout)["ok"]
        assert list(Path(tmp).iterdir()) == [source]
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / "definition.R"
    source.write_text(valid + '\n# 输出\n', encoding="utf-8")
    for extra in (("--formal-dir", str(Path(tmp) / "absent")),
                  ("--expected-files", "required.xlsx"),
                  ("--report", str(Path(tmp) / "unexpected.json"))):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts/check_definition_output.py"),
             "--public-r-script", str(source), *extra],
            capture_output=True, encoding="utf-8",
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert list(Path(tmp).iterdir()) == [source]
print("PUBLIC_DICTIONARY_PREFLIGHT_PASS")
