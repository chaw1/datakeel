# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect compound Chinese credential separators and their exact value offsets."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize(
    ("text", "expected", "value"),
    [
        ("密码是\uff1aAbc12345!x", "密码是\uff1a[SECRET]", "Abc12345!x"),
        ("密码为\uff1aAbc12345!x", "密码为\uff1a[SECRET]", "Abc12345!x"),
        ("口令是: Abc12345x", "口令是: [SECRET]", "Abc12345x"),
    ],
)
def test_reported_compound_separators_preserve_the_exact_secret_span(
    text: str, expected: str, value: str
) -> None:
    """The reported compound assignments redact only their value, including punctuation."""
    findings = detect_pii(text)
    assert [(item.type, item.start, item.end) for item in findings] == [
        ("secret", text.index(value), text.index(value) + len(value))
    ]
    assert redact_pii(text) == expected


@pytest.mark.parametrize("label", ["密码", "口令", "密钥", "访问令牌", "password", "api_key"])
@pytest.mark.parametrize("verb", ["是", "为"])
@pytest.mark.parametrize("colon", [":", "\uff1a"])
@pytest.mark.parametrize("spacing", ["", " ", "  ", "\t"])
@pytest.mark.parametrize("quote", ["", '"', "'"])
def test_compound_separator_masks_only_the_complete_value(
    label: str, verb: str, colon: str, spacing: str, quote: str
) -> None:
    """Optional whitespace after the compound separator never enters the secret span."""
    value = "Qwerty123!@#"
    prefix = f"配置{label}{verb}{colon}{spacing}{quote}"
    suffix = f"{quote}就行。"
    text = prefix + value + suffix
    findings = detect_pii(text)
    assert [(item.type, item.start, item.end) for item in findings] == [
        ("secret", len(prefix), len(prefix) + len(value))
    ]
    assert redact_pii(text) == prefix + "[SECRET]" + suffix


@pytest.mark.parametrize("separator", ["是:", "是\uff1a ", "为:", "为\uff1a "])
def test_compound_separator_preserves_adjacent_assignment_labels(separator: str) -> None:
    """Compound separators obey the same independent-assignment boundary as colons."""
    text = f"密码{separator}Qwerty123!&token{separator}Abcd1234!"
    assert redact_pii(text) == f"密码{separator}[SECRET]&token{separator}[SECRET]"
    assert [item.type for item in detect_pii(text)] == ["secret", "secret"]


@pytest.mark.parametrize("separator", ["是:", "是\uff1a ", "为:", "为\uff1a "])
@pytest.mark.parametrize("value", ["", " ", "abc", "!!!!!!!!", "[SECRET]", "[REDACTED]"])
def test_compound_separator_without_a_valid_secret_stays_negative(
    separator: str, value: str
) -> None:
    """A more flexible assignment prefix cannot bypass value validation."""
    text = "密码" + separator + value
    assert not detect_pii(text)
    assert redact_pii(text) == text


def test_compound_separator_mutation_guard() -> None:
    """Removing the optional colon must expose a measured value-boundary failure."""
    for separator in ("是:", "是\uff1a", "为:", "为\uff1a", "是 : ", "为\t\uff1a "):
        text = "密码" + separator + "Abc12345!x"
        assert redact_pii(text) == "密码" + separator + "[SECRET]"
        assert [text[item.start : item.end] for item in detect_pii(text)] == ["Abc12345!x"]
