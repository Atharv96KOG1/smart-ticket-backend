import pytest

from smart_ticket_router.core.guardrails import (
    BlankTicketError,
    billing_priority_floor,
    escalation_override,
    head_tail_trim,
    prepare_ticket_text,
    strip_quoted_thread,
)


def test_strip_quoted_thread_removes_quote_lines():
    text = "My real question.\n> old quoted line\n> another quoted line"
    assert strip_quoted_thread(text) == "My real question."


def test_strip_quoted_thread_removes_reply_header():
    text = "Still broken.\nOn Tue, Jan 1, 2030 at 9:00 AM Support wrote:\n> we looked into it"
    result = strip_quoted_thread(text)
    assert "wrote:" not in result
    assert "Still broken." in result


def test_strip_quoted_thread_removes_multiple_quoted_blocks():
    text = (
        "Latest reply, still an issue.\n"
        "On Mon, Jan 1, 2030 at 9:00 AM Support wrote:\n"
        "> first agent reply\n"
        "> more of the first reply\n"
        "On Tue, Jan 2, 2030 at 10:00 AM Customer wrote:\n"
        "> the original message\n"
        "> more of the original message"
    )
    result = strip_quoted_thread(text)
    assert result == "Latest reply, still an issue."
    assert "wrote:" not in result
    assert ">" not in result


def test_head_tail_trim_no_truncation_under_budget():
    text = "short message"
    result, truncated = head_tail_trim(text, budget=100)
    assert result == text
    assert truncated is False


def test_head_tail_trim_truncates_over_budget():
    text = "head" * 100 + "tail" * 100  # 800 distinguishable chars, well over budget
    result, truncated = head_tail_trim(text, budget=400)
    assert truncated is True
    assert len(result) <= 400 + len(
        "\n\n[... middle of message elided — routed on head + tail ...]\n\n"
    )
    assert result.startswith("head")
    assert result.endswith("tail")


def test_head_tail_trim_with_a_budget_smaller_than_the_elision_marker():
    # Regression test: when the elision marker alone doesn't fit the budget,
    # tail_len must not go negative — `text[-0:]` in Python returns the WHOLE
    # string, not an empty one, which used to silently balloon the result far
    # past the requested budget.
    text = "a" * 500
    result, truncated = head_tail_trim(text, budget=10)
    assert truncated is True
    assert len(result) <= 10 + len(
        "\n\n[... middle of message elided — routed on head + tail ...]\n\n"
    )


def test_prepare_ticket_text_raises_on_blank():
    with pytest.raises(BlankTicketError):
        prepare_ticket_text("")
    with pytest.raises(BlankTicketError):
        prepare_ticket_text("   \n  ")
    with pytest.raises(BlankTicketError):
        prepare_ticket_text(None)  # type: ignore[arg-type]


def test_prepare_ticket_text_raises_on_blank_after_stripping_quotes():
    with pytest.raises(BlankTicketError):
        prepare_ticket_text("> just a quoted line\n> nothing else")


def test_prepare_ticket_text_truncates_over_max_chars():
    cleaned, truncated = prepare_ticket_text("b" * 3000, max_chars=2000)
    assert truncated is True
    assert len(cleaned) < 3000


def test_prepare_ticket_text_uses_config_default_when_max_chars_omitted():
    from smart_ticket_router.config import MAX_TICKET_CHARS

    cleaned, truncated = prepare_ticket_text("c" * (MAX_TICKET_CHARS + 500))
    assert truncated is True
    assert len(cleaned) < MAX_TICKET_CHARS + 500

    cleaned, truncated = prepare_ticket_text("short enough")
    assert truncated is False


@pytest.mark.parametrize(
    "text",
    [
        "I was charged twice this month",
        "I got double charged for my subscription",
        "This is an unauthorized transaction on my card",
        "My payment failed but the money left my account",
        "I think there's been a data breach on my account",
        "I noticed a suspicious login from another country",
    ],
)
def test_escalation_override_raises_priority_on_hard_signals(text):
    assert escalation_override(text, "Low") == "High"
    assert escalation_override(text, "Medium") == "High"


def test_escalation_override_never_lowers_priority():
    assert escalation_override("nothing notable here", "High") == "High"


def test_escalation_override_does_not_fire_without_a_signal():
    assert escalation_override("the app is a bit slow today", "Low") == "Low"


@pytest.mark.parametrize(
    "text",
    [
        "what is your refund policy?",
        "this is a breach of contract in my opinion",
        "I got an unauthorized permissions error in the admin panel",
        "can't log in, forgot my password",
    ],
)
def test_escalation_override_does_not_misfire_on_ambiguous_bare_words(text):
    # Regression test: bare "refund"/"breach"/"unauthorized" and plain login
    # lockouts used to substring-match and force High regardless of context.
    assert escalation_override(text, "Low") == "Low"


def test_billing_priority_floor_forces_high_for_billing():
    assert billing_priority_floor("Billing", "Low") == "High"
    assert billing_priority_floor("Billing", "Medium") == "High"
    assert billing_priority_floor("Billing", "High") == "High"


def test_billing_priority_floor_leaves_other_categories_alone():
    assert billing_priority_floor("Technical Issue", "Low") == "Low"
    assert billing_priority_floor("General Inquiry", "Medium") == "Medium"
