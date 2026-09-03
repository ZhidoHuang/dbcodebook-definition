"""Load machine-specific settings without putting them in the public skill."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ENV = "DBCODEBOOK_DEFINITION_CONFIG"


def _resolved_path(value: str | None, base: Path) -> Path | None:
    if value is None or not str(value).strip():
        return None
    expanded = os.path.expandvars(os.path.expanduser(str(value).strip()))
    path = Path(expanded)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def find_config(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    elif os.environ.get(CONFIG_ENV):
        candidates.append(Path(os.environ[CONFIG_ENV]))
    else:
        candidates.append(SKILL_ROOT / "config.local.json")

    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file():
            return resolved
    if explicit is not None:
        raise FileNotFoundError(f"configuration file does not exist: {explicit}")
    return None


def load_config(explicit: Path | None = None, *, required: bool = False) -> dict[str, Any]:
    path = find_config(explicit)
    if path is None:
        if required:
            raise FileNotFoundError(
                f"no configuration found; pass --config, set {CONFIG_ENV}, "
                "or create config.local.json"
            )
        return {"schema_version": 1, "_config_path": None}

    with path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    if config.get("schema_version") != 1:
        raise ValueError("configuration schema_version must be 1")
    config["_config_path"] = str(path)
    return config


def configured_path(config: dict[str, Any], name: str) -> Path | None:
    config_path = config.get("_config_path")
    base = Path(config_path).parent if config_path else SKILL_ROOT
    paths = config.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("configuration paths must be an object")
    return _resolved_path(paths.get(name), base)


def configured_executable(config: dict[str, Any], name: str) -> str | None:
    values = config.get("executables", {})
    if values is not None and not isinstance(values, dict):
        raise ValueError("configuration executables must be an object")
    value = (values or {}).get(name)
    if value:
        path = _resolved_path(str(value), Path(config.get("_config_path") or SKILL_ROOT).parent)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"configured executable does not exist: {value}")
        return str(path)

    if name == "python":
        return sys.executable
    return shutil.which(name)


def database_config(config: dict[str, Any], database: str) -> dict[str, Any]:
    databases = config.get("databases", {})
    if not isinstance(databases, dict):
        raise ValueError("configuration databases must be an object")
    value = databases.get(database.lower())
    if not isinstance(value, dict):
        raise ValueError(f"database is not configured: {database}")
    return value


def database_url(config: dict[str, Any], database: str) -> str:
    website = config.get("website", {})
    if not isinstance(website, dict):
        raise ValueError("configuration website must be an object")
    base = str(website.get("base_url", "")).rstrip("/")
    paths = website.get("database_paths", {})
    if not base or not isinstance(paths, dict) or database.lower() not in paths:
        raise ValueError(f"website route is not configured for {database}")
    route = "/" + str(paths[database.lower()]).strip("/") + "/"
    return base + route


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve dbcodebook-definition settings.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--database")
    args = parser.parse_args()
    try:
        config = load_config(args.config, required=True)
        result: dict[str, Any] = {
            "config": config.get("_config_path"),
            "formal_root": str(configured_path(config, "formal_root")),
            "process_root": str(configured_path(config, "process_root")),
            "python": configured_executable(config, "python"),
            "rscript": configured_executable(config, "rscript"),
        }
        if args.database:
            result["database"] = database_config(config, args.database)
            result["website_url"] = database_url(config, args.database)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"CONFIG_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
