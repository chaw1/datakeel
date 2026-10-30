# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A mobile whose first three digits are bracketed is one phone, brackets included."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

PREFIXES = ("130", "138", "139", "150", "166", "186", "199")
BRACKETS = (("(", ")"), ("\uff08", "\uff09"))
GAPS = ("", " ", "-")
BODIES = ("{}{}", "{} {}", "{}-{}")
CONTEXTS = ("{}", "手机{}", "电话 {} 找我", "Call {} today.", "联系\uff1a{}。")
WORD_FREE = ("{}", "Call {} today.", "联系\uff1a{}。")


def _mobiles() -> list[str]:
    """Return every prefix, bracket width, gap and four-plus-four body grouping."""
    return [
        opening + prefix + closing + gap + body.format(*digits)
        for prefix in PREFIXES
        for opening, closing in BRACKETS
        for gap in GAPS
        for body in BODIES
        for digits in (("1234", "5678"), ("0000", "1234"))
    ]


@pytest.mark.parametrize("context", CONTEXTS)
def test_bracketed_mobile_prefixes_keep_complete_spans(context: str) -> None:
    """All 252 shapes report one phone covering both brackets inside each context."""
    misses = []
    for phone in _mobiles():
        text = context.format(phone)
        start = text.index(phone)
        found = [(match.type, match.start, match.end) for match in detect_pii(text)]
        if found != [("phone", start, start + len(phone))]:
            misses.append((text, found))
    assert not misses, misses[:5]


NOT_PHONES = (
    "(120) 1234 5678",
    "\uff08120\uff091234-5678",
    "(100)12345678",
    "\uff08110\uff098888 6666",
    "(1999) 888 8888",
    "(123) 456-7890",
    "(138) 1234 567",
    "(138)1234567",
    "\uff08139\uff09888 6666",
    "(186) 0000-123",
    "(138) 1234 56789",
    "(138) 1234 5678 9",
    "1(138) 1234 5678",
    "\uff081380\uff091234 5678",
)
REFERENCES = ("编号 (138) 1234 5678", "(138) 1234 5678号", "No. (186) 0000-1234")


@pytest.mark.parametrize("context", CONTEXTS)
def test_other_prefixes_short_bodies_and_references_stay(context: str) -> None:
    """Non-mobile brackets, wrong lengths, adjacent digits and references stay unchanged."""
    # A phone word before an identifier keeps its phone meaning, so references use the others.
    values = NOT_PHONES + (REFERENCES if context in WORD_FREE else ())
    changed = [
        context.format(value)
        for value in values
        if redact_pii(context.format(value)) != context.format(value)
    ]
    assert not changed, changed


def test_bracketed_mobile_mutation_guard() -> None:
    """One measured anchor protects both bracket widths, the prefix and the body length."""
    assert redact_pii("(138) 1234 5678") == "[PHONE]"
    assert redact_pii("手机\uff08139\uff098888 6666") == "手机[PHONE]"
    assert redact_pii("电话 (186) 0000-1234 找我") == "电话 [PHONE] 找我"
    assert redact_pii("(120) 1234 5678") == "(120) 1234 5678"
    assert redact_pii("\uff08120\uff091234 5678") == "\uff08120\uff091234 5678"
    assert redact_pii("(138) 1234 567") == "(138) 1234 567"
    assert redact_pii("\uff08139\uff09888 6666") == "\uff08139\uff09888 6666"
    assert redact_pii("(1999) 888 8888") == "(1999) 888 8888"
    assert redact_pii("(212) 736-5000") == "[PHONE]"
