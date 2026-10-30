# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect credential spans adjacent to multilingual prose and delimiters."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize("prefix", ["地址是", "\uff0c", "\uff08", '"', "“", "[", "Use "])
@pytest.mark.parametrize("suffix", ["。", "\uff0c继续", "\uff09", '"', "”", "]", " then"])
@pytest.mark.parametrize("scheme", ["postgres", "ftp", "https", "redis", "s3"])
def test_credential_url_adjacent_to_prose_masks_userinfo_before_contacts(
    prefix: str, suffix: str, scheme: str
) -> None:
    """The enclosing URL takes priority over an email or IP inside its credentials."""
    host = f"{203}.0.113.7" if scheme == "ftp" else "example.org"
    value = scheme + "://reader:p4ssword@" + host + "/data"
    text = prefix + value + suffix
    findings = detect_pii(text)
    assert [item.type for item in findings] == ["credential_url"]
    assert redact_pii(text) == prefix + "[CREDENTIAL_URL]" + suffix
    assert "p4ssword" not in redact_pii(text)


@pytest.mark.parametrize("prefix", ["密码是", "配置里写", "\uff0c", "\uff08", '"', "“", "Use "])
@pytest.mark.parametrize("label", ["password", "api_key", "access-token", "client_secret"])
@pytest.mark.parametrize("quoted", [False, True])
def test_labeled_credentials_adjacent_to_prose_preserve_only_label(
    prefix: str, label: str, *, quoted: bool
) -> None:
    """ASCII label boundaries accept Chinese prose without requiring inserted whitespace."""
    quote = '"' if quoted else ""
    text = f"{prefix}{label}={quote}p4ssword{quote}就行"
    assert [item.type for item in detect_pii(text)] == ["secret"]
    assert redact_pii(text) == f"{prefix}{label}={quote}[SECRET]{quote}就行"


@pytest.mark.parametrize("prefix", ["认证是", "\uff0c", "\uff08", '"', "“", "Use "])
def test_bearer_adjacent_to_prose_redacts_the_complete_token(prefix: str) -> None:
    """Bearer's left boundary follows the same ASCII rule as credential labels."""
    value = "a1B2c3D4" * 4
    assert redact_pii(prefix + "Bearer " + value + "\uff09") == prefix + "Bearer [SECRET]\uff09"


def test_quoted_password_adjacent_to_chinese_masks_special_characters() -> None:
    """The quoted-value path also recognizes Chinese adjacency independently of bare values."""
    assert redact_pii('密码是password="long secret !@#"就行') == '密码是password="[SECRET]"就行'


@pytest.mark.parametrize(
    "value",
    [
        "notpassword=p4ssword",
        "my_api_keys=p4ssword",
        "xBearer a1B2c3D4a1B2c3D4",
        "0123456789abcdef" * 4,
        "123e4567-e89b-12d3-a456-426614174000",
        "v1.2.3",
        "https://example.org/data",
    ],
)
def test_unlabelled_hashes_versions_and_label_suffixes_remain_negative(value: str) -> None:
    """Replacing Unicode boundaries must retain protection against embedded ASCII labels."""
    assert not detect_pii(value)


@pytest.mark.parametrize("password", ["p'assword", "p(ass)word", "p%40ssword", "密钥口令"])
def test_url_userinfo_punctuation_keeps_existing_credential_detection(password: str) -> None:
    """Delimiters surrounding a URL must not restrict punctuation inside its userinfo."""
    value = "https://reader:" + password + "@example.org/path"
    assert redact_pii('Use "' + value + '".') == 'Use "[CREDENTIAL_URL]".'
