# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reference numbers are not phones; complete phones separated by one space all count."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize(
    "text",
    [
        "编号\uff08010\uff092024-0315号",
        "编号(010)2024-0315",
        "编号\uff1a010-62345678",
        "订单号13800138000",
        "订单号\uff1a13800138000。",
        "运单号 13800138000",
        "批次 010-62345678",
        "批次号\uff1a(021)68888888",
        "No. 13800138000",
        "No.13800138000",
        "Order #13800138000",
        "Ref. 010-62345678",
        "第13800138000号",
        "文件 010-62345678号",
    ],
)
def test_reference_numbers_are_not_phones(text: str) -> None:
    """Identifier words before or 号 after a digit run veto the phone reading."""
    assert not detect_pii(text)
    assert redact_pii(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("电话13800138000", "电话[PHONE]"),
        ("手机号13800138000", "手机号[PHONE]"),
        ("联系电话\uff1a010-62345678。", "联系电话\uff1a[PHONE]。"),
        ("Call (0571) 8888-6666 now", "Call [PHONE] now"),
        ("casino 13800138000", "casino [PHONE]"),
        ("Phone No 13800138000 is mine", "Phone No [PHONE] is mine"),
        ("Tel No. 0571-88886666", "Tel No. [PHONE]"),
        ("Mobile No.: 13800138000", "Mobile No.: [PHONE]"),
        ("电话#13800138000", "电话#[PHONE]"),
    ],
)
def test_reference_veto_keeps_ordinary_phone_context(text: str, expected: str) -> None:
    """Only the listed identifier words veto; phone labels and other words do not."""
    assert redact_pii(text) == expected


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("010-62345678", "021-55556666"),
        ("0571-88886666", "010-62345678"),
        ("(010)62345678", "(021)55556666"),
        ("010-62345678", "13800138000"),
        ("13800138000", "0755-12345678"),
    ],
)
@pytest.mark.parametrize(("prefix", "suffix"), [("", ""), ("电话", "。"), ("Tel: ", " ok")])
def test_single_space_separated_phones_are_both_found(
    first: str, second: str, prefix: str, suffix: str
) -> None:
    """Two complete numbers one space apart become two phone findings."""
    text = prefix + first + " " + second + suffix
    assert [item.type for item in detect_pii(text)] == ["phone", "phone"]
    assert redact_pii(text) == prefix + "[PHONE] [PHONE]" + suffix


def test_three_space_separated_phones_are_all_found() -> None:
    """Runs longer than two keep every complete number."""
    text = "010-62345678 021-55556666 0755-12345678"
    assert redact_pii(text) == "[PHONE] [PHONE] [PHONE]"


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("记录 010-62345678 0215", "0215"),
        ("记录 010-62345678 021-5555", "021-5555"),
        ("记录 1001-2024 123456", "1001-2024 123456"),
        ("记录 (0571)88886666 1", "(0571)88886666 1"),
    ],
)
def test_incomplete_sequences_do_not_create_partial_phones(text: str, kept: str) -> None:
    """A trailing fragment is never reported, and an ambiguous run keeps its digits."""
    assert kept in redact_pii(text)


def test_phone_reference_and_sequence_mutation_guard() -> None:
    """One measured anchor protects both precision and two-landline recall."""
    assert redact_pii("编号\uff08010\uff092024-0315号") == "编号\uff08010\uff092024-0315号"
    assert redact_pii("订单号13800138000") == "订单号13800138000"
    assert redact_pii("No. 13800138000") == "No. 13800138000"
    assert redact_pii("文件 010-62345678号") == "文件 010-62345678号"
    assert redact_pii("(123) 456-7890") == "(123) 456-7890"
    assert redact_pii("010-62345678 021-55556666") == "[PHONE] [PHONE]"
    assert redact_pii("电话(0571) 8888-6666") == "电话[PHONE]"
