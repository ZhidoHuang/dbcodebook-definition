"""Preserve observed writing versions; never infer a semantic PASS."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COPY_SCOPES = ("title_summary", "definition_logic", "criteria", "insight_card", "references")


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def skill_version(root=ROOT):
    """Hash executable guidance, not PDFs, caches, credentials or browser state."""
    candidates = [root / "SKILL.md", root / "references/database-routing.json", root / "references/database-themes.json"]
    for folder in ("scripts", "templates", "references/rules", "references/databases"):
        candidates.extend(p for p in (root / folder).rglob("*")
                          if p.is_file() and p.suffix.lower() in {".py", ".r", ".ps1", ".js", ".md", ".json"}
                          and "__pycache__" not in p.parts)
    files = {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(set(candidates)) if p.is_file()}
    return {"id": digest(files), "files": files}


def capture_copy(report, process_dir, stage, copy_path=None):
    """Called at the existing copy handoff. First means first, even if uncaptured."""
    version = skill_version()
    report.setdefault("skill_versions", {})[version["id"]] = version["files"]
    candidates = [Path(copy_path)] if copy_path else [Path(p) for p in stage.get("outputs", []) if Path(p).name == "文案.md"]
    if len(candidates) > 1:
        raise ValueError("copy 环节有多个文案路径，请用 --copy 明确本次文案")
    entry = {"captured_at": datetime.now().astimezone().isoformat(), "skill_version": version["id"],
             "skill_changed_since_start": version["id"] != report.get("skill_version_at_start"),
             "summary": list(stage.get("summary", [])), "stage_attempt": stage.get("attempt")}
    if not candidates:
        entry.update(status="not_recorded", reason="copy 环节未提供文案路径；后续修稿不能补称首次稿")
    else:
        source = candidates[0].expanduser().resolve()
        data = source.read_bytes()
        if not data.strip():
            raise ValueError("首次文案快照不能保存空文件")
        folder = Path(process_dir) / "copy_versions" / report["run_id"]
        folder.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z") + ".md"
        target = folder / filename
        with target.open("xb") as handle:
            handle.write(data)
        entry.update(status="captured", source_path=str(source), snapshot_path=str(target.resolve()),
                     sha256=digest(data), bytes=len(data))
    report.setdefault("copy_history", []).append(entry)
    report.setdefault("first_copy", dict(entry))
    return entry


def copy_execution_conclusions(process_dir, copy_path):
    report_path = Path(process_dir) / "execution_report.json"
    if not report_path.is_file():
        return {"status": "unavailable"}
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    history = report.get("copy_history", [])
    if not history:
        return {"status": "unavailable"}
    entry = history[-1]
    if entry.get("status") != "captured" or entry.get("sha256") != digest(Path(copy_path).read_bytes()):
        return {"status": "stale", "reason": "执行结论未绑定当前文案"}
    return {"run_id": report["run_id"], **entry,
            "status": "available", "semantic_pass_inferred": False}


def scope_bindings(formal_dir, process_dir, artifacts):
    from check_reader_copy import read_copy
    formal_dir, process_dir = Path(formal_dir), Path(process_dir)
    path = formal_dir / "文案.md"
    content = read_copy(path)
    source = process_dir / "definition_search_record.json"
    common = {"source": digest(source.read_bytes()) if source.is_file() else None,
              "artifacts": {k: v["sha256"] for k, v in artifacts.items() if k != "note"},
              "writing_rules": {name: digest((ROOT / name).read_bytes()) for name in (
                  "references/rules/stages/03-copy.md", "templates/reader-copy.md")}}
    title = path.read_text(encoding="utf-8-sig").splitlines()[0]
    note_path = artifacts.get("note", {}).get("path")
    note_title = None
    if note_path and (formal_dir / note_path).is_file():
        match = re.search(r"(?m)^# (.+)$", (formal_dir / note_path).read_text(encoding="utf-8-sig"))
        note_title = match[1] if match else None
    sections = {
        "title_summary": [title, note_title, content["summary"], content["criteria"], content.get("questionnaire")],
        "definition_logic": [content["criteria"], content.get("questionnaire")],
        "criteria": content["criteria"],
        "insight_card": content,
        "references": content["references"],
    }
    return {name: digest([common, sections[name]]) for name in COPY_SCOPES}


def carry_copy_scopes(previous, payload):
    """Only carry explicit, previously passed judgments with identical dependencies."""
    if previous.get("status") != "FULL_TEXT_READABILITY_PASS":
        return []
    previous_scopes = {scope["name"]: scope for scope in previous.get("scopes", [])}
    carried = []
    for scope in payload["scopes"]:
        name = scope["name"]
        old = previous_scopes.get(name, {})
        binding = payload["copy_scope_bindings"].get(name)
        if (binding and binding == previous.get("copy_scope_bindings", {}).get(name)
                and old.get("result") == "pass" and old.get("evidence", "").strip()
                and not previous.get("unresolved_issues")):
            scope.update(old)
            carried.append(name)
    return carried
