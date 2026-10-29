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
import zipfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from skill_config import load_config, playwright_command, database_url


@contextmanager
def temporary_browser_script(code):
    with tempfile.TemporaryDirectory(prefix='dbcodebook-browser-') as folder:
        path = Path(folder) / 'action.js'
        path.write_text(code, encoding='utf-8')
        yield path


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


def bind_code(code, tab_id, receipt_id=None, expires_at_ms=None, retain_receipt=False, receipt_scope=None):
    if not tab_id:
        return code
    return """async defaultPage => {
      let selected;
      const bindingWarnings = [];
      const targetKey = Symbol.for('dbCodeBook.targetId');
      const candidates = [defaultPage, ...defaultPage.context().pages().filter(p => p !== defaultPage)];
      for (const candidate of candidates) {
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
      const receiptId = %s;
      const dbCodeBookOperationReceipt = {id:receiptId, tab_id:%s, scope:%s,
        state:'running', started_at:new Date().toISOString(), submission_requested:null};
      if (%s) {
        const context = selected.context();
        const key = Symbol.for('dbCodeBook.syncReceipts');
        const receipts = context[key] || (context[key] = new Map());
        receipts.set(receiptId, dbCodeBookOperationReceipt);
      }
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
      dbCodeBookOperationReceipt.operation = operation;
      operation.then(result => Object.assign(dbCodeBookOperationReceipt,
        {state:'completed', result, finished_at:new Date().toISOString()}), error =>
        Object.assign(dbCodeBookOperationReceipt,
          {state:'failed', error:String(error), finished_at:new Date().toISOString()}));
      if (receiptId) selected[Symbol.for('dbCodeBook.boundAction')] = dbCodeBookOperationReceipt;
      return await operation;
    }""" % (json.dumps(tab_id), json.dumps(expires_at_ms), json.dumps(receipt_id), json.dumps(tab_id),
           json.dumps(receipt_scope), str(bool(retain_receipt)).lower(), code)


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
        self.operation_timeout = 40
        self.retain_receipts = False
        self.receipt_scope = None
        self.last_receipt_id = None
        self.body_check = None

    def call(self, *args, timeout=None):
        timeout = self.operation_timeout if timeout is None else timeout
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Website phase exceeded its execution limit")
        result = subprocess.run(self.command + list(args), cwd=self.workdir,
                                capture_output=True, encoding="utf-8", timeout=timeout,
                                stdin=subprocess.DEVNULL)
        if result.returncode or "### Error" in result.stdout:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    def code(self, code):
        receipt_id = uuid.uuid4().hex
        self.last_receipt_id = receipt_id
        if self.retain_receipts and self.tab_id:
            self.code_path.with_suffix('.receipt.json').write_text(json.dumps({
                'receipt_id':receipt_id, 'tab_id':self.tab_id, 'scope':self.receipt_scope,
                'recorded_at':time.time(), 'phase_timeout_seconds':self.operation_timeout,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        with temporary_browser_script(bind_code(code, self.tab_id, receipt_id,
                                               int((time.time() + 40) * 1000),
                                               self.retain_receipts, self.receipt_scope)) as path:
            output = self.call("--raw", "run-code", "--filename", str(path))
        # The CLI returns early when its selected tab opens a dialog, even if
        # our bound handler dismisses it. Retrieve that same operation only;
        # never replay the click/upload/submit to obtain a result.
        if not output.strip() and self.tab_id:
            recovery = '''async page => {
              const receipt = page.context()[Symbol.for('dbCodeBook.syncReceipts')]?.get(%s)
                || page[Symbol.for('dbCodeBook.boundAction')];
              if (!receipt || receipt.id !== %s) throw new Error('Bound action receipt unavailable; do not replay');
              return await receipt.operation;
            }''' % (json.dumps(receipt_id), json.dumps(receipt_id))
            with temporary_browser_script(bind_code(recovery, self.tab_id)) as path:
                output = self.call("--raw", "run-code", "--filename", str(path))
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLI did not return JSON: " + output) from exc

    def upload(self, selector, path):
        # Wait for each asynchronous attachment import before starting the next.
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        file_path = str(Path(path).resolve())
        attachment = selector == "#documents-sidebar-input"
        read_names = """() => document.querySelector('#documents-sidebar-list').innerText
          .split(/\\r?\\n/).map(line => line.trim())
          .filter(line => /\\.(xlsx|xls|csv|docx?|txt|pdf)$/i.test(line))"""
        wait_ms = 60000
        wait_code = """async page => {
          await page.waitForFunction(expected => {
            const actual = document.querySelector('#documents-sidebar-list').innerText
              .split(/\\r?\\n/).map(line => line.trim())
              .filter(line => /\\.(xlsx|xls|csv|docx?|txt|pdf)$/i.test(line));
            return JSON.stringify(actual) === JSON.stringify(expected);
          }, EXPECTED, {timeout: ATTACHMENT_WAIT_MS});
          return {ok:true};
        }"""
        wait_code = wait_code.replace('ATTACHMENT_WAIT_MS', str(wait_ms))
        if self.tab_id:
            prefix = ('const expected = await page.evaluate(' + read_names + ');'
                      + ' expected.push(' + json.dumps(Path(path).name) + ');') if attachment else ''
            wait = wait_code.split('async page => {', 1)[1].rsplit('}', 1)[0].replace('EXPECTED', 'expected') if attachment else '''await page.waitForFunction(expected => {const text=document.querySelector('#editor').value; return expected ? text.length===expected.length_utf16 && text.slice(0,160)===expected.head && text.slice(-150)===expected.tail : text.length>0;}, BODY_CHECK, {timeout:30000}); return {ok:true};'''.replace('BODY_CHECK',json.dumps(self.body_check))
            self.code('async page => {' + prefix + ' await page.locator(' + json.dumps(selector)
                      + ').setInputFiles(' + json.dumps(file_path) + ');' + wait + '}')
            return
        expected = self.code('async page => page.evaluate(' + read_names + ')') if attachment else None
        output = self.call("click", selector)
        if "[File chooser]" not in output:
            raise RuntimeError("Upload click did not open a CLI file chooser")
        self.call("upload", file_path)
        if attachment:
            self.code(wait_code.replace('EXPECTED', json.dumps(expected + [Path(path).name])))

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
    if payload.get('navigation_removal'):
        proof = payload['navigation_removal']
        files.append({'path': proof['before'], 'sha256': proof['before_sha256']})
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
    session.deadline = None
    session.retain_receipts = True
    session.body_check = payload.get('body_check')
    session.receipt_scope = {key:payload.get(key) for key in
                             ('sync_run_id','sync_attempt','sync_started_at','preload_sha256')}
    active_step = 'identity'
    phase_timings = {}

    def perform(name, operation, timeout=40):
        nonlocal active_step
        active_step = name
        session.receipt_scope['step'] = name
        session.operation_timeout = timeout
        phase_started = time.monotonic()
        try:
            return operation()
        finally:
            phase_timings[name] = round((time.monotonic() - phase_started) * 1000)

    def step():
        script = ("async page => { const downloadTarget = null;\n" + ADAPTER + helper
                  + "\nconst tab = await resolveDbCodeBookTab(" + json.dumps(action["existing_tab_match"]) + ");"
                  + "\nreturn await syncDbCodeBookPost(tab," + json.dumps(payload) + ","
                  + json.dumps(state) + "); }")
        return session.code(script)

    try:
        validate_sync_files(payload)
        perform('identity', lambda: session.select_target(action["existing_tab_match"]))
        state = perform('prepare', step)
        validate_sync_files(payload)
        perform('body_import', lambda: session.upload("#content-import-input", payload["note"]))
        state = perform('body_check', step)
        for index, attachment in enumerate(payload["attachments"][state["keep"]:]):
            validate_sync_files(payload)
            perform('attachment_' + str(index + state['keep'] + 1),
                    lambda: session.upload("#documents-sidebar-input", attachment["path"]), 65)
        validate_sync_files(payload)
        # Record uncertain submissions truthfully; timeout recovery uses a fresh task window.
        submitted = True
        return perform('submit', step)
    except Exception as exc:
        session.deadline = None  # Recovery is disclosed separately, not a second submission.
        result = {"ok": False, "status": "SUBMISSION_UNCERTAIN" if submitted else "SYNC_FAILED",
                  "sync_run_id": payload.get("sync_run_id"),
                  "sync_attempt": payload.get("sync_attempt"),
                  "sync_started_at": payload.get("sync_started_at"),
                  "error": str(exc), "phase": state["phase"],
                  "browser_elapsed_ms": round((time.monotonic() - started) * 1000),
                  "recovery_attempted": False, "recovery_confirmed": False,
                  "recovery_scope": "editor_page_only",
                  "editor_page_restored": False,
                  "content_rollback_status": "NOT_VERIFIED"}
        # The CLI may time out while the original browser operation is still running.
        # Non-timeout failures may use the observer; timeouts follow the documented fresh-window retry.
        result['preload_sha256'] = payload.get('preload_sha256')
        result['phase_timings_ms'] = phase_timings
        result['observation'] = {
            'receipt_id':getattr(session, 'last_receipt_id', None),
            'tab_id':getattr(session, 'tab_id', None), 'step':active_step,
            'scope':dict(session.receipt_scope),
        }
        is_timeout = isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) or bool(
            re.search(r'timeout|timed out|超时', str(exc), re.IGNORECASE))
        result['next_action'] = ('close_task_window_and_retry_in_new_window'
                                 if is_timeout else 'sync-observe')
        result['save_check_required_before_retry'] = not is_timeout
        return result
    finally:
        session.deadline = None
        session.retain_receipts = False
        session.operation_timeout = 40


def observe_sync(session, action, failed_result):
    """Read the original operation; never upload, submit, discard, or reload."""
    payload = action['payload']
    observation = failed_result.get('observation') or {}
    keys = ('sync_run_id','sync_attempt','sync_started_at')
    if any(failed_result.get(key) != payload.get(key) for key in keys):
        raise ValueError('Observation does not belong to the prepared synchronization')
    if not observation.get('receipt_id'):
        return {**{key:payload.get(key) for key in keys}, 'ok':False,
                'status':'SYNC_RECEIPT_UNAVAILABLE', 'read_only':True,
                'next_action':'read_only_saved_state_check'}
    if not session.tab_id or observation.get('tab_id') != session.tab_id:
        raise ValueError('Observation requires the original bound tab')
    receipt_id = observation.get('receipt_id')
    if not isinstance(receipt_id,str) or not re.fullmatch('[0-9a-f]{32}',receipt_id):
        raise ValueError('Original operation receipt is missing; do not replay')
    expected_scope = observation['scope']
    expected_scope = dict(expected_scope)
    if any(expected_scope.get(key) != payload.get(key) for key in (*keys,'preload_sha256')):
        raise ValueError('Observation scope does not match the prepared synchronization')
    observed = session.code('''async page => {
      const receipt = page.context()[Symbol.for('dbCodeBook.syncReceipts')]?.get(RECEIPT);
      if (!receipt) return {state:'unavailable'};
      const expectedScope = SCOPE;
      if (receipt.tab_id !== TAB || !receipt.scope ||
          Object.keys(receipt.scope).length !== Object.keys(expectedScope).length ||
          !Object.keys(expectedScope).every(key => receipt.scope[key] === expectedScope[key]))
        throw new Error('Original receipt identity does not match');
      let timer;
      if (receipt.state === 'running') {
        try { await Promise.race([receipt.operation.catch(() => {}), new Promise(resolve => {
          timer = setTimeout(resolve, 10000);
        })]); } finally {clearTimeout(timer);}
      }
      let returnedPost=null, returnedUrl=null;
      if (receipt.state==='failed' && receipt.submission_requested===true && expectedScope.step==='submit') {
        returnedUrl=page.url();
        const element=await page.locator('#post-data').count();
        if (element) returnedPost=await page.locator('#post-data').evaluate(el=>{
          const p=JSON.parse(el.textContent);return {id:p.id,title:p.title,
            documents:(p.documents || []).filter(d=>(d.displayIn || 'sidebar')==='sidebar').map(d=>d.name)};
        });
      }
      return {state:receipt.state, result:receipt.result, error:receipt.error,
        submission_requested:receipt.submission_requested, url:returnedUrl, returned_post:returnedPost,
        verified:receipt.verified, finished_at:receipt.finished_at};
    }'''.replace('RECEIPT',json.dumps(receipt_id)).replace('TAB',json.dumps(session.tab_id))
        .replace('SCOPE',json.dumps(expected_scope)))
    common = {key:payload.get(key) for key in keys}
    common.update(observation=observation, observed_at=time.time(), read_only=True,
                  original_status=failed_result.get('status'))
    if observed['state'] == 'completed' and observation['step'] == 'submit':
        result = observed.get('result') or {}
        if result.get('status') == 'ARTICLE_PAGE_RETURNED' and result.get('ok') is True:
            if any(result.get(key) != payload.get(key) for key in keys):
                raise ValueError('Recovered result belongs to another synchronization')
            return {**result, 'recovered_original_result':True, 'recovery':common}
    # The original wait may end before the already-submitted page returns.
    # Apply the normal URL completion condition to that same bound receipt;
    # preserve the failed receipt rather than relabeling it as completed.
    if (observed['state']=='failed' and observation['step']=='submit'
            and observed.get('submission_requested') is True
            and all((observed.get('verified') or {}).get(k) is True for k in
                    ('edit_url_verified','title_verified','body_verified','attachment_order_verified'))):
        from urllib.parse import urlsplit
        current=urlsplit(observed.get('url') or ''); expected=urlsplit(payload['edit_url'])
        match=re.fullmatch(r'/nodes/post/(?:local-)?([1-9][0-9]*)/',current.path)
        post=observed.get('returned_post') or {}
        correct_update=payload.get('create') or (
            current.path.replace('/local-','/')==urlsplit(payload.get('post_url','')).path.replace('/local-','/'))
        if (current.scheme==expected.scheme and current.netloc==expected.netloc and match
                and str(post.get('id'))==match[1] and correct_update
                and post.get('title')==payload.get('desired_title')
                and post.get('documents')==[x['name'] for x in payload['attachments']]):
            validate_sync_files(payload)
            return {**common,'ok':True,'status':'ARTICLE_PAGE_RETURNED',
                'preload_sha256':payload['preload_sha256'],'post_url':observed['url'],
                'browser_elapsed_ms':failed_result['browser_elapsed_ms'],
                'phase_timings_ms':failed_result.get('phase_timings_ms',{}),
                'late_navigation_observed':True,'original_operation_state':'failed',
                'recovered_original_result':False,
                'quality_checks':{**observed['verified'],'article_page_returned':True}}
    status = {'running':'SYNC_ACTION_PENDING','unavailable':'SYNC_RECEIPT_UNAVAILABLE'}
    result = {**common, 'ok':False, 'status':status.get(observed['state'],
              'SYNC_SAVE_CHECK_REQUIRED' if observed.get('submission_requested') or
              (observation['step']=='submit' and observed.get('submission_requested') is None)
              else 'SYNC_NOT_SUBMITTED'), 'operation_state':observed['state'],
              'operation_error':observed.get('error'), 'verified':observed.get('verified'), 'observed_url':observed.get('url')}
    result['next_action'] = {
        'SYNC_ACTION_PENDING':'observe_same_receipt_later',
        'SYNC_RECEIPT_UNAVAILABLE':'read_only_saved_state_check',
        'SYNC_SAVE_CHECK_REQUIRED':'read_only_saved_state_check',
        'SYNC_NOT_SUBMITTED':'prepare_after_original_operation_ended',
    }[result['status']]
    return result


def saved_note_sections(note):
    """Compare the site's public lazy sections without depending on website code."""
    section_headings = ('定义的组分概览','定义的组分详情')
    sections = {}
    for heading in section_headings:
        candidates = []
        for match in re.finditer(r'^##[ \t]+' + re.escape(heading) + r'[ \t]*$',note,re.M):
            end = re.search(r'^##[ \t]+',note[match.end():],re.M)
            end = match.end()+end.start() if end else len(note)
            candidates.append((end-match.end(),match.start(),match.end(),end))
        if not candidates:
            continue
        _,start,body_start,end=max(candidates)
        part=note[body_start:end].strip()
        opening=re.match(r'^\s*<details\b(?=[^>]*\bcustom-details\b)[^>]*>',part,re.I)
        if opening:
            summary=re.search(r'<summary\b[^>]*>.*?</summary>',part[opening.end():],re.I|re.S)
            if not summary:
                raise ValueError('Lazy section has no summary')
            body=opening.end()+summary.end(); depth=0; close=None
            for tag in re.finditer(r'<\s*(/?)details\b[^>]*>',part,re.I):
                depth += -1 if tag[1] else 1
                if depth==0:
                    close=tag.start();break
            if close is None or close<=body:
                raise ValueError('Lazy section has unbalanced details')
            part=part[body:close].strip()
        sections[heading]=part
        # Preserve heading boundaries. Only section body is replaced in this view.
        note=note[:body_start]+'\n\n__LAZY_SECTION__\n\n'+note[end:]
    return note,sections


def confirm_saved_sync(session, action, failed_result, original_result_path, out):
    """Confirm an ended uncertain submission through normal read-only page controls."""
    observed=observe_sync(session,action,failed_result)
    if observed.get('status')!='SYNC_SAVE_CHECK_REQUIRED':
        return observed
    if not all((observed.get('verified') or {}).get(k) is True for k in
               ('edit_url_verified','title_verified','body_verified','attachment_order_verified')):
        raise ValueError('Original submission has no complete pre-submit checks')
    payload=action['payload'];validate_sync_files(payload)
    started=datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    evidence_path=out.with_suffix('.saved-page.json')
    archive=out.with_suffix('.attachments.zip')
    code=r"""async boundPage => {
      const payload=PAYLOAD;
      const target=payload.create ? boundPage.url() : payload.post_url;
      const targetUrl=new URL(target), expected=new URL(payload.post_url || payload.edit_url);
      if (targetUrl.origin!==expected.origin || !/^\/nodes\/post\/(?:local-)?[1-9][0-9]*\/$/.test(targetUrl.pathname))
        throw new Error('No confirmed article URL is available; keep the original page');
      const reuseBoundPage=boundPage.url()===target;
      const page=reuseBoundPage ? boundPage : await boundPage.context().newPage();
      try {
      if (!reuseBoundPage) await page.goto(target,{waitUntil:'commit',timeout:20000});
      const current=new URL(page.url());
      if (current.origin!==expected.origin || !/^\/nodes\/post\/(?:local-)?[1-9][0-9]*\/$/.test(current.pathname))
        throw new Error('Read-only confirmation is not on a task article');
      if (!payload.create && current.pathname.replace('/local-','/')!==new URL(payload.post_url).pathname.replace('/local-','/'))
        throw new Error('Read-only confirmation article identity mismatch');
      const post=JSON.parse(await page.locator('#post-data').textContent({timeout:15000}));
      if (post.title!==payload.desired_title) throw new Error('Saved title differs');
      const documents=(post.documents || []).filter(d=>(d.displayIn || 'sidebar')==='sidebar');
      if (JSON.stringify(documents.map(d=>d.name))!==JSON.stringify(payload.attachments.map(d=>d.name)))
        throw new Error('Saved attachment order differs');
      const sections=[];
      if (post.lazy_component_sections?.length)
        await page.waitForFunction(n => document.querySelectorAll('details[data-component-details-url]').length === n,
          post.lazy_component_sections.length, {timeout:15000});
      const nodes=page.locator('details[data-component-details-url]');
      for(let i=0;i<await nodes.count();i++) {
        const node=nodes.nth(i), path=await node.getAttribute('data-component-details-url');
        const responsePromise=page.waitForResponse(r=>new URL(r.url()).pathname===path,{timeout:20000});
        await node.locator(':scope > summary').click({noWaitAfter:true});
        const response=await responsePromise;
        const part=await response.json();
        if (!response.ok() || part.status!=='success') throw new Error('Saved lazy section could not load');
        sections.push({url:path,markdown:part.markdown});
      }
      const downloadPromise=page.waitForEvent('download',{timeout:30000});
      await page.getByRole('button',{name:'下载全部',exact:true}).click({noWaitAfter:true});
      const download=await downloadPromise;await download.saveAs(payload.confirmation_archive);
      if (await download.failure()) throw new Error('Saved attachment download failed');
      return {url:page.url(),title:post.title,content:post.content,documents,sections};
      } finally { if (!reuseBoundPage) await page.close({runBeforeUnload:false}); }
    }""".replace('PAYLOAD',json.dumps({
        **{k:payload.get(k) for k in ('create','post_url','edit_url','desired_title','attachments')},
        'confirmation_archive':str(archive.resolve())},ensure_ascii=False))
    previous_timeout=session.operation_timeout;session.operation_timeout=120
    try:
        saved=session.code(code)
    finally:
        session.operation_timeout=previous_timeout
    evidence_path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    expected=Path(payload['note']).read_text(encoding='utf-8-sig').strip()
    expected_outside,expected_sections=saved_note_sections(expected)
    styles=lambda text: {style for style in re.findall(r'<style\b[^>]*>.*?</style>',text,re.I|re.S) if '.custom-details' in style}
    if styles(expected)!=styles(saved['content']):
        raise ValueError('Saved component styles differ')
    actual_outside,actual_sections=saved_note_sections(saved['content'].strip())
    if expected_outside!=actual_outside or set(expected_sections)!=set(actual_sections):
        raise ValueError('Saved article content differs outside lazy sections')
    for heading,key in (('定义的组分概览','overview'),('定义的组分详情','details')):
        if heading not in expected_sections:
            continue
        candidates=[s for s in saved['sections'] if s['url'].rstrip('/').endswith('/'+key)]
        if candidates:
            if len(candidates)!=1 or candidates[0]['markdown']!=expected_sections[heading]:
                raise ValueError('Saved lazy section differs: '+heading)
        elif actual_sections[heading]!=expected_sections[heading]:
            raise ValueError('Saved component section differs: '+heading)
    attachment_checks=[]
    with zipfile.ZipFile(archive) as z:
        for item in payload['attachments']:
            names=[name for name in z.namelist() if Path(name).name==item['name']]
            if len(names)!=1 or hashlib.sha256(z.read(names[0])).hexdigest().upper()!=item['sha256'].upper():
                raise ValueError('Saved attachment bytes differ: '+item['name'])
            attachment_checks.append({'name':item['name'],'sha256':item['sha256']})
    validate_sync_files(payload)
    return {'ok':True,'status':'ARTICLE_SAVED_CONFIRMED',
        **{key:payload.get(key) for key in ('sync_run_id','sync_attempt','sync_started_at','preload_sha256')},
        'post_url':saved['url'],'confirmation_started_at':started,
        'confirmation_finished_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'original_result_path':str(original_result_path.resolve()),
        'original_browser_elapsed_ms':failed_result['browser_elapsed_ms'],
        'read_only':True,'saved_content_verified':True,'saved_attachment_hashes_verified':True,
        'observation':failed_result['observation'], 'evidence_path':str(evidence_path.resolve()),
        'quality_checks':{k:True for k in ('edit_url_verified','title_verified','body_verified',
                         'attachment_order_verified','article_page_returned')},
        'attachment_signatures':attachment_checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--action", type=Path)
    actions.add_argument("--action-json", help="source-read: inline action JSON without an action file")
    parser.add_argument("--mode", choices=["bind", "tab-code", "source-read", "website-prepare", "taxonomy-options", "login-status", "login-open", "select", "download", "download-observe", "preflight", "sync", "sync-observe", "sync-confirm"], required=True)
    parser.add_argument("--database", choices=['charls', 'elsa', 'hrs', 'share', 'chns', 'knhanes', 'klosa', 'mhas', 'nhanes', 'nhanesiii', 'nhis'])
    parser.add_argument('--dataset-id')
    parser.add_argument("--script", type=Path, help="tab-code: async page function restricted to the bound page")
    parser.add_argument("--tab-index", type=int, help="Observed tab-list index; only used to create a binding")
    parser.add_argument("--tab-id", help="Stable Chromium target id from mode bind; never an index")
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--result", type=Path, help="sync-observe: original unmodified failure result")
    parser.add_argument("--resume", type=Path, help="source-read: reuse completed receipts from an earlier identical request")
    parser.add_argument("--session", required=True)
    parser.add_argument("--session-workdir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument('--language', choices=['en', 'ko'])
    args = parser.parse_args()
    if args.action_json is not None and args.mode != 'source-read':
        parser.error('--action-json is only supported for source-read')
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
        if not args.tab_id or not args.database or (args.action is None and args.action_json is None):
            parser.error('source-read requires --tab-id, --database and --action-json or --action')
        try:
            action = json.loads(args.action_json) if args.action_json is not None else read_action(args.action)
            if not isinstance(action, dict):
                raise ValueError('source-read action must be a JSON object')
            if args.database == "klosa":
                from klosa_adapter_contract import require_context
                require_context(action, args.language)
            payload = run_read(
                Session(args.session, args.session_workdir, args.out.with_suffix('.browser.js'), config, args.tab_id),
                action, database_url(config, args.database, args.language, args.dataset_id), args.database, args.out, args.resume)
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
        url = database_url(config, args.database, args.language, args.dataset_id)
        if args.database == "klosa" and args.mode == "select":
            from klosa_adapter_contract import require_context
            require_context(action, args.language, url)
        if args.database == 'nhis' and args.mode == 'select':
            from nhis_export_contract import require_context
            require_context(action, args.dataset_id)
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
    if args.mode == 'download' and action.get('database') == 'nhis':
        from nhis_export_contract import require_context
        require_context(action, args.dataset_id)
        if action.get('existing_tab_path') != database_url(config, 'nhis', dataset_id=args.dataset_id):
            parser.error('NHIS download action differs from the configured dataset URL')
    preflight = read_action(args.preflight) if args.preflight else None
    target = args.out.parent / ("download-" + action.get("attempt_id", "unused") + ".zip")
    if args.mode in {'sync-observe','sync-confirm'}:
        if not args.result or not args.tab_id:
            parser.error('sync-observe requires --result and the original --tab-id')
        if args.result.resolve() == args.out.resolve():
            parser.error('Keep the original failure result; use a separate --out')
        session = Session(args.session, args.session_workdir, args.out.with_suffix('.browser.js'), config, args.tab_id)
        try:
            if args.mode == 'sync-confirm':
                payload = confirm_saved_sync(session, action, read_action(args.result),args.result,args.out)
            else:
                payload = observe_sync(session, action, read_action(args.result))
                if payload.get("late_navigation_observed"):
                    payload["original_result_path"] = str(args.result.resolve())
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            payload = {'ok':False, 'status':'SYNC_CONFIRMATION_INCOMPLETE',
                       'error':str(exc), 'read_only':True, 'allow_resubmit':False,
                       'next_action':'resolve_the_reported_evidence_gap',
                       'original_result_path':str(args.result.resolve())}
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get('ok') else 1)
    if args.mode == "sync":
        payload = run_sync(Session(args.session, args.session_workdir, args.out.with_suffix(".browser.js"), config, args.tab_id),
                           action, preflight)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload.get("ok") else 1)
    code = bind_code(build_code(action, args.mode, preflight, target), args.tab_id)
    if args.mode == "download":
        # Claim locally before dispatch: a timeout must never cause a second paid click.
        attempt_file = Path(action["attempt_file"])
        with attempt_file.open("x", encoding="utf-8") as handle:
            json.dump({"attempt_id": action["attempt_id"], "session": args.session,
                       "status": "claimed_before_cli_dispatch"}, handle)
    try:
        with temporary_browser_script(code) as code_path:
            result = subprocess.run(
                command + ["-s=" + args.session, "--raw", "run-code", "--filename", str(code_path)],
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
