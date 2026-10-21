"""Exercise the native CLI adapter against generated download and website actions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import argparse
import base64
import shutil
import hashlib
import copy
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from playwright_session_action import (
    build_code, bind_code, Session, run_sync, observe_sync, confirm_saved_sync, saved_note_sections,
)
from unittest.mock import patch
from recover_dbcodebook_export import build_download_browser_action


def exercise_sync_receipts(root):
    """Keep the original browser promise observable across unrelated CLI calls."""
    receipt_id = "a" * 32
    scope = {"sync_run_id": "fixture-run", "sync_attempt": 1, "step": "body_import"}
    original = bind_code("""async page => {
      page.imports++;
      await page.importReady;
      dbCodeBookOperationReceipt.verified = {body:true};
      return {ok:true,status:'BODY_IMPORTED'};
    }""", "fixture-target", receipt_id, retain_receipt=True, receipt_scope=scope)
    unrelated = bind_code("async page => ({ok:true,status:'READ_ONLY'})", "fixture-target", "b" * 32)
    rejected = bind_code("async page => {throw Error('fixture import failed');}",
                         "fixture-target", "c" * 32, retain_receipt=True, receipt_scope=scope)
    expired = bind_code("async page => {page.imports++;}", "fixture-target", "d" * 32,
                       expires_at_ms=1, retain_receipt=True, receipt_scope=scope)
    script = root / "sync-receipts.cjs"
    script.write_text(r"""
const assert = require('node:assert/strict');
const receiptsKey = Symbol.for('dbCodeBook.syncReceipts');
let release;
const context = {pages: () => [page]};
const page = {context:() => context, isClosed:() => false, imports:0,
  importReady:new Promise(resolve => {release=resolve;}),
  on:() => {}, off:() => {}, [Symbol.for('dbCodeBook.targetId')]:'fixture-target'};
(async () => {
  const running = (ORIGINAL)(page);
  const receipts = context[receiptsKey];
  assert.ok(receipts instanceof Map);
  const receipt = receipts.get(RECEIPT);
  assert.equal(receipt.state, 'running');
  assert.equal(receipt.submission_requested, null, 'Legacy helpers have no submit tracking evidence');
  assert.equal(receipt.tab_id, 'fixture-target');
  assert.deepEqual(receipt.scope, SCOPE);
  const operation = receipt.operation;
  assert.ok(operation instanceof Promise);
  assert.equal(page.imports, 1);
  assert.equal((await (UNRELATED)(page)).status, 'READ_ONLY');
  assert.equal(context[receiptsKey], receipts);
  assert.equal(receipts.size, 1, 'Generic code must not add or replace stable receipts');
  assert.equal(receipts.get(RECEIPT), receipt);
  assert.equal(receipt.operation, operation);
  assert.equal(receipt.state, 'running');
  release();
  const result = await running;
  assert.equal(receipt.state, 'completed');
  assert.equal(receipt.result, result);
  assert.deepEqual(receipt.verified, {body:true});
  assert.equal(await receipt.operation, result);
  assert.equal(page.imports, 1, 'Observing the original operation must not replay import');
  await assert.rejects(() => (REJECTED)(page), /fixture import failed/);
  const failed = receipts.get('c'.repeat(32));
  assert.equal(failed.state, 'failed');
  assert.match(failed.error, /fixture import failed/);
  assert.ok(failed.finished_at);
  assert.equal(receipts.get(RECEIPT), receipt, 'Later sync phases retain prior receipts');
  await assert.rejects(() => (EXPIRED)(page), /expired before execution/);
  assert.equal(receipts.size, 2);
  assert.equal(page.imports, 1);
})().catch(error => {console.error(error);process.exitCode=1;});
""".replace("ORIGINAL", original).replace("UNRELATED", unrelated)
       .replace("REJECTED", rejected).replace("EXPIRED", expired)
       .replace("RECEIPT", json.dumps(receipt_id)).replace("SCOPE", json.dumps(scope)), encoding="utf-8")
    subprocess.run(["node", str(script)], check=True)


def exercise_sync_observation(root, action, failed_result):
    scripts = []
    class Observer:
        tab_id = "fixture-target"
        observed = {"state": "running", "submission_requested": False}
        def code(self, code):
            scripts.append(code)
            return copy.deepcopy(self.observed)
        def upload(self, *args):
            raise AssertionError('Observation must not upload')
        def discard(self, *args):
            raise AssertionError('Observation must not discard')
        def select_target(self, *args):
            raise AssertionError('Observation must keep the original tab')
        def call(self, *args):
            raise AssertionError('Observation must not reload or dispatch another action')
    observer = Observer()
    original_failure = copy.deepcopy(failed_result)
    pending = observe_sync(observer, action, failed_result)
    again = observe_sync(observer, action, failed_result)
    assert pending['status'] == again['status'] == 'SYNC_ACTION_PENDING'
    assert pending['read_only'] and pending['next_action'] == 'observe_same_receipt_later'
    assert failed_result == original_failure
    assert scripts[0] == scripts[1], 'A second observation must read the same receipt'
    original_result = {"ok": True, "status": "ARTICLE_PAGE_RETURNED",
                       **{key: action['payload'][key] for key in
                          ('sync_run_id', 'sync_attempt', 'sync_started_at')}}
    observer.observed = {'state': 'completed', 'result': original_result, 'submission_requested': True}
    recovered = observe_sync(observer, action, failed_result)
    assert recovered['ok'] and recovered['status'] == 'ARTICLE_PAGE_RETURNED'
    assert recovered['recovered_original_result'] and recovered['recovery']['read_only']
    assert recovered['sync_run_id'] == original_result['sync_run_id']
    observer.observed = {'state': 'failed', 'error': 'import failed', 'submission_requested': False}
    ended = observe_sync(observer, action, failed_result)
    assert ended['status'] == 'SYNC_NOT_SUBMITTED'
    assert ended['operation_error'] == 'import failed'
    observer.observed['submission_requested'] = True
    uncertain = observe_sync(observer, action, failed_result)
    assert uncertain['status'] == 'SYNC_SAVE_CHECK_REQUIRED'
    assert uncertain['next_action'] == 'read_only_saved_state_check'
    # Old prepared helpers did not record the click boundary. A terminated
    # submit operation is still uncertain when that tracking field is absent.
    for legacy_receipt in ({'state':'failed'}, {'state':'failed', 'submission_requested':None}):
        observer.observed = legacy_receipt
        legacy_submit = observe_sync(observer, action, failed_result)
        assert legacy_submit['status'] == 'SYNC_SAVE_CHECK_REQUIRED'
        assert legacy_submit['next_action'] == 'read_only_saved_state_check'
        earlier_step = copy.deepcopy(failed_result)
        earlier_step['observation']['step'] = 'body_import'
        earlier_step['observation']['scope']['step'] = 'body_import'
        legacy_import = observe_sync(observer, action, earlier_step)
        assert legacy_import['status'] == 'SYNC_NOT_SUBMITTED'
    observer.observed = {'state': 'unavailable'}
    unavailable = observe_sync(observer, action, failed_result)
    assert unavailable['status'] == 'SYNC_RECEIPT_UNAVAILABLE' and unavailable['read_only']
    assert unavailable['next_action'] == 'read_only_saved_state_check'
    missing_receipt = copy.deepcopy(failed_result)
    missing_receipt['observation']['receipt_id'] = None
    before = len(scripts)
    unavailable = observe_sync(observer, action, missing_receipt)
    assert unavailable['status'] == 'SYNC_RECEIPT_UNAVAILABLE'
    assert len(scripts) == before, 'A missing receipt cannot dispatch or infer another action'
    # A valid failure receipt may not be used with a different action or tab.
    for key in ('sync_run_id', 'sync_attempt', 'sync_started_at'):
        changed = copy.deepcopy(failed_result)
        changed[key] = 'another synchronization'
        try:
            observe_sync(observer, action, changed)
            raise AssertionError('Mismatched synchronization identity accepted')
        except ValueError:
            pass
    for key, value in (('tab_id', 'another-target'), ('scope', {'sync_run_id': 'another-run'})):
        changed = copy.deepcopy(failed_result)
        changed['observation'][key] = value
        try:
            observe_sync(observer, action, changed)
            raise AssertionError('Mismatched observation identity accepted')
        except ValueError:
            pass
    observer.observed = {'state': 'completed', 'result': {**original_result, 'sync_attempt': 999}}
    try:
        observe_sync(observer, action, failed_result)
        raise AssertionError('Mismatched original success result accepted')
    except ValueError:
        pass

    # Execute the actual observer JavaScript with a never-finished import. Only
    # its ten-second observation timer is accelerated; the operation stays pending.
    script = root / "sync-observation.cjs"
    script.write_text(r"""
const assert = require('node:assert/strict');
const timers = [];
const realTimer = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms) => {timers.push(ms);return realTimer(fn, ms===10000 ? 1 : ms);};
const receipts = new Map();
const context = {[Symbol.for('dbCodeBook.syncReceipts')]:receipts};
const forbidden = () => {throw Error('Observation attempted a browser mutation');};
const page = {context:() => context, goto:forbidden, reload:forbidden, locator:forbidden};
const operation = new Promise(() => {});
const receipt = {tab_id:'fixture-target',scope:SCOPE,state:'running',operation};
receipts.set(RECEIPT, receipt);
receipts.set('unrelated', {state:'completed',result:{ok:true,status:'ARTICLE_PAGE_RETURNED'}});
const observe = OBSERVER;
(async () => {
  assert.equal((await observe(page)).state, 'running');
  assert.equal((await observe(page)).state, 'running');
  assert.deepEqual(timers, [10000,10000]);
  assert.equal(receipts.get(RECEIPT), receipt);
  assert.equal(receipt.operation, operation);
  receipt.state='completed'; receipt.result={ok:true,status:'ARTICLE_PAGE_RETURNED'};
  const originalScopeKeys = Object.keys(receipt.scope);
  receipt.scope=Object.fromEntries(Object.entries(receipt.scope).reverse());
  assert.notDeepEqual(Object.keys(receipt.scope),originalScopeKeys);
  const completed = await observe(page);
  assert.equal(completed.result, receipt.result);
  assert.equal(timers.length, 2, 'A completed original operation returns immediately');
  receipt.state='failed';receipt.error='late import failed';
  assert.equal((await observe(page)).error, 'late import failed');
  receipt.tab_id='another-target';
  await assert.rejects(() => observe(page), /receipt identity does not match/);
  receipts.delete(RECEIPT);
  assert.deepEqual(await observe(page), {state:'unavailable'});
})().catch(error => {console.error(error);process.exitCode=1;});
""".replace("OBSERVER", scripts[0])
       .replace("RECEIPT", json.dumps(failed_result['observation']['receipt_id']))
       .replace("SCOPE", json.dumps(failed_result['observation']['scope'])), encoding="utf-8")
    subprocess.run(["node", str(script)], check=True)


def exercise_body_import(root):
    body = 'head' * 50 + '😀' + 'tail' * 45
    path = root / 'body-import.md'
    path.write_text(body, encoding='utf-8')
    scripts = []
    session = Session('fixture', root, root / 'body-import.js', tab_id='fixture-target')
    session.body_check = {'length_utf16':len(body.encode('utf-16-le')) // 2,
                          'head':body[:160], 'tail':body[-150:]}
    session.code = lambda code: scripts.append(code) or {'ok':True}
    session.upload('#content-import-input', path)
    assert len(scripts) == 1, 'Import and completion observation must share one original receipt'
    script = root / 'body-import.cjs'
    script.write_text(r"""
const assert = require('node:assert/strict');
const body = BODY;
let editor='Existing nonempty article', imported=false, waits=0;
global.document={querySelector:selector=>{assert.equal(selector,'#editor');return {value:editor};}};
const page={
  locator:selector=>{assert.equal(selector,'#content-import-input');return {
    setInputFiles:async()=>{setTimeout(()=>{editor=body;imported=true;},20);}
  };},
  waitForTimeout:()=>{throw Error('Body import must not use a fixed sleep');},
  waitForFunction:async(fn,expected,options)=>{
    waits++;
    assert.equal(options.timeout,30000);
    assert.equal(fn(expected),false,'Old nonempty content is not a completed import');
    assert.equal(expected.length_utf16,body.length,'Body checks use browser UTF-16 length');
    for(let i=0;i<100;i++) {
      if(fn(expected)) return;
      await new Promise(resolve=>setTimeout(resolve,2));
    }
    throw Error('Body import did not finish');
  }
};
(async()=>{
  assert.deepEqual(await (IMPORT)(page),{ok:true});
  assert.equal(imported,true);assert.equal(editor,body);assert.equal(waits,1);
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('BODY',json.dumps(body)).replace('IMPORT',scripts[0]), encoding='utf-8')
    subprocess.run(['node',str(script)],check=True)


def exercise_saved_confirmation(root, source_action, failed_result):
    note = """# Fixture title

Fixture introduction.

<style>.custom-details { color: navy; }</style>

## 定义的组分概览

<details class="custom-details">
<summary>概览</summary>

| Group | Value |
| --- | --- |
| A | 1 |

</details>

## 定义的组分详情

<details class="custom-details">
<summary>详情</summary>

### Component A

Definition text.

<details><summary>Nested evidence</summary>Nested text.</details>

</details>

## References

Fixture reference.
"""
    action = copy.deepcopy(source_action)
    payload = action['payload']
    note_path = root / 'confirmation-note.md'
    note_path.write_text(note, encoding='utf-8')
    payload.update(note=str(note_path), note_sha256=hashlib.sha256(note_path.read_bytes()).hexdigest().upper(),
                   create=False, desired_title='Fixture title', post_url='http://localhost/nodes/post/123/')
    for item in payload['attachments']:
        item['name'] = Path(item['path']).name
    normalized, sections = saved_note_sections(note.strip())
    assert set(sections) == {'定义的组分概览', '定义的组分详情'}
    assert '<summary>概览</summary>' not in sections['定义的组分概览']
    assert '<details><summary>Nested evidence</summary>Nested text.</details>' in sections['定义的组分详情']
    assert normalized.count('__LAZY_SECTION__') == 2 and 'Fixture reference.' in normalized
    snapshot = {'url':payload['post_url'], 'title':payload['desired_title'],
                'content':note.replace(sections['定义的组分概览'], 'Lazy overview placeholder.')
                              .replace(sections['定义的组分详情'], 'Lazy details placeholder.'),
                'documents':[{'name':item['name']} for item in payload['attachments']],
                'sections':[{'url':'/components/123/overview', 'markdown':sections['定义的组分概览']},
                            {'url':'/components/123/details', 'markdown':sections['定义的组分详情']}]}
    verified = {key:True for key in ('edit_url_verified', 'title_verified', 'body_verified', 'attachment_order_verified')}
    out = root / 'saved-confirmation.json'
    original = root / 'original-sync-failure.json'
    original.write_text(json.dumps(failed_result), encoding='utf-8')
    original_bytes = original.read_bytes()
    class SavedSession:
        tab_id = 'fixture-target'
        operation_timeout = 40
        def __init__(self):
            self.scripts = []
            self.snapshot = copy.deepcopy(snapshot)
            self.observed = {'state':'failed', 'submission_requested':True, 'verified':verified}
            self.corrupt_attachment = False
        def code(self, code):
            self.scripts.append(code)
            if len(self.scripts) == 1:
                return self.observed
            assert self.operation_timeout == 120
            with zipfile.ZipFile(out.with_suffix('.attachments.zip'), 'w') as archive:
                for index, item in enumerate(payload['attachments']):
                    content = b'wrong remote bytes' if self.corrupt_attachment and index == 0 else Path(item['path']).read_bytes()
                    archive.writestr('saved/' + item['name'], content)
            return self.snapshot
        def upload(self, *args):
            raise AssertionError('Saved confirmation cannot upload or submit')
        def discard(self, *args):
            raise AssertionError('Saved confirmation cannot discard')
    saved_session = SavedSession()
    confirmed = confirm_saved_sync(saved_session, action, failed_result, original, out)
    assert confirmed['ok'] and confirmed['status'] == 'ARTICLE_SAVED_CONFIRMED'
    assert confirmed['read_only'] and confirmed['saved_content_verified']
    assert confirmed['saved_attachment_hashes_verified'] and len(confirmed['attachment_signatures']) == 2
    assert confirmed['original_result_path'] == str(original.resolve())
    assert original.read_bytes() == original_bytes, 'A confirmation must preserve original failure evidence'
    assert saved_session.operation_timeout == 40
    assert out.with_suffix('.saved-page.json').is_file()

    generated = root / 'saved-confirmation-browser.cjs'
    generated.write_text(r"""
const assert = require('node:assert/strict');
const saved = SNAPSHOT;
const confirm = GENERATED;
function fixture(failLazy) {
  const events=[];
  let current='about:blank', responseHandler, downloadHandler, closed=0, originalMutations=0, controlsReady=false;
  const originalMutation=()=>{originalMutations++;throw Error('Original bound page was modified');};
  const temporary={
    url:()=>current,
    goto:async(url,options)=>{assert.equal(url,saved.url);assert.equal(options.timeout,20000);current=url;events.push('goto');},
    locator:selector=>{
      if(selector==='#post-data') return {textContent:async options=>{
        assert.equal(options.timeout,15000);events.push('post');return JSON.stringify({...saved,lazy_component_sections:['overview','details']});
      }};
      assert.equal(controlsReady,true,'Wait for asynchronous article controls before reading them');
      assert.equal(selector,'details[data-component-details-url]');
      return {count:async()=>saved.sections.length,nth:index=>({
        getAttribute:async name=>{assert.equal(name,'data-component-details-url');return saved.sections[index].url;},
        locator:summary=>{assert.equal(summary,':scope > summary');return {click:async options=>{
          assert.equal(options.noWaitAfter,true);assert.ok(responseHandler,'Listen before expanding lazy content');
          events.push('summary-'+index);
          const deliver=responseHandler;responseHandler=null;
          deliver({url:()=>new URL(saved.sections[index].url,saved.url).href,ok:()=>true,
            json:async()=>{if(failLazy)throw Error('fixture lazy read failed');return {status:'success',markdown:saved.sections[index].markdown};}});
        }};}
      })};
    },
    waitForFunction:async(fn,n,options)=>{assert.equal(n,2);assert.equal(options.timeout,15000);controlsReady=true;events.push('wait-controls');},
    waitForResponse:(predicate,options)=>{assert.equal(options.timeout,20000);events.push('wait-response');
      return new Promise(resolve=>{responseHandler=response=>{assert.ok(predicate(response));resolve(response);};});},
    waitForEvent:(name,options)=>{assert.equal(name,'download');assert.equal(options.timeout,30000);events.push('wait-download');
      return new Promise(resolve=>{downloadHandler=resolve;});},
    getByRole:(role,options)=>{assert.equal(role,'button');assert.equal(options.name,'下载全部');assert.equal(options.exact,true);
      return {click:async clickOptions=>{assert.equal(clickOptions.noWaitAfter,true);assert.ok(downloadHandler);events.push('download-click');
        downloadHandler({saveAs:async path=>{assert.equal(path,ARCHIVE);events.push('save');},failure:async()=>null});}};},
    close:async options=>{assert.deepEqual(options,{runBeforeUnload:false});closed++;events.push('close');}
  };
  const bound={url:()=> 'http://localhost/nodes/edit/123/',goto:originalMutation,close:originalMutation,
    locator:originalMutation,context:()=>({newPage:async()=>{events.push('new-page');return temporary;}})};
  return {bound,events,closed:()=>closed,originalMutations:()=>originalMutations};
}
(async()=>{
  const success=fixture(false);
  assert.deepEqual(await confirm(success.bound),saved);
  assert.deepEqual(success.events,['new-page','goto','post','wait-controls','wait-response','summary-0','wait-response','summary-1',
    'wait-download','download-click','save','close']);
  assert.equal(success.closed(),1);assert.equal(success.originalMutations(),0);
  const failure=fixture(true);
  await assert.rejects(()=>confirm(failure.bound),/fixture lazy read failed/);
  assert.deepEqual(failure.events,['new-page','goto','post','wait-controls','wait-response','summary-0','close']);
  assert.equal(failure.closed(),1);assert.equal(failure.originalMutations(),0);
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('GENERATED',saved_session.scripts[1]).replace('SNAPSHOT',json.dumps(snapshot,ensure_ascii=False))
       .replace('ARCHIVE',json.dumps(str(out.with_suffix('.attachments.zip').resolve()))),encoding='utf-8')
    subprocess.run(['node',str(generated)],check=True)

    missing = SavedSession()
    missing.snapshot['sections'] = missing.snapshot['sections'][:1]
    corrupted = SavedSession()
    corrupted.corrupt_attachment = True
    wrong_section = SavedSession()
    wrong_section.snapshot['sections'][1]['markdown'] += '\nwrong saved definition'
    wrong_styles = SavedSession()
    wrong_styles.snapshot['content'] = wrong_styles.snapshot['content'].replace('color: navy;', 'color: red;')
    incomplete_checks = SavedSession()
    incomplete_checks.observed = {**incomplete_checks.observed, 'verified':{'body_verified':True}}
    for session, expected_error in ((missing, 'Saved component section differs'),
                                    (corrupted, 'Saved attachment bytes differ'),
                                    (wrong_section, 'Saved lazy section differs'),
                                    (wrong_styles, 'Saved component styles differ'),
                                    (incomplete_checks, 'no complete pre-submit checks')):
        try:
            confirm_saved_sync(session, action, failed_result, original, out)
            raise AssertionError('Incomplete saved-state evidence accepted')
        except ValueError as error:
            assert expected_error in str(error), error
        assert session.operation_timeout == 40
        assert original.read_bytes() == original_bytes
    pending = SavedSession()
    pending.observed = {'state':'running', 'submission_requested':True}
    result = confirm_saved_sync(pending, action, failed_result, original, out)
    assert result['status'] == 'SYNC_ACTION_PENDING' and len(pending.scripts) == 1
    for malformed in ('## 定义的组分详情\n\n<details class="custom-details">no summary</details>',
                      '## 定义的组分详情\n\n<details class="custom-details"><summary>Title</summary>unclosed'):
        try:
            saved_note_sections(malformed)
            raise AssertionError('Malformed saved section accepted')
        except ValueError:
            pass


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
const handlers = {};
const realTimer = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms) => realTimer(fn, ms === 30000 ? 5 : ms);
const event = {saveAs: async path => {assert.ok(path.endsWith('download.zip')); calls.push('save');}};
const final = {count: async () => 1, click: async options => {assert.equal(options.timeout,10000); calls.push('click'); handlers.download(event);}};
const modal = {getAttribute: async () => 'display: block', waitFor: async () => {}, locator: () => final};
const page = {
  evaluate: async (fn, arg) => fn(arg),
  url: () => 'http://localhost:8000/home/charls/',
  locator: selector => selector === '#tag-area .tag' ? {count: async () => 2} : selector === '#download-modal' ? modal : {count: async () => 1},
  on: (name, fn) => {handlers[name]=fn; if(name==='download')calls.push('wait');},
  off: (name) => {delete handlers[name];},
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

        failure_cases = root / "download-failures.cjs"
        failure_cases.write_text(fixture + "\nconst run = " + code + r""";
(async () => {
  const before = {...page, locator: () => {throw Error('page unavailable before click');}};
  const notClicked = await run(before);
  assert.equal(notClicked.status, 'DOWNLOAD_NOT_CLICKED');
  assert.equal(notClicked.click_requested, false);
  assert.equal(notClicked.operation_completed, true);
  assert.equal(notClicked.next_action, 'fix_cause_then_prepare_new_attempt');
  assert.deepEqual(calls, []);
  const busy = {...page, [Symbol.for('dbCodeBook.downloadCapture')]: {attempt_id:'earlier',state:'waiting'}};
  const blocked = await run(busy);
  assert.equal(blocked.status, 'DOWNLOAD_NOT_CLICKED');
  assert.equal(blocked.click_requested, false);
  assert.deepEqual(calls, []);
  final.click = async () => {calls.push('click'); throw Error('click response lost');};
  const uncertain = await run({...page, waitForEvent: async () => {throw Error('no event');}});
  assert.equal(uncertain.status, 'DOWNLOAD_EVENT_PENDING');
  assert.equal(uncertain.allow_new_export, false);
  assert.deepEqual(calls, ['wait','click']);
  calls.length = 0;
  final.click = async () => {calls.push('click'); handlers.download({saveAs:async()=>{throw Error('save failed');}});};
  const saveFailure = await run({...page});
  assert.equal(saveFailure.status, 'DOWNLOAD_PATH_UNAVAILABLE');
  assert.equal(saveFailure.allow_new_export, false);
  assert.deepEqual(calls, ['wait','click']);
})().catch(error => {console.error(error);process.exitCode=1;});
""", encoding='utf-8')
        subprocess.run(['node', str(failure_cases)], check=True)
        try:
            build_code({"preload_sha256": "wrong"}, "sync", {"preload_sha256": "other"}, root / "x")
            raise AssertionError("Mismatched preflight accepted")
        except ValueError:
            pass
        exercise_sync_receipts(root)
        # File selection returns before client-side parsing finishes. A slower first
        # file must finish rendering before a faster second file can be selected.
        upload_code = []
        bound = Session("fixture", root, root / "upload.js", tab_id="bound")
        bound.code = lambda code: upload_code.append(code) or {"ok": True}
        for name in ("large.xlsx", "small.xlsx"):
            item = root / name
            item.write_bytes(b"fixture")
            bound.upload("#documents-sidebar-input", item)
        waiting = root / "upload-wait.cjs"
        waiting.write_text("""
const assert = require('node:assert/strict');
let names = [], pending = false, waits = 0;
global.document = {querySelector: () => ({get innerText() { return names.join('\\n'); }})};
const page = {
  evaluate: async fn => fn(),
  locator: () => ({setInputFiles: async path => {
    assert.equal(pending, false, 'Previous file is still being processed');
    pending = true;
    setTimeout(() => {names.push(path.split(/[\\\\/]/).pop()); pending = false;}, 20);
  }}),
  waitForFunction: async (fn, expected, options) => {
    waits++;
    assert.equal(options.timeout, 60000);
    for (let i=0;i<100;i++) {
      if (fn(expected)) return;
      await new Promise(resolve => setTimeout(resolve, 2));
    }
    throw Error('Attachment did not finish');
  }
};
(async () => {
""" + "\n".join("await (" + code + ")(page);" for code in upload_code) + """
  assert.deepEqual(names, ['large.xlsx', 'small.xlsx']);
  assert.equal(waits, 2);
})().catch(error => {console.error(error);process.exitCode=1;});
""", encoding="utf-8")
        subprocess.run(["node", str(waiting)], check=True)
        exercise_body_import(root)
        calls = []
        operations = []
        fake_clock = {"time": 0}
        class FakeSession:
            def __init__(self):
                self.tab_id = "fixture-target"
                self.last_receipt_id = None
                self.code_calls = 0
            def record(self, name):
                calls.append(name)
                self.last_receipt_id = format(len(operations) + 1, '032x')
                operations.append((name, self.operation_timeout, self.deadline,
                                   self.retain_receipts, dict(self.receipt_scope)))
                fake_clock["time"] += 25
            def select_target(self, urls):
                self.record('select')
            def code(self, code):
                self.record('code')
                self.code_calls += 1
                if self.code_calls == 1:
                    return {"phase": "body"}
                if self.code_calls == 2:
                    return {"phase": "submit", "keep": 0}
                return {"ok": True, "status": "ARTICLE_PAGE_RETURNED",
                        "sync_run_id": "fixture-run", "sync_attempt": 1,
                        "sync_started_at": "fixture-time"}
            def upload(self, selector, path):
                self.record(selector)
            def discard(self, url):
                calls.append('discard')
                raise AssertionError('A failed transport must be observed before discard')
        files = [root / name for name in ("note.md", "data.xlsx", "book.xlsx")]
        for item in files:
            item.write_bytes(b"stable fixture")
        signature = hashlib.sha256(b"stable fixture").hexdigest().upper()
        website = {"payload": {"note": str(files[0]), "note_sha256": signature,
                   "sync_run_id": "fixture-run", "sync_attempt": 1, "sync_started_at": "fixture-time",
                   "preload_sha256": "fixture-helper",
                   "edit_url": "editor", "attachments": [{"path": str(p), "sha256": signature} for p in files[1:]]},
                   "existing_tab_match": ["editor"]}
        with patch('playwright_session_action.build_code'), patch(
                'playwright_session_action.time.monotonic', lambda: fake_clock["time"]):
            successful = FakeSession()
            result = run_sync(successful, website, {"preload_script": ""})
            assert result["ok"]
            assert calls == ['select', 'code', '#content-import-input', 'code', '#documents-sidebar-input', '#documents-sidebar-input', 'code']
            assert [item[1] for item in operations] == [40, 40, 40, 40, 65, 65, 40]
            assert all(item[2] is None and item[3] for item in operations)
            assert fake_clock['time'] > 60, 'Independent phase budgets must survive a total over 60 seconds'
            assert not successful.retain_receipts and successful.operation_timeout == 40
            calls.clear()
            failed = FakeSession()
            def fail_upload(selector, path):
                failed.record(selector)
                raise RuntimeError('fixture failure')
            failed.upload = fail_upload
            result = run_sync(failed, website, {"preload_script": ""})
            assert calls == ['select', 'code', '#content-import-input']
            assert not result["recovery_attempted"] and not result["recovery_confirmed"]
            assert not result["editor_page_restored"] and result["recovery_scope"] == 'editor_page_only'
            assert result["content_rollback_status"] == 'NOT_VERIFIED' and not result['ok']
            assert result['observation']['receipt_id'] == failed.last_receipt_id
            assert result['observation']['tab_id'] == failed.tab_id
            assert result['observation']['step'] == 'body_import'
            assert result['observation']['scope']['step'] == 'body_import'
            assert result['phase_timings_ms'] == {'identity': 25000, 'prepare': 25000, 'body_import': 25000}
            assert result['next_action'] == 'sync-observe'
            calls.clear()
            uncertain = FakeSession()
            original = uncertain.code
            def fail_submit(code):
                if uncertain.code_calls == 2:
                    uncertain.record('code')
                    raise RuntimeError('submit response lost')
                return original(code)
            uncertain.code = fail_submit
            result = run_sync(uncertain, website, {"preload_script": ""})
            assert result["status"] == 'SUBMISSION_UNCERTAIN' and 'discard' not in calls
            assert not result['recovery_attempted'] and not result['editor_page_restored']
            assert result['content_rollback_status'] == 'NOT_VERIFIED'
            assert result['sync_run_id'] == 'fixture-run' and result['sync_attempt'] == 1
            assert result['sync_started_at'] == 'fixture-time'
            assert result['observation']['step'] == 'submit'
            submission_failure = copy.deepcopy(result)
            for item in files:
                calls.clear()
                item.write_bytes(b"changed after readiness")
                result = run_sync(FakeSession(), website, {"preload_script": ""})
                assert result["status"] == "SYNC_FAILED" and "SYNC_INPUT_CHANGED" in result["error"]
                assert calls == [] and not result["recovery_attempted"]
                item.write_bytes(b"stable fixture")
            calls.clear()
            changed_during_upload = FakeSession()
            def upload_then_change(selector, path):
                changed_during_upload.record(selector)
                files[2].write_bytes(b"changed during sync")
            changed_during_upload.upload = upload_then_change
            result = run_sync(changed_during_upload, website, {"preload_script": ""})
            assert result["status"] == "SYNC_FAILED" and not result["recovery_attempted"]
            assert calls.count('code') == 2 and 'discard' not in calls
            files[2].write_bytes(b"stable fixture")
        exercise_sync_observation(root, website, submission_failure)
        exercise_saved_confirmation(root, website, submission_failure)
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
