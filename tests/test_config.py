from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_config import configured_path, database_config, database_url, load_config


def main() -> int:
    example = load_config(REPO_ROOT / "config.example.json", required=True)
    assert configured_path(example, "formal_root") == (REPO_ROOT.parent / "definition-results").resolve()
    assert database_config(example, "charls")["formal_subdir"] == "CHARLS"
    assert database_url(example, "elsa") == "https://dbcodebook.example/home/elsa/"

    with tempfile.TemporaryDirectory(prefix="dbcodebook_config_") as tmp:
        invalid = Path(tmp) / "invalid.json"
        invalid.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
        try:
            load_config(invalid, required=True)
        except ValueError as error:
            assert "schema_version" in str(error)
        else:
            raise AssertionError("invalid configuration schema was accepted")

    print("skill configuration fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
