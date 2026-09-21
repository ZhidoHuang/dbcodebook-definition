"""Probe a new host without installing packages, opening a browser or writing a topic."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from skill_config import load_config, configured_executable, configured_path, playwright_command


R_PACKAGES = ("openxlsx", "dplyr", "tidyr", "jsonlite", "dbCodeBookr")


def browser_path(channel, explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return str(path) if path.is_file() else None
    executable = "msedge" if channel == "msedge" else "chrome"
    found = shutil.which(executable)
    if found:
        return found
    relative = ("Microsoft/Edge/Application/msedge.exe" if channel == "msedge"
                else "Google/Chrome/Application/chrome.exe")
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(key):
            path = Path(os.environ[key]) / relative
            if path.is_file():
                return str(path)
    return None


def command_probe(command, *, timeout=30, env=None):
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout, env=env,
                            stdin=subprocess.DEVNULL)
    detail = (result.stdout + result.stderr).strip()
    if result.returncode:
        raise RuntimeError(detail or f"exit code {result.returncode}")
    return detail


def check_environment(config, mode, browser, explicit_browser=None):
    checks = []

    def check(name, action, remedy):
        try:
            detail = action()
            checks.append({"name": name, "ok": True, "detail": detail})
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            checks.append({"name": name, "ok": False, "detail": str(error), "remedy": remedy})

    def executable(name):
        value = configured_executable(config, name)
        if not value:
            raise FileNotFoundError(f"{name} was not found")
        return value

    check("python", lambda: command_probe([executable("python"), "-c",
          "import csv,json,zipfile,xml.etree.ElementTree; import sys; print(sys.executable); print(sys.version)"]),
          "Set executables.python in config.local.json to the actual Python executable.")

    if mode in ("full", "local"):
        def writable_root(name):
            root = configured_path(config, name)
            if root is None or not root.is_dir():
                raise FileNotFoundError(f"paths.{name} must point to an existing directory: {root}")
            with tempfile.TemporaryFile(dir=root):
                pass
            return str(root)

        for name in ("formal_root", "process_root"):
            check(name, lambda name=name: writable_root(name),
                  f"Create the intended directory and set paths.{name}; do not reuse another device's path.")

        def r_probe():
            rscript = executable("rscript")
            # Match the runner's UTF-8 startup without changing the host's locale.
            env = dict(os.environ)
            for key in ("LC_ALL", "LANG", "LC_CTYPE"):
                env.pop(key, None)
            code = ('pkgs <- c(' + ','.join(json.dumps(p) for p in R_PACKAGES) + '); '
                    'missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly=TRUE)]; '
                    'cat("R=", R.version.string, "\\nTEMP=", tempdir(), "\\nLIB=", '
                    'paste(.libPaths(), collapse=";"), "\\n"); '
                    'f <- tempfile(); writeLines("runtime check", f); '
                    'stopifnot(identical(readLines(f), "runtime check")); unlink(f); '
                    'if(length(missing)) stop(paste("Missing R packages:", paste(missing, collapse=", "))); '
                    'cat("R_RUNTIME_READY\\n")')
            with tempfile.TemporaryDirectory(prefix="definition_env_") as temporary:
                script = Path(temporary) / "probe.R"
                script.write_text(code, encoding="utf-8")
                return command_probe([rscript, "--vanilla", "--encoding=UTF-8", str(script)],
                                     timeout=60, env=env)

        check("r_runtime", r_probe,
              "Use setup_definition_environment.ps1 with the configured Rscript for missing packages. "
              "For temp/library failures inspect the reported paths and encoding; do not assume a non-ASCII username is invalid.")

    if mode in ("full", "browser"):
        def node_probe():
            node = configured_executable(config, "node")
            if not node:
                raise FileNotFoundError("node was not found")
            return command_probe([node, "--version"])

        check("node", node_probe,
              "Install Node.js and make node and npx available to this task, then retry the check.")

        def cli_probe():
            return command_probe(playwright_command(config) + ["--version"])

        check("playwright_cli_cached", cli_probe,
              "For a cache miss, provision @playwright/cli once using the installed Playwright skill. "
              "For a runtime error, repair the reported Node/CLI failure before browser work. "
              "This offline probe never treats printed version text alone as success.")

        def installed_browser():
            path = browser_path(browser, explicit_browser)
            if not path:
                raise FileNotFoundError(f"Selected browser not found: {browser}")
            return path

        check("browser_executable", installed_browser,
              "Install the selected Chrome/Edge or provide --browser-executable for its actual path. Do not switch browsers silently.")

    return {"ok": all(c["ok"] for c in checks), "mode": mode, "checks": checks,
            "not_verified": ["browser control and website login", "real download and upload",
                             "independent reviewer file access"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--mode", choices=("full", "local", "browser"), default="full")
    parser.add_argument("--browser", choices=("chrome", "msedge"), default="chrome")
    parser.add_argument("--browser-executable")
    args = parser.parse_args()
    try:
        result = check_environment(load_config(args.config, required=True), args.mode,
                                   args.browser, args.browser_executable)
    except (OSError, ValueError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
