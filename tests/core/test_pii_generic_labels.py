# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generic English labels mask only credential-like values; prose stays unchanged."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii
from datakeel.core.pii_credentials import credential_like, is_placeholder, label_kind

PROSE = (
    "The secret: practice every day.",
    "The secret: practice.",
    "Our secret: consistency!",
    "The key: patience, not talent.",
    "Key: value",
    "The key: self-discipline.",
    "One key: well-being matters.",
    "Auth: required for every request.",
    "auth: optional",
    "The token: gratitude?",
    "token: none",
    "The secret: responsibilities.",
    "The key: internationalization.",
    "The secret: don't panic.",
    "key: Hello",
)
CREDENTIALS = (
    "abc123XYZ789",
    "s3cr3t-v4lue",
    "Qwerty123!@#",
    "9f86d081884c7d659a2feaa0c55ad015",
    "dXNlcjpwYXNzd29yZA==",
    "QkVBUkVSVE9LRU5WQUxVRQ",
    "user:pass1",
    "kTqWzRbXyPmLsVnD",
)


@pytest.mark.parametrize("text", PROSE)
def test_generic_label_prose_remains_unchanged(text: str) -> None:
    """Ordinary sentences after secret/key/auth/token never become findings."""
    assert not detect_pii(text)
    assert redact_pii(text) == text


@pytest.mark.parametrize("label", ["secret", "token", "key", "auth", "Secret", "KEY"])
@pytest.mark.parametrize("separator", [": ", "=", "\uff1a", " = "])
@pytest.mark.parametrize("value", CREDENTIALS)
def test_generic_label_masks_credential_like_values(label: str, separator: str, value: str) -> None:
    """Mixed-class, hex and base64 values after a generic label are masked completely."""
    text = f"Use {label}{separator}{value} then"
    assert [item.type for item in detect_pii(text)] == ["secret"]
    assert redact_pii(text) == f"Use {label}{separator}[SECRET] then"


@pytest.mark.parametrize("label", ["secret", "token", "key", "auth"])
def test_generic_label_quoted_value_obeys_the_same_shape_rule(label: str) -> None:
    """Quoted prose keeps its words while quoted credentials are masked."""
    assert not detect_pii(f'The {label}: "practice every day"')
    assert not detect_pii(f'{{"{label}": "practice"}}')
    assert redact_pii(f'{{"{label}": "a1B2c3D4e5"}}') == f'{{"{label}": "[SECRET]"}}'


@pytest.mark.parametrize("label", ["password", "passwd", "pwd", "密码", "口令"])
@pytest.mark.parametrize("separator", [": ", "\uff1a", "是", "为", "是\uff1a"])
def test_password_labels_ignore_the_generic_shape_rule(label: str, separator: str) -> None:
    """Password-class labels still mask single-class words."""
    text = f"{label}{separator}practice"
    assert redact_pii(text) == f"{label}{separator}[SECRET]"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("practice", False),
        ("practice.", False),
        ("self-discipline", False),
        ("responsibilities", False),
        ("abc def12", False),
        ("ab1!", False),
        ("abcdefgh", False),
        ("12345678", True),
        ("abc12345", True),
        ("abcdefg#", True),
        ("abcdefg!", False),
        ("deadbeefdeadbeef", True),
        ("QkVBUkVSVE9LRU5WQUxVRQ", True),
        ("0123456789012345", True),
        ("kTqWzRbXyPmLsVnD", True),
        ("internationalization", False),
    ],
)
def test_credential_like_shape_rule(value: str, *, expected: bool) -> None:
    """Two classes from eight characters, or sixteen hex/base64 characters, look issued."""
    assert credential_like(value) is expected


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("secret", "generic"),
        ("TOKEN", "generic"),
        ("key", "generic"),
        ("auth", "generic"),
        ("password", "password"),
        ("DB_PASSWORD", "password"),
        ("redis.pass", "password"),
        ("密码", "password"),
        ("api_key", "named"),
        ("GITHUB_TOKEN", "named"),
        ("jwt-secret", "named"),
        ("STRIPE_SECRET_KEY", "named"),
        ("密钥", "named"),
        ("sort_key", None),
        ("max_tokens", None),
        ("", None),
    ],
)
def test_label_kind_uses_the_final_segment(label: str, kind: str | None) -> None:
    """Final key segments choose the password, named or generic value rule."""
    assert label_kind(label) == kind


@pytest.mark.parametrize(
    "value", ["***", "xxxx", "<redacted>", "[REDACTED]", "[secret]", "${DB_PASSWORD}", "••••"]
)
def test_existing_placeholders_are_not_masked_again(value: str) -> None:
    """Masks and template references are not treated as new credentials."""
    assert is_placeholder(value)
    for label in ("password: ", "DB_PASSWORD=", "token: "):
        assert redact_pii(label + value) == label + value


def test_generic_label_mutation_guard() -> None:
    """One measured anchor protects prose words, hyphenated words and credential recall."""
    assert redact_pii("The secret: practice every day.") == "The secret: practice every day."
    assert redact_pii("The key: self-discipline.") == "The key: self-discipline."
    assert redact_pii("The secret: responsibilities.") == "The secret: responsibilities."
    assert redact_pii("token: abc123XYZ789") == "token: [SECRET]"
    assert redact_pii("key: QkVBUkVSVE9LRU5WQUxVRQ") == "key: [SECRET]"
    assert redact_pii("auth: kTqWzRbXyPmLsVnD") == "auth: [SECRET]"
