from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_routing.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("skill_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load validate_routing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.validate_routes()["databases"] == ["charls", "elsa"]
    assert module.validate_manifest()["source_materials"] == 23
    assert module.validate_portability()["text_files"] > 20
    assert module.validate_markdown_links()["markdown_links"] >= 20
    print("skill portability fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
