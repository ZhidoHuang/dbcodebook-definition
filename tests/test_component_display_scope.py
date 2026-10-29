"""Retired component generation must not write or fall back to another runner."""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import component_display as c

with tempfile.TemporaryDirectory(prefix='component_retirement_') as temporary:
    root = Path(temporary)
    formal, process = root/'formal', root/'process'
    formal.mkdir(); process.mkdir()
    (formal/'raw_data.csv').write_text('id,value\n1,7\n', encoding='utf-8')
    (process/c.MARKER).write_text('{"status":"prepared"}', encoding='utf-8')
    def snapshot():
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file()}
    before = snapshot()
    for command in ('prepare', 'run', 'retry', 'finish', 'periods'):
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8',
            str(ROOT/'scripts/update_reader_copy.py'), command, '--component-only',
            '--formal-dir', str(formal), '--process-dir', str(process),
            '--reason', 'Retirement test: preserve all existing files and never regenerate.'],
            capture_output=True, text=True, encoding='utf-8')
        assert run.returncode == 1 and '已退役' in run.stderr, run.stdout + run.stderr
        assert snapshot() == before, 'Retired entry wrote or removed files'
    assert not hasattr(c, 'prepare') and not hasattr(c, 'run')
    # Keep historical verification fail-closed. Existing evidence must not be
    # accepted after candidate or evidence changes; no generation is involved.
    evidence = process/'historical.log'; evidence.write_text('original', encoding='utf-8')
    baseline = dict(topic='001', note='note.md', r='define.R', four={
        'analysis_codebook_x.xlsx':'', 'analysis_db_x.xlsx':'', 'codebook_x.xlsx':'', 'db_x.xlsx':''})
    receipt = dict(status='verified', files={p.name:c.sha(p) for p in formal.iterdir()},
                   evidence={str(evidence):c.sha(evidence)})
    with patch.object(c, 'inputs', return_value=(receipt, baseline, process)):
        evidence.write_text('changed', encoding='utf-8')
        try:
            c.verify(formal, process, '001')
        except ValueError as error:
            assert 'evidence changed' in str(error), error
        else:
            raise AssertionError('Changed historical evidence was accepted')
print('COMPONENT_RETIREMENT_PASS: all mutation commands rejected without writes; historical tampering rejected')
