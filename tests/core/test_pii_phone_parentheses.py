# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retain complete parenthesized phones without loosening numeric precision."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize(
    ("text", "phone", "redacted"),
    [
        ("电话(0571) 8888-6666转人工", "(0571) 8888-6666", "电话[PHONE]转人工"),
        ("(021)68888888", "(021)68888888", "[PHONE]"),
        ("(0591) 5654-2998", "(0591) 5654-2998", "[PHONE]"),
        ("(+86) 138 0013 8000", "(+86) 138 0013 8000", "[PHONE]"),
    ],
)
def test_reported_parenthesized_phones_are_fully_redacted(
    text: str, phone: str, redacted: str
) -> None:
    """Each reported regression replaces both parentheses and keeps surrounding prose."""
    matches = detect_pii(text)
    start = text.index(phone)
    assert [(match.type, match.start, match.end) for match in matches] == [
        ("phone", start, start + len(phone))
    ]
    assert redact_pii(text) == redacted


@pytest.mark.parametrize("area", ["021", "0571"])
@pytest.mark.parametrize("subscriber", ["1234567", "12345678", "123-4567", "1234-5678"])
@pytest.mark.parametrize("separator", ["", " ", "-"])
@pytest.mark.parametrize(("opening", "closing"), [("(", ")"), ("\uff08", "\uff09")])
def test_chinese_parenthesized_phone_variants_keep_complete_spans(
    area: str, subscriber: str, separator: str, opening: str, closing: str
) -> None:
    """Three/four-digit areas support seven/eight-digit subscribers and both bracket widths."""
    phone = opening + area + closing + separator + subscriber
    text = "电话" + phone + "转人工"
    matches = detect_pii(text)
    assert [(match.type, match.start, match.end) for match in matches] == [
        ("phone", len("电话"), len("电话") + len(phone))
    ]
    assert redact_pii(text) == "电话[PHONE]转人工"


@pytest.mark.parametrize(
    "phone",
    [
        "(415) 555-0132",
        "(212)555-0132",
        "(555) 234-5678",
        "(300) 200 3000",
        "\uff08415\uff09 555-0132",
        "\uff08212\uff09555-0132",
        "\uff08555\uff09 234-5678",
    ],
)
def test_north_american_parenthesized_phone_variants_keep_complete_spans(phone: str) -> None:
    """Recognize grouped North American numbers without leaving an opening bracket."""
    matches = detect_pii(phone)
    assert [(match.type, match.start, match.end) for match in matches] == [("phone", 0, len(phone))]
    assert redact_pii(phone) == "[PHONE]"
    assert redact_pii("Call " + phone + " today.") == "Call [PHONE] today."


@pytest.mark.parametrize("value", ["(123) 456-7890", "\uff08123\uff09456-7890", "(555) 123-4567"])
def test_parenthesized_area_and_exchange_starting_zero_or_one_are_not_phones(value: str) -> None:
    """A North American area or exchange code never starts with 0 or 1."""
    assert not detect_pii(value)
    assert redact_pii("记录" + value + "。") == "记录" + value + "。"


@pytest.mark.parametrize("phone", ["(415) 555-0132", "(212)555-0132", "(300) 200 3000"])
def test_international_prefix_keeps_foreign_parenthesized_recall(phone: str) -> None:
    """An explicit country code remains phone evidence for bracketed foreign area codes."""
    assert [match.type for match in detect_pii("+1 " + phone)] == ["phone"]
    assert redact_pii("+1 " + phone) == "[PHONE]"


@pytest.mark.parametrize(
    "value",
    [
        "1(0571)88886666",
        "9\uff08021\uff0968888888",
        "1 (0571) 8888-6666",
        "9-\uff08021\uff0968888888",
        "(0571)888866661",
        "\uff08021\uff09688888881",
        "(0571)88886666 1",
        "\uff08021\uff0968888888-9",
        "(555) 123-45678",
        "123456789012",
        "12345678901234",
        "20240315123045",
        "1001-2024-123456",
        "订单(2026) 12345678",
        "时间(2026) 10-301230",
    ],
)
def test_parenthesized_phone_support_does_not_accept_numeric_identifiers(value: str) -> None:
    """Adjacent digits, dates and order groups cannot yield a partial phone finding."""
    assert not detect_pii("记录 " + value + "。")
    assert redact_pii("记录 " + value + "。") == "记录 " + value + "。"


def test_parenthesized_phone_mutation_guard() -> None:
    """Independent anchor requires full brackets while retaining long-number rejection."""
    text = "电话(0571) 8888-6666转人工"
    matches = detect_pii(text)
    assert [(match.type, match.start, match.end) for match in matches] == [("phone", 2, 18)]
    assert redact_pii(text) == "电话[PHONE]转人工"
    assert redact_pii("\uff080571\uff0988886666") == "[PHONE]"
    for value in ("123456789012", "12345678901234", "20240315123045", "1001-2024-123456"):
        assert not detect_pii(value)
