# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise both wire protocols and lazy OCR with injected in-process fixtures only."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from datakeel.core.errors import ValidationError
from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.factory import create_transcriber, prepare_transcriber
from datakeel.transcription.loader import get_profile
from datakeel.transcription.ocr import RapidOCRTranscriber
from datakeel.transcription.quality import checked_transcribe
from datakeel.transcription.transport import request_transcription

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput, TranscriptionResult


@pytest.mark.parametrize("interface", ["openai", "ollama"])
def test_transport_when_success_sends_clean_pixels_and_retains_usage(
    image_input: ImageInput, transcription_result: TranscriptionResult, interface: str
) -> None:
    """Each interface uses its actual context and finish fields with exactly one request."""
    profile = get_profile(
        "ollama-vision-local" if interface == "ollama" else "bailian-qwen35-flash"
    )
    observed: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer synthetic-fixture"
        assert body["model"] == profile.model
        if interface == "ollama":
            assert str(request.url).endswith("/api/chat")
            assert body["options"]["num_ctx"] == 16384
            assert body["options"]["num_predict"] == 4096
            assert body["think"] is False
            assert base64.b64decode(body["messages"][0]["images"][0]) == image_input.png
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Alpha owns Beta."},
                    "done_reason": "length",
                    "prompt_eval_count": 9,
                    "eval_count": 7,
                },
            )
        assert str(request.url).endswith("/chat/completions")
        encoded = body["messages"][0]["content"][1]["image_url"]["url"]
        assert encoded.startswith("data:image/png;base64,")
        assert base64.b64decode(encoded.split(",")[1]) == image_input.png
        assert body["enable_thinking"] is False
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Alpha owns Beta."}, "finish_reason": "length"}
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 7},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client:
        result = request_transcription(
            profile, image_input, transcription_result, client, "synthetic-fixture"
        )
    assert len(observed) == 1
    assert result.finish_reason == "length"
    assert (result.input_tokens, result.output_tokens) == (9, 7)
    assert result.lines == transcription_result.lines
    assert result.backend == "vlm"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("timeout", "timeout"),
        ("connection", "provider_error"),
        ("quota", "账户只允许免费额度\uff0c且已用完"),
        ("status", "http_429"),
        ("invalid", "invalid_response"),
        ("missing", "invalid_response"),
        ("redirect", "invalid_response"),
    ],
)
def test_transport_when_failure_preserves_category_without_retry(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    failure: str,
    expected: str,
) -> None:
    """Quota errors have a useful message, and no failure transparently retries or redirects."""
    attempts: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        message = "fixture"
        if failure == "timeout":
            raise httpx.ReadTimeout(message, request=request)
        if failure == "connection":
            raise httpx.ConnectError(message, request=request)
        if failure == "quota":
            return httpx.Response(403, json={"error": {"code": "AllocationQuota.FreeTierOnly"}})
        if failure == "status":
            return httpx.Response(429)
        if failure == "invalid":
            return httpx.Response(200, content=b"not-json")
        if failure == "redirect":
            return httpx.Response(302, headers={"location": "https://fixture.invalid/redirect"})
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client:
        result = request_transcription(
            get_profile("bailian-qwen35-flash"),
            image_input,
            transcription_result.model_copy(update={"input_tokens": 0, "output_tokens": 0}),
            client,
            "",
        )
    assert result.error == expected
    assert result.input_tokens is None
    assert result.output_tokens is None
    assert len(attempts) == 1


@pytest.mark.parametrize("interface", ["openai", "ollama"])
def test_factory_when_vlm_runs_ocr_first_and_override_avoids_credentials(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    monkeypatch: pytest.MonkeyPatch,
    interface: str,
) -> None:
    """OCR-only file overrides never inspect settings or invoke the VLM transport."""
    profile = get_profile(
        "ollama-vision-local" if interface == "ollama" else "bailian-qwen35-flash"
    )
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append("request")
        payload = (
            {"message": {"content": "normal"}}
            if interface == "ollama"
            else {"choices": [{"message": {"content": "normal"}}]}
        )
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", lambda: pytest.fail("secret read")
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with create_transcriber(
            profile, client=client, ocr=FakeTranscriber((transcription_result,))
        ) as adapter:
            assert adapter.transcribe(image_input, "ocr") == transcription_result
        assert calls == []
        monkeypatch.setattr(
            "datakeel.transcription.factory.get_settings",
            lambda: SimpleNamespace(extraction_key=lambda _: SecretStr("synthetic-fixture")),
        )
        with create_transcriber(
            profile, client=client, ocr=FakeTranscriber((transcription_result,))
        ) as adapter:
            assert adapter.transcribe(image_input).text == "normal"
        assert not client.is_closed
    assert calls == ["request"]


def test_factory_when_external_key_missing_fails_before_http(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never obtain ambient vendor credentials or use network after missing-key validation."""
    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings",
        lambda: SimpleNamespace(extraction_key=lambda _: None),
    )
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("network"))) as client,
        create_transcriber(
            get_profile("bailian-qwen35-flash"),
            client=client,
            ocr=FakeTranscriber((transcription_result,)),
        ) as adapter,
        pytest.raises(ValidationError, match="No transcription API key"),
    ):
        adapter.transcribe(image_input)


def test_factory_when_sparse_ocr_and_local_native_endpoint_succeeds(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native API base paths and keyless loopback routes retain sparse-OCR VLM success."""
    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings",
        lambda: SimpleNamespace(extraction_key=lambda _: None),
    )
    profile = get_profile("ollama-vision-local").model_copy(
        update={"base_url": "http://127.0.0.1:11434/api", "request_parameters": {}}
    )
    empty = transcription_result.model_copy(update={"text": "", "lines": ()})

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/chat")
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={"message": {"content": "A complete readable paragraph."}, "done_reason": "stop"},
        )

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        create_transcriber(profile, client=client, ocr=FakeTranscriber((empty,))) as adapter,
    ):
        assert checked_transcribe(adapter, image_input).text == "A complete readable paragraph."


def test_ocr_when_optional_engine_missing_reports_installation(
    image_input: ImageInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not require OCR packages for normal imports or hide missing installation failures."""

    def absent(_: str) -> object:
        raise ImportError

    monkeypatch.setattr("datakeel.transcription.ocr.import_module", absent)
    with create_transcriber(get_profile("rapidocr-local")) as adapter:
        with pytest.raises(ValidationError, match="datakeel\\[ocr\\]"):
            adapter.transcribe(image_input)
        with pytest.raises(ValidationError, match="only ocr"):
            adapter.transcribe(image_input, "vlm")


def test_ocr_when_engine_returns_rotated_lines_preserves_order(
    image_input: ImageInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The optional engine boundary converts quadrilaterals and does not rerun initialization."""
    calls: list[str] = []
    output = SimpleNamespace(
        boxes=np.array([[[1, 4], [30, 2], [32, 12], [2, 14]]]), txts=("Fixture",), scores=(0.9,)
    )

    def engine(_: object) -> object:
        calls.append("ocr")
        return output

    def module(name: str) -> object:
        if name == "onnxruntime":
            return SimpleNamespace(disable_telemetry_events=lambda: None)
        calls.append("initialize")
        return SimpleNamespace(RapidOCR=lambda: engine)

    monkeypatch.setattr("datakeel.transcription.ocr.import_module", module)
    adapter = RapidOCRTranscriber()
    result = adapter.transcribe(image_input)
    assert result.text == "Fixture"
    assert result.lines[0].bbox == (1, 2, 32, 14)
    adapter.transcribe(image_input)
    assert calls == ["initialize", "ocr", "ocr"]
    output.boxes = None
    with pytest.raises(TranscriptionFailure, match="empty"):
        checked_transcribe(adapter, image_input)


def test_vlm_preparation_when_metering_uses_it_reuses_ocr_without_a_request(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local preflight and visual billing have separate boundaries for exactly one image."""
    counts: list[str] = []

    class CountingOCR(FakeTranscriber):
        def transcribe(self, image: object, mode: object = None) -> TranscriptionResult:
            counts.append("ocr")
            return transcription_result

    def respond(_: httpx.Request) -> httpx.Response:
        counts.append("http")
        return httpx.Response(200, json={"message": {"content": "complete transcript"}})

    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings",
        lambda: SimpleNamespace(extraction_key=lambda _: None),
    )
    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        create_transcriber(
            get_profile("ollama-vision-local"), client=client, ocr=CountingOCR()
        ) as adapter,
    ):
        prepare_transcriber(adapter, image_input)
        prepare_transcriber(adapter, image_input)
        assert counts == ["ocr"]
        adapter.transcribe(image_input)
        assert counts == ["ocr", "http"]
        prepare_transcriber(adapter, image_input, "ocr")
        assert counts == ["ocr", "http", "ocr"]
        prepare_transcriber(FakeTranscriber(), image_input)
        assert counts == ["ocr", "http", "ocr"]
