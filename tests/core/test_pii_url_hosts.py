# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect URL userinfo even when the host is empty or starts with CJK text."""

import pytest

from datakeel.core.pii import PiiMatch, detect_pii, redact_pii


@pytest.mark.parametrize(
    ("text", "userinfo", "suffix"),
    [
        (
            "https://alice:Secr3tPass@例子.中国/x",
            "https://alice:Secr3tPass@",
            "例子.中国/x",
        ),
        (
            "ftp://bob:Hunter2Hunter2@文件服务器/pub",
            "ftp://bob:Hunter2Hunter2@",
            "文件服务器/pub",
        ),
        ("redis://:Passw0rd123@本机", "redis://:Passw0rd123@", "本机"),
        ("https://u:Pa55word9@例子.com/x", "https://u:Pa55word9@", "例子.com/x"),
    ],
)
def test_cjk_host_preserves_suffix_without_exposing_userinfo(
    text: str, userinfo: str, suffix: str
) -> None:
    """Each reported regression masks exactly the scheme and complete userinfo."""
    assert detect_pii(text) == (PiiMatch(type="credential_url", start=0, end=len(userinfo)),)
    assert redact_pii(text) == "[CREDENTIAL_URL]" + suffix


@pytest.mark.parametrize(
    ("url", "suffix"),
    [
        ("https://reader:p4ssword@", ""),
        ("redis://:Passw0rd123@", ""),
        ("postgres://reader:中文口令@", "数据库/0"),
        ("https://reader:p'assword@", "カナ.example/data"),
        ("ftp://reader:p(ass)word@", "한글/data"),
        ("mysql://reader:p%40ssword@", "\U00020000/data"),
        ("https://reader:p4ssword@", "」记得改。"),
        ("ftp://reader:p4ssword@", ", then continue"),
        ("https://reader:p4ssword@example.org/data", "记得改。"),
        ("ftp://reader:p4ssword@example.org/data", "中文主机说明"),
    ],
)
def test_empty_and_multilingual_host_boundaries_keep_exact_privacy_span(
    url: str, suffix: str
) -> None:
    """Host omission cannot reject a URL or consume the following instruction."""
    prefix = "连接地址是"
    text = prefix + url + suffix
    assert detect_pii(text) == (
        PiiMatch(type="credential_url", start=len(prefix), end=len(prefix) + len(url)),
    )
    assert redact_pii(text) == prefix + "[CREDENTIAL_URL]" + suffix


def test_cjk_and_empty_url_hosts_cannot_expose_userinfo() -> None:
    """Requiring a nonempty ASCII host must fail this mutation anchor."""
    userinfo = "https://reader:p4ssword@"
    for suffix in ("", "例子.中国/x", "」记得改。"):
        text = userinfo + suffix
        assert detect_pii(text) == (PiiMatch(type="credential_url", start=0, end=len(userinfo)),)
        assert redact_pii(text) == "[CREDENTIAL_URL]" + suffix
