"""Offline input contracts and browser failure branches; no website or paid export."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_source_selection import build_action, browser_code, parse_selection


def main():
    action = build_action('q1 (Core data)=q1,\nq1 (Other file)=q1_other',
                          'http://localhost:8000/home/elsa/')
    assert action['aliases'] == ['q1', 'q1_other']
    for invalid in ['', 'q1=x', 'q1 (Core)=', 'q1 (Core)=x\nq2 (Core)=x',
                    'q1 (Core)=x\nq1 (Core)=y', 'q1 (Core)=a=b']:
        try:
            parse_selection(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Accepted invalid selection: ' + invalid)
    try:
        browser_code({**action, 'aliases': ['tampered']}, 'select')
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted inconsistent action')
    fixture = r'''
const assert = require('node:assert/strict');
const run = ACTION_CODE;
const loginStatus = LOGIN_STATUS_CODE;
const loginOpen = LOGIN_OPEN_CODE;
async function scenario(options = {}) {
  const calls = [];
  const locator = selector => ({
    count: async () => selector === '#tag-area .tag' ? (options.count ?? 2) : 1,
    isVisible: async () => !!options.open,
    waitFor: async () => {if (options.stuck) throw Error('still loading');},
    fill: async value => {assert.equal(value, __INPUT_TEXT__); calls.push('fill');},
    click: async () => {
      calls.push(selector);
      if (selector.includes('confirm')) assert.ok(calls.includes('listen'));
    }
  });
  const page = {
    url: () => options.wrong ? 'http://localhost:8000/home/charls/' : 'http://localhost:8000/home/elsa/',
    evaluate: async () => options.auth === undefined ? true : options.auth,
    locator,
    getByRole: (role, args) => {
      assert.equal(role,'button'); assert.equal(args.name,'批量输入标签');
      return locator('open');
    },
    waitForResponse: async predicate => {
      calls.push('listen');
      const response = {
        url: () => 'http://localhost:8000/home/elsa/validate_tags/',
        request: () => ({method: () => 'POST'}),
        ok: () => true,
        json: async () => options.reject ? {valid_tags:[{}],invalid_tags:['missing']} :
          options.malformed ? {} : {valid_tags:[{},{}],invalid_tags:[]}
      };
      assert.ok(predicate(response));
      assert.equal(predicate({...response,url:()=> 'http://other/home/elsa/validate_tags/'}),false);
      if (options.timeout) throw Error('timeout');
      return response;
    }
  };
  const result = await (options.mode === 'login-status' ? loginStatus :
    options.mode === 'login-open' ? loginOpen : run)(page);
  assert.ok(calls.filter(x => x.includes('confirm')).length <= 1);
  return {result,calls};
}
(async () => {
  for (const [options,status] of [
    [{},'SELECTION_READY'], [{wrong:true},'WRONG_PAGE'],
    [{auth:false},'LOGIN_REQUIRED'], [{auth:null},'LOGIN_STATE_UNKNOWN'],
    [{open:true},'INPUT_DIALOG_ALREADY_OPEN'], [{reject:true},'SOURCE_REJECTED'],
    [{malformed:true},'SELECTION_UNCERTAIN'], [{timeout:true},'SELECTION_UNCERTAIN'],
    [{count:1},'SELECTION_COUNT_MISMATCH'], [{stuck:true},'SELECTION_UNCERTAIN']]) {
    const {result,calls} = await scenario(options);
    assert.equal(result.status,status);
    if (options.wrong || options.auth === false || options.auth === null || options.open)
      assert.deepEqual(calls,[]);
  }
  assert.equal((await scenario({mode:'login-status'})).result.status,'LOGGED_IN');
  const login = await scenario({mode:'login-open',auth:false});
  assert.equal(login.result.status,'LOGIN_REQUIRED');
  assert.deepEqual(login.calls,['.auth-panel-trigger[data-mode="login"]:visible']);
  assert.deepEqual((await scenario({mode:'login-open'})).calls,[]);
})().catch(error => {console.error(error);process.exitCode=1;});
'''
    with tempfile.TemporaryDirectory() as folder:
        test = Path(folder) / 'test.cjs'
        test.write_text(fixture.replace('ACTION_CODE', browser_code(action, 'select'))
                        .replace('LOGIN_STATUS_CODE', browser_code({'url': action['url']}, 'login-status'))
                        .replace('LOGIN_OPEN_CODE', browser_code({'url': action['url']}, 'login-open'))
                        .replace('__INPUT_TEXT__', json.dumps(action['input_text'])), encoding='utf-8')
        subprocess.run(['node', str(test)], check=True)
        root = Path(folder)
        config = root / 'config.json'
        config.write_text(json.dumps({'schema_version': 1, 'website': {'base_url': 'http://localhost:8000',
                          'database_paths': {'elsa': '/home/elsa/'}}}), encoding='utf-8')
        source, output, aliases = (root / name for name in ('input.txt', 'action.json', 'aliases.txt'))
        source.write_text(action['input_text'], encoding='utf-8')
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/prepare_source_selection.py'),
                   '--config', str(config), '--database', 'elsa', '--input', str(source),
                   '--action-file', str(output), '--expect-vars-file', str(aliases)]
        subprocess.run(command, check=True, capture_output=True)
        assert json.loads(output.read_text(encoding='utf-8')) == action
        assert aliases.read_text(encoding='utf-8').splitlines() == action['aliases']
        previous = (output.read_bytes(), aliases.read_bytes())
        source.write_text('missing-file=alias', encoding='utf-8')
        assert subprocess.run(command, capture_output=True).returncode != 0
        assert previous == (output.read_bytes(), aliases.read_bytes()), 'Invalid input overwrote outputs'
    print('SOURCE_SELECTION_TESTS_PASS (offline fixtures only)')


if __name__ == '__main__':
    main()
