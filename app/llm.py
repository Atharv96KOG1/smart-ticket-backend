import os
import time

import openai

from app.prompt import SYSTEM_PROMPT

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class LLMAuthError(RuntimeError):
    pass


class LLMRateLimitError(RuntimeError):
    pass


class LLMConnectionError(RuntimeError):
    pass


def _client() -> openai.OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMAuthError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return openai.OpenAI(api_key=api_key)


def call_llm(messages: list[dict], max_retries: int = 2) -> str:
    """Call the model once. Retries transient network errors with backoff;
    surfaces auth/rate-limit errors distinctly so the caller can show a clean message.
    """
    client = _client()
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=300,
                temperature=0,
                response_format={"type": "json_object"},
                messages=full_messages,
            )
            return (response.choices[0].message.content or "").strip()

        except openai.AuthenticationError as e:
            raise LLMAuthError("API authentication failed — check your key.") from e

        except openai.RateLimitError as e:
            raise LLMRateLimitError("Rate limited by the provider — please wait and retry.") from e

        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            last_error = e
            if attempt == max_retries:
                raise LLMConnectionError(
                    f"Network/timeout error after {max_retries + 1} attempts."
                ) from e
            time.sleep(0.5 * (2 ** attempt))
            continue

    raise LLMConnectionError("Unreachable retry state.") from last_error
