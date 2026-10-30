# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A phone finding never starts or ends between a pair of brackets."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

GROUPS = ("1999", "1380", "1501", "1876", "2026", "9999")
BRACKETS = (("(", ")"), ("OPEN", "CLOSE"))
SUBSCRIBERS = ("888 8888", "8888888", "888-8888", " 888 8888", " 555-1234")
CONTEXTS = ("{}", "Call {} today.", "DIAL{}END", "NOTE: {}.")
COMPLETE = (
    "(0999) 888 8888",
    "OPEN0999CLOSE888 8888",
    "(021)68888888",
    "(0571) 8888-6666",
    "(+86) 138 0013 8000",
    "(212) 736-5000",
    "OPEN569CLOSE523-4910",
)


def _wide(text: str) -> str:
    """Spell full-width brackets, the Chinese call prefix and suffix, and colons."""
    return (
        text.replace("OPEN", chr(0xFF08))
        .replace("CLOSE", chr(0xFF09))
        .replace("DIAL", chr(0x7535) + chr(0x8BDD))
        .replace("END", chr(0x8F6C) + chr(0x4EBA) + chr(0x5DE5))
        .replace("NOTE:", chr(0x8BB0) + chr(0x5F55) + chr(0xFF1A))
    )


def _half_bracket_numbers() -> list[str]:
    """Return four-digit bracket groups not starting with 0, followed by a short number."""
    return [
        _wide(opening + group + closing + subscriber)
        for group in GROUPS
        for opening, closing in BRACKETS
        for subscriber in SUBSCRIBERS
    ]


@pytest.mark.parametrize("context", CONTEXTS)
def test_four_digit_bracket_groups_are_not_area_codes(context: str) -> None:
    """All 60 shapes stay unchanged: no finding starts inside the brackets."""
    changed = [
        _wide(context).format(value)
        for value in _half_bracket_numbers()
        if redact_pii(_wide(context).format(value)) != _wide(context).format(value)
    ]
    assert not changed, changed[:5]


@pytest.mark.parametrize("context", CONTEXTS)
def test_complete_bracketed_phones_keep_both_brackets(context: str) -> None:
    """Mainland, +86 and North American bracket forms are still reported in full."""
    misses = []
    for value in map(_wide, COMPLETE):
        text = _wide(context).format(value)
        start = text.index(value)
        found = [(match.type, match.start, match.end) for match in detect_pii(text)]
        if found != [("phone", start, start + len(value))]:
            misses.append((text, found))
    assert not misses, misses[:5]


@pytest.mark.parametrize("group", GROUPS)
def test_a_mobile_after_a_bracket_group_is_reported_alone(group: str) -> None:
    """A complete mobile after a non-area bracket group is found without the bracket."""
    text = "(" + group + ") 13800138000"
    assert [(match.type, match.start, match.end) for match in detect_pii(text)] == [
        ("phone", len(group) + 3, len(text))
    ]


def test_half_bracket_mutation_guard() -> None:
    """One measured anchor protects both bracket ends and keeps complete brackets."""
    assert redact_pii("(1999) 888 8888") == "(1999) 888 8888"
    assert redact_pii("(1380)8888888") == "(1380)8888888"
    assert redact_pii("138 0013 (8000") == "138 0013 (8000"
    assert redact_pii("(0999) 888 8888") == "[PHONE]"
    assert redact_pii("(+86) 138 0013 8000") == "[PHONE]"
    assert redact_pii("(212) 736-5000") == "[PHONE]"
