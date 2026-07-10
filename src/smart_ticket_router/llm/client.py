import time

import openai

from smart_ticket_router.config import OPENAI_API_KEY, OPENAI_MODEL
from smart_ticket_router.core.prompt import SYSTEM_PROMPT
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)


def _client() -> openai.OpenAI:
    if not OPENAI_API_KEY:
        raise LLMAuthError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return openai.OpenAI(api_key=OPENAI_API_KEY)


def _retry_after_seconds(error: openai.RateLimitError, attempt: int) -> float:
    """Prefer the provider's Retry-After header; fall back to exponential backoff."""
    headers = getattr(getattr(error, "response", None), "headers", None) or {}
    header = headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return 0.5 * (2**attempt)


def call_llm(messages: list[dict], max_retries: int = 2) -> str:
    """Call the model once. Retries transient network errors and rate limits with
    backoff; surfaces auth errors immediately (never worth retrying). Raises the
    typed error only after every retry is exhausted, so a single rate-limit hit
    doesn't immediately fail the whole request.
    """
    client = _client()
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                max_tokens=300,
                temperature=0,
                response_format={"type": "json_object"},
                messages=full_messages,
            )
            return (response.choices[0].message.content or "").strip()

        except openai.AuthenticationError as e:
            raise LLMAuthError("API authentication failed — check your key.") from e

        except openai.RateLimitError as e:
            last_error = e
            if attempt == max_retries:
                raise LLMRateLimitError(
                    f"Rate limited by the provider after {max_retries + 1} attempts — please wait and retry."
                ) from e
            time.sleep(_retry_after_seconds(e, attempt))
            continue

        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            last_error = e
            if attempt == max_retries:
                raise LLMConnectionError(
                    f"Network/timeout error after {max_retries + 1} attempts."
                ) from e
            time.sleep(0.5 * (2**attempt))
            continue

    raise LLMConnectionError("Unreachable retry state.") from last_error
