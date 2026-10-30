# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generic labels mask all-digit and inner-capital values; short numbers and words stay."""

import pytest

from datakeel.core.pii import redact_pii
from datakeel.core.pii_credentials import credential_like

LABELS = ("secret", "token", "key", "auth", "SECRET", "Token")
SEPARATORS = ("=", ": ", " = ", "\uff1a", " \uff1a ", "为", " 为 : ", "是")
# A trailing ASCII period stays part of a bare credential, so it appears in prose cases only.
CONTEXTS = ("{}", "Use {} then", "配置 {}。", "({})")
PROSE_CONTEXTS = (*CONTEXTS, "The {}.", "The {}, again.")
DIGITS = ("527436037", "902652056", "12345678", "000123456789", "20261030", "123456789012345")
MIXED_CASE = ("uHwhJAmF", "kIMsmnRumCf", "XVcHWiiSwCom", "aBcDeFgH", "ABCDEFGH", "passWORDs")
SHORT_NUMBERS = ("4096", "8080", "123456", "1234567", "2026")
PROSE_WORDS = (
    "Consistency",
    "consistency",
    "Practice",
    "practice",
    "Responsibilities",
    "Well-Being",
    "Self-Discipline",
    "O'Connor",
    "uHwhJA",
)


def _texts(value: str, contexts: tuple[str, ...] = CONTEXTS) -> list[tuple[str, str]]:
    """Return every label, separator and context pairing with its expected redaction."""
    return [
        (
            context.format(label + separator + value),
            context.format(label + separator + "[SECRET]"),
        )
        for label in LABELS
        for separator in SEPARATORS
        for context in contexts
    ]


@pytest.mark.parametrize("value", DIGITS + MIXED_CASE)
def test_all_digit_and_inner_capital_values_are_masked(value: str) -> None:
    """Each of 192 pairings masks exactly the value and keeps the label and context."""
    misses = [text for text, masked in _texts(value) if redact_pii(text) != masked]
    assert not misses, misses[:5]


@pytest.mark.parametrize("value", SHORT_NUMBERS + PROSE_WORDS)
def test_short_numbers_and_capitalised_words_stay(value: str) -> None:
    """Four- to seven-digit numbers, capitalised words and short values are never masked."""
    changed = [text for text, _ in _texts(value, PROSE_CONTEXTS) if redact_pii(text) != text]
    assert not changed, changed[:5]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12345678", True),
        ("1234567", False),
        ("527436037.", True),
        ("uHwhJAmF", True),
        ("uHwhJAm", False),
        ("ABCDEFGH", True),
        ("Consistency", False),
        ("Consistency.", False),
        ("Well-Being", False),
        ("well-bEing", True),
        ("O\u2019Connor", False),
        ("密钥密钥密钥密钥", False),
    ],
)
def test_digit_and_capital_shape_rule(value: str, *, expected: bool) -> None:
    """Digits from eight and capitals after the first letter of a word part look issued."""
    assert credential_like(value) is expected


def test_generic_shape_mutation_guard() -> None:
    """One measured anchor protects digit and capital recall and the prose exceptions."""
    assert redact_pii("secret=527436037") == "secret=[SECRET]"
    assert redact_pii("token: 902652056") == "token: [SECRET]"
    assert redact_pii("auth = uHwhJAmF") == "auth = [SECRET]"
    assert redact_pii("SECRET \uff1a kIMsmnRumCf") == "SECRET \uff1a [SECRET]"
    assert redact_pii("token 为 : XVcHWiiSwCom") == "token 为 : [SECRET]"
    assert redact_pii("token: 4096") == "token: 4096"
    assert redact_pii("token: 1234567") == "token: 1234567"
    assert redact_pii("The secret: Consistency.") == "The secret: Consistency."
    assert redact_pii("The key: Well-Being.") == "The key: Well-Being."
