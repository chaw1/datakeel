# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject empty, truncated, repetitive or failed transcriptions without silent omission."""

import re
from itertools import pairwise
from typing import Protocol

from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import (
    ImageInput,
    TranscriptionIssue,
    TranscriptionMode,
    TranscriptionResult,
)
from datakeel.transcription.alignment import normalize

_REPEAT_SUBSTRING = re.compile(r"(.{8,}?)\1{3,}", re.DOTALL)
_REPEAT_LINES = 3
_MIN_OCR_LENGTH = 20
_MAX_LENGTH_RATIO = 2.5


class TranscriberAdapter(Protocol):
    """Expose one typed attempt so callers can reserve and settle each model invocation."""

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Return raw text, OCR geometry and usage, preserving failed output."""
        ...


def _repeated(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    run = 1
    for first, second in pairwise(lines):
        run = run + 1 if first == second else 1
        if run >= _REPEAT_LINES and not re.fullmatch(r"[|\-: ]+", first):
            return True
    return bool(_REPEAT_SUBSTRING.search(normalize(text)))


def quality_issues(result: TranscriptionResult) -> tuple[TranscriptionIssue, ...]:
    """Apply the same rules to scripted, replay and live output, including sparse OCR."""
    issues = list(result.quality_issues)
    text = normalize(result.text)
    ocr = normalize("\n".join(line.text for line in result.lines))
    if result.error:
        issues.append("timeout" if result.error == "timeout" else "provider_error")
    if not text:
        issues.append("empty")
    if result.finish_reason == "length":
        issues.append("truncated")
    if _repeated(result.text) or (
        len(ocr) >= _MIN_OCR_LENGTH and len(text) > _MAX_LENGTH_RATIO * len(ocr)
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
        raise TranscriptionFailure(issues[0], result.model_copy(update={"quality_issues": issues}))
    return result
