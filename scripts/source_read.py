"""Read source pages sequentially and preserve a receipt for each completed period."""
import hashlib
import json
from pathlib import Path
import subprocess
import uuid


def browser_code(action, url, database):
    if database not in {"charls", "share"}:
        raise ValueError("source-read supports CHARLS and SHARE; other databases are not verified")
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
        for key in ("variable", "file"):
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
    if out.exists():
        raise ValueError("Output already exists; choose a new receipt path")
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
    if previous:
        state["completed"] = list(previous["completed"])
        for item in state["completed"]:
            path = Path(item["receipt"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Completed receipt changed; do not reuse it")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if not receipt.get("ok") or receipt["action"] != parts[item["index"]]:
                raise ValueError("Completed receipt identity mismatch")
        if [x["index"] for x in state["completed"]] != list(range(len(state["completed"]))):
            raise ValueError("Completed receipts must be a sequential prefix")
    out.parent.mkdir(parents=True, exist_ok=True)
    receipt_dir = out.parent / (out.stem + "-receipts")
    receipt_dir.mkdir(exist_ok=False)

    def save():
        state["remaining_periods"] = [p["periods"][0] for p in parts[len(state["completed"]):]] if action["kind"] == "detail" else []
        temporary = out.with_suffix(out.suffix + ".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(out)

    def capture(index, part, result):
        receipt = receipt_dir / (uuid.uuid4().hex + ".json")
        receipt.write_text(json.dumps({"action": part, **result}, ensure_ascii=False, indent=2), encoding="utf-8")
        item = {"index": index, "receipt": str(receipt.resolve()),
                "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}
        if result.get("ok"):
            state["completed"].append(item)
            state["pending"] = None
        else:
            state["failed"] = item
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
        state.update(variable=action["variable"], file=action["file"], details=[])
        for item in state["completed"]:
            state["details"].extend(json.loads(Path(item["receipt"]).read_text(encoding="utf-8"))["details"])
    else:
        # Preserve the existing directory/search result interface.
        receipt = json.loads(Path(state["completed"][0]["receipt"]).read_text(encoding="utf-8"))
        state.update({k: v for k, v in receipt.items() if k not in {"action", "ok", "status"}})
    save()
    return state
