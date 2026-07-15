import json

import pytest

from smart_ticket_router.core import router as router_module
from smart_ticket_router.core.guardrails import BlankTicketError
from smart_ticket_router.core.router import _extract_json, route_ticket
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)
from smart_ticket_router.schemas.ticket import Category, Confidence, Priority

VALID_RESPONSE = json.dumps(
    {
        "issues": [
            {
                "id": 1,
                "category": "Technical Issue",
                "priority": "Medium",
                "assigned_team": "Technical Support",
                "reasoning": "App is slow after the latest update.",
                "confidence": "High",
            }
        ]
    }
)


def test_extract_json_parses_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_parses_json_wrapped_in_prose_and_fences():
    raw = 'Sure, here you go:\n```json\n{"a": 1, "b": 2}\n```\nLet me know if you need anything else.'
    assert _extract_json(raw) == {"a": 1, "b": 2}


def test_extract_json_raises_without_any_json_object():
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


def test_route_ticket_raises_blank_ticket_error_without_calling_llm(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_llm should never be invoked for blank input")

    monkeypatch.setattr(router_module, "call_llm", fail_if_called)
    with pytest.raises(BlankTicketError):
        route_ticket("   ")


def test_route_ticket_happy_path(monkeypatch):
    monkeypatch.setattr(router_module, "call_llm", lambda messages: VALID_RESPONSE)

    result = route_ticket("The app is slow after the latest update.")

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.category is Category.TECHNICAL_ISSUE
    assert issue.priority is Priority.MEDIUM
    assert issue.confidence is Confidence.HIGH
    assert result.processing_time_ms >= 0


def test_route_ticket_applies_billing_priority_floor(monkeypatch):
    raw_response = json.dumps(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Billing",
                    "priority": "Low",  # model under-called it; the floor must correct this
                    "assigned_team": "Billing Team",
                    "reasoning": "Invoice question.",
                    "confidence": "Medium",
                }
            ]
        }
    )
    monkeypatch.setattr(router_module, "call_llm", lambda messages: raw_response)

    result = route_ticket("My invoice looks a little off.")

    assert result.issues[0].priority is Priority.HIGH


def test_route_ticket_escalation_only_applies_to_primary_issue(monkeypatch):
    raw_response = json.dumps(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Technical Issue",
                    "priority": "Medium",
                    "assigned_team": "Technical Support",
                    "reasoning": "Networking issue.",
                    "confidence": "Medium",
                },
                {
                    "id": 2,
                    "category": "Complaint",
                    "priority": "Low",
                    "assigned_team": "Customer Success",
                    "reasoning": "Also unhappy about wait times.",
                    "confidence": "Medium",
                },
            ]
        }
    )
    monkeypatch.setattr(router_module, "call_llm", lambda messages: raw_response)

    # "data loss" is a hard escalation signal in the raw text.
    result = route_ticket(
        "Networking issue, and by the way I've experienced data loss before too."
    )

    assert result.issues[0].priority is Priority.HIGH  # primary: escalated
    assert result.issues[1].priority is Priority.LOW  # secondary: untouched


def test_route_ticket_retries_once_on_invalid_json_then_succeeds(monkeypatch):
    responses = iter(["not valid json at all", VALID_RESPONSE])
    monkeypatch.setattr(router_module, "call_llm", lambda messages: next(responses))

    result = route_ticket("it's not working")

    assert result.issues[0].category is Category.TECHNICAL_ISSUE


def test_route_ticket_falls_back_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(
        router_module, "call_llm", lambda messages: "still not valid json"
    )

    result = route_ticket("something the model can't classify")

    assert result.issues[0].category is Category.GENERAL_INQUIRY
    assert result.issues[0].confidence is Confidence.LOW


def test_route_ticket_retries_once_on_schema_validation_error_then_succeeds(
    monkeypatch,
):
    # Valid JSON, but an enum value the model isn't allowed to invent — distinct
    # from the "not JSON at all" retry path already covered above.
    invalid_category_response = json.dumps(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Not A Real Category",
                    "priority": "Medium",
                    "assigned_team": "Technical Support",
                    "reasoning": "App is slow after the latest update.",
                    "confidence": "High",
                }
            ]
        }
    )
    responses = iter([invalid_category_response, VALID_RESPONSE])
    monkeypatch.setattr(router_module, "call_llm", lambda messages: next(responses))

    result = route_ticket("The app is slow after the latest update.")

    assert result.issues[0].category is Category.TECHNICAL_ISSUE


def test_route_ticket_applies_billing_priority_floor_to_a_secondary_issue(monkeypatch):
    raw_response = json.dumps(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Technical Issue",
                    "priority": "Medium",
                    "assigned_team": "Technical Support",
                    "reasoning": "App is slow.",
                    "confidence": "Medium",
                },
                {
                    "id": 2,
                    "category": "Billing",
                    "priority": "Low",  # model under-called it; the floor must correct it even off-primary
                    "assigned_team": "Billing Team",
                    "reasoning": "Also asked about an invoice.",
                    "confidence": "Medium",
                },
            ]
        }
    )
    monkeypatch.setattr(router_module, "call_llm", lambda messages: raw_response)

    result = route_ticket("The app is slow, and also my invoice looks off.")

    assert result.issues[1].priority is Priority.HIGH


def test_route_ticket_billing_floor_and_escalation_both_apply_to_primary(monkeypatch):
    raw_response = json.dumps(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Billing",
                    "priority": "Low",
                    "assigned_team": "Billing Team",
                    "reasoning": "Duplicate charge.",
                    "confidence": "Medium",
                }
            ]
        }
    )
    monkeypatch.setattr(router_module, "call_llm", lambda messages: raw_response)

    # "double charged" is both a billing ticket and a hard escalation signal.
    result = route_ticket("I was double charged this month, please refund me.")

    assert result.issues[0].priority is Priority.HIGH


@pytest.mark.parametrize(
    "error",
    [
        LLMAuthError("bad key"),
        LLMRateLimitError("slow down"),
        LLMConnectionError("network blip"),
    ],
)
def test_route_ticket_propagates_llm_provider_errors_unmodified(monkeypatch, error):
    def raise_it(messages):
        raise error

    monkeypatch.setattr(router_module, "call_llm", raise_it)

    with pytest.raises(type(error)):
        route_ticket("anything at all")
