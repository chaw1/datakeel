# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise multilingual assignment labels independently from vendor token prefixes."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii

LABELS = (
    "password",
    "passwd",
    "pwd",
    "api_key",
    "API-KEY",
    "secret",
    "token",
    "client_secret",
    "access_token",
    "密码",
    "口令",
    "密钥",
    "令牌",
    "访问密钥",
    "访问令牌",
)


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("separator", [":", "\uff1a", "=", "是", "为"])
@pytest.mark.parametrize("prefix", ["", "配置", "\uff08", '"', "[", "Use "])
@pytest.mark.parametrize("suffix", ["", "就行", "。", "」", "》", "]", ")", " then"])
def test_assignment_matrix_masks_complete_value_and_preserves_surroundings(
    label: str, separator: str, prefix: str, suffix: str
) -> None:
    """Each label, separator and prose adjacency retains only the nonsecret context."""
    value = "Qwerty123" + "!@#"
    text = f"{prefix}{label}{separator}{value}{suffix}"
    assert [match.type for match in detect_pii(text)] == ["secret"]
    assert redact_pii(text) == f"{prefix}{label}{separator}[SECRET]{suffix}"


@pytest.mark.parametrize(
    "text",
    [
        "password字段",
        "密码长度至少 8 位",
        "请修改密码。",
        "notpassword=1",
        "notpassword=Qwerty123!",
        "密码\uff1a",
        "token\uff1a   ",
        "口令是 !!!!!!!!",
        "密钥为 --------",
        'api_key\uff1a"!@#$%^&*"',
    ],
)
def test_assignment_without_a_secret_stays_negative(text: str) -> None:
    """Labels require an actual assignment value containing letters or digits."""
    assert not detect_pii(text)


@pytest.mark.parametrize(
    "label", ["密码", "口令", "密钥", "令牌", "访问密钥", "pwd", "secret", "token"]
)
def test_quoted_and_typed_labels_mask_special_characters(label: str) -> None:
    """Typed values and serialized assignments share the multilingual label registry."""
    value = "Qwerty123" + "!@#(tail)"
    assert redact_pii(f'{label}\uff1a"{value}"') == f'{label}\uff1a"[SECRET]"'
    assert redact_pii(value, label=label) == "[SECRET]"
    assert redact_pii(f"{label}\uff1a{value}」") == f"{label}\uff1a[SECRET]」"


def test_multilingual_assignment_guard_cannot_leave_a_secret_suffix() -> None:
    """A single measured test protects labels, separators and the full punctuation suffix."""
    for label in LABELS:
        value = "Qwerty123" + "!@#(tail)"
        assert redact_pii(f"{label}\uff1a{value}就行") == f"{label}\uff1a[SECRET]就行"
    assert not detect_pii("密码\uff1a!!!!!!!!")
    assert redact_pii("密码是password=p4ssword") == "密码是password=[SECRET]"


@pytest.mark.parametrize("prefix", ["x", "1", "_"])
@pytest.mark.parametrize("label", ["密码", "口令", "访问密钥"])
def test_chinese_label_after_ascii_context_keeps_script_boundary(prefix: str, label: str) -> None:
    """Chinese labels remain separate words beside ASCII prose or counters."""
    assert redact_pii(f"{prefix}{label}:Qwerty123!") == f"{prefix}{label}:[SECRET]"


@pytest.mark.parametrize(
    ("prefix", "suffix"), [("[(", ")]"), ("{[", "]}"), ("([", "])"), ("[({", "})]")]
)
def test_nested_delimiters_survive_complete_secret_redaction(prefix: str, suffix: str) -> None:
    """Mixed bracket orders cannot be consumed by a one-pass suffix trim."""
    assert redact_pii(f"{prefix}密码:Qwerty123!{suffix}") == f"{prefix}密码:[SECRET]{suffix}"


def test_placeholder_and_nested_delimiter_guard_keeps_only_the_secret_span() -> None:
    """Already-redacted content remains clean and nested punctuation retains its order."""
    for placeholder in ("[SECRET]", "[REDACTED]", "[PHONE]"):
        assert not detect_pii("password:" + placeholder)
    assert redact_pii("[(密码:Qwerty123!)]") == "[(密码:[SECRET])]"
    assert redact_pii("password:Qwerty123!,token:Abcd1234!") == "password:[SECRET],token:[SECRET]"
    value = "postgres://u:p@example.org/0"
    assert redact_pii("password:Qwerty123!," + value) == "password:[SECRET],[CREDENTIAL_URL]"


@pytest.mark.parametrize("separator", [",", ";", "\uff0c", "\uff1b", "&", "|"])
def test_adjacent_credentials_cannot_consume_each_others_labels(separator: str) -> None:
    """Independent assignments remain independent findings, including before URL priority."""
    text = f"密码:Qwerty123!{separator}token是Abcd1234!"
    assert redact_pii(text) == f"密码:[SECRET]{separator}token是[SECRET]"
    assert [match.type for match in detect_pii(text)] == ["secret", "secret"]


def test_containing_secret_guard_masks_every_fragment_around_an_embedded_url() -> None:
    """Inner URL priority must not expose parts of an explicitly labelled outer password."""
    value = "Qwerty123! https://u:p@example.org/0"
    assignment = "password" + "="
    assert redact_pii(assignment + '"' + value + '"') == assignment + '"[SECRET]"'
    assert redact_pii("password:Qwerty123!&token:Abcd1234!") == "password:[SECRET]&token:[SECRET]"


def test_crossing_credential_spans_cover_every_fragment() -> None:
    """A partial bare-password match and a crossing URL must redact their entire union."""
    for userinfo in ("中文口令", "p'assword", "p,assword", "p;assword"):
        for separator in ("&", "|"):
            url = "postgres://" + f"u:{userinfo}@example.org/0"
            text = "密码:Qwerty123!" + separator + url + "」记得改。"
            assert redact_pii(text) == "密码:[SECRET]」记得改。"
            matches = detect_pii(text)
            assert len(matches) == 1
            assert matches[0].type == "secret"
            assert text[matches[0].start : matches[0].end] == "Qwerty123!" + separator + url


def test_credential_url_usernames_cannot_capture_prose_as_quoted_assignments() -> None:
    """A label-like URL username is userinfo, even with quotes inside its password."""
    for username in ("password", "token", "api_key"):
        for quote in ("'", '"'):
            url = "postgres://" + username + ":" + quote + "p4ssword@example.org/0"
            suffix = "」记得改。" + quote
            assert redact_pii(url + suffix) == "[CREDENTIAL_URL]" + suffix
            assert redact_pii("密码:Qwerty123!&" + url + suffix) == "密码:[SECRET]" + suffix
            following = "」记得改。 密码:" + quote + "Abcd1234!中文" + quote
            expected = "[CREDENTIAL_URL]」记得改。 密码:" + quote + "[SECRET]" + quote
            assert redact_pii(url + following) == expected
