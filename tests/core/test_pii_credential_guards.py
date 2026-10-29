# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provide single measured assertion anchors for multilingual credential boundaries."""

from datakeel.core.pii import detect_pii, redact_pii


def test_credential_url_boundary_cannot_leak_userinfo() -> None:
    """A Chinese-adjacent credential URL must outrank the IP and email within it."""
    value = "ftp://reader:p4ssword@" + f"{203}.0.113.7/pub"
    assert redact_pii("地址是" + value + "\uff09") == "地址是[CREDENTIAL_URL]\uff09"
    assert [item.type for item in detect_pii("地址是" + value)] == ["credential_url"]


def test_credential_label_boundary_cannot_leak_password() -> None:
    """Both quoted and unquoted label paths must recognize preceding Chinese prose."""
    assert redact_pii("密码是password=p4ssword") == "密码是password=[SECRET]"
    assert redact_pii('配置里写api_key="q7R8s9T0"就行') == '配置里写api_key="[SECRET]"就行'
    assert redact_pii('密码是password="long secret !@#"') == '密码是password="[SECRET]"'


def test_bearer_boundary_cannot_leak_token() -> None:
    """Bearer tokens need the same multilingual left boundary as credential labels."""
    value = "a1B2c3D4" * 4
    assert redact_pii("认证是Bearer " + value) == "认证是Bearer [SECRET]"


def test_privacy_prefilters_preserve_minimum_numeric_and_secret_shapes() -> None:
    """Necessary-character filters cannot exclude short valid numbers or credential families."""
    samples = {
        "+12 34 56 78": "phone",
        "AKIA" + "A1B2C3D4" * 2: "secret",
        "ghr_" + "a1B2c3D4" * 4: "secret",
        "eyJ" + "a1B2c3D4" * 2 + "." + "a1B2c3D4" * 2 + "." + "a1B2c3D4" * 2: "secret",
        'API_KEY="q7R8s9T0"': "secret",
    }
    for value, kind in samples.items():
        assert [item.type for item in detect_pii(value)] == [kind]
