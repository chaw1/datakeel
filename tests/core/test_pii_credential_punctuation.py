# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve prose punctuation while enclosing complete credential URL userinfo."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize(
    ("text", "expected", "value", "kind"),
    [
        (
            "备注\uff08client_secret=RiekloLRujT4lVI\uff09记得改。",
            "备注\uff08client_secret=[SECRET]\uff09记得改。",
            "RiekloLRujT4lVI",
            "secret",
        ),
        (
            "密码\uff1aAbc12345x——别外传",
            "密码\uff1a[SECRET]——别外传",
            "Abc12345x",
            "secret",
        ),
        (
            "地址是ftp://u:Passw0rd9@db.example.com……",
            "地址是[CREDENTIAL_URL]……",
            "ftp://u:Passw0rd9@db.example.com",
            "credential_url",
        ),
    ],
)
def test_reported_prose_punctuation_survives_exact_credential_redaction(
    text: str, expected: str, value: str, kind: str
) -> None:
    """Each reported failure keeps its surrounding punctuation outside the finding."""
    findings = detect_pii(text)
    assert [(item.type, item.start, item.end) for item in findings] == [
        (kind, text.index(value), text.index(value) + len(value))
    ]
    assert redact_pii(text) == expected


@pytest.mark.parametrize("label", ["password=", "api_key:", "密码\uff1a", "口令为"])
@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ("\uff08", "\uff09"),
        ("配置", "\uff08说明\uff09"),
        ("配置", "\uff09继续"),
        ("配置", "…"),
        ("配置", "…继续"),
        ("配置", "—"),
        ("配置", "—继续"),
    ],
)
def test_bare_credential_keeps_surrounding_fullwidth_and_prose_punctuation(
    label: str, prefix: str, suffix: str
) -> None:
    """The secret span stops before fullwidth parentheses, ellipses and em dashes."""
    value = "Qwerty123!@#"
    leading = prefix + label
    text = leading + value + suffix
    findings = detect_pii(text)
    assert [(item.type, item.start, item.end) for item in findings] == [
        ("secret", len(leading), len(leading) + len(value))
    ]
    assert redact_pii(text) == leading + "[SECRET]" + suffix


@pytest.mark.parametrize("scheme", ["postgres", "ftp", "https"])
@pytest.mark.parametrize(
    "userinfo",
    [
        "reader:p4ssword",
        "reader:中文口令",
        "reader:p(ass)word",
        "reader:p'assword",
        "reader:p%40ssword",
        "reader:p\uff08ass\uff09word",
        "reader:p…ass—word",
        "reader:密钥\uff08口令\uff09…—",
    ],
)
@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ("\uff08", "\uff09"),
        ("地址是", "\uff08说明\uff09"),
        ("地址是", "\uff09继续"),
        ("地址是", "…"),
        ("地址是", "…继续"),
        ("地址是", "—"),
        ("地址是", "—继续"),
    ],
)
def test_credential_url_keeps_prose_punctuation_and_masks_complete_userinfo(
    scheme: str, userinfo: str, prefix: str, suffix: str
) -> None:
    """Host/path prose boundaries never restrict Unicode or punctuation in userinfo."""
    value = scheme + "://" + userinfo + "@example.org/data"
    text = prefix + value + suffix
    findings = detect_pii(text)
    assert [(item.type, item.start, item.end) for item in findings] == [
        ("credential_url", len(prefix), len(prefix) + len(value))
    ]
    assert redact_pii(text) == prefix + "[CREDENTIAL_URL]" + suffix


@pytest.mark.parametrize("value", ["Qwerty123\uff08tail\uff09", "Qwerty123…tail", "Qwerty123—tail"])
def test_quoted_password_keeps_punctuation_inside_the_secret(value: str) -> None:
    """An explicit quote keeps interior punctuation in the labelled password span."""
    text = '密码:"' + value + '"…继续'
    findings = detect_pii(text)
    assert len(findings) == 1
    assert text[findings[0].start : findings[0].end] == value
    assert redact_pii(text) == '密码:"[SECRET]"…继续'


def test_shared_prose_punctuation_mutation_guard() -> None:
    """Both credential paths preserve punctuation from the same shared stop set."""
    for suffix in ("\uff08说明\uff09", "\uff09", "……", "——"):
        assert redact_pii("密码:Abc12345x" + suffix) == "密码:[SECRET]" + suffix
        url = "ftp://u:Passw0rd9@example.org/data"
        assert redact_pii(url + suffix) == "[CREDENTIAL_URL]" + suffix
