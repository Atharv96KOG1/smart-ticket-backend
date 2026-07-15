import pytest
from pydantic import ValidationError

from smart_ticket_router.schemas.ticket import (
    SAFE_FALLBACK,
    Category,
    Issue,
    Priority,
    TicketRoute,
)

VALID_ISSUE = {
    "id": 1,
    "category": "Billing",
    "priority": "High",
    "assigned_team": "Billing Team",
    "reasoning": "Duplicate charge with urgency.",
    "confidence": "High",
}


def test_issue_accepts_a_valid_payload():
    issue = Issue.model_validate(VALID_ISSUE)
    assert issue.category is Category.BILLING
    assert issue.priority is Priority.HIGH


def test_issue_confidence_is_optional():
    payload = {k: v for k, v in VALID_ISSUE.items() if k != "confidence"}
    issue = Issue.model_validate(payload)
    assert issue.confidence is None


@pytest.mark.parametrize(
    "missing_field", ["category", "priority", "assigned_team", "reasoning"]
)
def test_issue_requires_core_fields(missing_field):
    payload = {k: v for k, v in VALID_ISSUE.items() if k != missing_field}
    with pytest.raises(ValidationError):
        Issue.model_validate(payload)


def test_issue_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Issue.model_validate({**VALID_ISSUE, "extra_field": "not allowed"})


def test_issue_rejects_invalid_category():
    with pytest.raises(ValidationError):
        Issue.model_validate({**VALID_ISSUE, "category": "Not A Real Category"})


def test_issue_reasoning_rejects_over_200_chars():
    with pytest.raises(ValidationError):
        Issue.model_validate({**VALID_ISSUE, "reasoning": "x" * 201})


def test_issue_reasoning_accepts_exactly_200_chars():
    issue = Issue.model_validate({**VALID_ISSUE, "reasoning": "x" * 200})
    assert len(issue.reasoning) == 200


def test_ticket_route_requires_at_least_one_issue():
    with pytest.raises(ValidationError):
        TicketRoute.model_validate({"issues": []})


def test_ticket_route_accepts_multiple_issues():
    route = TicketRoute.model_validate(
        {
            "issues": [
                VALID_ISSUE,
                {
                    **VALID_ISSUE,
                    "id": 2,
                    "category": "Technical Issue",
                    "assigned_team": "Technical Support",
                },
            ]
        }
    )
    assert len(route.issues) == 2
    assert route.processing_time_ms == 0


def test_safe_fallback_is_a_valid_low_confidence_general_inquiry():
    assert len(SAFE_FALLBACK.issues) == 1
    issue = SAFE_FALLBACK.issues[0]
    assert issue.category is Category.GENERAL_INQUIRY
    assert issue.assigned_team.value == "Tier-1 Support"
    assert issue.confidence is not None and issue.confidence.value == "Low"


def test_safe_fallback_copy_does_not_mutate_the_original():
    copy = SAFE_FALLBACK.model_copy(update={"processing_time_ms": 42})
    assert copy.processing_time_ms == 42
    assert SAFE_FALLBACK.processing_time_ms == 0
