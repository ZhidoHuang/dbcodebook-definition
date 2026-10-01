"""Read explicitly selected Codex logs; missing telemetry stays unknown, never zero."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path


def moment(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def summarize_log(path, start, end):
    start, end = moment(start), moment(end)
    totals = Counter()
    native_totals = Counter()
    native_requests = 0
    native_peak = None
    response_ids = set()
    calls = Counter()
    previous = None
    samples = requests = outputs = 0
    peak = None
    identity = None
    seen_events = set()
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line in stream:
            event = json.loads(line)
            p = event.get("payload", {})
            kind = event.get("type")
            if kind == "session_meta":
                identity = p.get("id")
            if not event.get("timestamp"):
                continue
            when = moment(event["timestamp"])
            if when > end:
                continue
            inside = start <= when
            if kind == "token_usage_record":
                response_id = p.get("response_id")
                if response_id and response_id in response_ids:
                    continue
                if response_id:
                    response_ids.add(response_id)
                native = p.get("usage")
                if inside and isinstance(native, dict):
                    native_requests += 1
                    for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                        if isinstance(native.get(key), int):
                            native_totals[key] += native[key]
                    if isinstance(native.get("input_tokens"), int):
                        native_peak = max(native_peak or 0, native["input_tokens"])
            # Cumulative counts can reset on resume; subtract baselines even
            # before the requested range instead of charging prior work again.
            info = p.get("info") or {}
            usage = info.get("total_token_usage") if p.get("type") == "token_count" else None
            if kind == "event_msg" and isinstance(usage, dict):
                if usage == previous:
                    continue
                keys = ("input_tokens", "cached_input_tokens", "output_tokens")
                if inside:
                    samples += 1
                    for key in keys:
                        current = usage.get(key)
                        old = (previous or {}).get(key, 0)
                        if isinstance(current, int):
                            totals[key] += current - old if current >= old else current
                    last = info.get("last_token_usage") or {}
                    if isinstance(last.get("input_tokens"), int):
                        peak = max(peak or 0, last["input_tokens"])
                    requests += 1
                previous = usage
            if not inside or kind != "response_item":
                continue
            if p.get("type") in {"function_call", "custom_tool_call"}:
                call_id = p.get("call_id")
                if call_id and call_id in seen_events:
                    continue
                if call_id:
                    seen_events.add(call_id)
                args = p.get("arguments", p.get("input", ""))
                if not isinstance(args, str):
                    args = json.dumps(args, sort_keys=True)
                signature = p.get("name", "unknown") + "\n" + args
                calls[hashlib.sha256(signature.encode()).hexdigest()] += 1
            elif p.get("type") in {"function_call_output", "custom_tool_call_output"}:
                value = p.get("output", "")
                outputs = max(outputs, len(value if isinstance(value, str) else json.dumps(value)))
    # The desktop can emit both formats for the same requests. Prefer its
    # per-response usage and never add cumulative fallback counters to it.
    if native_requests:
        totals, requests, samples, peak = native_totals, native_requests, native_requests, native_peak
    return {"log": str(Path(path).resolve()), "session_id": identity,
            "usage_format": "per_response" if native_requests else "cumulative_events",
            "usage_samples": samples, "requests_with_usage": requests if samples else None,
            "tokens": dict(totals) if samples else None,
            "largest_request_input_tokens": peak,
            "tool_calls": sum(calls.values()),
            "repeated_identical_tool_calls": sum(n - 1 for n in calls.values()),
            "max_tool_output_chars": outputs,
            "limitations": ["Usage samples are not necessarily all model requests.",
                            "Repeated calls are not necessarily waste or failures.",
                            "File rereads and causal retries cannot be inferred reliably from arbitrary shell code.",
                            "Cached input is part of input; tokens are not prices or quota percentages."]}


def find_logs(root, agent_id, parent_id=None):
    """Filename selection first, then verify identity; never search log bodies broadly."""
    result = []
    for path in Path(root).rglob(f"*{agent_id}*.jsonl"):
        with path.open(encoding="utf-8-sig") as stream:
            first = json.loads(next(stream))
        p = first.get("payload", {})
        source = p.get("source", {})
        spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
        recorded_parent = spawn.get("parent_thread_id") or p.get("forked_from_id")
        if p.get("id") == agent_id and (not parent_id or recorded_parent == parent_id):
            result.append(str(path.resolve()))
    return sorted(result)
