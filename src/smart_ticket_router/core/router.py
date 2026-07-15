import json
import logging
import time

from pydantic import ValidationError

from smart_ticket_router.core.guardrails import (
    BlankTicketError,
    billing_priority_floor,
    escalation_override,
    prepare_ticket_text,
)
from smart_ticket_router.core.prompt import build_messages
from smart_ticket_router.llm.client import call_llm
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)
from smart_ticket_router.schemas.ticket import SAFE_FALLBACK, Priority, TicketRoute

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
    start = time.perf_counter()
    cleaned_text, was_truncated = prepare_ticket_text(raw_text)
    if was_truncated:
        logger.info(
            "Ticket truncated by head/tail guardrail (over %d chars).", len(raw_text)
        )

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

        updated_issues = []
        for i, issue in enumerate(route.issues):
            final_priority = billing_priority_floor(
                issue.category.value, issue.priority.value
            )
            if i == 0:  # raw-text hard signals describe the ticket overall, so only the
                final_priority = escalation_override(
                    raw_text, final_priority
                )  # primary issue is escalated by them
            if final_priority != issue.priority.value:
                issue = issue.model_copy(update={"priority": Priority(final_priority)})
            updated_issues.append(issue)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return route.model_copy(
            update={"issues": updated_issues, "processing_time_ms": elapsed_ms}
        )

    logger.error("Both attempts failed validation; returning safe fallback.")
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return SAFE_FALLBACK.model_copy(update={"processing_time_ms": elapsed_ms})


__all__ = [
    "route_ticket",
    "BlankTicketError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMConnectionError",
]
