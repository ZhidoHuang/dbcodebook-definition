"""Return stable, isolated CLI browser paths for one topic; never open a browser."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def browser_paths(process_dir):
    process = Path(process_dir).resolve()
    identity = os.path.normcase(str(process))
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    root = process / "browser"
    return {
        "session": "dbcb-" + key,
        "session_workdir": str(root / "cli"),
        "profile": str(root / "profile"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = browser_paths(args.process_dir)
    for field in ("session_workdir", "profile"):
        Path(paths[field]).mkdir(parents=True, exist_ok=True)
    print(json.dumps(paths, ensure_ascii=False))


if __name__ == "__main__":
    main()
