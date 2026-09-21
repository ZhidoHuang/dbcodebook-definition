import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_definition_environment as probe

with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ready", "")) as run:
    assert probe.command_probe(["fixture", "--version"]) == "ready"
    assert run.call_args.kwargs["stdin"] == subprocess.DEVNULL
with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "0.1.21", "runtime failure")):
    try:
        probe.command_probe(["fixture", "--version"])
    except RuntimeError as error:
        assert "runtime failure" in str(error)
    else:
        raise AssertionError("Version text must not hide nonzero exit status")


with tempfile.TemporaryDirectory(prefix="env space_") as temporary:
    root = Path(temporary)
    config = {"paths": {"formal_root": str(root), "process_root": str(root)},
              "executables": {"python": sys.executable, "rscript": sys.executable}}
    with patch.object(probe, "command_probe", return_value="ready") as commands:
        result = probe.check_environment(config, "local", "chrome")
        assert result["ok"], result
        assert [c["name"] for c in result["checks"]] == ["python", "formal_root", "process_root", "r_runtime"]
        assert len(commands.call_args_list) == 2
        r_command = commands.call_args_list[1].args[0]
        assert "--encoding=UTF-8" in r_command
        assert not Path(r_command[-1]).exists()  # Temporary probe cleaned up.

    with patch.object(probe.shutil, "which", return_value=None), patch.object(probe, "browser_path", return_value=None):
        result = probe.check_environment(config, "browser", "msedge")
        failures = {c["name"] for c in result["checks"] if not c["ok"]}
        assert failures == {"node", "playwright_cli_cached", "browser_executable"}, result
        assert not result["ok"] and len(result["not_verified"]) == 3
        assert all(c.get("remedy") for c in result["checks"] if not c["ok"])

    with patch.object(probe.shutil, "which", return_value="fake-tool"), \
         patch.object(probe, "browser_path", return_value="installed-edge"), \
         patch.object(probe, "command_probe", return_value="ready") as commands:
        result = probe.check_environment(config, "browser", "msedge")
        assert result["ok"]
        assert "--offline" in commands.call_args_list[-1].args[0]
        assert "--version" in commands.call_args_list[-1].args[0]
        assert not any("open" in c.args[0] for c in commands.call_args_list)

    missing = {**config, "paths": {}, "executables": {"python": str(root / "absent"), "rscript": str(root / "absent-R")}}
    result = probe.check_environment(missing, "local", "chrome")
    assert len([c for c in result["checks"] if not c["ok"]]) == 4, result
    portable = root / "portable browser.exe"
    portable.touch()
    assert probe.browser_path("msedge", portable) == str(portable.resolve())
    assert probe.browser_path("msedge", root / "missing.exe") is None

    cfg = root / "config.json"
    cfg.write_text(json.dumps(missing), encoding="utf-8")
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/check_definition_environment.py"),
                             "--config", str(cfg), "--mode", "local"],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert not json.loads(result.stdout)["ok"]

setup = (ROOT / "scripts/setup_definition_environment.ps1").read_text(encoding="utf-8")
assert all(f'"{p}"' in setup for p in probe.R_PACKAGES if p != "dbCodeBookr")
print("ENVIRONMENT_PROBE_PASS: scoped checks, aggregated failures, offline CLI, explicit browser, temp cleanup")
