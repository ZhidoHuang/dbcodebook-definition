"""Validate the public skill's internal routes and portability boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
ROUTING_PATH = SKILL_ROOT / "references" / "database-routing.json"
MANIFEST_PATH = SKILL_ROOT / "references" / "source-materials" / "manifest.json"
TEXT_SUFFIXES = {".md", ".py", ".ps1", ".r", ".json", ".yaml", ".yml"}
FORBIDDEN_PATTERNS = {
    "private workspace path": re.compile(r"(?i)D:[\\/]zhido"),
    "private website source": re.compile(r"(?i)D:[\\/]project[\\/]bookapp"),
    "fixed Windows Python": re.compile(r"(?i)C:[\\/]Windows[\\/]py\.exe"),
    "fixed Windows R": re.compile(r"(?i)C:[\\/]Program Files[\\/]R[\\/]"),
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def relative_target(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must stay inside the skill: {value}")
    target = (SKILL_ROOT / path).resolve()
    if SKILL_ROOT not in target.parents and target != SKILL_ROOT:
        raise ValueError(f"{field} escapes the skill: {value}")
    if not target.exists():
        raise ValueError(f"{field} does not exist: {value}")
    return target


def validate_routes() -> dict:
    routing = load_json(ROUTING_PATH)
    if routing.get("schema_version") != 1:
        raise ValueError("database-routing schema_version must be 1")
    common = routing.get("common_rules")
    if not isinstance(common, list) or not common:
        raise ValueError("database-routing common_rules must not be empty")
    for index, value in enumerate(common):
        relative_target(value, f"common_rules[{index}]")

    databases = routing.get("databases")
    if not isinstance(databases, dict) or not databases:
        raise ValueError("database-routing databases must not be empty")
    for database, values in databases.items():
        if not isinstance(values, dict):
            raise ValueError(f"database route must be an object: {database}")
        for field in ("workflow", "profile"):
            relative_target(values.get(field), f"databases.{database}.{field}")
        source_materials = values.get("source_materials")
        if source_materials is not None:
            relative_target(source_materials, f"databases.{database}.source_materials")
    return {"common_rules": len(common), "databases": sorted(databases)}


def validate_manifest() -> dict:
    manifest = load_json(MANIFEST_PATH)
    files = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(files, list):
        raise ValueError("source-material manifest is invalid")
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"manifest files[{index}] must be an object")
        relative = item.get("path")
        expected = item.get("sha256")
        target = relative_target(relative, f"manifest files[{index}].path")
        if relative in seen:
            raise ValueError(f"manifest repeats a file: {relative}")
        seen.add(str(relative))
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"source material hash mismatch: {relative}")
    material_files = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in (SKILL_ROOT / "references" / "source-materials").rglob("*")
        if path.is_file() and path != MANIFEST_PATH
    }
    if material_files != seen:
        missing = sorted(material_files - seen)
        extra = sorted(seen - material_files)
        raise ValueError(f"source material manifest differs; missing={missing}, extra={extra}")
    return {"source_materials": len(files)}


def validate_portability() -> dict:
    issues: list[str] = []
    checked = 0
    for path in SKILL_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.name == "config.local.json":
            continue
        text = path.read_text(encoding="utf-8-sig")
        checked += 1
        for label, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                issues.append(f"{path.relative_to(SKILL_ROOT)}: {label}")
    if issues:
        raise ValueError("non-portable references found: " + "; ".join(issues))
    return {"text_files": checked}


def validate_markdown_links() -> dict:
    checked = 0
    missing: list[str] = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in SKILL_ROOT.rglob("*.md"):
        text = document.read_text(encoding="utf-8-sig")
        for raw_target in pattern.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, flags=re.I):
                continue
            checked += 1
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(SKILL_ROOT)} -> {raw_target}")
    if missing:
        raise ValueError("broken Markdown links: " + "; ".join(missing))
    return {"markdown_links": checked}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = {
            "ok": True,
            **validate_routes(),
            **validate_manifest(),
            **validate_portability(),
            **validate_markdown_links(),
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"SKILL_VALIDATE_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
