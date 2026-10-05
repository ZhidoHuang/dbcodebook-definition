"""Explicit free browser probe: delayed blob download across separate CLI calls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from skill_config import load_config, playwright_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    folder = args.out.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    cli = playwright_command(load_config(args.config)) + ['-s=late-probe-' + uuid.uuid4().hex[:10]]
    results = {}
    def call(*parts):
        result = subprocess.run(cli + list(parts), cwd=folder, capture_output=True,
                                encoding='utf-8', timeout=55)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout
    helper = (ROOT / 'scripts/download_capture.js').read_text(encoding='utf-8')
    target = folder / 'late.bin'
    def run(name, body):
        script = folder / (name + '.js')
        script.write_text('async page => {\n' + helper + '\n' + body + '\n}', encoding='utf-8')
        value = json.loads(call('--raw', 'run-code', '--filename', str(script)))
        results[name] = value
        return value
    try:
        call('open', 'about:blank', '--browser', 'chrome', '--headed', '--profile', str(folder / 'profile'))
        initial = run('start', '''
await page.setContent('<button id="start">Local delayed download</button>');
await page.evaluate(() => {
  window.probeClicks=0;
  document.querySelector('#start').onclick=()=>{
    window.probeClicks++;
    setTimeout(()=>{
      const a=document.createElement('a');
      a.href=URL.createObjectURL(new Blob(['late-download-fixture']));a.download='late.bin';a.click();
    },35000);
  };
});
downloadCapture(page,'probe',TARGET);
await page.locator('#start').click();
return observeDownload(page,'probe',1);
'''.replace('TARGET', json.dumps(str(target))))
        assert initial['status'] == 'DOWNLOAD_EVENT_PENDING', initial
        first = run('observe1', "return observeDownload(page,'probe');")
        assert first['status'] == 'DOWNLOAD_EVENT_PENDING', first
        second = run('observe2', "return observeDownload(page,'probe');")
        assert second['status'] == 'DOWNLOAD_FILE_READY', second
        clicks = run('click_count', "return {clicks:await page.evaluate(()=>window.probeClicks)};")
        assert clicks['clicks'] == 1, clicks
        results['file_hash_matches'] = target.is_file() and hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(b'late-download-fixture').digest()
        assert results['file_hash_matches']
        results['ok'] = True
    finally:
        results['close'] = call('close')
        (folder / 'result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': results['ok'], 'clicks': 1, 'delay_seconds':35, 'file_hash_matches':True}))


if __name__ == '__main__':
    main()
