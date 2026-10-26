# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject visual geometry contradicted by text-matched original OCR rectangles."""

from difflib import SequenceMatcher
from statistics import median

from datakeel.core.transcription_coordinates import LocatedTranscript
from datakeel.core.transcription_models import TranscriptionResult
from datakeel.transcription.alignment import normalize

decode_coordinates = LocatedTranscript.decode

_MIN_SIMILARITY = 0.8


def _iou(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    intersection = max(0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0, min(first[3], second[3]) - max(first[1], second[1])
    )
    return intersection / (
        (first[2] - first[0]) * (first[3] - first[1])
        + (second[2] - second[0]) * (second[3] - second[1])
        - intersection
    )


def check_coordinates(
    result: TranscriptionResult, reference: TranscriptionResult, threshold: float
) -> TranscriptionResult:
    """Drop all visual boxes when one-to-one OCR matches have insufficient median IoU.

    Equal text scores prefer overlap for repeated labels. Without comparable text,
    retain range-validated boxes; OCR never replaces missing visual locations.
    """
    pairs: list[tuple[float, float, int, int]] = []
    for visual_index, visual in enumerate(result.lines):
        text = normalize(visual.text)
        for ocr_index, ocr in enumerate(reference.lines):
            other = normalize(ocr.text)
            if not text or not other:
                continue
            similarity = SequenceMatcher(None, text, other, autojunk=False).ratio()
            if similarity >= _MIN_SIMILARITY:
                pairs.append((similarity, _iou(visual.bbox, ocr.bbox), visual_index, ocr_index))
    visual_used: set[int] = set()
    ocr_used: set[int] = set()
    overlaps: list[float] = []
    for _, overlap, visual_index, ocr_index in sorted(pairs, reverse=True):
        if visual_index not in visual_used and ocr_index not in ocr_used:
            visual_used.add(visual_index)
            ocr_used.add(ocr_index)
            overlaps.append(overlap)
    if overlaps and median(overlaps) < threshold:
        issues = tuple(dict.fromkeys((*result.quality_issues, "coordinates_unreliable")))
        return result.model_copy(update={"lines": (), "quality_issues": issues})
    return result
