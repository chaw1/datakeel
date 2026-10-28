# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise visual JSON, invalid geometry and portable recordings without external calls."""

from __future__ import annotations

import json
from math import ceil
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.transcription_auto import OCRReference
from datakeel.core.transcription_models import TranscriptionRecord, TranscriptionRecording
from datakeel.transcription.adapters import ReplayTranscriber
from datakeel.transcription.alignment import align_regions, match_box
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.coordinates import decode_coordinates
from datakeel.transcription.loader import get_profile
from datakeel.transcription.prompt import COORDINATE_PROMPT, input_token_bound, transcription_prompt
from datakeel.transcription.quality import quality_issues
from datakeel.transcription.transport import request_transcription

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput, TranscriptionResult


@pytest.mark.parametrize(
    "bbox",
    [
        None,
        [],
        [1, 2, 3],
        [1, 2, 3, 4, 5],
        [-1, 0, 10, 10],
        [0, -1, 10, 10],
        [1, 1, 121, 10],
        [1, 1, 10, 81],
        [10, 1, 1, 10],
        [1, 10, 10, 1],
        [1, 1, 1, 10],
        [1, 1, 10, 1],
        [False, 1, 10, 20],
        ["1", 1, 10, 20],
        [1, 1, "unknown", 20],
        {"x1": 1, "y1": 1, "x2": 10, "y2": 20},
    ],
)
def test_visual_json_when_geometry_invalid_keeps_text_and_other_valid_lines(bbox: object) -> None:
    """Bad rectangles never remove text or contaminate a separately validated rectangle."""
    content = json.dumps(
        {"lines": [{"text": "unlocated", "bbox": bbox}, {"text": "valid", "bbox": [1, 2, 90, 20]}]}
    )
    parsed = decode_coordinates(content, 120, 80)
    assert parsed.text == "unlocated\nvalid"
    assert [(line.text, line.bbox) for line in parsed.lines] == [("valid", (1, 2, 90, 20))]


@pytest.mark.parametrize("bbox", [[0, 0, 120, 80], [0.5, 1.5, 119.5, 79.5]])
def test_visual_json_when_geometry_valid_retains_original_pixels(bbox: list[float]) -> None:
    """Pixel coordinates are validated without normalizing, scaling or rounding them."""
    parsed = decode_coordinates(json.dumps({"lines": [{"text": "Alpha", "bbox": bbox}]}), 120, 80)
    assert parsed.text == "Alpha"
    assert parsed.lines[0].bbox == tuple(bbox)


@pytest.mark.parametrize(
    "text", ["Alpha owns Beta.", '{"text":"Alpha"}', '{"lines":[{"text":42}]}', "not JSON"]
)
def test_visual_json_when_schema_missing_reports_unparseable_output(text: str) -> None:
    """Unexpected model formats cannot manufacture geometry from OCR or the image extent."""
    parsed = decode_coordinates(text, 120, 80)
    assert parsed.text == ""
    assert parsed.lines == ()
    assert parsed.quality_issues == ("unparseable_structured_output",)


def test_visual_json_when_rectangles_missing_keeps_all_lines_unlocated() -> None:
    """A model may explicitly decline every location while retaining usable transcription."""
    parsed = decode_coordinates('{"lines":[{"text":"Alpha"},{"text":"Beta","bbox":null}]}', 120, 80)
    assert parsed.text == "Alpha\nBeta"
    assert parsed.lines == ()


def test_visual_json_when_relation_spans_lines_uses_existing_enclosing_rectangle() -> None:
    """The same P10 fragment alignment joins model-provided boxes into the relation region."""
    parsed = decode_coordinates(
        '{"lines":[{"text":"Alpha","bbox":[1,2,40,20]},{"text":"Beta","bbox":[70,40,100,60]}]}',
        120,
        80,
    )
    assert len(align_regions("Alpha --> Beta", parsed.lines, 120, 80)) == 2
    assert match_box("Alpha --> Beta", parsed.lines, 120, 80) == (1, 2, 100, 60)


@pytest.mark.parametrize("interface", ["openai", "ollama"])
def test_visual_transport_when_coordinate_version_requests_json_and_replaces_ocr_geometry(
    image_input: ImageInput, transcription_result: TranscriptionResult, interface: str
) -> None:
    """Both injected transports consume the same versioned JSON without retaining old OCR boxes."""
    profile = get_profile("bailian-qwen35-flash-coordinates").model_copy(
        update={"interface": interface, "coordinate_space": "pixel"}
    )
    content = '{"lines":[{"text":"Alpha --> Beta","bbox":[5,10,110,70]}]}'

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if interface == "ollama":
            assert body["format"] == "json"
            assert body["messages"][0]["content"] == transcription_prompt(
                profile.prompt_version, 120, 80
            )
            return httpx.Response(
                200, json={"message": {"content": content}, "done_reason": "stop"}
            )
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["content"][0]["text"] == transcription_prompt(
            profile.prompt_version, 120, 80
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = request_transcription(profile, image_input, transcription_result, client, "")
    assert result.text == "Alpha --> Beta"
    assert result.lines[0].bbox == (5, 10, 110, 70)
    assert result.lines != transcription_result.lines
    assert result.backend == "vlm"


@pytest.mark.parametrize("content", ["readable plain text", '{"lines":[{"text":"Alpha"}]}'])
def test_visual_transport_when_coordinates_absent_does_not_reuse_ocr_boxes(
    image_input: ImageInput, transcription_result: TranscriptionResult, content: str
) -> None:
    """Missing visual locations stay unlocated even if the preliminary OCR found unrelated boxes."""
    response = {"choices": [{"message": {"content": content}}]}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        result = request_transcription(
            get_profile("bailian-qwen35-flash-coordinates"),
            image_input,
            transcription_result,
            client,
            "",
        )
    assert result.text == ("Alpha" if content.startswith("{") else "")
    assert result.quality_issues == (
        () if content.startswith("{") else ("unparseable_structured_output",)
    )
    assert result.lines == ()


def test_replay_when_coordinate_record_contains_bad_box_keeps_text_and_valid_geometry(
    image_input: ImageInput,
) -> None:
    """Raw v2 JSON recordings share transport validation while old typed recordings remain valid."""
    record = TranscriptionRecord(
        image_hash=image_input.image_hash,
        text='{"lines":[{"text":"Alpha","bbox":[5,10,20,30]},{"text":"Beta","bbox":[-1,0,10,10]}]}',
        width=image_input.width,
        height=image_input.height,
        backend="vlm",
        mode="vlm",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=(record,),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.text == "Alpha\nBeta"
    assert [(line.text, line.bbox) for line in result.lines] == [("Alpha", (5, 10, 20, 30))]


def test_replay_when_legacy_record_lacks_geometry_preserves_original_content(
    image_input: ImageInput,
) -> None:
    """P10 recordings need no coordinate field or format conversion to replay identically."""
    record = TranscriptionRecord(
        image_hash=image_input.image_hash,
        text="Alpha --> Beta",
        width=image_input.width,
        height=image_input.height,
        backend="vlm",
        mode="vlm",
        model="fixture",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-24",
        prompt_version="image-transcription-v1",
        source="generated fixture",
        records=(record,),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.model_dump() == record.model_dump(exclude={"image_hash", "raw_output"})


def test_replay_when_v2_record_already_materialized_preserves_valid_typed_coordinates(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """Persisted decoded v2 results need no raw provider JSON to retain their pixel rectangles."""
    record = TranscriptionRecord(
        **transcription_result.model_dump(exclude={"backend", "mode", "model"}),
        image_hash=image_input.image_hash,
        backend="vlm",
        mode="vlm",
        model="fixture",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=(record,),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.model_dump() == record.model_dump(exclude={"image_hash", "raw_output"})
    local = ReplayTranscriber(archive, mode="ocr").transcribe(image_input)
    assert local.text == ""
    assert local.lines == ()
    automatic = AutoTranscriber(ReplayTranscriber(archive), get_profile("fake").auto_routing)
    routed = automatic.transcribe(image_input)
    assert routed.mode == "vlm"
    assert routed.auto_decision is not None
    assert routed.auto_decision.reasons == ("ocr_failed",)
    assert routed.lines == record.lines


def test_visual_transport_when_ocr_failed_does_not_carry_failure_into_visual_success(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """Automatic fallback keeps failed OCR as reference and accepts independent visual output."""
    ocr = transcription_result.model_copy(
        update={"text": "", "lines": (), "error": "ocr_not_installed", "quality_issues": ("empty",)}
    )
    response = {"choices": [{"message": {"content": '{"lines":[{"text":"Alpha owns Beta."}]}'}}]}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        result = request_transcription(
            get_profile("bailian-qwen35-flash-coordinates"), image_input, ocr, client, ""
        )
    assert result.error is None
    assert quality_issues(result) == ()
    assert result.ocr_reference == OCRReference(text="", error="ocr_not_installed")


@pytest.mark.parametrize(
    "reference",
    [
        OCRReference(text=""),
        OCRReference(text="short"),
        OCRReference(text="x" * 20, error="ocr_failed"),
    ],
)
def test_visual_quality_when_ocr_reference_sparse_or_failed_does_not_apply_length_ratio(
    transcription_result: TranscriptionResult, reference: OCRReference
) -> None:
    """An absent reliable OCR baseline cannot reject independently readable visual text."""
    result = transcription_result.model_copy(
        update={
            "text": "A complete independently readable visual transcription." * 2,
            "mode": "vlm",
            "ocr_reference": reference,
        }
    )
    assert quality_issues(result) == ()


def test_visual_quality_when_ocr_reference_available_keeps_original_length_guard(
    transcription_result: TranscriptionResult,
) -> None:
    """VLM line coordinates cannot replace the original OCR text in the P10 quality comparison."""
    result = transcription_result.model_copy(
        update={
            "text": "A much longer independently readable visual transcription." * 2,
            "mode": "vlm",
            "ocr_reference": OCRReference(text="x" * 20),
        }
    )
    assert quality_issues(result) == ("repeated",)


def test_coordinate_prompt_when_estimating_tokens_includes_full_structured_instruction() -> None:
    """The additive version has a distinct cache key and a complete consent token envelope."""
    assert input_token_bound(120, 80, "image-transcription-v2") == ceil(
        120 * 80 / 1024 + 2
    ) + estimate_tokens(transcription_prompt("image-transcription-v2", 120, 80))
    assert "JSON" in COORDINATE_PROMPT
    assert input_token_bound(120, 80, "image-transcription-v2") > input_token_bound(120, 80)


def test_replay_when_materialized_text_is_json_keeps_its_verified_coordinates(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """A JSON document in an image is content, not a second visual protocol envelope."""
    text = '{"key":"value"}'
    line = transcription_result.lines[0].model_copy(update={"text": text})
    record = TranscriptionRecord(
        **transcription_result.model_dump(exclude={"backend", "mode", "model", "text", "lines"}),
        image_hash=image_input.image_hash,
        text=text,
        lines=(line,),
        backend="vlm",
        mode="vlm",
        model="fixture",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=(record,),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.text == text
    assert result.lines == (line,)


@pytest.mark.parametrize(
    "text",
    ["Alpha [active] --> Beta", "Alpha {active} --> Beta", "```example```", "Alpha --> Beta"],
)
def test_replay_when_legacy_v2_text_is_materialized_keeps_punctuation(
    image_input: ImageInput, text: str
) -> None:
    """Only explicit raw responses use new wire decoding; old unlocated prose stays text."""
    record = TranscriptionRecord(
        image_hash=image_input.image_hash,
        text=text,
        width=image_input.width,
        height=image_input.height,
        backend="vlm",
        mode="vlm",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=(record,),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.text == text
    assert result.quality_issues == ()
    assert result.lines == ()
