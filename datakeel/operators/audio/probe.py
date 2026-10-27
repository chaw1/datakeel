# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect audio containers and streams with the user's ffprobe executable."""

from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import EmptyParams, Operator, OperatorResult, annotate, summarize
from datakeel.operators.media.tools import probe_file


def execute(files: list[FileItem], _output_dir: Path, _params: EmptyParams) -> OperatorResult:
    """Annotate duration, codec, sample rate and channel count from actual content."""
    output: list[FileItem] = []
    for file in files:
        probe = probe_file(file)
        if probe.audio_tracks == 0:
            msg = "audio.probe requires a decodable audio stream"
            raise ValidationError(msg)
        output.append(annotate(file, media_probe=probe.model_dump(mode="json")))
    return summarize(files, output)


OPERATOR = Operator("audio.probe", "audio", "inspection", EmptyParams, execute)
