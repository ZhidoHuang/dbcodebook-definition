"""Resolve writable R runtime paths without changing the user's global environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from skill_config import configured_path, load_config


def runtime_plan(config, environ=None):
    env = dict(os.environ if environ is None else environ)
    root = configured_path(config, "r_temp_root")
    if root is None:
        root = Path(env.get("TEMP") or env.get("TMP") or tempfile.gettempdir())
        if os.name == "nt" and not str(root).isascii():
            # Do not touch HOME/R_USER or migrate an existing library.
            public = env.get("PUBLIC")
            if not public or not public.isascii():
                raise ValueError("Set paths.r_temp_root to a writable ASCII directory in config.local.json")
            identity = env.get("USERPROFILE", str(root))
            key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            root = Path(public) / "dbcodebook-r-runtime" / key
    if os.name == "nt" and not str(root).isascii():
        raise ValueError("paths.r_temp_root must be an ASCII path for the Windows R launcher")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=root):
        pass
    changes = {"TEMP": str(root), "TMP": str(root), "TMPDIR": str(root)}
    if os.name == "nt":
        for key in ("LC_ALL", "LANG", "LC_CTYPE"):
            changes[key] = None
    library = configured_path(config, "r_library")
    if library is not None:
        if os.name == "nt" and not str(library).isascii():
            raise ValueError("paths.r_library must be an ASCII path for the Windows R launcher")
        library.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=library):
            pass
        changes["R_LIBS_USER"] = str(library)
    return {"temp_root": str(root), "environment": changes,
            "library_policy": "configured" if library else "preserve_existing"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    print(json.dumps(runtime_plan(load_config(args.config)), ensure_ascii=False))


if __name__ == "__main__":
    main()
