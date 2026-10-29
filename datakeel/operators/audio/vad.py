# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Estimate sound activity intervals from energy; no speech model is used."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.audio.common import (
    activity,
    activity_metrics,
    activity_samples,
    annotate_audio,
)
from datakeel.operators.audio.params import ActivityParams
from datakeel.operators.base import Operator, OperatorResult, summarize


def execute(files: list[FileItem], _output_dir: Path, params: ActivityParams) -> OperatorResult:
    """Report RMS activity and silence, including music or noise above the threshold."""
    output: list[FileItem] = []
    for file in files:
        measured = activity(activity_samples(file), params)
        output.append(annotate_audio(file, activity_metrics(measured), measured.silent))
    return summarize(files, output)


OPERATOR = Operator("audio.vad", "audio", "quality", ActivityParams, execute)
