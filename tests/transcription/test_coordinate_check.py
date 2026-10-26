# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cross-check visual geometry against generated local OCR without model calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from datakeel.core.transcription_auto import AutoRoutingConfig, OCRReference
from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import OCRLine, TranscriptionResult
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.coordinates import check_coordinates
from datakeel.transcription.quality import checked_transcribe

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput, TranscriptionMode

type _Box = tuple[float, float, float, float]
_FIRST: _Box = (1, 2, 21, 12)
_SECOND: _Box = (30, 20, 50, 30)
_THIRD: _Box = (60, 40, 80, 50)


def _result(*entries: tuple[str, _Box], backend: str = "vlm") -> TranscriptionResult:
    return TranscriptionResult(
        text="\n".join(text for text, _ in entries),
        lines=tuple(OCRLine(text=text, bbox=box, confidence=0.5) for text, box in entries),
        width=120,
        height=80,
        backend="ocr" if backend == "ocr" else "vlm",
        mode="ocr" if backend == "ocr" else "vlm",
    )


@pytest.mark.parametrize(("threshold", "rejected"), [(0.3, False), (0.34, True), (0, False)])
def test_coordinate_check_when_overlap_near_threshold_obeys_frozen_limit(
    threshold: float, *, rejected: bool
) -> None:
    """A configurable threshold compares median IoU without changing readable text."""
    result = _result(("Alpha", (0, 0, 10, 10)))
    reference = _result(("Alpha", (5, 0, 15, 10)), backend="ocr")
    checked = check_coordinates(result, reference, threshold)
    assert checked.text == result.text
    assert bool(checked.lines) is not rejected
    assert checked.quality_issues == (("coordinates_unreliable",) if rejected else ())


def test_coordinate_check_when_median_low_discards_every_visual_box() -> None:
    """A single passing location cannot leave other untrusted locations available for drawing."""
    result = _result(("Alpha", _FIRST), ("Beta", _FIRST), ("Gamma", _FIRST), ("new", _THIRD))
    reference = _result(("Alpha", _FIRST), ("Beta", _SECOND), ("Gamma", _THIRD), backend="ocr")
    result = result.model_copy(update={"quality_issues": ("coordinates_unreliable",)})
    checked = check_coordinates(result, reference, 0.3)
    assert checked.lines == ()
    assert checked.text == result.text
    assert checked.quality_issues == ("coordinates_unreliable",)


def test_coordinate_check_when_text_fuzzy_matches_uses_normalized_similar_lines() -> None:
    """Case, typography and one OCR character error still locate comparable text."""
    result = _result(("**\uff21lpha**", _FIRST), ("transcription", _SECOND))
    reference = _result(("alpha", _FIRST), ("transcriptlon", _SECOND), backend="ocr")
    assert check_coordinates(result, reference, 1) is result


def test_coordinate_check_when_duplicate_text_never_reuses_one_ocr_rectangle() -> None:
    """Repeated labels have one-to-one matches rather than borrowing the same good OCR box."""
    result = _result(("same", _FIRST), ("same", _FIRST), ("same", _FIRST))
    reference = _result(("same", _FIRST), ("same", _SECOND), ("same", _THIRD), backend="ocr")
    assert check_coordinates(result, reference, 0.3).lines == ()


def test_coordinate_check_when_duplicate_text_reordered_matches_actual_overlapping_boxes() -> None:
    """Equal textual scores use geometry to disambiguate independently ordered repeated labels."""
    result = _result(("same", _SECOND), ("same", _FIRST))
    reference = _result(("same", _FIRST), ("same", _SECOND), backend="ocr")
    assert check_coordinates(result, reference, 1) is result


def test_coordinate_check_when_text_exact_match_available_does_not_prefer_fuzzier_overlap() -> None:
    """Text similarity determines pair identity before the overlap used to check reliability."""
    result = _result(("Alpha", _FIRST))
    reference = _result(("Alphaa", _FIRST), ("Alpha", _SECOND), backend="ocr")
    assert check_coordinates(result, reference, 0.3).lines == ()


@pytest.mark.parametrize("reference_text", ["unrelated", "", "   "])
def test_coordinate_check_when_no_comparable_text_keeps_range_validated_geometry(
    reference_text: str,
) -> None:
    """No textual evidence permits a geometry judgment or fabrication of replacement boxes."""
    result = _result(("Alpha", _FIRST))
    reference = _result((reference_text, _SECOND), backend="ocr")
    assert check_coordinates(result, reference, 0.3) is result


def test_coordinate_check_when_no_ocr_geometry_preserves_visual_boxes() -> None:
    """OCR text alone cannot substitute invented rectangles for absent line geometry."""
    result = _result(("Alpha", _FIRST))
    reference = _result(backend="ocr").model_copy(update={"text": "Alpha"})
    assert check_coordinates(result, reference, 0.3) is result


def test_coordinate_check_when_visual_line_merges_labels_does_not_invent_ocr_rectangle() -> None:
    """A valid merged relation line has no comparable individual OCR label or synthetic frame."""
    result = _result(("Alpha owns Beta.", (1, 2, 80, 50)))
    reference = _result(("Alpha", _FIRST), ("owns", _SECOND), ("Beta", _THIRD), backend="ocr")
    assert check_coordinates(result, reference, 0.3) is result


def test_coordinate_check_when_visual_boxes_missing_does_not_borrow_ocr_locations() -> None:
    """Unlocated visual text remains unlocated even when OCR has a matching original line."""
    result = _result().model_copy(update={"text": "Alpha"})
    reference = _result(("Alpha", _FIRST), backend="ocr")
    assert check_coordinates(result, reference, 0.3) is result


@dataclass
class _OfflineAdapter:
    ocr: TranscriptionResult
    visual: TranscriptionResult
    fail: bool = False

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        if mode == "ocr":
            return self.ocr
        if self.fail:
            raise TranscriptionFailure(self.visual.quality_issues[0], self.visual)
        return self.visual


@pytest.mark.parametrize(("threshold", "rejected"), [(0.3, True), (0, False)])
def test_auto_when_offline_visual_geometry_disagrees_applies_configured_crosscheck(
    image_input: ImageInput, threshold: float, *, rejected: bool
) -> None:
    """Fake and replay paths share the OCR check rather than relying on HTTP transport checks."""
    reference = _result(("Alpha", _FIRST), backend="ocr")
    visual = _result(("Alpha", _SECOND))
    adapter = AutoTranscriber(
        _OfflineAdapter(reference, visual),
        AutoRoutingConfig(),
        coordinate_min_median_iou=threshold,
    )
    result = adapter.transcribe(image_input)
    assert bool(result.lines) is not rejected
    assert result.mode == "vlm"
    assert result.ocr_reference == OCRReference(text="Alpha")


def test_auto_when_visual_parse_fails_retains_reference_and_route_in_failed_result(
    image_input: ImageInput,
) -> None:
    """An image-local structured-output failure still exposes the independent OCR attempt."""
    reference = _result(("Alpha", _FIRST), backend="ocr")
    visual = _result().model_copy(update={"quality_issues": ("unparseable_structured_output",)})
    adapter = AutoTranscriber(_OfflineAdapter(reference, visual, fail=True), AutoRoutingConfig())
    with pytest.raises(TranscriptionFailure) as error:
        adapter.transcribe(image_input)
    result = error.value.result
    assert result.text == ""
    assert result.ocr_reference == OCRReference(text="Alpha")
    assert result.auto_decision is not None
    assert result.auto_decision.route == "vlm"


def test_coordinate_warning_when_output_is_also_truncated_keeps_both_diagnostics(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """Fatal quality checks retain coordinate warnings without changing the fatal reason."""
    result = transcription_result.model_copy(
        update={
            "lines": (),
            "quality_issues": ("coordinates_unreliable",),
            "finish_reason": "length",
        }
    )
    with pytest.raises(TranscriptionFailure) as caught:
        checked_transcribe(FakeTranscriber((result,)), image_input)
    assert caught.value.reason == "truncated"
    assert caught.value.result.quality_issues == ("coordinates_unreliable", "truncated")
