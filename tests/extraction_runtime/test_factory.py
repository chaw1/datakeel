# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application construction uses offline adapters or explicitly selected credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr

from datakeel.core.errors import ValidationError
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_models import RawExtraction, Recording, RecordingRecord
from datakeel.core.settings import Settings
from datakeel.extraction_runtime.factory import create_extractor
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor
from datakeel.kg.gliner import GlinerExtractor

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import TextBlock


def _profile(**fields: object) -> ExtractionProfile:
    return ExtractionProfile.model_validate(
        {
            "id": "fixture",
            "extractor": "llm",
            "provider": "openai",
            "model": "fixture-model",
            "base_url": "https://fixture.invalid/v1",
            "api_key_env": "SYNTHETIC_EXTRACTION_KEY",
            "output_method": "json_mode",
            **fields,
        }
    )


def test_factory_when_fake_does_not_read_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline construction cannot inspect credentials or construct a network client."""

    def forbidden() -> Settings:
        pytest.fail("Offline extraction read environment settings")

    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    with create_extractor(_profile(extractor="fake", provider="fake")) as adapter:
        assert isinstance(adapter, FakeExtractor)


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("provider", ["replay", "fake"])
def test_factory_when_replay_resolves_explicit_or_bundled_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    block: TextBlock,
    provider: str,
    *,
    absolute: bool,
) -> None:
    """Replay accepts bundled contract-relative paths and explicit local recording files."""
    path = tmp_path / "fixture.yaml"
    recording = Recording(
        model="fixture-model",
        recorded_at="2026-01-01",
        prompt_version="fixture-v1",
        source="Synthetic fixture",
        records=(RecordingRecord(text_hash=block.content_hash, output=RawExtraction()),),
    )
    path.write_text(recording.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("datakeel.extraction_runtime.factory.contracts_path", lambda: tmp_path)
    profile = _profile(
        extractor=provider, provider=provider, recording=str(path) if absolute else path.name
    )
    with create_extractor(profile) as adapter:
        assert isinstance(adapter, ReplayExtractor)
        assert adapter.recording == recording


@pytest.mark.parametrize("local", [False, True])
def test_factory_when_llm_selected_resolves_only_explicit_key_and_preserves_injected_client(
    monkeypatch: pytest.MonkeyPatch, schema: KGSchema, block: TextBlock, *, local: bool
) -> None:
    """Local anonymous endpoints use a placeholder; external calls require a selected secret."""
    settings = Settings.model_construct(provider_timeout=3)
    names: list[str | None] = []

    def selected(self: Settings, name: str | None) -> SecretStr | None:
        names.append(name)
        return None if local else SecretStr("synthetic-selected-key")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == 3
        assert request.headers["authorization"] == (
            "Bearer not-required" if local else "Bearer synthetic-selected-key"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"entities":[],"relations":[]}'}}
                ]
            },
        )

    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", lambda: settings)
    monkeypatch.setattr(Settings, "extraction_key", selected)
    profile = _profile(base_url="http://localhost/v1" if local else "https://fixture.invalid/v1")
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with create_extractor(profile, client=client) as adapter:
            adapter.extract(block, schema)
        assert not client.is_closed
    assert names == ["SYNTHETIC_EXTRACTION_KEY"]


def test_factory_when_external_key_missing_fails_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never let a vendor SDK discover an unrelated ambient credential as fallback."""
    monkeypatch.setattr(
        "datakeel.extraction_runtime.factory.get_settings", Settings.model_construct
    )
    monkeypatch.setattr(Settings, "extraction_key", lambda _self, _name: None)
    with (
        pytest.raises(ValidationError, match="No extraction API key"),
        create_extractor(_profile()),
    ):
        pytest.fail("A missing external key must stop before yielding an adapter")


def test_factory_when_creating_http_client_disables_proxies_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owned clients are closed with the adapter and ignore process proxy configuration."""
    original_client = httpx.Client
    clients: list[httpx.Client] = []
    options: list[dict[str, object]] = []

    def client(**kwargs: object) -> httpx.Client:
        options.append(kwargs)
        created = original_client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
        clients.append(created)
        return created

    monkeypatch.setattr(
        "datakeel.extraction_runtime.factory.get_settings", Settings.model_construct
    )
    monkeypatch.setattr(Settings, "extraction_key", lambda _self, _name: None)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.httpx.Client", client)
    with create_extractor(_profile(base_url="http://localhost/v1")):
        assert not clients[0].is_closed
    assert clients[0].is_closed
    assert options == [{"trust_env": False, "follow_redirects": False}]


@pytest.mark.parametrize("provider", ["replay", "fake"])
def test_factory_when_recording_frozen_never_reopens_changed_or_missing_file(
    block: TextBlock, schema: KGSchema, provider: str
) -> None:
    """Worker execution uses approved recording bytes even if its profile path changes."""
    frozen = Recording(
        model="scripted-fixture",
        recorded_at="2026-01-01",
        prompt_version="fixture-v1",
        source="Synthetic fixture",
        records=(
            RecordingRecord(
                text_hash=block.content_hash,
                output=RawExtraction(),
                input_tokens=17,
            ),
        ),
    )
    profile = _profile(extractor=provider, provider=provider, recording="missing-fixture.yaml")
    with create_extractor(profile, recording=frozen) as adapter:
        assert adapter.extract(block, schema).input_tokens == 17


def test_factory_when_gliner_selected_defers_optional_model_loading() -> None:
    """Constructing the optional adapter never imports its package or downloads a model."""
    with create_extractor(_profile(extractor="gliner2", provider="gliner2")) as adapter:
        assert isinstance(adapter, GlinerExtractor)
