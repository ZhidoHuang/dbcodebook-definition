"""Rebind explicitly selected historical file bindings without changing verdicts.

This module does no business validation. Callers must run the original validators
on the returned projection before recording or using it.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath


def _absolute(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Relocation paths must be nonempty absolute strings")
    path = PureWindowsPath(value) if PureWindowsPath(value).is_absolute() else PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Relocation paths must be absolute and cannot contain '..': " + value)
    return path


def _inside(path, root):
    return type(path) is type(root) and path.is_relative_to(root)


def _overlap(left, right):
    return _inside(left, right) or _inside(right, left)


class ReportRelocation:
    """Apply a strict root map and retain immutable source-report evidence."""

    def __init__(self, map_path, formal_dir, process_dir):
        self.map_path = Path(map_path).resolve(strict=True)
        self.map_bytes = self.map_path.read_bytes()
        config = json.loads(self.map_bytes.decode("utf-8-sig"))
        if config.get("schema_version") != 1 or not isinstance(config.get("roots"), list) or not config["roots"]:
            raise ValueError("Expected schema_version 1 and a nonempty roots list")
        allowed = [Path(value).resolve(strict=True) for value in (formal_dir, process_dir)]
        self.roots = []
        for item in config["roots"]:
            if not isinstance(item, dict) or set(item) != {"old", "new"}:
                raise ValueError("Each relocation root must contain only old and new")
            old = _absolute(item["old"])
            new_lexical = _absolute(item["new"])
            new = Path(item["new"]).resolve(strict=True)
            if not new.is_dir() or not any(new.is_relative_to(root) for root in allowed):
                raise ValueError("New roots must be directories within this formal/process directory")
            # A foreign-platform target is never silently interpreted as relative.
            if not Path(item["new"]).is_absolute():
                raise ValueError("New roots must be native absolute paths")
            self.roots.append((old, new, new_lexical))
        for index, (old, new, lexical) in enumerate(self.roots):
            for other_old, other_new, other_lexical in self.roots[index + 1:]:
                if _overlap(old, other_old):
                    raise ValueError("Old relocation roots cannot overlap")
                if new.is_relative_to(other_new) or other_new.is_relative_to(new):
                    raise ValueError("New relocation roots cannot overlap or share a target")
            for any_old, _, _ in self.roots:
                if _overlap(lexical, any_old) or _overlap(_absolute(str(new)), any_old):
                    raise ValueError("New relocation roots cannot point into old roots")
        self.originals = {}
        self.used_mappings = {}

    def _path(self, value):
        source = _absolute(value)
        matches = [(old, new) for old, new, _ in self.roots if _inside(source, old)]
        if len(matches) != 1:
            raise ValueError("No unique relocation root for bound file: " + value)
        old, new = matches[0]
        relative = source.relative_to(old)
        target_lexical = new.joinpath(*relative.parts)
        target = target_lexical.resolve(strict=True)
        if not target.is_relative_to(new) or not target.is_file():
            raise ValueError("Relocated binding escapes its root or is not a file: " + value)
        if target.name != source.name or target.relative_to(new).parts != relative.parts:
            raise ValueError("Relocated bindings must preserve names and relative structure")
        result = str(target)
        for previous, mapped in self.used_mappings.items():
            if mapped == result and _absolute(previous) != source:
                raise ValueError("Multiple old bindings cannot map to one file")
        self.used_mappings[value] = result
        return result

    def _bindings(self, bindings):
        if not isinstance(bindings, dict):
            raise ValueError("File hash bindings must be objects")
        result = {}
        for path, digest in bindings.items():
            target = self._path(path)
            if target in result:
                raise ValueError("Multiple bindings map to one file")
            result[target] = digest
        return result

    def report(self, path, roles=(), exploration=False):
        source = Path(path).resolve(strict=True)
        content = source.read_bytes()
        original = json.loads(content.decode("utf-8-sig"))
        report = deepcopy(original)
        selected = set(roles)
        if exploration:
            selected.update(("独立探索 A", "独立探索 B"))
            item = report.get("exploration", {})
            if "inputs" in item:
                item["inputs"] = self._bindings(item["inputs"])
            for branch in item.get("branches", {}).values():
                if "outputs" in branch:
                    branch["outputs"] = self._bindings(branch["outputs"])
            merge = item.get("merge", {})
            if "decision" in merge:
                merge["decision"] = self._bindings(merge["decision"])
            if merge.get("record"):
                merge["record"] = self._path(merge["record"])
            if item.get("from_report"):
                item["from_report"] = self._path(item["from_report"])
        for role in selected:
            review = report.get("stage_reviews", {}).get(role)
            if review and "inputs" in review:
                review["inputs"] = self._bindings(review["inputs"])
            # reused_from is historical attribution; validators do not read it.
        key = str(source)
        digest = hashlib.sha256(content).hexdigest()
        if key in self.originals and self.originals[key]["sha256"] != digest:
            raise ValueError("Original report changed during relocation")
        self.originals[key] = {"path": key, "sha256": digest, "bytes": content}
        return report

    def save_evidence(self, folder):
        folder = Path(folder).absolute()
        folder.mkdir(parents=True, exist_ok=False)
        reports = []
        for index, original in enumerate(self.originals.values(), 1):
            snapshot = folder / f"original_report_{index:03d}.json"
            with snapshot.open("xb") as stream:
                stream.write(original["bytes"])
            reports.append({"original_path": original["path"], "sha256": original["sha256"], "snapshot": str(snapshot)})
        map_snapshot = folder / "path_map.json"
        with map_snapshot.open("xb") as stream:
            stream.write(self.map_bytes)
        manifest = {"schema_version": 1, "purpose": "Path relocation only; original verdicts and hashes retained",
                    "map_path": str(self.map_path), "map_snapshot": str(map_snapshot),
                    "map_sha256": hashlib.sha256(self.map_bytes).hexdigest(),
                    "reports": reports, "used_mappings": dict(sorted(self.used_mappings.items()))}
        manifest_path = folder / "manifest.json"
        encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with manifest_path.open("xb") as stream:
            stream.write(encoded)
        return {"manifest": str(manifest_path), "sha256": hashlib.sha256(encoded).hexdigest(),
                "report_count": len(reports), "mapping_count": len(self.used_mappings), "reports": reports}
