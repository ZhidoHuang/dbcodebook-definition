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
from playwright_session_action import build_code
from recover_dbcodebook_export import build_download_browser_action


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-session")
    parser.add_argument("--session-workdir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
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
