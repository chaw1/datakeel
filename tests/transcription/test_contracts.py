# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate configuration, cache semantics and portable replay without credential access."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.transcription_models import (
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
)
from datakeel.transcription.adapters import FakeTranscriber, ReplayTranscriber
from datakeel.transcription.cache import cache_key, profile_digest
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.loader import contracts_path, get_profile, load_profile, read_recording
from datakeel.transcription.policy import is_external, target_host

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.transcription_models import ImageInput, TranscriptionResult


@pytest.mark.parametrize(
    "change",
    [
        {"api_key": "synthetic-secret"},
        {"backend": "unknown"},
        {"mode": "auto"},
        {"cloud_locator": True},
        {"prompt_version": "image-transcription-unknown"},
        {"api_key_env": "not a variable name"},
        {"base_url": "https://user:password@fixture.invalid/v1"},
        {"base_url": "https://fixture.invalid?query=synthetic"},
        {"base_url": "https://fixture.invalid#fragment"},
        {"base_url": "file:///fixture"},
        {"request_parameters": {"api_key": "hidden"}},
        {"request_parameters": {"enable_thinking": "false"}},
        {"request_parameters": {"num_ctx": True}, "interface": "ollama"},
        {"request_parameters": {"num_ctx": 16384}},
        {"request_parameters": {"reasoning_effort": "unlimited"}},
        {"request_parameters": {"reasoning_effort": "high"}, "interface": "ollama"},
        {"backend": "ocr", "mode": "vlm"},
        {"backend": "vlm"},
        {"backend": "replay"},
    ],
)
def test_profile_when_unsafe_or_unsupported_rejects(change: dict[str, object]) -> None:
    """Reject secrets, unrestricted options and intentionally deferred routes."""
    with pytest.raises(ModelValidationError):
        TranscriptionProfile.model_validate(
            {"id": "fixture", "backend": "fake", "model": "fixture", **change}
        )


def test_profiles_when_bundled_load_all_offline() -> None:
    """Keep every packaged example valid and the demo bound to measured Qwen text."""
    for path in (contracts_path() / "transcription-profiles").glob("*.yaml"):
        assert load_profile(path).id == path.stem
    assert get_profile().recording == "recordings/qwen-image.yaml"
    assert read_recording(get_profile("fake")) == (None, None)
    digest, recording = read_recording(get_profile())
    assert digest is not None
    assert len(digest) == 64
    assert recording is not None
    assert len(recording.records) == 60


def test_loader_when_missing_or_invalid_reports_safe_errors(tmp_path: Path) -> None:
    """Do not echo rejected credential values from YAML parser failures."""
    path = tmp_path / "bad.yaml"
    with pytest.raises(ValidationError):
        load_profile(path)
    path.write_text("id: fixture\nbackend: fake\nmodel: fixture\napi_key: synthetic-secret\n")
    with pytest.raises(ValidationError) as captured:
        load_profile(path)
    assert "synthetic-secret" not in str(captured.value)
    profile = get_profile().model_copy(update={"recording": str(path)})
    with pytest.raises(ValidationError):
        read_recording(profile)
    with pytest.raises(NotFoundError):
        get_profile("missing")


@pytest.mark.parametrize(
    "change",
    [
        {"model": "different"},
        {"backend": "vlm"},
        {"prompt_version": "next"},
        {"mode": "vlm"},
        {"request_parameters": {"enable_thinking": False}},
        {"ocr_model_version": "next"},
        {"max_output_tokens": 20},
    ],
)
def test_cache_when_transcription_semantics_change_changes_identity(
    change: dict[str, object],
) -> None:
    """Keep model, OCR model, mode, prompt and output options in the cache boundary."""
    profile = get_profile("fake")
    assert cache_key("a" * 64, profile) != cache_key("a" * 64, profile.model_copy(update=change))


def test_cache_when_replay_or_override_changes_and_labels_do_not() -> None:
    """Bind replay bytes and per-file routes while ignoring identifier and credential naming."""
    profile = get_profile()
    renamed = profile.model_copy(update={"id": "renamed", "api_key_env": "RENAMED_KEY"})
    assert profile_digest(profile) == profile_digest(renamed)
    assert cache_key("a" * 64, profile, "first") != cache_key("a" * 64, profile, "second")
    assert cache_key("a" * 64, profile, mode="ocr") != cache_key("a" * 64, profile)
    assert cache_key("a" * 64, profile) != cache_key("b" * 64, profile)


@pytest.mark.parametrize(
    ("url", "external"),
    [
        ("http://127.0.0.1:11434", False),
        ("http://[::1]:11434", False),
        ("http://localhost.:11434", False),
        ("http://fixture.invalid:11434", True),
    ],
)
def test_transfer_when_endpoint_varies_classifies_without_dns(url: str, *, external: bool) -> None:
    """Only literal loopback endpoints avoid outbound approval."""
    profile = get_profile("bailian-qwen35-flash").model_copy(update={"base_url": url})
    assert is_external(profile) == external
    assert target_host(profile) is not None
    assert is_external(get_profile("fake")) is False
    assert target_host(get_profile("fake")) is None
    assert is_external(profile.model_copy(update={"base_url": None})) is True


def test_replay_when_hash_matches_uses_archive_without_profile_key(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay metadata and failures share the same hash-only lookup without reading settings."""
    record = TranscriptionRecord(
        **transcription_result.model_dump(), image_hash=image_input.image_hash
    )
    archive = TranscriptionRecording(
        model="recorded",
        recorded_at="2026-10-24",
        prompt_version="v1",
        source="fixture",
        records=(record,),
    )
    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", lambda: pytest.fail("settings")
    )
    for profile in (get_profile(), get_profile("fake")):
        with create_transcriber(profile, recording=archive) as adapter:
            assert adapter.transcribe(image_input, "ocr").text == record.text
    adapter = ReplayTranscriber(archive)
    with pytest.raises(ValidationError, match="no visual-model"):
        adapter.transcribe(image_input, "vlm")
    with pytest.raises(ValidationError, match="content hash"):
        adapter.transcribe(image_input.model_copy(update={"image_hash": "0" * 64}))
    with pytest.raises(ValidationError, match="dimensions"):
        adapter.transcribe(image_input.model_copy(update={"width": 121}))
    with pytest.raises(ModelValidationError, match="duplicate"):
        TranscriptionRecording(**archive.model_dump(exclude={"records"}), records=(record, record))
    with create_transcriber(get_profile("fake")) as scripted:
        assert scripted.transcribe(image_input).backend == "fake"
    fake = FakeTranscriber((transcription_result,))
    assert fake.transcribe(image_input) == transcription_result


def test_replay_when_file_selects_ocr_uses_recorded_lines_instead_of_visual_text(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """Mode overrides change the actual transcript as well as its route and provenance."""
    record = TranscriptionRecord(
        **transcription_result.model_copy(
            update={"backend": "vlm", "text": "A different structural transcript"}
        ).model_dump(),
        image_hash=image_input.image_hash,
    )
    archive = TranscriptionRecording(
        model="recorded",
        recorded_at="2026-10-24",
        prompt_version="v1",
        source="fixture",
        records=(record,),
    )
    adapter = ReplayTranscriber(archive, "vlm")
    assert adapter.transcribe(image_input).text == record.text
    result = adapter.transcribe(image_input, "ocr")
    assert result.text == transcription_result.text
    assert result.backend == "ocr"
    assert result.model == "rapidocr-3.10.0-defaults"


def test_replay_when_recording_loaded_in_factory_uses_packaged_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default factory can resolve packaged replay and rejects a missing frozen archive."""
    with create_transcriber(get_profile()) as adapter:
        assert isinstance(adapter, ReplayTranscriber)
    monkeypatch.setattr("datakeel.transcription.factory.read_recording", lambda _: (None, None))
    with (
        pytest.raises(ValidationError, match="requires a recording"),
        create_transcriber(get_profile()),
    ):
        pytest.fail("Must not yield an unconfigured adapter")


def test_profile_loader_when_prompt_version_unknown_rejects(tmp_path: Path) -> None:
    """Reject unknown prompt semantics when loading YAML before any transcriber exists."""
    path = tmp_path / "unsupported.yaml"
    path.write_text("id: fixture\nbackend: fake\nmodel: fixture\nprompt_version: unknown-version\n")
    with pytest.raises(ValidationError, match="invalid transcription profile"):
        load_profile(path)
