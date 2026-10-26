# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject empty, truncated, repetitive or failed transcriptions without silent omission."""

import re
from itertools import pairwise

from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import (
    ImageInput,
    TranscriberAdapter,
    TranscriptionIssue,
    TranscriptionMode,
    TranscriptionResult,
)
from datakeel.transcription.alignment import normalize

__all__ = ["TranscriberAdapter", "checked_transcribe", "quality_issues"]

_FILLERS = re.compile(r"[_\.\-\u2014\u2013]{4,}|…{2,}")
_TABLE_SEPARATOR = re.compile(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?")
_REPEAT_SUBSTRING = re.compile(r"(.{8,}?)\1{3,}", re.DOTALL)
_REPEAT_LINES = 3
# Table rows and short labels repeat legitimately in forms; only long runs signal a model loop.
_REPEAT_LOOSE_LINES = 8
_SHORT_LINE = 8
_MIN_OCR_LENGTH = 20
_MAX_LENGTH_RATIO = 2.5


def _repeated(text: str) -> bool:
    lines = [
        (cleaned, _loose(line, cleaned))
        for line in text.splitlines()
        if not _TABLE_SEPARATOR.fullmatch(line.strip())
        and (cleaned := _FILLERS.sub("", line).strip())
    ]
    run = 1
    for (first, loose), (second, _) in pairwise(lines):
        run = run + 1 if first == second else 1
        if run >= (_REPEAT_LOOSE_LINES if loose else _REPEAT_LINES):
            return True
    prose = "\n".join(line for line, loose in lines if not loose)
    return bool(_REPEAT_SUBSTRING.search(normalize(prose)))


def _loose(line: str, cleaned: str) -> bool:
    return (
        cleaned.startswith("|")
        or bool(_FILLERS.search(line))
        or len(normalize(cleaned)) < _SHORT_LINE
    )


def quality_issues(result: TranscriptionResult) -> tuple[TranscriptionIssue, ...]:
    """Apply the same rules to scripted, replay and live output, including sparse OCR."""
    issues: list[TranscriptionIssue] = [
        issue for issue in result.quality_issues if issue != "coordinates_unreliable"
    ]
    text = normalize(result.text)
    reference = result.ocr_reference
    ocr = normalize(reference.text if reference else "\n".join(line.text for line in result.lines))
    if reference and reference.error:
        ocr = ""
    if result.error and not issues:
        issues.append("timeout" if result.error == "timeout" else "provider_error")
    if not text:
        issues.append("empty")
    if result.finish_reason == "length":
        issues.append("truncated")
    if result.mode == "vlm" and (
        _repeated(result.text)
        or (len(ocr) >= _MIN_OCR_LENGTH and len(text) > _MAX_LENGTH_RATIO * len(ocr))
    ):
        issues.append("repeated")
    return tuple(dict.fromkeys(issues))


def checked_transcribe(
    adapter: TranscriberAdapter, image: ImageInput, mode: TranscriptionMode | None = None
) -> TranscriptionResult:
    """Turn quality failures into explicit failed image blocks after usage is available."""
    result = adapter.transcribe(image, mode)
    issues = quality_issues(result)
    if issues:
        flags = tuple(dict.fromkeys((*result.quality_issues, *issues)))
        raise TranscriptionFailure(issues[0], result.model_copy(update={"quality_issues": flags}))
    return result
