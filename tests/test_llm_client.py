import httpx
import openai
import pytest

from smart_ticket_router.llm import client as client_module
from smart_ticket_router.llm.client import call_llm
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code, headers=headers or {}, request=_REQUEST
    )


class _FakeCompletions:
    """Replays a scripted sequence of results: exceptions are raised, anything
    else is returned as the "model output" wrapped in the SDK's response shape.
    """

    def __init__(self, script):
        self._script = iter(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = next(self._script)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, script):
        self.chat = _FakeChat(_FakeCompletions(script))


def _fake_success(content: str):
    message = type("Msg", (), {"content": content})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # Retry backoff should not actually slow down the test suite.
    monkeypatch.setattr(client_module.time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def has_api_key(monkeypatch):
    monkeypatch.setattr(client_module, "OPENAI_API_KEY", "test-key")


def _install_fake_client(monkeypatch, script):
    fake = _FakeClient(script)
    monkeypatch.setattr(client_module, "_client", lambda: fake)
    return fake


def test_call_llm_raises_auth_error_and_never_retries(monkeypatch):
    fake = _install_fake_client(
        monkeypatch,
        [openai.AuthenticationError("bad key", response=_response(401), body=None)],
    )

    with pytest.raises(LLMAuthError):
        call_llm([{"role": "user", "content": "hi"}])

    assert fake.chat.completions.calls == 1


def test_call_llm_retries_rate_limit_then_succeeds(monkeypatch):
    fake = _install_fake_client(
        monkeypatch,
        [
            openai.RateLimitError("slow down", response=_response(429), body=None),
            _fake_success('{"issues":[]}'),
        ],
    )

    result = call_llm([{"role": "user", "content": "hi"}])

    assert result == '{"issues":[]}'
    assert fake.chat.completions.calls == 2


def test_call_llm_honors_retry_after_header(monkeypatch):
    sleeps = []
    monkeypatch.setattr(
        client_module.time, "sleep", lambda seconds: sleeps.append(seconds)
    )
    _install_fake_client(
        monkeypatch,
        [
            openai.RateLimitError(
                "slow down", response=_response(429, {"retry-after": "3"}), body=None
            ),
            _fake_success('{"issues":[]}'),
        ],
    )

    call_llm([{"role": "user", "content": "hi"}])

    assert sleeps == [3.0]


def test_call_llm_raises_rate_limit_error_after_exhausting_retries(monkeypatch):
    fake = _install_fake_client(
        monkeypatch,
        [openai.RateLimitError("slow down", response=_response(429), body=None)] * 10,
    )

    with pytest.raises(LLMRateLimitError):
        call_llm([{"role": "user", "content": "hi"}], max_retries=2)

    assert fake.chat.completions.calls == 3  # 1 try + 2 retries


def test_call_llm_retries_connection_error_then_succeeds(monkeypatch):
    fake = _install_fake_client(
        monkeypatch,
        [
            openai.APIConnectionError(message="network blip", request=_REQUEST),
            _fake_success('{"issues":[]}'),
        ],
    )

    result = call_llm([{"role": "user", "content": "hi"}])

    assert result == '{"issues":[]}'
    assert fake.chat.completions.calls == 2


def test_call_llm_raises_connection_error_after_exhausting_retries(monkeypatch):
    _install_fake_client(
        monkeypatch,
        [openai.APITimeoutError(request=_REQUEST)] * 10,
    )

    with pytest.raises(LLMConnectionError):
        call_llm([{"role": "user", "content": "hi"}], max_retries=1)


def test_call_llm_without_api_key_raises_auth_error(monkeypatch):
    monkeypatch.setattr(client_module, "OPENAI_API_KEY", None)

    with pytest.raises(LLMAuthError):
        call_llm([{"role": "user", "content": "hi"}])


def test_call_llm_falls_back_to_backoff_on_non_numeric_retry_after_header(monkeypatch):
    sleeps = []
    monkeypatch.setattr(
        client_module.time, "sleep", lambda seconds: sleeps.append(seconds)
    )
    _install_fake_client(
        monkeypatch,
        [
            openai.RateLimitError(
                "slow down",
                response=_response(429, {"retry-after": "not-a-number"}),
                body=None,
            ),
            _fake_success('{"issues":[]}'),
        ],
    )

    call_llm([{"role": "user", "content": "hi"}])

    assert sleeps == [0.5]  # exponential backoff for attempt 0, not the bad header


def test_call_llm_returns_empty_string_when_content_is_none(monkeypatch):
    _install_fake_client(monkeypatch, [_fake_success(None)])

    result = call_llm([{"role": "user", "content": "hi"}])

    assert result == ""


def test_call_llm_sends_expected_request_kwargs(monkeypatch):
    captured = {}

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _fake_success('{"issues":[]}')

    fake = _FakeClient([])
    fake.chat = _FakeChat(_CapturingCompletions())
    monkeypatch.setattr(client_module, "_client", lambda: fake)

    call_llm([{"role": "user", "content": "hi"}])

    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {
        "role": "system",
        "content": client_module.SYSTEM_PROMPT,
    }
    assert captured["messages"][1] == {"role": "user", "content": "hi"}
