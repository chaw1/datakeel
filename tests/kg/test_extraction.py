# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cover deterministic extraction, chunk boundaries and complete cache identity."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from datakeel.core.errors import ProviderError
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.harness_models import TokenUsage
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_errors import ExtractionProviderError, KGExtractionError
from datakeel.core.kg_models import ExtractionResult, RawExtraction, Recording, TextBlock
from datakeel.kg import cache
from datakeel.kg.cache import build_cache_key
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor, checked_extract
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg.policy import is_external, target_host
from datakeel.kg.prompt import extraction_prompt, output_schema
from datakeel.kg.text import chunk_text, decode_text


def _block(text: str = "Example.") -> TextBlock:
    return TextBlock(text=text, start=0, end=len(text))


def test_sentence_and_paragraph_chunks_cover_source_without_offset_drift() -> None:
    """Every emitted chunk is an exact document slice including whitespace."""
    text = "One sentence. Two sentences.\n\n第三句。第四句。\nTail without punctuation"
    chunks = chunk_text(text, 20, 4)
    positions = set()
    for block in chunks:
        assert block.text == text[block.start : block.end]
        assert len(block.text) <= 20
        positions.update(range(block.start, block.end))
    assert positions == set(range(len(text)))
    assert chunks[0].text == "One sentence. "
    assert chunk_text("", 5) == ()


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (3, -1), (3, 3)])
def test_invalid_chunk_parameters_are_rejected(size: int, overlap: int) -> None:
    """Invalid overlap cannot loop forever or silently skip content."""
    with pytest.raises(ValueError, match="Chunk size"):
        chunk_text("Example", size, overlap)


def test_utf8_decode_normalizes_combining_characters_and_rejects_bad_bytes() -> None:
    """NFC is established before calculating any text offsets."""
    assert decode_text("Jo\u0301se".encode()) == "Jóse"
    with pytest.raises(UnicodeDecodeError):
        decode_text(b"\xff")
    with pytest.raises(ValidationError):
        TextBlock(text="Example", start=0, end=3)


def test_cache_key_changes_for_model_schema_prompt_parameters_and_recording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All actual extraction semantics invalidate cache while paths cannot enter its key."""
    block, schema, profile = _block(), get_schema(), get_profile("fake")
    extractor = ExtractorRef(id="fake", version="1")
    original = build_cache_key(block, schema, profile, extractor).digest()
    variations = (
        profile.model_copy(update={"model": "another-model"}),
        profile.model_copy(update={"request_parameters": {"enable_thinking": False}}),
        profile.model_copy(update={"output_method": "json_mode"}),
        profile.model_copy(update={"chunk_size": 1234}),
        profile.model_copy(update={"chunk_overlap": 1}),
    )
    assert all(
        build_cache_key(block, schema, value, extractor).digest() != original
        for value in variations
    )
    assert (
        build_cache_key(
            block, schema.model_copy(update={"version": "next"}), profile, extractor
        ).digest()
        != original
    )
    assert build_cache_key(block, schema, profile, extractor, "recording-1").digest() != original
    assert (
        build_cache_key(
            block, schema, profile, extractor.model_copy(update={"version": "2"})
        ).digest()
        != original
    )
    assert (
        build_cache_key(
            block.model_copy(update={"start": 50, "end": 58}), schema, profile, extractor
        ).digest()
        == original
    )
    monkeypatch.setattr(cache, "PROMPT_VERSION", "next-prompt")
    assert build_cache_key(block, schema, profile, extractor).digest() != original


def test_replay_uses_content_and_retains_attribution() -> None:
    """Bundled recordings provide an offline typed response and source metadata."""
    replay = ReplayExtractor.from_path(contracts_path() / "recordings" / "qwen3.5.yaml")
    assert replay.recording.recorded_at == "2026-10-24"
    record = replay.recording.records[0]
    assert record.original is not None
    with pytest.raises(KGExtractionError, match="replay_missing"):
        checked_extract(replay, _block("Unrecorded content"), get_schema())
    custom = Recording(
        model="script",
        recorded_at="2026-10-24",
        prompt_version="v1",
        source="fixture",
        records=(
            {"text_hash": _block().content_hash, "output": {"entities": [], "relations": []}},
        ),
    )
    result = checked_extract(ReplayExtractor(custom), _block(), get_schema())
    assert result.output == RawExtraction()
    with pytest.raises(ValidationError, match="duplicate text_hash"):
        Recording.model_validate({**custom.model_dump(), "records": custom.records * 2})


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        ("call_error", "call_error"),
        ("parse_failure", "parse_failure"),
        (ExtractionResult(output=RawExtraction(), finish_reason="length"), "truncated"),
    ],
)
def test_failed_blocks_are_explicit(script: ExtractionResult | str, reason: str) -> None:
    """Truncation and failures cannot be mistaken for successful empty responses."""
    fake = FakeExtractor((script,))
    with pytest.raises(KGExtractionError, match=reason):
        checked_extract(fake, _block(), get_schema())
    assert fake.calls == 1
    assert checked_extract(fake, _block(), get_schema()).output == RawExtraction()


def test_parse_validation_failure_is_classified() -> None:
    """An adapter's schema parse exception becomes a safe block failure category."""

    class InvalidExtractor:
        def extract(self, block: TextBlock, schema: object) -> ExtractionResult:
            return ExtractionResult.model_validate({"output": {"entities": "wrong"}})

    with pytest.raises(KGExtractionError, match="parse_failure"):
        checked_extract(InvalidExtractor(), _block(), get_schema())


@pytest.mark.parametrize(
    ("url", "external"),
    [
        ("http://localhost:11434/v1", False),
        ("http://localhost.:11434/v1", False),
        ("http://127.0.0.1/v1", False),
        ("http://127.255.255.254/v1", False),
        ("http://[::1]/v1", False),
        ("http://[::1%lo0]/v1", True),
        ("http://0.0.0.0/v1", True),
        ("http://example.test/v1", True),
        ("http://localhost.example.test/v1", True),
        ("http://[::]/v1", True),
        ("http://128.0.0.1/v1", True),
    ],
)
def test_external_policy_only_accepts_literal_loopback(url: str, *, external: bool) -> None:
    """No DNS result or wildcard listener can bypass external approval."""
    profile = ExtractionProfile(
        id="test", extractor="llm", provider="openai", model="test", base_url=url
    )
    assert is_external(profile) is external
    assert target_host(profile)


def test_offline_providers_and_default_hosts_are_classified() -> None:
    """Offline modes stay local while known cloud defaults are external."""
    assert not is_external(get_profile("fake"))
    assert not is_external(get_profile("replay-demo"))
    profile = ExtractionProfile(id="test", extractor="llm", provider="openai", model="test")
    assert is_external(profile)
    assert target_host(profile) == "api.openai.com"
    assert is_external(profile.model_copy(update={"provider": "ollama"}))
    with pytest.raises(ValidationError, match="llm provider"):
        ExtractionProfile(id="test", extractor="llm", provider="fake", model="test")
    with pytest.raises(ValidationError, match="provider must match"):
        ExtractionProfile(id="test", extractor="fake", provider="openai", model="test")


def test_prompt_and_schema_include_enum_vocabulary_and_source() -> None:
    """Preparation and provider transmission share one versioned instruction rendering."""
    schema = get_schema()
    prompt = extraction_prompt(_block(), schema)
    assert "Example." in prompt
    assert "untrusted" in prompt
    assert "two top-level keys: entities and relations" in prompt
    assert "additionalProperties" not in prompt
    assert "Example source:" in prompt
    assert "organization/person -> location" in prompt
    assert "works_for" in str(output_schema(schema))
    assert _block().content_hash == hashlib.sha256(b"Example.").hexdigest()


def test_ollama_prompt_with_worst_case_unicode_block_fits_default_context() -> None:
    """The local profile leaves room beyond a UTF-8 byte upper bound for chat wrappers."""
    profile = get_profile("ollama")
    text = "𠀀" * profile.chunk_size
    prompt = extraction_prompt(_block(text), get_schema())
    assert len(prompt.encode("utf-8")) + 256 < 4096
    assert "num_ctx" not in profile.request_parameters


@pytest.mark.parametrize("truncated", [False, True])
def test_checked_extraction_failed_response_preserves_observed_usage(*, truncated: bool) -> None:
    """Failure translation cannot erase usage returned with invalid or incomplete output."""
    observed = TokenUsage(input_tokens=13, output_tokens=5, cache_read_tokens=3)

    class InvalidExtractor:
        def extract(self, block: TextBlock, schema: object) -> ExtractionResult:
            if not truncated:
                reason = "parse_error"
                raise ExtractionProviderError(reason, observed_usage=observed)
            return ExtractionResult(
                output=RawExtraction(), finish_reason="length", **observed.model_dump()
            )

    with pytest.raises(KGExtractionError) as caught:
        checked_extract(InvalidExtractor(), _block(), get_schema())
    assert caught.value.observed_usage == observed


def test_profile_and_schema_resolve_from_bundled_contracts() -> None:
    """All distributed profiles pass the same validation used by custom files."""
    for identity in ("replay-demo", "replay-flash", "fake", "ollama", "cloud"):
        assert get_profile(identity).id == identity
    assert contracts_path().is_dir()
    assert isinstance(contracts_path(), Path)


@pytest.mark.parametrize("reason", ["timeout", "parse_error", "http_500"])
def test_provider_failures_become_retryable_block_failures(reason: str) -> None:
    """SDK-level failures stay visible without aborting remaining document blocks."""

    class FailingExtractor:
        def extract(self, block: TextBlock, schema: object) -> ExtractionResult:
            raise ProviderError(reason)

    with pytest.raises(KGExtractionError, match=reason):
        checked_extract(FailingExtractor(), _block(), get_schema())


def test_extractor_identity_changes_only_for_extraction_semantics() -> None:
    """Credential variable names and recording paths do not version factual content."""
    profile, schema = get_profile("replay-demo"), get_schema()
    original = cache.extraction_identity(schema, profile, "recording-digest")
    assert original.id == "evidence.kg"
    assert original.version.startswith("1:")
    relocated = profile.model_copy(update={"recording": "different.yaml", "api_key_env": "NEW_KEY"})
    assert cache.extraction_identity(schema, relocated, "recording-digest") == original
    assert cache.extraction_identity(schema, profile, "changed-digest") != original
    assert (
        cache.extraction_identity(schema.model_copy(update={"version": "2"}), profile) != original
    )
