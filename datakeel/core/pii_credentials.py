# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Classify credential labels and validate their assigned values without network services."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Literal

from datakeel.core import pii_patterns as patterns

if TYPE_CHECKING:
    from collections.abc import Iterator

LabelKind = Literal["password", "named", "generic"]
Span = tuple[int, int]

PLACEHOLDERS = frozenset(
    {
        "[CREDENTIAL_URL]",
        "[SECRET]",
        "[CHINA_ID]",
        "[BANK_CARD]",
        "[EMAIL]",
        "[PHONE]",
        "[IP]",
        "[REDACTED]",
    }
)
_MIN_PASSWORD_LENGTH = 4
_MIN_SECRET_LENGTH = 8
_MIN_ENCODED_LENGTH = 16
_MIN_CHARACTER_CLASSES = 2
# gitleaks' generic-api-key rule treats Shannon entropy >= 3.5 bits/char as a random token.
_MIN_WORD_ENTROPY = 3.5
_PASSWORD_WORDS = frozenset({"password", "passwd", "pwd", "pass", "passphrase", "密码", "口令"})
_GENERIC_WORDS = frozenset({"secret", "token", "key", "auth"})
_NAMED_LABELS = frozenset(
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
        "privatekey",
        "密钥",
        "令牌",
        "访问密钥",
        "访问令牌",
    }
)
_SEGMENT = re.compile(r"[_.\-\s]+")
_PROSE_WORD = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*")
_HEX = re.compile(r"[0-9A-Fa-f]{16,}")
_BASE64 = re.compile(r"(?:[A-Za-z0-9+/]{16,}|[A-Za-z0-9_-]{16,})={0,2}")
_MASK = re.compile(r"[*xX•●#.\-_]+")
_WRAPPED_WORD = re.compile(r"(?:[<\[{(]{1,2}\s*[A-Za-z][A-Za-z _-]{0,39}\s*[>\]})]{1,2}|\$\{\w+\})")


def label_kind(label: str) -> LabelKind | None:
    """Classify a credential label by its final key segment, ignoring case.

    Password-like final segments use the short-password rule. Single generic English words
    (secret, token, key, auth) require a credential-like value. Other recognized labels,
    including prefixed environment keys ending in secret or token, keep the named rule.
    """
    segments = [part for part in _SEGMENT.split(label.casefold()) if part]
    if not segments:
        return None
    last = segments[-1]
    if last in _PASSWORD_WORDS:
        return "password"
    if len(segments) == 1 and last in _GENERIC_WORDS:
        return "generic"
    suffixes = ("".join(segments[index:]) for index in range(len(segments)))
    if last in {"secret", "token"} or any(suffix in _NAMED_LABELS for suffix in suffixes):
        return "named"
    return None


def is_placeholder(value: str) -> bool:
    """Return whether a value is already a mask, redaction marker or template reference."""
    return (
        value.upper() in PLACEHOLDERS
        or _MASK.fullmatch(value) is not None
        or _WRAPPED_WORD.fullmatch(value) is not None
    )


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum(count / len(value) * math.log2(count / len(value)) for count in counts.values())


def credential_like(value: str) -> bool:
    """Return whether a generic-label value looks like an issued credential.

    The value has no whitespace and either has at least eight characters from two of the
    letter, digit and symbol classes, or is a hex/base64 string of at least sixteen. Trailing
    sentence punctuation is ignored, and hyphenated prose words count as letters only.
    """
    value = value.rstrip(".,;:!?")
    if not value or any(char.isspace() for char in value):
        return False
    if _HEX.fullmatch(value):
        return True
    if _PROSE_WORD.fullmatch(value):
        return (
            len(value) >= _MIN_ENCODED_LENGTH
            and _BASE64.fullmatch(value) is not None
            and _entropy(value) >= _MIN_WORD_ENTROPY
        )
    classes = (
        any(char.isalpha() for char in value)
        + any(char.isdigit() for char in value)
        + any(not char.isalnum() for char in value)
    )
    # Digits-only runs are hex above; letter-only base64 is the prose-word branch.
    return len(value) >= _MIN_SECRET_LENGTH and classes >= _MIN_CHARACTER_CLASSES


def _accepts(value: str, kind: LabelKind | None) -> bool:
    if kind is None or is_placeholder(value) or not any(char.isalnum() for char in value):
        return False
    if kind == "password":
        return len(value) >= _MIN_PASSWORD_LENGTH
    if kind == "generic":
        return credential_like(value)
    return len(value) >= _MIN_SECRET_LENGTH


def _bare_secret(value: str, start: int, kind: LabelKind | None) -> Span | None:
    value = value.rstrip(",;")
    while any(
        value.endswith(closing) and value.count(closing) > value.count(opening)
        for opening, closing in (("(", ")"), ("[", "]"), ("{", "}"))
    ):
        value = value[:-1].rstrip(",;")
    if _accepts(value, kind):
        return start, start + len(value)
    return None


def labeled_secret(text: str, label: str | None) -> Span | None:
    """Locate a labelled value supplied as a quoted string or a field with a known label."""
    if label is None:
        return None
    kind = label_kind(label)
    value = text.strip()
    if not _accepts(value, kind):
        return None
    if kind == "named" and not patterns.SECRET_VALUE.fullmatch(value):
        return None
    start = len(text) - len(text.lstrip())
    return start, start + len(value)


def credential_spans(text: str) -> Iterator[Span]:
    """Yield labelled, quoted and bearer credential value spans in one text."""
    if patterns.LABEL_HINT.search(text) is None:
        return
    urls = tuple(patterns.CREDENTIAL_URL.finditer(text)) if "://" in text else ()
    starts = [
        match.start()
        for match in patterns.CREDENTIAL_ASSIGNMENT.finditer(text)
        if not any(url.start() <= match.start() < url.end() for url in urls)
    ]
    for index, start in enumerate(starts):
        if match := patterns.LABELED_SECRET.match(text, start):
            end = min(
                match.end("value"), starts[index + 1] if index + 1 < len(starts) else len(text)
            )
            value = text[match.start("value") : end]
            if end < match.end("value"):
                value = value.rstrip("&|")
            kind = label_kind(match.group("label"))
            if span := _bare_secret(value, match.start("value"), kind):
                yield span
    for match in patterns.BEARER.finditer(text):
        yield match.start("value"), match.end("value")
    for start in starts:
        match = patterns.QUOTED_SECRET.match(text, start)
        if match is not None and (
            span := labeled_secret(match.group("value"), match.group("label"))
        ):
            value_start = match.start("value")
            yield value_start + span[0], value_start + span[1]
