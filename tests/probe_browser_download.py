"""Explicit offline browser probe, not part of automated unit tests or paid exports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from skill_config import load_config, playwright_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=["msedge", "chrome"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    command = playwright_command(load_config(args.config)) + ["-s=probe-" + uuid.uuid4().hex[:12]]
    def call(*parts):
        return subprocess.run(command + list(parts), cwd=root, capture_output=True,
                              encoding="utf-8", timeout=90)
    target = root / "probe.bin"
    code = root / "probe.js"
    code.write_text("async page => {\n"
        "await page.setContent('<a id=download>Download test</a>');\n"
        "await page.evaluate(() => {const a=document.querySelector('#download');"
        "a.href=URL.createObjectURL(new Blob([new Uint8Array(19024242).fill(42)]));"
        "a.download='probe.bin';});\n"
        "const pending=page.waitForEvent('download');\n"
        "await page.locator('#download').click();\n"
        "const download=await pending;\n"
        "await download.saveAs(" + json.dumps(str(target)) + ");\n"
        "return {ok:true};}", encoding="utf-8")
    result = {}
    try:
        opened = call("open", "about:blank", "--browser", args.browser,
                      "--headed", "--profile", str(root / "profile"))
        result["open"] = {"code": opened.returncode, "output": opened.stdout + opened.stderr}
        if opened.returncode == 0:
            download = call("--raw", "run-code", "--filename", str(code))
            result["download"] = {"code": download.returncode, "output": download.stdout + download.stderr}
        result["file_ok"] = target.is_file() and hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(bytes([42]) * 19024242).digest()
    finally:
        closed = call("close")
        result["close_code"] = closed.returncode
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
