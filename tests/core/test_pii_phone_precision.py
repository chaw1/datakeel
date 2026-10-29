# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require phone structure and complete numeric boundaries for everyday prose."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

PHONES = (
    "13800138000",
    "+8613800138000",
    "+86 13800138000",
    "0086 13800138000",
    "138 0013 8000",
    "138-0013-8000",
    "+86 138 0013 8000",
    "+86-138-0013-8000",
    "010-88888888",
    "021-87654321",
    "0755-12345678",
    "010 8888 8888",
    "0411-1234567",
    "415-555-0132",
    "+1 (415) 555-0132",
    "+44 7911 123456",
    "+33 6 12 34 56 78",
    "+49 1512 3456789",
    "+81 90 1234 5678",
    "+12 34 56 78",
)
NONPHONES = (
    "123456789012",
    "12345678901234",
    "20240315123045",
    "1001-2024-123456",
    "2026-10-30",
    "2026/10/30",
    "20261030",
    "12:30:45",
    "23:59",
    "100.50元",
    "\uffe512345.67",
    "\uffe513800138000",
    "$123456789012",
    "v1.2.3456789012",
    "v1.2.13800138000",
    "13800138000.25",
    "13800138000%",
    "13800138000元",
    "100000",
    "200001",
    "CA1234",
    "MU5101",
    "95%",
    "0.95",
    "\uff11\uff12\uff13\uff1413800138000",
    "13800138000\uff19",
    "913800138000",
    "138001380001",
    "13800138000123",
    "012345678901234",
)


@pytest.mark.parametrize("value", PHONES)
@pytest.mark.parametrize(("prefix", "suffix"), [("", ""), ("电话", "联系"), ("Call ", ".")])
def test_common_phones_keep_complete_recall(value: str, prefix: str, suffix: str) -> None:
    """Country codes, grouping and adjacent Chinese all retain exactly one phone span."""
    text = prefix + value + suffix
    assert [match.type for match in detect_pii(text)] == ["phone"]
    assert redact_pii(text) == prefix + "[PHONE]" + suffix


@pytest.mark.parametrize("value", NONPHONES)
def test_daily_numeric_values_do_not_become_phone_findings(value: str) -> None:
    """Orders, timestamps, prices, versions and counters need no privacy replacement."""
    assert not detect_pii("记录 " + value + "。")


@pytest.mark.parametrize("prefix", ["", "1", "9", "12", "123"])
@pytest.mark.parametrize("suffix", ["1", "9", "12", "123"])
def test_phone_substrings_inside_longer_digit_runs_remain_negative(
    prefix: str, suffix: str
) -> None:
    """An otherwise valid mobile is not evidence inside a larger identifier."""
    assert not any(match.type == "phone" for match in detect_pii(prefix + PHONES[0] + suffix))


def test_phone_precision_guard_rejects_long_bare_numbers_and_keeps_formats() -> None:
    """Independent mutation guard checks precision together with supported recall."""
    for value in NONPHONES:
        assert not detect_pii(value)
    for value in PHONES:
        assert [match.type for match in detect_pii(value)] == ["phone"]
