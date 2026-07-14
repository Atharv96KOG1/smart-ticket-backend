import pytest
from fastapi.testclient import TestClient

from smart_ticket_router.api import routes as routes_module
from smart_ticket_router.core.guardrails import BlankTicketError
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)
from smart_ticket_router.main import app
from smart_ticket_router.schemas.ticket import TicketRoute

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_route_returns_classification_on_success(monkeypatch):
    fake_route = TicketRoute.model_validate(
        {
            "issues": [
                {
                    "id": 1,
                    "category": "Billing",
                    "priority": "High",
                    "assigned_team": "Billing Team",
                    "reasoning": "Duplicate charge.",
                    "confidence": "High",
                }
            ],
            "processing_time_ms": 12,
        }
    )
    monkeypatch.setattr(routes_module, "route_ticket", lambda message: fake_route)

    res = client.post("/route", json={"message": "I was charged twice"})

    assert res.status_code == 200
    body = res.json()
    assert body["issues"][0]["category"] == "Billing"
    assert body["processing_time_ms"] == 12


@pytest.mark.parametrize(
    "exc, expected_status",
    [
        (BlankTicketError("blank"), 400),
        (LLMAuthError("bad key"), 502),
        (LLMRateLimitError("slow down"), 429),
        (LLMConnectionError("network blip"), 503),
    ],
)
def test_route_maps_each_error_to_its_http_status(monkeypatch, exc, expected_status):
    def raise_it(message):
        raise exc

    monkeypatch.setattr(routes_module, "route_ticket", raise_it)

    res = client.post("/route", json={"message": "anything"})

    assert res.status_code == expected_status
    assert "detail" in res.json()


def test_route_rejects_message_over_max_length():
    res = client.post("/route", json={"message": "x" * 8001})
    assert res.status_code == 422  # request-validation failure, before route_ticket runs


def test_data_mount_serves_sample_tickets():
    res = client.get("/data/sample_tickets.json")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
