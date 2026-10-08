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
import uuid
from skill_config import load_config, playwright_command, database_url


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
      if (name === "download" && typeof downloadAttemptId !== 'undefined') {
        const record = downloadCapture(p, downloadAttemptId, downloadTarget);
        await record.wait(convertOptions(options).timeout);
        if (record.state === 'ready') return {path: async () => record.target};
        // The receiver remains attached. A later CLI call observes this attempt without clicking.
        throw new Error('DOWNLOAD_RECEIVER_PENDING: ' + record.state);
      }
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
  list: async () => typeof dbCodeBookBoundPage !== 'undefined'
    ? [{id: 'bound', url: page.url()}]
    : page.context().pages().map((p, i) => ({id: String(i), url: p.url()})),
  get: async id => {
    if (typeof dbCodeBookBoundPage !== 'undefined') {
      if (id !== 'bound') throw new Error('Tab is outside this task binding');
      return wrapPage(page);
    }
    return wrapPage(page.context().pages()[Number(id)]);
  }
}};
let actionResult;
const nodeRepl = {write: value => {actionResult = JSON.parse(value);}};
'''


def bind_code(code, tab_id, receipt_id=None, expires_at_ms=None):
    if not tab_id:
        return code
    return """async defaultPage => {
      let selected;
      const bindingWarnings = [];
      const targetKey = Symbol.for('dbCodeBook.targetId');
      for (const candidate of defaultPage.context().pages()) {
        if (candidate.isClosed()) continue;
        if (!candidate[targetKey]) {
          const cdp = await defaultPage.context().newCDPSession(candidate);
          try { candidate[targetKey] = (await cdp.send('Target.getTargetInfo')).targetInfo.targetId; }
          finally {
            let timer;
            try {
              await Promise.race([cdp.detach(), new Promise((_, reject) => {
                timer = setTimeout(() => reject(new Error('CDP detach timed out')), 2000);
              })]);
            } catch (error) {
              bindingWarnings.push({target_id: candidate[targetKey] || null, cleanup_error: String(error)});
            } finally { clearTimeout(timer); }
          }
        }
        if (candidate[targetKey] === %s) { selected = candidate; break; }
      }
      if (!selected) throw new Error('Bound tab is closed or unavailable; do not select another tab');
      const expiresAt = %s;
      if (expiresAt && Date.now() >= expiresAt) throw new Error('Bound action expired before execution; action was not started');
      const dbCodeBookBoundPage = selected;
      const cancellations = [], pending = [];
      const onDialog = dialog => {
        if (dialog.type() !== 'confirm' || !/清空[^\\r\\n]*标签/.test(dialog.message())) return;
        const record = {type: 'confirm', message: dialog.message(), action: 'dismiss', confirmed: false};
        cancellations.push(record);
        pending.push(dialog.dismiss().then(() => {record.confirmed = true;},
          error => {record.error = String(error);}));
      };
      selected.on('dialog', onDialog);
      const operation = (async () => { try {
        const result = await (%s)(selected);
        await Promise.all(pending);
        if (cancellations.some(item => !item.confirmed)) throw new Error('Native dialog cancellation failed: ' + JSON.stringify(cancellations));
        if (bindingWarnings.length && result && typeof result === 'object' && !Array.isArray(result)) {
          result.binding_cleanup_warnings = bindingWarnings;
        }
        if (!cancellations.length) return result;
        return result && typeof result === 'object' && !Array.isArray(result)
          ? {...result, native_dialogs: cancellations} : {result, native_dialogs: cancellations};
      } finally { selected.off('dialog', onDialog); } })();
      const receiptId = %s;
      if (receiptId) selected[Symbol.for('dbCodeBook.boundAction')] = {id:receiptId, operation};
      return await operation;
    }""" % (json.dumps(tab_id), json.dumps(expires_at_ms), code, json.dumps(receipt_id))


def read_action(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data.get("browser_action", data)


def cli_action_result(result):
    """Keep structured failure evidence even when the CLI exits unsuccessfully."""
    for stream in (result.stdout, result.stderr):
        try:
            payload = json.loads(stream.strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("ok"), bool):
            if result.returncode and payload["ok"]:
                break
            return payload
    return {"ok": False, "status": "CLI_ACTION_UNCERTAIN",
            "allow_new_export": False, "cli_returncode": result.returncode,
            "message": result.stdout + result.stderr}


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
    if mode == "download":
        tracks_click = "dbCodeBookMarkDownloadClickRequested();" in script
        script = (
            "let downloadClickRequested = " + ("false" if tracks_click else "true") + ";\n"
            "const dbCodeBookMarkDownloadClickRequested = () => {downloadClickRequested = true;};\n"
            "try {\n"
            "const earlier = page[Symbol.for('dbCodeBook.downloadCapture')];\n"
            "if (earlier && ['waiting','saving'].includes(earlier.state)) throw new Error('Earlier download receiver still pending; observe the original attempt');\n"
            + script + "\n} catch (error) {\n"
            "actionResult = {ok:false, status:downloadClickRequested ? 'DOWNLOAD_SUBMISSION_UNCERTAIN' : 'DOWNLOAD_NOT_CLICKED',\n"
            "click_requested:downloadClickRequested, operation_completed:true, allow_new_export:false,\n"
            "next_action:downloadClickRequested ? 'run_watch_command' : 'fix_cause_then_prepare_new_attempt',\n"
            "attempt_id:" + json.dumps(action["attempt_id"]) + ", message:String(error)};\n}\n"
        )
    return (
        "async (page) => {\n"
        + "const downloadTarget = " + json.dumps(str(download_target.resolve())) + ";\n"
        + ((Path(__file__).with_name('download_capture.js').read_text(encoding='utf-8')
            + "\nconst downloadAttemptId = " + json.dumps(action['attempt_id']) + ";\n") if mode == 'download' else '')
        + "const dbCodeBookAttemptClaimed = " + str(mode == "download").lower() + ";\n"
        + ADAPTER + "\n" + script
        + ("\nif (downloadClickRequested && actionResult && !actionResult.ok) {\n"
           " const observed = await observeDownload(page, downloadAttemptId, 0);\n"
           " actionResult = {...actionResult, ...observed, click_requested:true};\n}\n" if mode == 'download' else '')
        + "\nreturn actionResult;\n}\n"
    )


class Session:
    def __init__(self, name, workdir, code_path, config=None, tab_id=None):
        self.command = playwright_command(config) + ["-s=" + name]
        self.workdir, self.code_path = workdir, code_path
        self.deadline = None
        self.tab_id = tab_id

    def call(self, *args, timeout=40):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Website operation exceeded 60 seconds")
        result = subprocess.run(self.command + list(args), cwd=self.workdir,
                                capture_output=True, encoding="utf-8", timeout=timeout,
                                stdin=subprocess.DEVNULL)
        if result.returncode or "### Error" in result.stdout:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    def code(self, code):
        receipt_id = uuid.uuid4().hex
        self.code_path.write_text(bind_code(code, self.tab_id, receipt_id,
                                           int((time.time() + 40) * 1000)), encoding="utf-8")
        output = self.call("--raw", "run-code", "--filename", str(self.code_path.resolve()))
        # The CLI returns early when its selected tab opens a dialog, even if
        # our bound handler dismisses it. Retrieve that same operation only;
        # never replay the click/upload/submit to obtain a result.
        if not output.strip() and self.tab_id:
            recovery = '''async page => {
              const receipt = page[Symbol.for('dbCodeBook.boundAction')];
              if (!receipt || receipt.id !== %s) throw new Error('Bound action receipt unavailable; do not replay');
              return await receipt.operation;
            }''' % json.dumps(receipt_id)
            self.code_path.write_text(bind_code(recovery, self.tab_id), encoding="utf-8")
            output = self.call("--raw", "run-code", "--filename", str(self.code_path.resolve()))
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLI did not return JSON: " + output) from exc

    def upload(self, selector, path):
        # CLI owns the intercepted chooser. Native setFiles in run-code leaves it pending.
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        if self.tab_id:
            self.code('async page => { await page.locator(' + json.dumps(selector)
                      + ').setInputFiles(' + json.dumps(str(Path(path).resolve()))
                      + '); return {ok:true}; }')
            return
        output = self.call("click", selector)
        if "[File chooser]" not in output:
            raise RuntimeError("Upload click did not open a CLI file chooser")
        self.call("upload", str(Path(path).resolve()))

    def select_target(self, urls):
        if self.tab_id:
            actual = self.code('async page => ({url: page.url()})')
            if actual['url'].rstrip('/') not in {url.rstrip('/') for url in urls}:
                raise RuntimeError('Bound tab URL does not match the prepared action')
            return
        listing = self.call("tab-list")
        tabs = re.findall(r"^- (\d+): (.*?)\((https?://[^\s)]+)\)\s*$", listing, re.M)
        matches = [tab for tab in tabs if tab[2].rstrip('/') in {url.rstrip('/') for url in urls}]
        if any('(current)' in tab[1] for tab in matches):
            return
        if len(matches) != 1:
            raise RuntimeError("No unique matching website tab")
        self.call("tab-select", matches[0][0])

    def discard(self, edit_url):
        if self.tab_id:
            return self.code('async page => { if (page.url() !== ' + json.dumps(edit_url)
                             + ') throw new Error("Unexpected editor URL");'
                             + ' await page.goto(' + json.dumps(edit_url)
                             + '); return {url:page.url(),editor:await page.locator("#editor").count()}; }')
        listing = self.call("tab-list")
        current = re.search(r"^- (\d+): \(current\).*\((https?://[^\s)]+)\)", listing, re.M)
        if not current or current[2] != edit_url:
            raise RuntimeError("Cannot discard: current tab is not the expected editor")
        # Keep the browser and its session cookies alive when cancelling the only tab.
        self.call("tab-new", edit_url)
        self.call("tab-close", current[1])
        return self.code('async page => ({url: page.url(), editor: await page.locator("#editor").count()})')


def validate_sync_files(payload):
    files = [{"path": payload["note"], "sha256": payload.get("note_sha256")},
             *payload["attachments"]]
    for item in files:
        expected = item.get("sha256")
        path = Path(item["path"])
        if (not expected or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest().upper() != expected.upper()):
            raise ValueError("SYNC_INPUT_CHANGED: " + str(path))


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
        validate_sync_files(payload)
        session.select_target(action["existing_tab_match"])
        state = step()
        validate_sync_files(payload)
        session.upload("#content-import-input", payload["note"])
        state = step()
        for attachment in payload["attachments"][state["keep"]:]:
            validate_sync_files(payload)
            session.upload("#documents-sidebar-input", attachment["path"])
        validate_sync_files(payload)
        # A failed submit call may already have written remotely; never retry or discard it.
        submitted = True
        return step()
    except Exception as exc:
        session.deadline = None  # Recovery is disclosed separately, not a second submission.
        result = {"ok": False, "status": "SUBMISSION_UNCERTAIN" if submitted else "SYNC_FAILED",
                  "error": str(exc), "phase": state["phase"],
                  "browser_elapsed_ms": round((time.monotonic() - started) * 1000),
                  "recovery_attempted": False, "recovery_confirmed": False,
                  "recovery_scope": "editor_page_only",
                  "editor_page_restored": False,
                  "content_rollback_status": "NOT_VERIFIED"}
        if not submitted and state["phase"] != "prepare":
            result["recovery_attempted"] = True
            try:
                restored = session.discard(payload["edit_url"])
                result["recovery_confirmed"] = restored == {"url": payload["edit_url"], "editor": 1}
                result["editor_page_restored"] = result["recovery_confirmed"]
            except Exception as recovery:
                result["recovery_error"] = str(recovery)
        return result
    finally:
        session.deadline = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", type=Path)
    parser.add_argument("--mode", choices=["bind", "tab-code", "source-read", "website-prepare", "taxonomy-options", "login-status", "login-open", "select", "download", "download-observe", "preflight", "sync"], required=True)
    parser.add_argument("--database", choices=['charls', 'elsa', 'hrs', 'share', 'chns', 'knhanes', 'klosa'])
    parser.add_argument("--script", type=Path, help="tab-code: async page function restricted to the bound page")
    parser.add_argument("--tab-index", type=int, help="Observed tab-list index; only used to create a binding")
    parser.add_argument("--tab-id", help="Stable Chromium target id from mode bind; never an index")
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--resume", type=Path, help="source-read: reuse completed receipts from an earlier identical request")
    parser.add_argument("--session", required=True)
    parser.add_argument("--session-workdir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument('--language', choices=['en', 'ko'])
    args = parser.parse_args()
    config = load_config(args.config)
    command = playwright_command(config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == 'download-observe':
        if not args.tab_id or not args.action:
            parser.error('download-observe requires the original --action and --tab-id')
        action = read_action(args.action)
        helper = Path(__file__).with_name('download_capture.js').read_text(encoding='utf-8')
        code = 'async page => {\n' + helper + '\nreturn observeDownload(page, ' + json.dumps(action['attempt_id']) + ');}'
        try:
            payload = Session(args.session, args.session_workdir,
                              args.out.with_suffix('.browser.js'), config, args.tab_id).code(code)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            payload = {'ok': False, 'status': 'DOWNLOAD_RECEIVER_UNAVAILABLE',
                       'allow_new_export': False, 'next_action': 'run_watch_command', 'error': str(exc)}
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get('ok') else 1)
    if args.mode == "website-prepare":
        from prepare_website import browser_code
        if not args.tab_id or not args.action:
            parser.error('website-prepare requires --tab-id and --action')
        try:
            code = browser_code(read_action(args.action))
        except ValueError as exc:
            parser.error(str(exc))
        try:
            payload = Session(args.session, args.session_workdir,
                              args.out.with_suffix('.browser.js'), config, args.tab_id).code(code)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            payload = {'ok': False, 'status': 'WEBSITE_PREPARE_INCOMPLETE', 'error': str(exc)}
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get('ok') else 1)
    if args.mode == "source-read":
        from source_read import run_read
        if not args.tab_id or not args.database or not args.action:
            parser.error('source-read requires --tab-id, --database and --action')
        try:
            action = read_action(args.action)
            if args.database == "klosa":
                from klosa_adapter_contract import require_context
                require_context(action, args.language)
            payload = run_read(
                Session(args.session, args.session_workdir, args.out.with_suffix('.browser.js'), config, args.tab_id),
                action, database_url(config, args.database, args.language), args.database, args.out, args.resume)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps({"ok": payload["ok"], "status": payload["status"],
                          "receipt": str(args.out.resolve()),
                          "completed_count": len(payload["completed"]),
                          "remaining_periods": payload["remaining_periods"],
                          "pending": payload["pending"], "failed": payload["failed"]}, ensure_ascii=False))
        raise SystemExit(0 if payload.get('ok') else 1)
    if args.mode in {"login-status", "login-open", "select"}:
        from prepare_source_selection import browser_code
        if not args.tab_id or not args.database:
            parser.error('login/selection requires --tab-id and --database')
        action = read_action(args.action) if args.action else {}
        url = database_url(config, args.database, args.language)
        if args.database == "klosa" and args.mode == "select":
            from klosa_adapter_contract import require_context
            require_context(action, args.language, url)
        if args.mode == 'select':
            if action.get('url') != url:
                parser.error('selection action must match the configured database URL')
        else:
            action = {'url': url}
        code = browser_code(action, args.mode)
        try:
            payload = Session(args.session, args.session_workdir,
                              args.out.with_suffix('.browser.js'), config, args.tab_id).code(code)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            payload = {'ok': False, 'status': 'SESSION_UNAVAILABLE_OR_UNCERTAIN', 'error': str(exc)}
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get('ok') else 1)
    if args.mode == "taxonomy-options":
        if not args.tab_id:
            parser.error('taxonomy-options requires --tab-id')
        helper = Path(__file__).with_name('website_taxonomy.js').read_text(encoding='utf-8')
        payload = Session(args.session, args.session_workdir,
                          args.out.with_suffix('.browser.js'), config, args.tab_id).code(
                              'async page => {\n' + helper + '\nreturn {ok:true, url:page.url(), fields:await readWebsiteTaxonomy({playwright:page})}; }')
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        return
    if args.mode == "tab-code":
        if not args.tab_id or not args.script:
            parser.error('tab-code requires --tab-id and --script')
        payload = Session(args.session, args.session_workdir,
                          args.out.with_suffix('.browser.js'), config, args.tab_id).code(
                              args.script.read_text(encoding='utf-8-sig'))
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        return
    if args.mode == "bind":
        if args.tab_index is None or args.tab_index < 0:
            parser.error('bind requires a nonnegative --tab-index from tab-list')
        session = Session(args.session, args.session_workdir, args.out.with_suffix('.browser.js'), config)
        payload = session.code('''async page => {
          const selected = page.context().pages()[%d];
          if (!selected) throw new Error('Observed tab index no longer exists');
          const cdp=await page.context().newCDPSession(selected);
          try { const result=await cdp.send('Target.getTargetInfo');
            return {ok:true,tab_id:result.targetInfo.targetId,url:selected.url()}; }
          finally {await cdp.detach();}
        }''' % args.tab_index)
        payload.update(session=args.session, session_workdir=str(args.session_workdir.resolve()))
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        return
    if not args.action:
        parser.error('--action is required for browser actions')
    action = read_action(args.action)
    if args.mode == "download" and action.get("database") == "klosa":
        from klosa_adapter_contract import require_context
        require_context(action, args.language, database_url(config, "klosa", args.language))
    preflight = read_action(args.preflight) if args.preflight else None
    target = args.out.parent / ("download-" + action.get("attempt_id", "unused") + ".zip")
    if args.mode == "sync":
        payload = run_sync(Session(args.session, args.session_workdir, args.out.with_suffix(".browser.js"), config, args.tab_id),
                           action, preflight)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get("ok") else 1)
    code = bind_code(build_code(action, args.mode, preflight, target), args.tab_id)
    code_path = args.out.with_suffix(".browser.js")
    code_path.write_text(code, encoding="utf-8")
    if args.mode == "download":
        # Claim locally before dispatch: a timeout must never cause a second paid click.
        attempt_file = Path(action["attempt_file"])
        with attempt_file.open("x", encoding="utf-8") as handle:
            json.dump({"attempt_id": action["attempt_id"], "session": args.session,
                       "status": "claimed_before_cli_dispatch"}, handle)
    try:
        result = subprocess.run(
            command + ["-s=" + args.session, "--raw", "run-code", "--filename", str(code_path.resolve())],
            cwd=args.session_workdir, encoding="utf-8", capture_output=True,
            timeout=action.get("timeout_ms", 90000) / 1000 + 30, stdin=subprocess.DEVNULL,
        )
        payload = cli_action_result(result)
    except (subprocess.TimeoutExpired, OSError) as exc:
        payload = {"ok": False, "status": "CLI_ACTION_UNCERTAIN",
                   "allow_new_export": False, "message": str(exc)}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    if not payload.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
