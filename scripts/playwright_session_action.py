"""Run prepared browser actions in an existing extension-free Playwright CLI session."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


ADAPTER = r'''
const dbCodeBookParseUrl = value => page.evaluate(value => {
  const url = new URL(value);
  url.hash = "";
  return {origin: url.origin, pathname: url.pathname, href: url.href};
}, value);
const setTimeout = (callback, ms) => page.waitForTimeout(ms).then(callback);
const convertOptions = options => {
  if (!options || typeof options !== "object" || Array.isArray(options)) return options;
  const {timeoutMs, ...rest} = options;
  return timeoutMs === undefined ? rest : {...rest, timeout: timeoutMs};
};
const wrapLocator = locator => new Proxy(locator, {get(target, key) {
  if (typeof target[key] !== "function") return target[key];
  return (...args) => {
    const result = target[key](...args.map(convertOptions));
    return result && typeof result.click === "function" ? wrapLocator(result) : result;
  };
}});
const wrapPage = p => ({
  url: () => p.url(), goto: url => p.goto(url),
  playwright: {
    locator: selector => wrapLocator(p.locator(selector)),
    getByRole: (role, options) => wrapLocator(p.getByRole(role, options)),
    evaluate: (...args) => p.evaluate(...args),
    waitForLoadState: ({state, ...options}) => p.waitForLoadState(state, convertOptions(options)),
    waitForURL: (url, options) => p.waitForURL(url, convertOptions(options)),
    waitForEvent: async (name, options) => {
      const event = await p.waitForEvent(name, convertOptions(options));
      if (name !== "download") return event;
      return {path: async () => {
        await event.saveAs(downloadTarget);
        return downloadTarget;
      }};
    }
  }
});
const dbCodeBookBrowser = {tabs: {
  selected: async () => wrapPage(page),
  list: async () => page.context().pages().map((p, i) => ({id: String(i), url: p.url()})),
  get: async id => wrapPage(page.context().pages()[Number(id)])
}};
let actionResult;
const nodeRepl = {write: value => {actionResult = JSON.parse(value);}};
'''


def read_action(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data.get("browser_action", data)


def build_code(action: dict, mode: str, preflight: dict | None, download_target: Path) -> str:
    if mode == "preflight":
        script = action["preload_script"]
    elif mode == "sync":
        if not preflight or action["preload_sha256"] != preflight["preload_sha256"]:
            raise ValueError("Website preflight and submission helper hashes differ")
        helper = preflight["preload_script"].split("\nvar dbCodeBookSyncPreflightTab =", 1)[0]
        if hashlib.sha256(helper.encode("utf-8")).hexdigest() != action["preload_sha256"]:
            raise ValueError("Website helper does not match its declared hash")
        script = helper + "\n" + action["run_script"]
    else:
        script = action["run_script"]
    return (
        "async (page) => {\n"
        + "const downloadTarget = " + json.dumps(str(download_target.resolve())) + ";\n"
        + "const dbCodeBookAttemptClaimed = " + str(mode == "download").lower() + ";\n"
        + ADAPTER + "\n" + script + "\nreturn actionResult;\n}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True, type=Path)
    parser.add_argument("--mode", choices=["download", "preflight", "sync"], required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--session-workdir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    action = read_action(args.action)
    preflight = read_action(args.preflight) if args.preflight else None
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx was not found")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    target = args.out.parent / ("download-" + action.get("attempt_id", "unused") + ".zip")
    code = build_code(action, args.mode, preflight, target)
    code_path = args.out.with_suffix(".browser.js")
    code_path.write_text(code, encoding="utf-8")
    if args.mode == "download":
        # Claim locally before dispatch: a timeout must never cause a second paid click.
        attempt_file = Path(action["attempt_file"])
        with attempt_file.open("x", encoding="utf-8") as handle:
            json.dump({"attempt_id": action["attempt_id"], "session": args.session,
                       "status": "claimed_before_cli_dispatch"}, handle)
    result = subprocess.run(
        [npx, "--yes", "--package", "@playwright/cli", "playwright-cli",
         "-s=" + args.session, "--raw", "run-code", "--filename", str(code_path.resolve())],
        cwd=args.session_workdir, encoding="utf-8", capture_output=True,
        timeout=action.get("timeout_ms", 90000) / 1000 + 30,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CLI did not return an action result: " + result.stdout) from exc
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    if not payload.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
