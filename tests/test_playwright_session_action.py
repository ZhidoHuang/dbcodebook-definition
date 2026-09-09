"""Exercise the native CLI adapter against generated download and website actions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import argparse
import base64
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from playwright_session_action import build_code, Session, run_sync
from unittest.mock import patch
from recover_dbcodebook_export import build_download_browser_action


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-session")
    parser.add_argument("--session-workdir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--editor-action", type=Path, help="Exercise an authorized new-article draft; never publish")
    args = parser.parse_args()
    if args.editor_action:
        action = json.loads(args.editor_action.read_text(encoding="utf-8-sig"))["browser_action"]
        payload = action["payload"]
        assert payload["create"], "Live fixture must use a new-article draft"
        args.out.mkdir(parents=True, exist_ok=True)
        session = Session(args.live_session, args.session_workdir, args.out / "editor-test.browser.js")
        result = {}
        # The previous manual import belongs to this authorized test, not an unrelated draft.
        session.call("goto", payload["edit_url"])
        session.upload("#content-import-input", payload["note"])
        for item in payload["attachments"]:
            session.upload("#documents-sidebar-input", item["path"])
        actual = session.code('''async page => ({body: await page.locator('#editor').inputValue(),
          attachments: await page.locator('#documents-sidebar-list').innerText()})''')
        assert actual["body"] == Path(payload["note"]).read_text(encoding="utf-8-sig")
        names = [line.strip() for line in actual["attachments"].splitlines() if line.strip().endswith('.xlsx')]
        assert names == [item["name"] for item in payload["attachments"]]
        result["body_and_two_attachments"] = True
        session.call("click", "#content-import-input")
        try:
            session.call("upload", str(args.out / "intentionally-missing.md"))
            raise AssertionError("Missing upload file was accepted")
        except RuntimeError:
            result["failed_upload_detected"] = True
        restored = session.discard(payload["edit_url"])
        assert restored == {"url": payload["edit_url"], "editor": 1}
        blank = session.code('''async page => ({title: await page.locator('#title').inputValue(),
          body: await page.locator('#editor').inputValue(),
          attachments: await page.locator('#documents-sidebar-list').innerText()})''')
        assert all(not value.strip() for value in blank.values()), blank
        result.update(cancellation_and_blank_form_verified=True, login_preserved=True, submitted=False)
        (args.out / "editor-test-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        return
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        action = build_download_browser_action("http://localhost:8000", "charls", "test", 2, root / "attempt.json")
        code = build_code(action, "download", None, root / "download.zip")
        fixture = r'''
const assert = require('node:assert/strict');
const calls = [];
const final = {count: async () => 1, click: async options => {assert.equal(options.timeout,10000); calls.push('click');}};
const modal = {getAttribute: async () => 'display: block', waitFor: async () => {}, locator: () => final};
const page = {
  evaluate: async (fn, arg) => fn(arg),
  url: () => 'http://localhost:8000/home/charls/',
  locator: selector => selector === '#tag-area .tag' ? {count: async () => 2} : selector === '#download-modal' ? modal : {count: async () => 1},
  waitForEvent: async (name, options) => {
    assert.equal(name, 'download'); assert.equal(options.timeout, 30000); calls.push('wait');
    return {saveAs: async path => {assert.ok(path.endsWith('download.zip')); calls.push('save');}};
  }
};
'''
        script = root / "test.cjs"
        script.write_text(fixture + "\n(" + code + ")(page).then(result => {\n"
                          "assert.equal(result.status, 'DOWNLOAD_FILE_READY');\n"
                          "assert.deepEqual(calls, ['wait','click','save']);\n"
                          "}).catch(error => {console.error(error);process.exitCode=1;});", encoding="utf-8")
        subprocess.run(["node", str(script)], check=True)
        assert not (root / "attempt.json").exists(), "CLI action must not import fs or claim twice"
        try:
            build_code({"preload_sha256": "wrong"}, "sync", {"preload_sha256": "other"}, root / "x")
            raise AssertionError("Mismatched preflight accepted")
        except ValueError:
            pass
        calls = []
        class FakeSession:
            def select_target(self, urls):
                pass
            def code(self, code):
                calls.append('code')
                if len(calls) == 1:
                    return {"phase": "body"}
                if calls.count('code') == 2:
                    return {"phase": "submit", "keep": 0}
                return {"ok": True, "status": "ARTICLE_PAGE_RETURNED"}
            def upload(self, selector, path):
                calls.append(selector)
            def discard(self, url):
                calls.append('discard')
                return {"url": url, "editor": 1}
        website = {"payload": {"note": "note", "edit_url": "editor", "attachments": [{"path": "data"}, {"path": "book"}]},
                   "existing_tab_match": ["editor"]}
        with patch('playwright_session_action.build_code'):
            result = run_sync(FakeSession(), website, {"preload_script": ""})
            assert result["ok"]
            assert calls == ['code', '#content-import-input', 'code', '#documents-sidebar-input', '#documents-sidebar-input', 'code']
            calls.clear()
            failed = FakeSession()
            failed.upload = lambda *args: (_ for _ in ()).throw(RuntimeError('fixture failure'))
            result = run_sync(failed, website, {"preload_script": ""})
            assert result["recovery_confirmed"] and calls == ['code', 'discard']
            calls.clear()
            uncertain = FakeSession()
            original = uncertain.code
            def fail_submit(code):
                if calls.count('code') == 2:
                    raise RuntimeError('submit response lost')
                return original(code)
            uncertain.code = fail_submit
            result = run_sync(uncertain, website, {"preload_script": ""})
            assert result["status"] == 'SUBMISSION_UNCERTAIN' and 'discard' not in calls
    if args.live_session:
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / "fixture-download.zip"
        action = build_download_browser_action("http://skill-test.invalid", "charls", "fixture", 2, args.out / "unused-attempt.json")
        generated = build_code(action, "download", None, target)
        content = b"local browser transport fixture; not dbCodeBook data"
        html = '<div id="tag-area"><span class="tag">a</span><span class="tag">b</span></div>'
        html += '<button aria-label="下载数据">Open</button><div id="download-modal" style="display: block">'
        html += '<button class="bili-btn confirm" onclick="document.getElementById(\'payload\').click()">Download</button></div>'
        html += '<a id="payload" download="fixture.zip" href="data:application/zip;base64,' + base64.b64encode(content).decode() + '">fixture</a>'
        browser_code = '''async (page) => {
const fixture = await page.context().newPage();
try {
  await fixture.route('http://skill-test.invalid/**', route => route.fulfill({contentType: 'text/html; charset=utf-8', body: HTML}));
  await fixture.goto('http://skill-test.invalid/home/charls/');
  const result = await (GENERATED)(fixture);
  await fixture.setContent('<input type="file" id="upload">');
  const chooserPromise = fixture.waitForEvent('filechooser');
  await fixture.locator('#upload').click();
  await (await chooserPromise).setFiles([TARGET]);
  const count = await fixture.locator('#upload').evaluate(el => el.files.length);
  if (count !== 1) throw new Error('File chooser did not accept fixture');
  return {...result, native_filechooser: true};
} finally { await fixture.close(); }
}'''.replace('HTML', json.dumps(html)).replace('GENERATED', generated).replace('TARGET', json.dumps(str(target.resolve())))
        code_file = args.out / "transport-fixture.js"
        code_file.write_text(browser_code, encoding="utf-8")
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        run = subprocess.run([npx, "--yes", "--package", "@playwright/cli", "playwright-cli", "-s=" + args.live_session,
                              "--raw", "run-code", "--filename", str(code_file.resolve())],
                             cwd=args.session_workdir, capture_output=True, encoding="utf-8", timeout=60)
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
        result = json.loads(run.stdout)
        assert result["ok"] and result["native_filechooser"]
        assert target.read_bytes() == content
        (args.out / "transport-fixture-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("LIVE_EDGE_DOWNLOAD_AND_FILECHOOSER_PASS (local fixture, no paid website action)")
    print("PLAYWRIGHT_SESSION_ACTION_PASS")


if __name__ == "__main__":
    main()
