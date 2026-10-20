from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_routing.py"


def main(*, routes_only: bool = False) -> int:
    spec = importlib.util.spec_from_file_location("skill_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load validate_routing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes = module.validate_routes()
    assert routes["databases"] == ["charls", "chns", "elsa", "hrs", "klosa", "knhanes", "mhas", "nhanes", "share"]
    assert routes["database_themes"] == ["CHARLS", "CHNS", "ELSA", "HRS", "KLOSA", "KNHANES", "MHAS", "NHANES", "SHARE"]
    for invalid_path in (
        "references/databases/__missing_route__/profile.md",
        "../SKILL.md",
        str(REPO_ROOT / "SKILL.md"),
    ):
        try:
            module.relative_target(invalid_path, "route fixture")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid route was accepted: {invalid_path}")
    source_spec = importlib.util.spec_from_file_location(
        "source_checker", REPO_ROOT / "scripts" / "check_definition_source_record.py")
    source_module = importlib.util.module_from_spec(source_spec)
    source_spec.loader.exec_module(source_module)
    config = json.loads((REPO_ROOT / "references/database-routing.json").read_text(encoding="utf-8-sig"))
    for group in ("databases", "reference_materials"):
        for database, route in config[group].items():
            assert "status" not in route and "scope" not in route
            root = source_module.LOCAL_EVIDENCE_ROOTS[database.upper()]
            assert root == REPO_ROOT / route["source_materials"]
            if group == "reference_materials":
                assert (REPO_ROOT / route["index"]).is_file()
    # Routes locate rules and evidence; production capability is checked by its entrypoint.
    chns = config["databases"]["chns"]
    assert chns["workflow"] == chns["profile"] == "references/databases/chns/profile.md"
    assert chns["profile"] == config["reference_materials"]["chns"]["profile"]
    assert chns["source_materials"] == config["reference_materials"]["chns"]["source_materials"]
    assert source_module.resolve_material_path(
        "材料索引.md", "CHNS", source_module.LOCAL_EVIDENCE_ROOTS["CHNS"]
    ).is_file()
    elsa = source_module.LOCAL_EVIDENCE_ROOTS["ELSA"]
    assert elsa == REPO_ROOT / "references/source-materials/elsa"
    assert (elsa / "材料索引.md").is_file()
    assert not (REPO_ROOT / "references/databases/elsa/official-materials").exists()
    assert not (REPO_ROOT / "references/rules/copy-examples.md").exists()
    if not routes_only:
        assert module.validate_manifest()["source_materials"] >= 22
        assert module.validate_portability()["text_files"] > 20
        assert module.validate_markdown_links()["markdown_links"] >= 20
    print("skill route fixtures PASS" if routes_only else "skill portability fixtures PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
