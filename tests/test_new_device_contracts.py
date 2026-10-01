import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import r_runtime
import execution_metrics as metrics
import execution_report as report
import check_definition_output as output
from check_reader_copy import route_matches
assert route_matches("跳至 DB011", "跳至DB011")
assert route_matches("跳至DB011", "跳至 DB011")
assert route_matches("DB011", "go to DB011 and then stop")
assert not route_matches("DB011", "DB0110")
assert not route_matches("DB011", "XDB011")


def event(kind, payload, second):
    return {"type": kind, "payload": payload, "timestamp": f"2026-09-22T00:00:{second:02d}+00:00"}


with tempfile.TemporaryDirectory(prefix="new_device_") as temporary:
    root = Path(temporary)
    unicode_root = root / "中文用户 工作路径"
    unicode_root.mkdir()
    config = {"paths": {"r_temp_root": str(root / "r-temp"), "r_library": str(root / "r-lib")}}
    before = dict(os.environ)
    plan = r_runtime.runtime_plan(config)
    assert plan["environment"]["R_LIBS_USER"] == str(root / "r-lib")
    assert os.environ == before
    inherited = r_runtime.runtime_plan({"paths": {}}, {"TEMP": str(root)})
    assert "R_LIBS_USER" not in inherited["environment"]
    if os.name == "nt":
        fallback = r_runtime.runtime_plan({}, {"TEMP": str(unicode_root), "PUBLIC": str(root), "USERPROFILE": str(unicode_root)})
        assert fallback["temp_root"].isascii() and Path(fallback["temp_root"]).is_dir()
        try:
            r_runtime.runtime_plan({"paths": {"r_temp_root": str(unicode_root)}})
        except ValueError as error:
            assert "ASCII" in str(error)
        else:
            raise AssertionError("Unsafe Windows launcher path was accepted")
    bad = root / "not-directory"
    bad.write_text("file")
    try:
        r_runtime.runtime_plan({"paths": {"r_temp_root": str(bad)}})
    except OSError:
        pass
    else:
        raise AssertionError("Non-directory temp root accepted")

    # Read a broken note before result checks; no audit/readiness files created.
    note = unicode_root / "note.md"
    note.write_text('<style>noise</style><p>原题与说明</p>', encoding="utf-8")
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/check_definition_readability.py"),
                             "preview", "--note", str(note)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0 and "原题与说明" in result.stdout and "noise" not in result.stdout, result
    assert list(unicode_root.iterdir()) == [note]

    # Canonical report path needs no guessed --report argument.
    args = ["check", "--complete", "--formal-dir", str(root), "--process-dir", str(unicode_root),
            "--expected-files", "raw_data.csv", "--raw-vars", "x", "--analysis-db", "db_a.xlsx",
            "--analysis-columns", "x", "--analysis-codebook", "codebook_a.xlsx", "--analysis-vars", "x",
            "--check-summary-facts", "--require-log-exit-code"]
    with patch.object(sys, "argv", args):
        parsed = output.parse_args()
    assert parsed.report == unicode_root / "result_check.json"

    formal = root / "formal"
    formal.mkdir()
    for count in (0, 1, 2):
        if count:
            (formal / f"define_{count}.R").write_text("x <- 1")
        if count == 1:
            assert output.include_formal_r(formal, ["note.md"]) == ["note.md", "define_1.R"]
        else:
            try:
                output.include_formal_r(formal, ["note.md"])
            except ValueError:
                pass
            else:
                raise AssertionError("Ambiguous or missing R should not be guessed")
    assert output.include_formal_r(formal, ["define_2.R"]) == ["define_2.R"]

    # A cumulative baseline before the interval, duplicate telemetry and reset.
    log = root / "rollout-agent-id.jsonl"
    rows = [event("session_meta", {"id": "agent-id", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}}, 0)]
    def usage(n, second):
        return event("event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": n, "cached_input_tokens": n // 2, "output_tokens": n // 10},
            "last_token_usage": {"input_tokens": 30}}}, second)
    rows += [usage(100, 1), usage(150, 3), usage(150, 4), usage(20, 5), usage(1000, 12)]
    for second in (6, 7):
        rows.append(event("response_item", {"type": "function_call", "name": "read", "arguments": "same", "call_id": str(second)}, second))
    rows.append(event("response_item", {"type": "function_call_output", "output": "x" * 80}, 8))
    log.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = metrics.summarize_log(log, "2026-09-22T00:00:02+00:00", "2026-09-22T00:00:10+00:00")
    assert result["tokens"] == {"input_tokens": 70, "cached_input_tokens": 35, "output_tokens": 7}, result
    assert result["requests_with_usage"] == 2 and result["repeated_identical_tool_calls"] == 1
    assert result["max_tool_output_chars"] == 80
    assert metrics.find_logs(root, "agent-id", "parent") == [str(log.resolve())]
    assert metrics.find_logs(root, "agent-id", "wrong-parent") == []
    empty = metrics.summarize_log(log, "2026-09-22T00:00:06+00:00", "2026-09-22T00:00:10+00:00")
    assert empty["tokens"] is None and empty["requests_with_usage"] is None

    # Native per-response records take precedence over duplicate cumulative events.
    native = event("token_usage_record", {"response_id":"resp1", "usage":
                   {"input_tokens": 40, "cached_input_tokens": 30, "output_tokens": 4}}, 9)
    with log.open("a", encoding="utf-8") as stream:
        stream.write("\n" + json.dumps(native) + "\n" + json.dumps(native))
    native_result = metrics.summarize_log(log, "2026-09-22T00:00:02+00:00", "2026-09-22T00:00:10+00:00")
    assert native_result["tokens"]["input_tokens"] == 40 and native_result["requests_with_usage"] == 1
    assert native_result["usage_format"] == "per_response"

    # Optional findings do not manufacture findings; unresolved findings block pass.
    proc = root / "process"
    report.command_init(argparse.Namespace(process_dir=str(proc), database="test", topic_id="test", topic_name="test",
        task="test", workflow="general"))
    source = root / "source.txt"
    source.write_text("stable")
    report.command_review_stage(argparse.Namespace(command="review-start", process_dir=str(proc), role="test", input=[str(source)]))
    findings = root / "findings.json"
    findings.write_text(json.dumps([{"category":"source", "location":"p1", "problem":"wrong", "evidence":"original", "changed_artifact":False,"resolved":False}]))
    with patch.object(report, "validate_stage_review", return_value={}):
        try:
            report.command_review_stage(argparse.Namespace(command="review-result", process_dir=str(proc), role="test",
                result="pass", evidence="reviewed", agent_id="a", isolated_reason=None, findings_file=findings))
        except ValueError as error:
            assert "Unresolved" in str(error)
        else:
            raise AssertionError("Unresolved finding allowed to pass")
        findings.write_text("[]")
        report.command_review_stage(argparse.Namespace(command="review-result", process_dir=str(proc), role="test",
            result="pass", evidence="reviewed", agent_id="a", isolated_reason=None, findings_file=findings))
        saved = json.loads((proc / "execution_report.json").read_text(encoding="utf-8"))
        assert saved["stage_reviews"]["test"]["findings"] == []

    # Real R launched with a Chinese user/temp path and a configured ASCII runtime.
    rscript = os.environ.get("RSCRIPT") or shutil.which("Rscript")
    pwsh = shutil.which("pwsh")
    if rscript and pwsh:
        cfg = unicode_root / "config.json"
        # Preserve installed libraries for this runtime smoke test.
        cfg.write_text(json.dumps({"schema_version":1,"paths":{"r_temp_root":str(root / "r-temp")},
                                  "executables":{"python":sys.executable}}), encoding="utf-8")
        probe = root / "r-temp" / "probe.R"
        probe.write_text('stopifnot(!grepl("[^ -~]", tempdir())); f <- tempfile(); writeLines("ok", f); stopifnot(readLines(f)=="ok"); unlink(f); cat("R_PATH_OK")', encoding="utf-8")
        def q(value):
            return "'" + str(value).replace("'", "''") + "'"
        command = f""". {q(ROOT / 'scripts/r_environment.ps1')}
$oldTemp = $env:TEMP
$state = Start-DefinitionREnvironment -Config {q(cfg)} -Python {q(sys.executable)}
try {{ & {q(rscript)} --vanilla --encoding=UTF-8 {q(probe)}; if ($LASTEXITCODE -ne 0) {{ throw 'R failed' }} }}
finally {{ Stop-DefinitionREnvironment -State $state }}
if ($env:TEMP -ne $oldTemp) {{ throw 'TEMP was not restored' }}
$state = Start-DefinitionREnvironment -Config {q(cfg)} -Python {q(sys.executable)}
try {{ throw 'simulated failure' }} catch {{ }} finally {{ Stop-DefinitionREnvironment -State $state }}
if ($env:TEMP -ne $oldTemp) {{ throw 'TEMP was not restored after failure' }}
"""
        env = {**os.environ, "TEMP":str(unicode_root), "TMP":str(unicode_root), "USERPROFILE":str(unicode_root)}
        result = subprocess.run([pwsh, "-NoProfile", "-Command", command], env=env, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0 and "R_PATH_OK" in result.stdout, (result.stdout,result.stderr)
    else:
        print("R_PATH_SMOKE_SKIP: Rscript or pwsh not configured")

print("NEW_DEVICE_CONTRACTS_PASS")
