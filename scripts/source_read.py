"""Read source pages sequentially; keep evidence and recovery in one current file."""
import hashlib
import json
from pathlib import Path
import subprocess
import uuid


def receipt_hash(receipt):
    return hashlib.sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def saved_receipt(item, state):
    if 'receipt' in item:  # Read existing external evidence without rewriting it.
        content = Path(item['receipt']).read_bytes()
        if hashlib.sha256(content).hexdigest() != item['sha256']:
            raise ValueError('Completed receipt changed; do not reuse it')
        return json.loads(content.decode('utf-8'))
    receipt = dict(item['result'])
    if 'details_slice' in item:
        start, end = item['details_slice']
        receipt['details'] = state['details'][start:end]
    for key in item.get('fields', []):
        receipt[key] = state[key]
    if receipt_hash(receipt) != item['sha256']:
        raise ValueError('Completed receipt changed; do not reuse it')
    return receipt


def browser_code(action, url, database):
    if database not in {"charls", "share", "elsa", "hrs", "klosa", "chns", "knhanes", "mhas"}:
        raise ValueError("Unsupported source-read database")
    if database == "klosa":
        from klosa_adapter_contract import require_context, page_url
        from urllib.parse import urlsplit
        require_context(action, action.get("language"))
        origin = urlsplit(url)
        if url != page_url(f"{origin.scheme}://{origin.netloc}", action["language"]):
            raise ValueError("KLoSA URL and language differ")
    kind = action.get("kind")
    if kind not in {"directory", "search", "detail"}:
        raise ValueError("kind must be directory, search or detail")
    if kind == "directory":
        path = action.get("path", [])
        if not isinstance(path, list) or len(path) > 6 or any(not isinstance(x, str) or not x.strip() or any(c in x for c in "[]") for x in path):
            raise ValueError("path must contain up to six nonempty directory names")
    elif kind == "search":
        if not isinstance(action.get("query"), str) or len(action["query"].strip()) < 2:
            raise ValueError("query must contain at least two characters")
    else:
        identity_key = "base_variable" if database in {"hrs", "klosa", "mhas"} else "variable"
        other_key = "variable" if identity_key == "base_variable" else "base_variable"
        if other_key in action:
            raise ValueError(f"{database} detail uses {identity_key} from the search result")
        for key in (identity_key, "file"):
            if not isinstance(action.get(key), str) or not action[key].strip() or any(c in action[key] for c in "[]"):
                raise ValueError(f"detail requires an unambiguous {key}")
        periods = action.get("periods")
        if not isinstance(periods, list) or not 1 <= len(periods) <= 6 or any(not isinstance(x, str) or not x.strip() for x in periods) or len(set(periods)) != len(periods):
            raise ValueError("detail requires one to six distinct period strings")
    helper = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return "async page => await (" + helper + ")(page," + json.dumps({**action, "url": url, "database": database}, ensure_ascii=False) + ")"


def run_read(session, action, url, database, out, resume=None):
    """One source per request, one period per browser call; never replay a pending call."""
    out = Path(out)
    if out.exists() and (not resume or out.resolve() != Path(resume).resolve()):
        raise ValueError("Output already exists; use --resume with this same file to continue")
    if action.get("kind") == "detail":
        periods = action.get("periods")
        if not isinstance(periods, list) or not periods or any(not isinstance(p, str) or not p.strip() for p in periods) or len(set(periods)) != len(periods):
            raise ValueError("detail requires distinct nonempty periods")
        parts = [{**action, "periods": [period]} for period in periods]
    else:
        parts = [action]
    for part in parts:
        browser_code(part, url, database)  # Validate everything before browser activity.
    digest = hashlib.sha256(Path(__file__).with_suffix(".js").read_bytes() + Path(__file__).read_bytes()).hexdigest()
    binding = {"action": action, "url": url, "database": database,
               "tab_id": session.tab_id, "session": session.command, "helper_sha256": digest}
    previous = json.loads(Path(resume).read_text(encoding="utf-8-sig")) if resume else None
    if previous and previous.get("binding") != binding:
        raise ValueError("Resume requires the same action, browser binding and helper version")
    state = {"ok": False, "status": "READ_INCOMPLETE", "binding": binding,
             "completed": [], "pending": None, "failed": None}
    if action['kind'] == 'detail':
        state['details'] = []

    def store_result(index, receipt):
        item = {'index': index, 'sha256': receipt_hash(receipt), 'result': dict(receipt)}
        if action['kind'] == 'detail':
            details = item['result'].pop('details')
            start = len(state['details'])
            state['details'].extend(details)
            item['details_slice'] = [start, len(state['details'])]
        else:
            fields = [key for key in receipt if key not in {'action', 'ok', 'status'}]
            if any(key in state for key in fields):
                raise ValueError('Source result collides with recovery fields')
            item['fields'] = fields
            for key in fields:
                state[key] = item['result'].pop(key)
        state['completed'].append(item)

    if previous:
        completed = previous['completed']
        if len(completed) > len(parts) or [x['index'] for x in completed] != list(range(len(completed))):
            raise ValueError('Completed receipts must be a sequential prefix')
        for item in completed:
            receipt = saved_receipt(item, previous)
            if not receipt.get("ok") or receipt["action"] != parts[item["index"]]:
                raise ValueError("Completed receipt identity mismatch")
            store_result(item['index'], receipt)
        if previous.get('pending') and (previous['pending']['index'] != len(completed) or len(completed) >= len(parts)):
            raise ValueError('Pending index does not follow completed receipts')
        if previous.get('ok') and out.resolve() == Path(resume).resolve():
            if len(completed) != len(parts) or previous.get('pending'):
                raise ValueError('Successful result has unfinished periods')
            return previous
    out.parent.mkdir(parents=True, exist_ok=True)

    def save():
        state["remaining_periods"] = [p["periods"][0] for p in parts[len(state["completed"]):]] if action["kind"] == "detail" else []
        temporary = out.with_suffix(out.suffix + ".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(out)

    def capture(index, part, result):
        receipt = {"action": part, **result}
        if result.get("ok"):
            store_result(index, receipt)
            state["pending"] = None
            state['failed'] = None
        else:
            state["failed"] = {'index': index, 'result': receipt}
            state["status"] = result.get("status", "READ_INCOMPLETE")
        save()
        return bool(result.get("ok"))

    if previous and previous.get("pending"):
        state["pending"] = previous["pending"]
        save()
        # Observe the original operation; this code performs no page interaction.
        request_id = state["pending"]["request_id"]
        observe = """async page => {
          const r = page[Symbol.for('dbCodeBook.sourceRead')];
          if (!r || r.request_id !== REQUEST) return {ok:false,status:'READ_STATE_UNKNOWN'};
          return r.running ? {ok:false,status:'READ_STILL_RUNNING'} :
            {ok:true,status:'READ_FINISHED',result:r.result};
        }""".replace("REQUEST", json.dumps(request_id))
        try:
            observed = session.code(observe)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            observed = {"ok": False, "status": "READ_STATE_UNKNOWN", "error": str(exc)}
        if not observed.get("ok"):
            state["status"] = observed["status"]
            save()
            return state
        index = len(state["completed"])
        state["pending"] = None
        if not capture(index, parts[index], observed["result"]):
            return state  # Save the ended failure first; an explicit later resume may retry it.

    for index in range(len(state["completed"]), len(parts)):
        part = parts[index]
        request_id = uuid.uuid4().hex
        state["pending"] = {"index": index, "request_id": request_id}
        save()  # Save before dispatch, including when Python/CLI later times out.
        try:
            result = session.code(browser_code({**part, "request_id": request_id}, url, database))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            state.update(status="READ_ACTION_UNCERTAIN", error=str(exc))
            save()
            return state
        state["pending"] = None
        if not capture(index, part, result):
            return state
    state.update(ok=True, status={"detail":"SOURCE_READ", "directory":"DIRECTORY_READ", "search":"SEARCH_READ"}[action["kind"]])
    if action["kind"] == "detail":
        identity_key = "base_variable" if database in {"hrs", "klosa", "mhas"} else "variable"
        state.update({identity_key:action[identity_key], "file":action["file"]})
    save()
    return state
