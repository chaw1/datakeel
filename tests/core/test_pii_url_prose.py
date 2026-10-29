# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep credentials private without erasing adjacent CJK instructions."""

import pytest

from datakeel.core.pii import detect_pii, redact_pii


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "mysql", "redis", "ftp", "https"])
@pytest.mark.parametrize("prefix", ["连接串 ", "配置", "「", "《", '"', "Use "])
@pytest.mark.parametrize(
    "suffix",
    [
        "记得改。",
        "」记得改。",
        "《说明》",
        "、接下来",
        "「说明」",
        "》继续",
        "。",
        "中文",
        "\U00020000",
        "カナ",
        "한글",
    ],
)
def test_url_matrix_stops_at_cjk_prose_and_keeps_the_complete_userinfo(
    scheme: str, prefix: str, suffix: str
) -> None:
    """Every surrounding instruction survives while credentials disappear in one span."""
    value = scheme + "://reader:p4ssword@" + f"{203}.0.113.5/0"
    text = prefix + value + suffix
    findings = detect_pii(text)
    assert [item.type for item in findings] == ["credential_url"]
    assert text[findings[0].start : findings[0].end] == value
    assert redact_pii(text) == prefix + "[CREDENTIAL_URL]" + suffix


@pytest.mark.parametrize("password", ["中文口令", "p(ass)word", "p'assword", "p%40ssword"])
def test_userinfo_keeps_unicode_and_punctuation_before_the_prose_boundary(password: str) -> None:
    """Only the host/path boundary stops at CJK; userinfo must remain fully enclosed."""
    value = "postgres://reader:" + password + "@example.org/data"
    assert redact_pii(value + "」记得改。") == "[CREDENTIAL_URL]」记得改。"


def test_url_prose_guard_preserves_suffix_without_leaking_credentials() -> None:
    """Removing the suffix boundary must fail this independent mutation anchor."""
    value = "postgres://reader:中文口令@" + f"{203}.0.113.5/0"
    for suffix in ("记得改。", "」记得改。", "《说明》", "、继续", "\U00020000"):
        assert redact_pii(value + suffix) == "[CREDENTIAL_URL]" + suffix
