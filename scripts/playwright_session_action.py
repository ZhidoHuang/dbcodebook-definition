"""Run prepared browser actions in an existing extension-free Playwright CLI session."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import re
import time


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


class Session:
    def __init__(self, name, workdir, code_path):
        self.command = [shutil.which("npx.cmd") or shutil.which("npx"), "--yes",
                        "--package", "@playwright/cli", "playwright-cli", "-s=" + name]
        self.workdir, self.code_path = workdir, code_path
        self.deadline = None

    def call(self, *args, timeout=40):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Website operation exceeded 60 seconds")
        result = subprocess.run(self.command + list(args), cwd=self.workdir,
                                capture_output=True, encoding="utf-8", timeout=timeout)
        if result.returncode or "### Error" in result.stdout:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    def code(self, code):
        self.code_path.write_text(code, encoding="utf-8")
        output = self.call("--raw", "run-code", "--filename", str(self.code_path.resolve()))
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLI did not return JSON: " + output) from exc

    def upload(self, selector, path):
        # CLI owns the intercepted chooser. Native setFiles in run-code leaves it pending.
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        output = self.call("click", selector)
        if "[File chooser]" not in output:
            raise RuntimeError("Upload click did not open a CLI file chooser")
        self.call("upload", str(Path(path).resolve()))

    def select_target(self, urls):
        listing = self.call("tab-list")
        tabs = re.findall(r"^- (\d+): (.*?)\((https?://[^\s)]+)\)\s*$", listing, re.M)
        matches = [tab for tab in tabs if tab[2].rstrip('/') in {url.rstrip('/') for url in urls}]
        if any('(current)' in tab[1] for tab in matches):
            return
        if len(matches) != 1:
            raise RuntimeError("No unique matching website tab")
        self.call("tab-select", matches[0][0])

    def discard(self, edit_url):
        listing = self.call("tab-list")
        current = re.search(r"^- (\d+): \(current\).*\((https?://[^\s)]+)\)", listing, re.M)
        if not current or current[2] != edit_url:
            raise RuntimeError("Cannot discard: current tab is not the expected editor")
        # Keep the browser and its session cookies alive when cancelling the only tab.
        self.call("tab-new", edit_url)
        self.call("tab-close", current[1])
        return self.code('async page => ({url: page.url(), editor: await page.locator("#editor").count()})')


def run_sync(session, action, preflight):
    build_code(action, "sync", preflight, Path("unused"))  # Validate the prepared helper hash.
    helper = preflight["preload_script"].split("\nvar dbCodeBookSyncPreflightTab =", 1)[0]
    payload = action["payload"]
    state = {"phase": "prepare"}
    submitted = False
    started = time.monotonic()
    session.deadline = started + 60

    def step():
        script = ("async page => { const downloadTarget = null;\n" + ADAPTER + helper
                  + "\nconst tab = await resolveDbCodeBookTab(" + json.dumps(action["existing_tab_match"]) + ");"
                  + "\nreturn await syncDbCodeBookPost(tab," + json.dumps(payload) + ","
                  + json.dumps(state) + "); }")
        return session.code(script)

    try:
        session.select_target(action["existing_tab_match"])
        state = step()
        session.upload("#content-import-input", payload["note"])
        state = step()
        for attachment in payload["attachments"][state["keep"]:]:
            session.upload("#documents-sidebar-input", attachment["path"])
        # A failed submit call may already have written remotely; never retry or discard it.
        submitted = True
        return step()
    except Exception as exc:
        session.deadline = None  # Recovery is disclosed separately, not a second submission.
        result = {"ok": False, "status": "SUBMISSION_UNCERTAIN" if submitted else "SYNC_FAILED",
                  "error": str(exc), "phase": state["phase"],
                  "browser_elapsed_ms": round((time.monotonic() - started) * 1000),
                  "recovery_attempted": False, "recovery_confirmed": False}
        if not submitted and state["phase"] != "prepare":
            result["recovery_attempted"] = True
            try:
                restored = session.discard(payload["edit_url"])
                result["recovery_confirmed"] = restored == {"url": payload["edit_url"], "editor": 1}
            except Exception as recovery:
                result["recovery_error"] = str(recovery)
        return result
    finally:
        session.deadline = None


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
    if args.mode == "sync":
        payload = run_sync(Session(args.session, args.session_workdir, args.out.with_suffix(".browser.js")),
                           action, preflight)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get("ok") else 1)
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
