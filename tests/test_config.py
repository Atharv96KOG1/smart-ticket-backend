import importlib
import os

import pytest

from smart_ticket_router import config as config_module

_ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_MODEL", "MAX_TICKET_CHARS", "ALLOWED_ORIGINS")


@pytest.fixture
def reload_config():
    """Reloads config.py under a scratch env, then restores the original env
    and module state afterwards so other test files never see stale values.
    """
    original = {key: os.environ.get(key) for key in _ENV_KEYS}

    def _reload(**env):
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(env)
        return importlib.reload(config_module)

    yield _reload

    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(config_module)


def test_allowed_origins_defaults_when_env_var_unset(reload_config):
    reloaded = reload_config()
    assert reloaded.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_allowed_origins_splits_and_strips_whitespace(reload_config):
    reloaded = reload_config(
        ALLOWED_ORIGINS=" https://a.example.com , https://b.example.com "
    )
    assert reloaded.ALLOWED_ORIGINS == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_allowed_origins_filters_out_empty_entries(reload_config):
    reloaded = reload_config(ALLOWED_ORIGINS="https://a.example.com,,  ,")
    assert reloaded.ALLOWED_ORIGINS == ["https://a.example.com"]


def test_max_ticket_chars_parses_int_from_env(reload_config):
    reloaded = reload_config(MAX_TICKET_CHARS="500")
    assert reloaded.MAX_TICKET_CHARS == 500


def test_max_ticket_chars_defaults_to_2000(reload_config):
    reloaded = reload_config()
    assert reloaded.MAX_TICKET_CHARS == 2000
