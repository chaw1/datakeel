# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deduplicate audio by MFCC shape and fluctuation, robust to gain and lossy coding."""

from pathlib import Path
from typing import Any

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem
from datakeel.operators.audio.common import annotate_audio, fingerprint_samples
from datakeel.operators.audio.fingerprint import Signature, fingerprint, is_duplicate, signature
from datakeel.operators.audio.models import AudioMetrics
from datakeel.operators.audio.params import DedupParams
from datakeel.operators.base import Operator, OperatorResult, summarize


def execute(files: list[FileItem], _output_dir: Path, params: DedupParams) -> OperatorResult:
    """Retain the first matching clip and optionally annotate later duplicates."""
    retained: list[tuple[FileItem, Signature]] = []
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    for file in files:
        measured = signature(fingerprint_samples(file))
        match = next(
            (prior.id for prior, previous in retained if is_duplicate(measured, previous, params)),
            None,
        )
        annotated = annotate_audio(
            file,
            AudioMetrics(
                fingerprint=fingerprint(measured).coefficients,
                fingerprint_method="temporal_mfcc_v2",
                duplicate_of=match,
            ),
            (
                MediaInterval(
                    code="audio_duplicate",
                    start_ms=0,
                    end_ms=measured.duration_ms,
                    severity="info",
                ),
            )
            if match is not None
            else (),
        )
        if match is None:
            retained.append((file, measured))
        else:
            issues.append(
                {
                    "file_id": file.id,
                    "code": "audio_duplicate",
                    "severity": "info",
                    "duplicate_of": match,
                }
            )
        if match is None or not params.remove:
            output.append(annotated)
    return summarize(files, output, issues)


OPERATOR = Operator("audio.dedup", "audio", "deduplication", DedupParams, execute)
