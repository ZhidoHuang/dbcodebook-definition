"""Partial receipts, uncertain actions and explicit continuation without replay."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_read import run_read, saved_receipt


class Session:
    tab_id = "bound"
    command = ["cli", "-s=fixture"]

    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.observation = None

    def code(self, code):
        if code.startswith("async page"):
            return self.observation
        action = json.loads(code)
        period = action["periods"][0]
        self.calls.append(period)
        if self.failure == period:
            self.failure = None
            raise subprocess.TimeoutExpired("fixture", 40)
        return {"ok": True, "status": "SOURCE_READ", "details": [{"period": period, "status": "DETAIL_READ"}]}


def main():
    action = {"kind": "detail", "variable": "v", "file": "f", "periods": [f"Wave {i}" for i in range(1, 10)]}
    with tempfile.TemporaryDirectory() as directory, patch("source_read.browser_code", side_effect=lambda a, *_: json.dumps(a)):
        root = Path(directory)
        s = Session("Wave 3")
        first = run_read(s, action, "site", "share", root / "first.json")
        assert s.calls == ["Wave 1", "Wave 2", "Wave 3"]
        assert len(first["completed"]) == 2 and first["pending"]["index"] == 2
        s.observation = {"ok": False, "status": "READ_STILL_RUNNING"}
        pending = run_read(s, action, "site", "share", root / "first.json", root / "first.json")
        assert pending["status"] == "READ_STILL_RUNNING" and len(s.calls) == 3
        s.observation = {"ok": True, "result": {"ok": True, "status": "SOURCE_READ", "details": [{"period": "Wave 3"}]}}
        result = run_read(s, action, "site", "share", root / "first.json", root / "first.json")
        assert result["ok"] and len(result["details"]) == 9
        assert s.calls == action["periods"], "An already dispatched period was replayed"
        for item in result['completed']:
            assert saved_receipt(item, result)['details'][0]['period'] == action['periods'][item['index']]
        assert list(root.iterdir()) == [root / 'first.json'], 'Per-period or temporary files were retained'
        assert (root / 'first.json').read_text(encoding='utf-8').count('"DETAIL_READ"') == 8
        before = (root / 'first.json').read_bytes()
        run_read(s, action, 'site', 'share', root / 'first.json', root / 'first.json')
        assert (root / 'first.json').read_bytes() == before and s.calls == action['periods']
        try:
            run_read(s, action, "site", "share", root / "first.json")
        except ValueError:
            pass
        else:
            raise AssertionError("Previous receipt overwritten")
        s = Session("Wave 3")
        run_read(s, action, "site", "share", root / "fail.json")
        s.observation = {"ok": True, "result": {"ok": False, "status": "READ_INCOMPLETE", "operation_completed": True}}
        ended = run_read(s, action, "site", "share", root / "ended.json", root / "fail.json")
        assert not ended["ok"] and ended["pending"] is None and len(s.calls) == 3
        resumed = run_read(s, action, "site", "share", root / "retry.json", root / "ended.json")
        assert resumed["ok"] and s.calls.count("Wave 1") == 1 and s.calls.count("Wave 3") == 2
        assert resumed['failed'] is None
        resumed['details'][0]['period'] = 'tampered'
        (root / 'retry.json').write_text(json.dumps(resumed), encoding='utf-8')
        try:
            run_read(s, action, "site", "share", root / "bad.json", root / "retry.json")
        except ValueError as error:
            assert "changed" in str(error)
        else:
            raise AssertionError("Modified evidence reused")
        for kind in ('search', 'directory'):
            query = {'kind': kind, 'query': 'age'} if kind == 'search' else {'kind': kind, 'path': []}
            response = {'ok': True, 'status': kind.upper() + '_READ', 'rows': [{'label': 'Unique source text'}]}
            target = root / (kind + '.json')
            with patch.object(s, 'code', return_value=response) as read:
                r = run_read(s, query, 'site', 'share', target)
                assert r['rows'] == response['rows']
                run_read(s, query, 'site', 'share', target, target)
                assert read.call_count == 1
            assert target.read_text(encoding='utf-8').count('Unique source text') == 1
    print("SOURCE_READ_BATCH_PASS")


if __name__ == "__main__":
    main()
