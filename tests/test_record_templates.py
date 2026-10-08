"""Generated record structures stay incomplete until actual evidence is supplied."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_definition_readability as c
import execution_report as e


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        c.initialize_impact(root, "004", question_group_names=["实际题组"])
        impact = json.loads((root / c.IMPACT_NAME).read_text(encoding="utf-8"))
        group = impact["question_groups"][0]
        assert group["name"] == "实际题组"
        assert {"periods", "respondent", "official_source", "definition_use",
                "draft_location", "question_mode", "question_text"} <= group.keys()
        assert group["periods"] == [] and group["question_mode"] == ""
        assert impact["status"] == c.IMPACT_SCOPE_STATUS
        path = root / "findings.json"
        e.command_review_template(argparse.Namespace(out=path))
        findings = json.loads(path.read_text(encoding="utf-8"))
        assert findings[0]["changed_artifact"] is False and findings[0]["resolved"] is False
        assert findings[0]["evidence"] == ""
        path.write_text("[]")
        try:
            e.command_review_template(argparse.Namespace(out=path))
        except FileExistsError:
            pass
        else:
            raise AssertionError("Actual findings overwritten")
        assert path.read_text() == "[]"
    print("RECORD_TEMPLATES_PASS")


if __name__ == "__main__":
    main()
