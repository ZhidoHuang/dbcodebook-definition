"""Bind the output check to Python logic reachable from its entry point.

Comments, whitespace and uncalled helper bodies are not execution changes.
Module initialization, referenced constants and transitive local imports remain
bound. This records dependencies; it does not cache checks or run topic code.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

VERSION = 1
ENTRY = "check_definition_output.py"
# This table is loaded during source-contract module initialization.
RESOURCES = {"check_definition_source_record.py:@module": "references/database-routing.json"}


def digest(nodes):
    text = ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def make_binding(scripts=None):
    scripts = Path(scripts or Path(__file__).parent).resolve()
    modules, hashes, pending = {}, {}, [(ENTRY, "main")]

    def local(module):
        path = scripts / ((module or "").replace(".", "/") + ".py")
        return path.name if path.parent == scripts and path.is_file() else None

    def load(filename):
        if filename in modules:
            return modules[filename]
        body = ast.parse((scripts / filename).read_text(encoding="utf-8-sig")).body
        names, aliases, shell = {}, {}, []
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.setdefault(node.name, []).append(node)
                header = deepcopy(node)
                header.body = [ast.Pass()]
                shell.append(header)
            elif (isinstance(node, ast.If)
                  and ast.dump(node.test) == ast.dump(ast.parse("__name__ == '__main__'", mode="eval").body)):
                continue  # Imported modules do not execute their CLI.
            else:
                shell.append(node)
                for item in ast.walk(node):
                    if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
                        names.setdefault(item.id, []).append(node)
        for node in shell:
            for item in ast.walk(node):
                aliases.update(imports(item))
        modules[filename] = body, names, aliases, shell
        return modules[filename]

    def imports(node):
        if isinstance(node, ast.ImportFrom):
            filename = local(node.module)
            return {x.asname or x.name: (filename, x.name) for x in node.names} if filename else {}
        if isinstance(node, ast.Import):
            return {x.asname or x.name: (local(x.name), "*") for x in node.names if local(x.name)}
        return {}

    # The binding algorithm is itself part of the check, as a complete module.
    own = Path(__file__).name
    pending.append((own, "*"))
    while pending:
        filename, symbol = pending.pop()
        key = filename + ":" + symbol
        if key in hashes:
            continue
        body, names, aliases, shell = load(filename)
        if filename == own:
            hashes[filename + ":*"] = digest(body)
            continue
        if symbol == "*":
            nodes = body
        elif symbol == "@module":
            nodes = shell
        elif symbol in names:
            nodes = names[symbol]
        elif symbol in aliases:
            hashes[key] = digest([])
            pending.extend([(filename, "@module"), aliases[symbol]])
            continue
        else:
            raise ValueError("结果检查依赖无法定位：" + key)
        hashes[key] = digest(nodes)
        if symbol != "@module":
            pending.append((filename, "@module"))
        walked = [item for node in nodes for item in ast.walk(node)]
        scope_aliases = dict(aliases)
        for item in walked:
            for alias, target in imports(item).items():
                scope_aliases[alias] = target
                pending.append((target[0], "@module"))
                if symbol != "@module" or target[1] == "*":
                    pending.append(target)
        module_attributes = set()
        for item in walked:
            if isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name):
                target = scope_aliases.get(item.value.id)
                if target and target[1] == "*":
                    pending.append((target[0], item.attr))
                    module_attributes.add(id(item.value))
        for item in walked:
            if not isinstance(item, ast.Name) or not isinstance(item.ctx, ast.Load):
                continue
            if item.id in scope_aliases and id(item) not in module_attributes:
                pending.append(scope_aliases[item.id])
            elif item.id in names:
                pending.append((filename, item.id))
    for trigger, name in RESOURCES.items():
        if trigger in hashes:
            data = json.loads((scripts.parent / name).read_text(encoding="utf-8-sig"))
            normalized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            hashes[name] = hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()
    return {"version": VERSION, "entry": ENTRY + ":main", "logic": dict(sorted(hashes.items()))}


def validate_binding(record, scripts=None):
    saved = record.get("checker_binding")
    if not isinstance(saved, dict) or saved.get("version") != VERSION:
        raise ValueError("结果检查缺少程序依赖记录；运行一次现有输出检查 --complete，无需重跑 R 或下载")
    current = make_binding(scripts)
    if saved == current:
        return
    before = saved.get("logic", {})
    if not isinstance(before, dict):
        before = {}
    changed = sorted(key for key in set(before) | set(current["logic"])
                     if before.get(key) != current["logic"].get(key))
    detail = ", ".join(changed[:8]) or "依赖记录结构"
    if len(changed) > 8:
        detail += f"（另 {len(changed) - 8} 项）"
    raise ValueError("结果检查逻辑已变化：" + detail + "；重新运行输出检查 --complete，无需重跑 R 或下载")
