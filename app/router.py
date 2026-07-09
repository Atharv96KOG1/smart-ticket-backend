"""Core reliability pipeline: guardrails -> prompt -> LLM -> parse -> validate ->
retry -> fallback. The LLM call is the only unreliable step; everything else here is
ordinary deterministic code wrapping it.
"""

import json
import logging

from pydantic import ValidationError

from app.guardrails import (
    BlankTicketError,
    billing_priority_floor,
    escalation_override,
    prepare_ticket_text,
)
from app.llm import LLMAuthError, LLMConnectionError, LLMRateLimitError, call_llm
from app.prompt import build_messages
from app.schema import SAFE_FALLBACK, TicketRoute

logger = logging.getLogger("smart_ticket_router")


def _extract_json(raw: str) -> dict:
    """Parse defensively: strip code fences / stray prose, then re-parse."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(raw[start : end + 1])


def route_ticket(raw_text: str) -> TicketRoute:
    """Classify one support message. Always returns a schema-valid TicketRoute —
    either a real classification or the documented safe fallback. Never raises for
    a malformed/unreliable model response; only raises for blank input or a hard
    provider failure (auth/rate-limit/connection), which callers surface as clean errors.
    """
    cleaned_text, was_truncated = prepare_ticket_text(raw_text)
    if was_truncated:
        logger.info("Ticket truncated by head/tail guardrail (over %d chars).", len(raw_text))

    retry_error: str | None = None
    for attempt in range(2):  # one shot + one repair retry
        messages = build_messages(cleaned_text, retry_error=retry_error)
        raw_response = call_llm(messages)

        try:
            data = _extract_json(raw_response)
            route = TicketRoute.model_validate(data)
        except (ValueError, ValidationError) as e:
            retry_error = str(e)
            logger.warning("Attempt %d failed validation: %s", attempt + 1, retry_error)
            continue

        final_priority = billing_priority_floor(route.category.value, route.priority.value)
        final_priority = escalation_override(raw_text, final_priority)
        if final_priority != route.priority.value:
            route = route.model_copy(update={"priority": final_priority})
        return route

    logger.error("Both attempts failed validation; returning safe fallback.")
    return SAFE_FALLBACK.model_copy()


__all__ = [
    "route_ticket",
    "BlankTicketError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMConnectionError",
]
