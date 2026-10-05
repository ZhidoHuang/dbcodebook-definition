"""Compare research inputs without treating questionnaire presentation as research."""
from copy import deepcopy

SOURCE_SCOPE = "research_v1"
DISPLAY_FIELDS = ("rendered_in_copy", "copy_locator", "display",
                  "display_required", "display_omission_reason")


def research_record(record):
    data = deepcopy(record)
    data.pop("logic_review", None)
    data.pop("questionnaire_display_policy", None)
    for item in data.get("questionnaire_evidence", []):
        for key in DISPLAY_FIELDS:
            item.pop(key, None)
    # Question wording, source locators, variable correspondence, routing,
    # definitions and observed data remain bound to the implementation review.
    return data
