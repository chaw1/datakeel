# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bracketed North American numbers are phones; 0/1 area or exchange digits are not."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

AREAS = ("201", "212", "300", "415", "569", "999")
EXCHANGES = ("200", "523", "736", "999")
BRACKETS = (("(", ")"), ("\uff08", "\uff09"))
LAYOUTS = (" {}-{}", "{}-{}", "{}{}", " {} {}", " {}{}")
CONTEXTS = ("{}", "Call {} today.", "电话{}转人工", "联系\uff1a{}。")


def _phones() -> list[str]:
    """Return every area, exchange, bracket width and grouping, with line number 4910."""
    return [
        opening + area + closing + layout.format(exchange, "4910")
        for area in AREAS
        for exchange in EXCHANGES
        for opening, closing in BRACKETS
        for layout in LAYOUTS
    ]


@pytest.mark.parametrize("context", CONTEXTS)
def test_north_american_bracketed_numbers_keep_complete_spans(context: str) -> None:
    """All 240 shapes report one phone covering both brackets inside each context."""
    misses = []
    for phone in _phones():
        text = context.format(phone)
        start = text.index(phone)
        found = [(match.type, match.start, match.end) for match in detect_pii(text)]
        if found != [("phone", start, start + len(phone))]:
            misses.append((text, found))
    assert not misses, misses[:5]


NOT_PHONES = (
    "(123) 456-7890",
    "\uff08123\uff09456-7890",
    "(155) 234-5678",
    "(199)9999999",
    "(555) 123-4567",
    "(212) 055-1234",
    "\uff08415\uff09155-0132",
    "(555) 234-56789",
    "(555) 23-45678",
    "(55) 234-5678",
    "1(212)736-5000",
    "(212)736-50001",
)
REFERENCES = (
    "编号 (555) 234-5678",
    "单号\uff1a(212) 736-5000",
    "No. (212) 736-5000",
    "Order #(415) 555-0132",
    "(212) 736-5000号",
)


@pytest.mark.parametrize("context", CONTEXTS)
def test_zero_or_one_digits_and_references_are_not_phones(context: str) -> None:
    """Area or exchange codes starting 0/1, bad lengths and references stay unchanged."""
    # A phone word before the identifier keeps its phone meaning ("Tel No."), so references
    # are checked outside the phone-word context.
    values = NOT_PHONES if context.startswith(CONTEXTS[2][:2]) else NOT_PHONES + REFERENCES
    changed = [
        context.format(value)
        for value in values
        if redact_pii(context.format(value)) != context.format(value)
    ]
    assert not changed, changed


def test_north_american_phone_mutation_guard() -> None:
    """One measured anchor protects the NXX area and exchange rule in both bracket widths."""
    assert redact_pii("\uff08569\uff09523-4910") == "[PHONE]"
    assert redact_pii("(569)5591890") == "[PHONE]"
    assert redact_pii("(300) 200 3000") == "[PHONE]"
    assert redact_pii("Call (212) 736-5000 today.") == "Call [PHONE] today."
    assert redact_pii("(123) 456-7890") == "(123) 456-7890"
    assert redact_pii("\uff08123\uff09456-7890") == "\uff08123\uff09456-7890"
    assert redact_pii("(555) 123-4567") == "(555) 123-4567"
    assert redact_pii("(212) 736-5000号") == "(212) 736-5000号"
