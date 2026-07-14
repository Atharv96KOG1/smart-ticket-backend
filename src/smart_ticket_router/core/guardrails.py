import re

from smart_ticket_router.config import MAX_TICKET_CHARS

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


# Deterministic escalation-only rule: can only RAISE priority, never lower it,
# and only on hard signals — never on tone alone. Payment/billing signals are
# listed first since any money-at-risk issue is always High.
# NOTE: plain "can't log in" is deliberately excluded — a single user's login
# lockout defaults to Medium (blocked work for one person, not widespread). It
# only escalates via the security signals below (suspicious login, breach,
# data loss), i.e. the edge case, not the common case.
# NOTE: bare, ambiguous single words are deliberately excluded even though they
# sound like hard signals — "refund" (matches refund-policy questions), "breach"
# (matches "breach of contract"), "unauthorized" (matches unrelated permission
# bugs) all substring-matched into unrelated tickets and forced them to High
# regardless of actual severity, overriding the model's own correct judgment.
# Only multi-word phrases specific enough to not misfire are listed.
_ESCALATION_SIGNALS = (
    "charged twice",
    "double charged",
    "double-charged",
    "overcharged",
    "unauthorized charge",
    "unauthorized transaction",
    "payment failed",
    "money left my account",
    "data loss",
    "data is missing",
    "data corrupted",
    "corrupted data",
    "data got corrupted",
    "lost all my data",
    "data breach",
    "security breach",
    "suspicious login",
)


def escalation_override(ticket_text: str, priority: str) -> str:
    """If the raw text contains a hard-impact signal, force priority to High."""
    lowered = ticket_text.lower()
    if priority != "High" and any(sig in lowered for sig in _ESCALATION_SIGNALS):
        return "High"
    return priority


def billing_priority_floor(category: str, priority: str) -> str:
    """Any Billing-categorized ticket is always High — a deterministic guarantee,
    not just a prompt instruction the model might not follow every time.
    """
    if category == "Billing":
        return "High"
    return priority
