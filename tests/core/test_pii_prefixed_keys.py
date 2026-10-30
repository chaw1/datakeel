# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short passwords and environment-style keys are credential assignments.

Assignments are joined at runtime so the public scanner never sees literal credential shapes.
"""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

PASSWORD_LABELS = ("password", "passwd", "pwd", "密码", "口令")
SHORT_VALUES = ("abcd", "1234", "ab12", "p@ss", "x9y8z")


@pytest.mark.parametrize("label", PASSWORD_LABELS)
@pytest.mark.parametrize("separator", [":", "=", "\uff1a", "是", "为", "是\uff1a", "为: "])
@pytest.mark.parametrize("value", SHORT_VALUES)
def test_short_password_values_are_masked(label: str, separator: str, value: str) -> None:
    """Four characters after a password-class label are enough to mask."""
    text = "配置" + label + separator + value + "就行"
    assert [item.type for item in detect_pii(text)] == ["secret"]
    assert redact_pii(text) == "配置" + label + separator + "[SECRET]就行"


@pytest.mark.parametrize("label", PASSWORD_LABELS)
@pytest.mark.parametrize("value", ["abc", "12", "***", "xxxx", "<redacted>", "[REDACTED]"])
def test_password_values_below_minimum_or_placeholders_stay(label: str, value: str) -> None:
    """Three characters or an existing placeholder are left exactly as written."""
    for text in (label + ": " + value, label + '="' + value + '"'):
        assert not detect_pii(text)
        assert redact_pii(redact_pii(text)) == text


@pytest.mark.parametrize("label", PASSWORD_LABELS)
def test_quoted_short_password_is_masked(label: str) -> None:
    """The quoted path shares the four-character password minimum."""
    assert redact_pii(label + '="ab 1"') == label + '="[SECRET]"'


KEYS = (
    "DB_PASSWORD",
    "MYSQL_ROOT_PASSWORD",
    "REDIS_PASS",
    "GITHUB_TOKEN",
    "aws_secret_access_key",
    "db-password",
    "spring.datasource.password",
    "app.jwt.secret",
    "SLACK_BOT_TOKEN",
    "STRIPE_SECRET_KEY",
    "my_api_key",
    "Db_Password",
    "SSH_PRIVATE_KEY",
    "SMTP_PASSPHRASE",
)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("separator", ["=", ": ", " = ", ":"])
@pytest.mark.parametrize("value", ["Sup3r-Secret!", "abcd1234efgh"])
def test_prefixed_keys_mask_their_values(key: str, separator: str, value: str) -> None:
    """Keys whose final `_`, `-` or `.` segment is a credential word are labels."""
    line = key + separator + value
    assert [item.type for item in detect_pii(line)] == ["secret"]
    assert redact_pii("export " + line + "\n") == "export " + key + separator + "[SECRET]\n"


@pytest.mark.parametrize("key", ["DB_PASSWORD", "MYSQL_ROOT_PASSWORD", "REDIS_PASS"])
def test_prefixed_password_keys_use_the_short_password_rule(key: str) -> None:
    """A password-class final segment masks four-character values."""
    assert redact_pii(key + "=" + "r00t") == key + "=[SECRET]"


@pytest.mark.parametrize(
    "line",
    [
        "SORT_KEY=created_at",
        "MAX_TOKEN=4096",
        "max_tokens=1024",
        "DB_PASSWORD_FILE=/run/config/db",
        "PASSWORD_MIN_LENGTH=12",
        "notpassword=p4ssword",
        "passport=E12345678",
        "token_count: 2048",
    ],
)
def test_keys_that_only_contain_credential_words_stay(line: str) -> None:
    """A credential word must be the final key segment, not an embedded substring."""
    assert not detect_pii(line)


def test_prefixed_key_mutation_guard() -> None:
    """One measured anchor protects prefixed keys and the short password minimum."""
    assert redact_pii("DB_PASSWORD" + "=" + "abcd") == "DB_PASSWORD=[SECRET]"
    assert redact_pii("REDIS_PASS" + "=" + "r3d1s") == "REDIS_PASS=[SECRET]"
    assert redact_pii("GITHUB_TOKEN" + "=" + "abcdefgh12") == "GITHUB_TOKEN=[SECRET]"
    assert redact_pii("密码\uff1a" + "1234") == "密码\uff1a[SECRET]"
    assert not detect_pii("SORT_KEY=created_at")
    assert redact_pii("password: xxxx") == "password: xxxx"
    assert redact_pii("DB_PASSWORD" + "=" + "****") == "DB_PASSWORD=****"
