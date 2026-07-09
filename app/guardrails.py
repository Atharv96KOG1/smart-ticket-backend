"""Defense-in-depth for oversized/blank input. Never blind-truncate — the customer's
actual ask can be anywhere in a long paste, so we strip quoted threads first and, if
still over budget, keep head+tail rather than the middle.
"""

import os
import re

MAX_TICKET_CHARS = int(os.environ.get("MAX_TICKET_CHARS", "2000"))

_QUOTE_LINE = re.compile(r"^\s*>.*$", re.MULTILINE)
_REPLY_HEADER = re.compile(
    r"^\s*On .{0,80} wrote:\s*$", re.MULTILINE | re.IGNORECASE
)
_ELISION = "\n\n[... middle of message elided — routed on head + tail ...]\n\n"


class BlankTicketError(ValueError):
    pass


def strip_quoted_thread(text: str) -> str:
    """Remove quoted reply chains and '>' quoted lines. Routing only needs the newest message."""
    text = _REPLY_HEADER.sub("", text)
    text = _QUOTE_LINE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def head_tail_trim(text: str, budget: int) -> tuple[str, bool]:
    """Keep the first ~70% and last ~30% of the budget. Returns (text, was_truncated)."""
    if len(text) <= budget:
        return text, False
    head_len = int(budget * 0.7)
    tail_len = budget - head_len - len(_ELISION)
    tail_len = max(tail_len, 0)
    return text[:head_len] + _ELISION + text[-tail_len:], True


def prepare_ticket_text(raw: str, max_chars: int = MAX_TICKET_CHARS) -> tuple[str, bool]:
    """Server-side guardrail pipeline. Raises BlankTicketError on empty/whitespace input.
    Returns (cleaned_text, was_truncated) so callers can log truncation events.
    """
    if raw is None or not raw.strip():
        raise BlankTicketError("Ticket message is blank.")

    cleaned = strip_quoted_thread(raw)
    if not cleaned.strip():
        raise BlankTicketError("Ticket message is blank after stripping quoted content.")

    cleaned, truncated = head_tail_trim(cleaned, max_chars)
    return cleaned, truncated


# Deterministic escalation-only rule (§8.3): can only RAISE priority, never lower it,
# and only on hard signals — never on tone alone.
_ESCALATION_SIGNALS = (
    "charged twice",
    "double charged",
    "double-charged",
    "can't log in",
    "cannot log in",
    "can't access my account",
    "data loss",
    "data is missing",
    "breach",
    "security breach",
    "suspicious login",
    "money left my account",
    "unauthorized",
)


def escalation_override(ticket_text: str, priority: str) -> str:
    """If the raw text contains a hard-impact signal, force priority to High."""
    lowered = ticket_text.lower()
    if priority != "High" and any(sig in lowered for sig in _ESCALATION_SIGNALS):
        return "High"
    return priority
