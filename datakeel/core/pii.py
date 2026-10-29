# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect and redact personal data and credential shapes without network services."""

from __future__ import annotations

import re
from datetime import date
from ipaddress import IPv6Address, ip_address
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from datakeel.core import pii_patterns as patterns
from datakeel.core.models import Record

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from re import Pattern

PiiType = Literal["email", "phone", "china_id", "bank_card", "ip", "secret", "credential_url"]
_PRIORITY: tuple[PiiType, ...] = (
    "credential_url",
    "secret",
    "china_id",
    "bank_card",
    "email",
    "phone",
    "ip",
)
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECKS = "10X98765432"
_MIN_BIRTH_YEAR = 1800
_MAX_BIRTH_YEAR = 2099
_ID_LENGTH = 18
_MAX_DECIMAL_DIGIT = 9
_MIN_PHONE_DIGITS = 8
_MAX_PHONE_DIGITS = 15
_MIN_COMPACT_PHONE_DIGITS = 10
_MIN_SECRET_LENGTH = 8
_SECRET_LABELS = frozenset(
    {
        "apikey",
        "accesstoken",
        "authtoken",
        "secretkey",
        "secretaccesskey",
        "awssecretaccesskey",
        "clientsecret",
        "githubtoken",
        "ghtoken",
        "password",
        "passwd",
    }
)
_PLACEHOLDERS = frozenset(f"[{kind.upper()}]" for kind in _PRIORITY) | {"[REDACTED]"}
_CARD_ISSUERS = (
    ({13, 16, 19}, "4", "4"),
    ({15}, "34", "34"),
    ({15}, "37", "37"),
    ({16}, "51", "55"),
    ({16}, "2221", "2720"),
    ({16, 17, 18, 19}, "62", "62"),
    ({16, 17, 18, 19}, "81", "81"),
    ({16, 19}, "6011", "6011"),
    ({16, 19}, "65", "65"),
    ({16, 19}, "644", "649"),
    ({16, 17, 18, 19}, "3528", "3589"),
    ({14}, "300", "305"),
    ({14}, "36", "36"),
    ({14}, "38", "39"),
)
_PROVINCES = frozenset(
    {
        11,
        12,
        13,
        14,
        15,
        21,
        22,
        23,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        41,
        42,
        43,
        44,
        45,
        46,
        50,
        51,
        52,
        53,
        54,
        61,
        62,
        63,
        64,
        65,
        71,
        81,
        82,
    }
)


class PiiMatch(Record):
    """Locate one nonoverlapping privacy finding without retaining its original value."""

    type: PiiType
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @property
    def placeholder(self) -> str:
        """Return a stable, type-labelled replacement for this finding."""
        return f"[{self.type.upper()}]"


def _valid_id(value: str) -> bool:
    if not _id_shape(value):
        return False
    checksum = sum(int(char) * weight for char, weight in zip(value[:17], _ID_WEIGHTS, strict=True))
    return value[-1].upper() == _ID_CHECKS[checksum % 11]


def _id_shape(value: str) -> bool:
    if int(value[:2]) not in _PROVINCES or value[14:17] == "000":
        return False
    try:
        birth = date(int(value[6:10]), int(value[10:12]), int(value[12:14]))
    except ValueError:
        return False
    return _MIN_BIRTH_YEAR <= birth.year <= _MAX_BIRTH_YEAR


def _valid_card(value: str) -> bool:
    digits = value.replace(" ", "").replace("-", "")
    length = len(digits)
    if len(set(digits)) == 1 or not _card_prefix(digits):
        return False
    # An 18-digit resident ID is never reclassified as a payment card.
    if length == _ID_LENGTH and _id_shape(digits):
        return False
    doubled = [int(char) * (2 if index % 2 else 1) for index, char in enumerate(digits[::-1])]
    checksum = sum(
        number - _MAX_DECIMAL_DIGIT if number > _MAX_DECIMAL_DIGIT else number for number in doubled
    )
    return checksum % 10 == 0


def _card_prefix(digits: str) -> bool:
    return any(
        len(digits) in lengths and lower <= digits[: len(lower)] <= upper
        for lengths, lower, upper in _CARD_ISSUERS
    )


def _valid_phone(value: str) -> bool:
    digits = "".join(char for char in value if char.isdigit())
    digits = digits.removeprefix("00")
    if not _MIN_PHONE_DIGITS <= len(digits) <= _MAX_PHONE_DIGITS or len(set(digits)) == 1:
        return False
    if not value.startswith("+") and _card_prefix(digits):
        return False
    return (
        len(digits) >= _MIN_COMPACT_PHONE_DIGITS
        or value.startswith("+")
        or any(char in value for char in "()-")
    )


def _candidates(text: str) -> Iterator[PiiMatch]:
    simple: tuple[tuple[PiiType, Pattern[str], bool], ...] = (
        ("credential_url", patterns.CREDENTIAL_URL, "://" in text),
        ("secret", patterns.SECRET, patterns.SECRET_HINT.search(text) is not None),
        ("secret", patterns.PRIVATE_KEY, "PRIVATE KEY-----" in text),
        ("email", patterns.EMAIL, "@" in text),
    )
    for kind, pattern, possible in simple:
        if not possible:
            continue
        for match in pattern.finditer(text):
            end = match.end()
            if kind == "credential_url":
                end = match.start() + len(
                    match.group().rstrip(".,;!?\u3002\uff0c\uff1b\uff01\uff1f")
                )
            yield PiiMatch(type=kind, start=match.start(), end=end)
    yield from _credential_candidates(text)
    yield from _number_candidates(text)
    yield from _ip_candidates(text)


def _credential_candidates(text: str) -> Iterator[PiiMatch]:
    if patterns.ASCII_LETTER.search(text) is None:
        return
    if patterns.LABEL_HINT.search(text) is None:
        return
    for pattern in (patterns.LABELED_SECRET, patterns.BEARER):
        for match in pattern.finditer(text):
            yield PiiMatch(type="secret", start=match.start("value"), end=match.end("value"))
    for match in patterns.QUOTED_SECRET.finditer(text):
        if candidate := _labeled_secret(match.group("value"), match.group("label")):
            start = match.start("value")
            yield PiiMatch(type="secret", start=start + candidate.start, end=start + candidate.end)


def _ip_candidates(text: str) -> Iterator[PiiMatch]:
    for pattern in (patterns.IPV4, patterns.IPV6):
        if (pattern is patterns.IPV4 and "." not in text) or (
            pattern is patterns.IPV6 and ":" not in text
        ):
            continue
        for match in pattern.finditer(text):
            try:
                ip_address(match.group())
            except ValueError:
                continue
            yield PiiMatch(type="ip", start=match.start(), end=match.end())
    if ":" not in text:
        return
    for match in patterns.LABELED_IP.finditer(text):
        value = match.group("value").rstrip(".")
        try:
            address = ip_address(value)
        except ValueError:
            continue
        if isinstance(address, IPv6Address):
            yield PiiMatch(
                type="ip", start=match.start("value"), end=match.start("value") + len(value)
            )


def _number_candidates(text: str) -> Iterator[PiiMatch]:
    if patterns.NUMBER_RUN.search(text) is None:
        return
    checks: tuple[tuple[PiiType, Pattern[str], Callable[[str], bool]], ...] = (
        ("china_id", patterns.CHINA_ID, _valid_id),
        ("bank_card", patterns.BANK_CARD, _valid_card),
        ("phone", patterns.CHINA_MOBILE, _valid_phone),
        ("phone", patterns.PHONE, _valid_phone),
    )
    for kind, pattern, validate in checks:
        for match in pattern.finditer(text):
            if pattern is not patterns.CHINA_MOBILE and _numeric_prefix(text, match.start()):
                continue
            if validate(match.group()):
                yield PiiMatch(type=kind, start=match.start(), end=match.end())


def _numeric_prefix(text: str, start: int) -> bool:
    if text[start] == "+":
        return False
    index = start - 1
    while index >= 0 and text[index] in " -()":
        index -= 1
    return index >= 0 and text[index].isdigit()


def _labeled_secret(text: str, label: str | None) -> PiiMatch | None:
    if label is None:
        return None
    normalized = re.sub(r"[^a-z0-9]", "", label.casefold())
    value = text.strip()
    if (
        normalized not in _SECRET_LABELS
        or len(value) < _MIN_SECRET_LENGTH
        or value in _PLACEHOLDERS
    ):
        return None
    if normalized not in {"password", "passwd"} and not patterns.SECRET_VALUE.fullmatch(value):
        return None
    start = len(text) - len(text.lstrip())
    return PiiMatch(type="secret", start=start, end=start + len(value))


def detect_pii(text: str, *, label: str | None = None) -> tuple[PiiMatch, ...]:
    """Return validated findings, resolving enclosing credentials before their contents.

    Resident IDs require a valid province, birth date, sequence and checksum. Cards
    require a recognized issuer shape and Luhn checksum. These are shape checks,
    not proof that an identity, card, account or secret is issued or active.
    An optional credential-field label supplies context for otherwise opaque values;
    all offsets still refer to the original value, without a synthetic prefix.
    """
    candidates = list(_candidates(text))
    if finding := _labeled_secret(text, label):
        candidates.append(finding)
    selected: list[PiiMatch] = []
    for match in sorted(
        candidates, key=lambda item: (_PRIORITY.index(item.type), item.start, -item.end)
    ):
        if not any(match.start < item.end and item.start < match.end for item in selected):
            selected.append(match)
    return tuple(sorted(selected, key=lambda item: item.start))


def redact_pii(
    text: str,
    *,
    replacement: str | None = None,
    kinds: frozenset[PiiType] | None = None,
    label: str | None = None,
) -> str:
    """Replace findings with type placeholders, or an explicitly supplied legacy label."""
    result: list[str] = []
    cursor = 0
    for match in detect_pii(text, label=label):
        if kinds is not None and match.type not in kinds:
            continue
        result.extend((text[cursor : match.start], replacement or match.placeholder))
        cursor = match.end
    result.append(text[cursor:])
    return "".join(result)
