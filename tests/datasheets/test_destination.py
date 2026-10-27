# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline destination inspection mirrors the existing extraction approval policy."""

import pytest

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ValidationError
from datakeel.datasheets.destination import is_external_destination, model_destination


@pytest.mark.parametrize(
    ("destination", "external"),
    [
        (None, False),
        ("http://localhost/v1", False),
        ("http://localhost./v1", False),
        ("http://127.0.0.1/v1", False),
        ("http://[::1]/v1", False),
        ("https://fixture.example.test/v1", True),
        ("https://127.0.0.1.example.test/v1", True),
        ("http://[::2]/v1", True),
    ],
)
def test_externality_uses_only_literal_destination_without_dns(
    destination: str | None,
    *,
    external: bool,
) -> None:
    """A host that merely resembles loopback remains an explicitly approved outbound call."""
    assert is_external_destination(destination) is external


@pytest.mark.parametrize(
    "destination",
    [
        "file:///fixture",
        "ftp://fixture.example.test/v1",
        "https://fixture.example.test?key=value",
        "https://name:password@fixture.example.test/v1",
        "https://fixture.example.test/#fragment",
    ],
)
def test_model_destination_rejects_unsupported_scheme_and_embedded_credentials(
    monkeypatch: pytest.MonkeyPatch,
    destination: str,
) -> None:
    """The frozen public plan never stores authentication carried inside a URL."""
    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", destination)
    with pytest.raises(ValidationError, match="embedded credentials"):
        model_destination(ConversationCreate(provider="openai"))


def test_fake_destination_ignores_real_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The offline path never resolves or constructs a configured model destination."""
    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", "not-a-url")
    assert model_destination(ConversationCreate()) is None


def test_explicit_destination_is_frozen_without_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review and execution use the same normalized destination string."""
    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", "https://fixture.example.test/v1/")
    assert (
        model_destination(ConversationCreate(provider="openai"))
        == "https://fixture.example.test/v1"
    )
