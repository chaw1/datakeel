# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reference numbers and foreign bracketed area codes are not mainland phones."""

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


def test_phone_reference_and_sequence_mutation_guard() -> None:
    """One measured anchor protects reference and area-code precision."""
    assert redact_pii("编号\uff08010\uff092024-0315号") == "编号\uff08010\uff092024-0315号"
    assert redact_pii("订单号13800138000") == "订单号13800138000"
    assert redact_pii("No. 13800138000") == "No. 13800138000"
    assert redact_pii("文件 010-62345678号") == "文件 010-62345678号"
    assert redact_pii("(300) 200 3000") == "(300) 200 3000"
    assert redact_pii("电话(0571) 8888-6666") == "电话[PHONE]"
